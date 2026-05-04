"""
Pack 18.3 — Контекст для DOCX-шаблона `npd_certificate_template.docx`
(справка о постановке на учёт самозанятого, форма КНД 1122035).

Намеренно отделён от основного `context.build_context()` — справке не нужны
банковская выписка, курсы ЦБ, акты, договоры и прочая обвязка пакета.

Pack 18.9.0 (свежие изменения):
- _pick_mfc() теперь сначала ищет МФЦ с is_universal=True. Если такой найден —
  возвращает его для ВСЕХ клиентов независимо от region_code. Это означает
  что в справке у всех клиентов будет один и тот же московский МФЦ
  (Новоясеневский просп. д.1), а варьироваться будут только staff_names.
- Если is_universal-запись отсутствует в БД (флаг убрали или не было
  миграции 18.9.0) — возвращается старое поведение по region_code.

Pack 18.3.4 (свежие изменения):
- Восстановлен auto-fill Pack 18.3.1 (видимо был потерян при переписываниях).
  Если у applicant'а пустые inn_registration_date или inn_kladr_code — генерим
  на лету и сохраняем в БД. Поддержка ручного ввода ИНН менеджером.
- Логика даты НПД теперь использует submission_date (дату подачи в консул)
  как базу, диапазон 120-210 дней (4-7 месяцев). Раньше было contract_sign_date
  и 30-90 дней — этого было НЕДОСТАТОЧНО для критерия консула «3 месяца
  самозанятости на дату подачи». Теперь критерий проходит с запасом 30 дней.
- Логика идентична _synthetic_npd_registration_date в pipeline.py (один
  алгоритм для двух точек входа: inn-suggest И генерация справки).

Логика подбора ИФНС/МФЦ (без изменений):
- Берём region_code = applicant.inn_kladr_code[:2]. Если пусто — fallback
  на applicant.inn[:2]. Если и ИНН пуст — поднимаем ValueError.
- IfnsOffice: WHERE region_code=... AND is_active=True, ORDER BY
  is_default DESC, code → берём первую.
- MfcOffice: список всех is_active в регионе. Детерминистично
  applicant.id % len(list).
- mfc.staff_names: детерминистично applicant.id % len(staff_names).
- Если ИФНС или МФЦ для региона не найдены — fallback на регион '77' (Москва).
- Если и в Москве пусто — критическая ошибка конфигурации.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from random import Random
from typing import Optional

from sqlmodel import Session, select

from app.models import Applicant, Application
from app.models.ifns_mfc import IfnsOffice, MfcOffice

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_date_short(d) -> str:
    """date(2026, 4, 21) → '21.04.2026'."""
    if not d:
        return ""
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _format_datetime_ru(dt) -> str:
    """datetime(2026, 4, 21, 10, 4) → '21.04.2026, 10:04'."""
    if not dt:
        return ""
    return f"{dt.day:02d}.{dt.month:02d}.{dt.year}, {dt.hour:02d}:{dt.minute:02d}"


def _full_name_caps(applicant: Applicant) -> str:
    """
    Q6: фамилия + имя + отчество (если есть), всё ЗАГЛАВНЫМИ.
    Если отчества нет — только фамилия + имя.
    """
    parts = [
        (applicant.last_name_native or "").strip(),
        (applicant.first_name_native or "").strip(),
    ]
    middle = (applicant.middle_name_native or "").strip()
    if middle:
        parts.append(middle)
    return " ".join(p for p in parts if p).upper()


def _resolve_region_code(applicant: Applicant) -> str:
    """
    Pack 18.3 Q1: «по ИНН и адресу». ИНН и адрес после Pack 18.1 синхронизированы,
    поэтому берём из inn_kladr_code (там и есть регион ИНН).

    Если inn_kladr_code пустой — fallback на inn[:2].
    Если ИНН тоже пустой — ValueError (вызывающий endpoint вернёт 422).
    """
    kladr = (applicant.inn_kladr_code or "").strip()
    if len(kladr) >= 2:
        return kladr[:2]
    inn = (applicant.inn or "").strip()
    if len(inn) >= 2:
        log.warning(
            "_resolve_region_code: applicant id=%s has inn but no inn_kladr_code, "
            "deriving region from inn[:2]=%s",
            applicant.id,
            inn[:2],
        )
        return inn[:2]
    raise ValueError(
        f"Applicant id={applicant.id} has no INN — cannot generate NPD certificate. "
        f"Run inn-suggest first."
    )


def _pick_ifns(session: Session, region_code: str) -> Optional[IfnsOffice]:
    """
    Q4: ставим default-first, иначе первая по коду. Если в регионе ничего —
    None (вызывающий код решит делать ли fallback на Москву).
    """
    stmt = (
        select(IfnsOffice)
        .where(IfnsOffice.region_code == region_code)
        .where(IfnsOffice.is_active == True)  # noqa: E712
        .order_by(IfnsOffice.is_default.desc(), IfnsOffice.code)
    )
    return session.exec(stmt).first()


def _pick_mfc(
    session: Session, region_code: str, applicant_id: int
) -> Optional[MfcOffice]:
    """
    Pack 18.9.0: сначала ищем универсальный МФЦ (is_universal=True).
    Если найден — возвращаем его независимо от region_code (один МФЦ для всех клиентов).

    Если не найден — старая логика Pack 18.0:
    Q2 — детерминистично по applicant.id % len(list). Если в регионе нет МФЦ — None.

    Этот fallback оставлен на случай если is_universal-запись будет отключена
    или удалена — система автоматически вернётся к региональному выбору.
    """
    # Pack 18.9.0: сначала ищем универсальный МФЦ
    universal_stmt = (
        select(MfcOffice)
        .where(MfcOffice.is_universal == True)  # noqa: E712
        .where(MfcOffice.is_active == True)  # noqa: E712
        .order_by(MfcOffice.id)
    )
    universal = session.exec(universal_stmt).first()
    if universal is not None:
        log.debug(
            "_pick_mfc: returning universal MFC id=%s for applicant_id=%s "
            "(ignoring region_code=%s)",
            universal.id, applicant_id, region_code,
        )
        return universal

    # Старая логика — региональный выбор
    stmt = (
        select(MfcOffice)
        .where(MfcOffice.region_code == region_code)
        .where(MfcOffice.is_active == True)  # noqa: E712
        .order_by(MfcOffice.id)
    )
    mfc_list = list(session.exec(stmt).all())
    if not mfc_list:
        return None
    idx = (applicant_id or 0) % len(mfc_list)
    return mfc_list[idx]


def _pick_mfc_employee(mfc: MfcOffice, applicant_id: int) -> str:
    """
    Q3: детерминистично applicant.id % len(staff_names).
    Если staff_names пустой — fallback на placeholder.
    """
    names = mfc.staff_names or []
    if not names:
        log.warning("MfcOffice id=%s has empty staff_names list", mfc.id)
        return "Иванов Иван Иванович"
    idx = (applicant_id or 0) % len(names)
    return names[idx]


# ---------------------------------------------------------------------------
# Pack 18.3.1 — auto-fill для ручного ввода ИНН (восстановлено в 18.3.4)
# ---------------------------------------------------------------------------

def _ensure_inn_registration_date(
    applicant: Applicant,
    application: Application,
    session: Session,
) -> date:
    """
    Pack 18.3.4: auto-fill inn_registration_date (поддержка ручного ввода ИНН).

    Если менеджер ввёл ИНН руками (не через ✨ + Принять модалку), у applicant'а
    inn_registration_date останется пустым. При первой генерации справки эта
    функция:
    1. Генерит дату по той же схеме что pipeline.py (Pack 18.3.4):
       база = submission_date (или fallback на contract_sign_date+90 / today+30)
       минус random(120..210) дней
    2. Сохраняет в БД (session.commit) — повторные генерации справки дают
       стабильную дату.
    3. Если inn_source был None — ставит "manual".

    Логика синхронизирована с _synthetic_npd_registration_date в pipeline.py.
    Любые изменения в одной функции должны зеркалиться в другой.
    """
    if applicant.inn_registration_date is not None:
        return applicant.inn_registration_date

    # Базовая дата — submission_date / contract_sign_date+90 / today()+30
    if application.submission_date is not None:
        base = application.submission_date
    elif application.contract_sign_date is not None:
        base = application.contract_sign_date + timedelta(days=90)
    else:
        base = date.today() + timedelta(days=30)

    rng = Random(applicant.id or 0)
    days_before = rng.randint(120, 210)  # 4-7 месяцев
    derived = base - timedelta(days=days_before)

    log.info(
        "Pack 18.3.4: applicant id=%s has no inn_registration_date, deriving "
        "%s (base=%s, days_before=%s) and writing back to DB",
        applicant.id,
        derived,
        base,
        days_before,
    )

    applicant.inn_registration_date = derived
    if not applicant.inn_source:
        applicant.inn_source = "manual"  # ИНН видимо ввёлся руками
    session.add(applicant)
    session.commit()
    session.refresh(applicant)

    return derived


def _ensure_inn_kladr_code(
    applicant: Applicant,
    session: Session,
) -> str:
    """
    Pack 18.3.4 (восстановлено из 18.3.1): если inn_kladr_code пустой,
    генерируем заглушку из inn[:2] + 11 нулей (валидный 13-значный KLADR
    на уровне субъекта) и сохраняем в БД.
    """
    existing = (applicant.inn_kladr_code or "").strip()
    if len(existing) >= 2:
        return existing

    inn = (applicant.inn or "").strip()
    if len(inn) < 2:
        raise ValueError(
            f"Applicant id={applicant.id} has neither inn_kladr_code nor inn — "
            f"cannot derive region. Run inn-suggest first."
        )

    derived = inn[:2] + "0" * 11
    log.info(
        "Pack 18.3.4: applicant id=%s has no inn_kladr_code, deriving %s from "
        "inn prefix and writing back to DB",
        applicant.id,
        derived,
    )

    applicant.inn_kladr_code = derived
    session.add(applicant)
    session.commit()
    session.refresh(applicant)

    return derived


# ---------------------------------------------------------------------------
# Главный entry point
# ---------------------------------------------------------------------------

def build_npd_certificate_context(
    application: Application,
    session: Session,
    *,
    today: Optional[date] = None,
) -> dict:
    """
    Собирает context для DOCX-шаблона `npd_certificate_template.docx`.

    Pack 18.3.4: автоматически дозаполняет inn_registration_date и
    inn_kladr_code если они пустые (для сценариев ручного ввода ИНН).
    Эти поля сохраняются обратно в БД при первой генерации.

    Аргументы:
        application — заявка
        session — DB session
        today — для тестов; в проде = date.today()

    Возвращает плоский dict с 4 ключами: applicant, certificate, ifns, mfc.
    """
    if today is None:
        today = date.today()

    applicant_id = application.applicant_id
    if applicant_id is None:
        raise ValueError(
            f"Application id={application.id} has no applicant — cannot generate certificate"
        )
    applicant = session.get(Applicant, applicant_id)
    if applicant is None:
        raise ValueError(
            f"Applicant id={applicant_id} not found"
        )

    # Pack 18.3.4: только inn и passport_number обязательны на входе.
    # inn_registration_date и inn_kladr_code дозаполняются автоматически
    # через _ensure_* функции.
    missing: list[str] = []
    if not applicant.inn:
        missing.append("inn")
    if not applicant.passport_number:
        missing.append("passport_number")
    if missing:
        raise ValueError(
            f"Applicant id={applicant_id} is missing required fields for NPD "
            f"certificate: {', '.join(missing)}. Run inn-suggest and fill passport first."
        )

    # Pack 18.3.4: auto-fill недостающих полей с записью в БД
    inn_registration_date = _ensure_inn_registration_date(applicant, application, session)
    _ensure_inn_kladr_code(applicant, session)

    # ---- 1. Регион + ИФНС + МФЦ ----
    region_code = _resolve_region_code(applicant)
    ifns = _pick_ifns(session, region_code)
    mfc = _pick_mfc(session, region_code, applicant_id)

    # Fallback на Москву если в регионе пусто
    if ifns is None:
        log.warning(
            "build_npd_certificate_context: no IfnsOffice for region_code=%s, "
            "falling back to '77' (Moscow)",
            region_code,
        )
        ifns = _pick_ifns(session, "77")
    if mfc is None:
        log.warning(
            "build_npd_certificate_context: no MfcOffice for region_code=%s, "
            "falling back to '77' (Moscow)",
            region_code,
        )
        mfc = _pick_mfc(session, "77", applicant_id)

    if ifns is None:
        raise ValueError(
            "Pack 18.3: no IfnsOffice found in DB even for region '77' (Moscow). "
            "Check that Pack 18.0 seed migration applied successfully."
        )
    if mfc is None:
        raise ValueError(
            "Pack 18.3: no MfcOffice found in DB even for region '77' (Moscow). "
            "Check that Pack 18.0 seed migration applied successfully."
        )

    employee_name = _pick_mfc_employee(mfc, applicant_id)

    # ---- 2. Дата выдачи справки (за 14-21 день до today) ----
    rng = Random(applicant_id or 0)
    days_back = rng.randint(14, 21)
    issued_date = today - timedelta(days=days_back)
    issued_hour = rng.randint(9, 17)
    issued_minute = rng.randint(0, 59)
    issued_datetime = datetime(
        issued_date.year, issued_date.month, issued_date.day,
        issued_hour, issued_minute,
    )

    # ---- 3. Номер справки ----
    base = 106_800_000
    cert_number = base + (applicant_id or 0) * 7 + (issued_date.toordinal() % 100)
    cert_number = cert_number % 1_000_000_000

    # ---- 4. Код документа удостоверения личности ----
    # 21 = паспорт РФ, 10 = паспорт иностранного гражданина (Pack 18.3.1)
    nat = (applicant.nationality or "").upper()
    passport_code = "21" if nat == "RUS" else "10"

    # ---- 5. Сборка контекста ----
    return {
        "applicant": {
            "inn": applicant.inn,
            "full_name_caps": _full_name_caps(applicant),
            "passport_number": applicant.passport_number or "",
        },
        "certificate": {
            "number": str(cert_number),
            "year": str(issued_date.year),
            "issued_date_short": _format_date_short(issued_date),
            "issued_datetime_ru": _format_datetime_ru(issued_datetime),
            "passport_code": passport_code,
            "npd_start_date_short": _format_date_short(inn_registration_date),
        },
        "ifns": {
            "full_name": ifns.full_name,
            "short_name": ifns.short_name,
            "code": ifns.code,
            "address": ifns.address or "",
        },
        "mfc": {
            "name": mfc.name,
            "address": mfc.address,
            "city": mfc.city,
            "employee_name": employee_name,
        },
    }
