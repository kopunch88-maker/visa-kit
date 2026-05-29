"""
Pack 50.38-D3 — применение распарсенного текста менеджера к заявке.

Берёт результат parse_manager_text() + resolve_* (справочники) и раскладывает
по заявке:
  - applicant-поля (имя, ДР, паспорт, родители, контакты) — ТОЛЬКО пустые
    (скан = истина: если OCR уже заполнил поле, текст не трогает)
  - company/position/representative/spain_address → resolve → привязка id
    (не нашлось → заметка)
  - submission_city (дефолт Barcelona) + провинция авто
  - diploma «жду» + unrecognized + ненайденные справочники → internal_notes

application_type (НАЙМ/самозанятый) решается ВНЕ этого сервиса — при создании
заявки (см. determine_application_type).

Применяется ПОСЛЕ OCR (в _auto_apply_ocr_to_applicant), поэтому скан имеет
приоритет автоматически — текст заполняет лишь то, что осталось пустым.
"""
import logging
from typing import Optional

from sqlmodel import Session

from app.models import Applicant, Application, ApplicationType
from .reference_resolver import (
    resolve_company, resolve_position,
    resolve_representative, resolve_spain_address,
)

log = logging.getLogger(__name__)


# Маппинг парсер.applicant → поля модели Applicant
# (ключ парсера → имя поля модели; большинство совпадает)
_APPLICANT_FIELD_MAP = {
    "first_name_latin": "first_name_latin",
    "last_name_latin": "last_name_latin",
    "first_name_native": "first_name_native",
    "last_name_native": "last_name_native",
    "middle_name_native": "middle_name_native",
    "birth_date": "birth_date",
    "sex": "sex",
    "nationality": "nationality",
    "birth_country": "birth_country",
    "birth_place_latin": "birth_place_latin",
    "father_name": "father_name_latin",   # парсер даёт father_name → модель father_name_latin
    "mother_name": "mother_name_latin",
    "email": "email",
    "phone": "phone",                      # испанский телефон
    "passport_number": "passport_number",  # простое поле; только если пусто
}

_CITY_PROVINCE = {"barcelona": "Barcelona", "madrid": "Madrid"}


def _is_empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def determine_application_type(parsed: dict) -> Optional[ApplicationType]:
    """Определяет тип заявки из текста менеджера.

    «НАЙМ» (в любом регистре, с эмодзи и т.п.) → EMPLOYMENT.
    Иначе None (вызывающий код применит дефолт — SELF_EMPLOYED из модели).
    """
    # тип может прийти в unrecognized или отдельным маркером — ищем по всему сырому
    raw = parsed.get("_raw_text") or ""
    hay = (raw + " " + " ".join(str(x) for x in parsed.get("unrecognized", []))).upper()
    if "НАЙМ" in hay or "NAIM" in hay or "EMPLOYMENT" in hay:
        return ApplicationType.EMPLOYMENT
    return None


