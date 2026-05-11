"""
Pack 18.3 — Контекст для DOCX-шаблона `npd_certificate_template.docx`
(справка о постановке на учёт самозанятого, форма КНД 1122035).

Намеренно отделён от основного `context.build_context()` — справке не нужны
банковская выписка, курсы ЦБ, акты, договоры и прочая обвязка пакета.

Pack 33.8 (10.05.2026):
- _pick_ifns() получил новый Tier A: матч по IfnsOffice.coverage_keywords
  (точные lowercase подстроки в applicant.home_address). Это позволяет точно
  выбирать районную инспекцию по адресу без зависимости от случайных совпадений
  слов. Старая логика Pack 31.1 (общие слова >=4 букв в IfnsOffice.address)
  оставлена как Tier B fallback для записей без coverage_keywords.

Pack 18.9.0:
- _pick_mfc() теперь сначала ищет МФЦ с is_universal=True. Если такой найден —
  возвращает его для ВСЕХ клиентов независимо от region_code.

Pack 18.3.4:
- Восстановлен auto-fill (Pack 18.3.1).
- Логика даты НПД использует submission_date как базу, диапазон 120-210 дней.

Логика подбора ИФНС (Pack 33.8):
- Берём region_code = applicant.inn_kladr_code[:2] (где выдан ИНН).
- Tier A: ищем non-default ИФНС в регионе с непустым coverage_keywords;
  если ЛЮБАЯ keyword содержится в applicant.home_address.lower() —
  возвращаем эту инспекцию. Точный матч по районам.
- Tier B (fallback Pack 31.1): среди non-default ищем по общим словам
  >=4 букв в IfnsOffice.address. Сохранён для обратной совместимости.
- Tier C: default-first ordering (УФНС региона).
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
    """date(2026, 4, 21) -> '21.04.2026'."""
    if not d:
        return ""
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _format_datetime_ru(dt) -> str:
    """datetime(2026, 4, 21, 10, 4) -> '21.04.2026, 10:04'."""
    if not dt:
        return ""
    return f"{dt.day:02d}.{dt.month:02d}.{dt.year}, {dt.hour:02d}:{dt.minute:02d}"


def _full_name_caps(applicant: Applicant) -> str:
    """
    Q6: фамилия + имя + отчество (если есть), всё ЗАГЛАВНЫМИ.
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
    Pack 18.3 Q1: «по ИНН и адресу». Берём из inn_kladr_code (там и есть регион ИНН).
    Если inn_kladr_code пустой — fallback на inn[:2].
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


def _pick_ifns(
    session: Session,
    region_code: str,
    applicant: Optional[Applicant] = None,
) -> Optional[IfnsOffice]:
    """
    Q4 + Pack 31.1 + Pack 33.8: подбор ИФНС с учётом адреса самозанятого.

    Tier A (Pack 33.8) — coverage_keywords:
      Среди non-default ИФНС региона ищем такую, у которой ЛЮБАЯ из
      coverage_keywords является подстрокой applicant.home_address.lower().

    Tier B (Pack 31.1, legacy) — общие слова >=4 букв в address.

    Tier C-prime (Pack 33.8) — если в регионе РОВНО ОДНА non-default запись,
      возвращаем её. Покрывает кейс «парадокс Ся Инь»: ИНН выдан в регионе
      X, но home_address в другом субъекте — выбираем единственную МИФНС
      региона X, а не общерегиональную УФНС-управление.

    Tier C (fallback) — default-first ordering.
    """
    # --- Tier A: coverage_keywords (Pack 33.8) ---
    if applicant and applicant.home_address:
        addr_lower = applicant.home_address.lower()
        non_default = list(session.exec(
            select(IfnsOffice)
            .where(IfnsOffice.region_code == region_code)
            .where(IfnsOffice.is_active == True)  # noqa: E712
            .where(IfnsOffice.is_default == False)  # noqa: E712
            .order_by(IfnsOffice.code)
        ).all())

        for ifns in non_default:
            keywords = ifns.coverage_keywords or []
            for kw in keywords:
                if not kw:
                    continue
                kw_lower = kw.strip().lower()
                if kw_lower and kw_lower in addr_lower:
                    log.info(
                        "_pick_ifns Pack 33.8 Tier A: matched %s by keyword %r in addr",
                        ifns.short_name, kw_lower,
                    )
                    return ifns

        # --- Tier B: legacy Pack 31.1 — общие слова >=4 букв в address ---
        for ifns in non_default:
            if not ifns.address:
                continue
            ifns_addr_lower = ifns.address.lower()
            for word in ifns_addr_lower.replace(",", " ").split():
                w = word.strip(".").strip()
                if len(w) < 4:
                    continue
                if w in {"улица", "переулок", "проспект", "шоссе", "наб", "пер"}:
                    continue
                if w in addr_lower:
                    log.info(
                        "_pick_ifns Pack 31.1 Tier B: matched %s by city marker %r in addr",
                        ifns.short_name, w,
                    )
                    return ifns

        # --- Tier C-prime (Pack 33.8): если в регионе ровно одна non-default ---
        # запись, возвращаем её. Это покрывает «парадокс Ся Инь»: ИНН выдан
        # в регионе X, но home_address в другом субъекте РФ. У нас в этом
        # регионе X есть только одна специфическая МИФНС — она и должна быть
        # выбрана вместо общерегиональной УФНС-управление.
        # Москва (с 5+ non-default) НЕ затронута — там нужен точный keyword-матч.
        if len(non_default) == 1:
            log.info(
                "_pick_ifns Pack 33.8 Tier C-prime: exactly one non-default in "
                "region %s, returning %s without address match",
                region_code, non_default[0].short_name,
            )
            return non_default[0]

    # --- Tier C: fallback — default-first, иначе первая по коду ---
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
    Иначе — региональный выбор (Pack 18.0).
    """
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
    """
    if applicant.inn_registration_date is not None:
        return applicant.inn_registration_date

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
        applicant.id, derived, base, days_before,
    )

    applicant.inn_registration_date = derived
    if not applicant.inn_source:
        applicant.inn_source = "manual"
    session.add(applicant)
    session.commit()
    session.refresh(applicant)

    return derived


def _ensure_inn_kladr_code(
    applicant: Applicant,
    session: Session,
) -> str:
    """
    Pack 18.3.4: если inn_kladr_code пустой, генерируем заглушку из
    inn[:2] + 11 нулей и сохраняем в БД.
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
        applicant.id, derived,
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
        raise ValueError(f"Applicant id={applicant_id} not found")

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

    inn_registration_date = _ensure_inn_registration_date(applicant, application, session)
    _ensure_inn_kladr_code(applicant, session)

    # ---- 1. Регион + ИФНС + МФЦ ----
    region_code = _resolve_region_code(applicant)
    ifns = _pick_ifns(session, region_code, applicant)
    mfc = _pick_mfc(session, region_code, applicant_id)

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
    # Pack 35.1: МФЦ не работают в выходные — сдвигаем на предыдущий рабочий
    # (суббота → пятница, воскресенье → пятница). Сдвиг НАЗАД, чтобы не
    # «омолодить» справку и не нарушить порядок submission_date.
    # weekday(): 0=пн ... 4=пт, 5=сб, 6=вс.
    while issued_date.weekday() >= 5:
        issued_date -= timedelta(days=1)
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
