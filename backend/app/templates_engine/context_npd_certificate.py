"""
Pack 18.3 — Контекст для DOCX-шаблона `npd_certificate_template.docx`
(справка о постановке на учёт самозанятого, форма КНД 1122035).

Намеренно отделён от основного `context.build_context()` — справке не нужны
банковская выписка, курсы ЦБ, акты, договоры и прочая обвязка пакета.

Логика подбора ИФНС/МФЦ:
- Берём region_code = applicant.inn_kladr_code[:2]. Если пусто — fallback
  на applicant.inn[:2]. Если и ИНН пуст — поднимаем ValueError.
- IfnsOffice: WHERE region_code=... AND is_active=True, ORDER BY
  is_default DESC, code → берём первую (если default есть — он будет первым,
  иначе самая первая по коду).
- MfcOffice: список всех is_active в этом регионе. Если несколько —
  детерминистично выбираем по applicant.id % len(list) (Q2: повторная
  генерация даёт тот же МФЦ).
- mfc.staff_names: детерминистично applicant.id % len(staff_names) (Q3).
- Если ИФНС или МФЦ для региона не найдены — fallback на регион '77' (Москва).
- Если и в Москве пусто — это критическая ошибка конфигурации (поднимаем
  ValueError с понятным сообщением).
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
        # is_default DESC: True (=1) идёт перед False (=0) в сортировке desc
        .order_by(IfnsOffice.is_default.desc(), IfnsOffice.code)
    )
    return session.exec(stmt).first()


def _pick_mfc(
    session: Session, region_code: str, applicant_id: int
) -> Optional[MfcOffice]:
    """
    Q2: детерминистично по applicant.id % len(list). Если в регионе нет МФЦ —
    None.
    """
    stmt = (
        select(MfcOffice)
        .where(MfcOffice.region_code == region_code)
        .where(MfcOffice.is_active == True)  # noqa: E712
        .order_by(MfcOffice.id)  # стабильная сортировка для детерминизма
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

    Аргументы:
        application — заявка (нужна только чтобы найти applicant_id; реально
            справка персональная, нужны только данные applicant'а)
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

    # Базовая валидация — без этих полей справка лишена смысла
    missing: list[str] = []
    if not applicant.inn:
        missing.append("inn")
    if not applicant.inn_registration_date:
        missing.append("inn_registration_date")
    if not applicant.passport_number:
        missing.append("passport_number")
    if missing:
        raise ValueError(
            f"Applicant id={applicant_id} is missing required fields for NPD "
            f"certificate: {', '.join(missing)}. Run inn-suggest and fill passport first."
        )

    # ---- 1. Регион + ИФНС + МФЦ ----
    region_code = _resolve_region_code(applicant)
    ifns = _pick_ifns(session, region_code)
    mfc = _pick_mfc(session, region_code, applicant_id)

    # Fallback на Москву если в регионе пусто (для ИФНС или МФЦ отдельно)
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

    # ---- 2. Дата выдачи справки (Q: за 2-3 недели до today) ----
    # Детерминистично по applicant_id (одинаковая дата при повторной генерации
    # того же applicant'а).
    rng = Random(applicant_id or 0)
    days_back = rng.randint(14, 21)
    issued_date = today - timedelta(days=days_back)
    # Время — рабочие часы 09:00-17:00, рандом по applicant_id
    issued_hour = rng.randint(9, 17)
    issued_minute = rng.randint(0, 59)
    issued_datetime = datetime(
        issued_date.year, issued_date.month, issued_date.day,
        issued_hour, issued_minute,
    )

    # ---- 3. Номер справки (Q5 вариант C: формула) ----
    # 9-значный, "псевдо-нарастающий". Базовое значение около образца (106735761).
    # Формула: 106_800_000 + applicant_id*7 + (issued_date_ordinal % 100).
    base = 106_800_000
    cert_number = base + (applicant_id or 0) * 7 + (issued_date.toordinal() % 100)
    # Гарантия 9 цифр (на всякий случай)
    cert_number = cert_number % 1_000_000_000

    # ---- 4. Код документа удостоверения личности ----
    # Pack 18.3.1 (фикс): по реальным образцам справки КНД 1122035 от ФНС:
    #   21 = паспорт гражданина Российской Федерации
    #   10 = паспорт иностранного гражданина
    # (в первом образце Сахиджафарлы было ошибочно прочитано как "1 21" — на самом
    # деле "1" это надстрочный знак сноски ¹, а код = 21)
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
            "npd_start_date_short": _format_date_short(applicant.inn_registration_date),
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