def apply_parsed_to_application(
    session: Session,
    application: Application,
    parsed: dict,
) -> dict:
    """Раскладывает распарсенный текст по заявке (applicant + справочники +
    submission + заметки). Возвращает dict с отчётом (что применено, что в заметки).

    ВАЖНО: applicant-поля заполняются только если пустые (скан = истина).
    Вызывать ПОСЛЕ применения OCR.
    """
    notes_lines: list[str] = []
    report = {"applicant_fields": [], "resolved": {}, "not_found": [], "notes_added": []}

    # ── 1. Applicant-поля (только пустые) ──
    applicant = None
    if application.applicant_id:
        applicant = session.get(Applicant, application.applicant_id)

    ap = parsed.get("applicant") or {}
    if applicant is not None:
        for src_key, model_field in _APPLICANT_FIELD_MAP.items():
            val = ap.get(src_key)
            if _is_empty(val):
                continue
            current = getattr(applicant, model_field, None)
            if _is_empty(current):
                setattr(applicant, model_field, val)
                report["applicant_fields"].append(model_field)
        if report["applicant_fields"]:
            session.add(applicant)
    # если applicant ещё нет — applicant-поля проигнорим (OCR создаст; текст без
    # сканов редок — паспортные данные в заметки ниже)

    # ── 2. Справочники ──
    # Компания
    comp = parsed.get("company") or {}
    comp_name = comp.get("name")
    if comp_name and not application.company_id:
        cid, dbg = resolve_company(session, comp_name)
        if cid:
            application.company_id = cid
            report["resolved"]["company_id"] = cid
        else:
            notes_lines.append(f"Компания не найдена в справочнике: «{comp_name}» — добавить вручную")
            report["not_found"].append("company")

    # Должность
    pos = parsed.get("position") or {}
    pos_title = pos.get("title")
    if pos_title and not application.position_id:
        pid, dbg = resolve_position(session, pos_title)
        if pid:
            application.position_id = pid
            report["resolved"]["position_id"] = pid
        else:
            notes_lines.append(f"Должность не найдена в справочнике: «{pos_title}» — добавить вручную и указать в дровере")
            report["not_found"].append("position")

    # Представитель (по имени; NIE бонусом)
    rep = parsed.get("representative") or {}
    rep_name = rep.get("full_name")
    rep_nie = rep.get("nie")
    if rep_name and not application.representative_id:
        rid, dbg = resolve_representative(session, rep_name, nie=rep_nie)
        if rid:
            application.representative_id = rid
            report["resolved"]["representative_id"] = rid
        else:
            notes_lines.append(f"Представитель не найден в справочнике: «{rep_name}» — проверить вручную")
            report["not_found"].append("representative")

    # Адрес в Испании
    addr = parsed.get("spain_address") or {}
    addr_raw = addr.get("raw")
    addr_city = addr.get("city")
    addr_street = addr.get("street")
    if (addr_raw or addr_street or addr_city) and not application.spain_address_id:
        aid, dbg = resolve_spain_address(session, raw=addr_raw, city=addr_city, street=addr_street)
        if aid:
            application.spain_address_id = aid
            report["resolved"]["spain_address_id"] = aid
        else:
            notes_lines.append(f"Адрес в Испании не найден в справочнике: «{addr_raw or addr_street or addr_city}» — добавить вручную")
            report["not_found"].append("spain_address")

    # ── 3. Город/провинция подачи (дефолт Barcelona) ──
    sub = parsed.get("submission") or {}
    sub_city = (sub.get("city") or "").strip()
    if not application.submission_city:
        if not sub_city:
            sub_city = "Barcelona"  # дефолт по договорённости
        application.submission_city = sub_city
        sub_prov = (sub.get("province") or "").strip()
        if not sub_prov:
            sub_prov = _CITY_PROVINCE.get(sub_city.lower(), "")
        if sub_prov and not application.submission_province:
            application.submission_province = sub_prov
        report["resolved"]["submission_city"] = sub_city

    # ── 4. Заметки: диплом, паспорт-из-текста, нераспознанное ──
    dip = parsed.get("diploma") or {}
    if (dip.get("status") or "").lower() == "awaiting":
        notes_lines.append("Диплом — ожидание")

    # паспорт из текста, если у applicant пусто (скан даст полноценную запись)
    pass_num = ap.get("passport_number")
    if pass_num and (applicant is None or _is_empty(getattr(applicant, "passport_number", None))):
        # уже записан в applicant выше если applicant был; для отсутствующего — в заметку
        if applicant is None:
            notes_lines.append(f"Паспорт из текста: {pass_num} — проверить (нет скана)")

    unrec = parsed.get("unrecognized") or []
    if unrec:
        notes_lines.append("Не распознано из текста: " + "; ".join(str(x) for x in unrec))

    # ── 5. Запись заметок в internal_notes (добавляем, не затираем) ──
    if notes_lines:
        prefix = (application.internal_notes or "").rstrip()
        block = "[Из текста менеджера]\n" + "\n".join(f"• {l}" for l in notes_lines)
        application.internal_notes = (prefix + "\n\n" + block).strip() if prefix else block
        report["notes_added"] = notes_lines

    session.add(application)
    log.info(
        f"apply_parsed: app={application.id} "
        f"applicant_fields={report['applicant_fields']} "
        f"resolved={list(report['resolved'].keys())} not_found={report['not_found']}"
    )
    return report
