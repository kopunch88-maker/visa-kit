# -*- coding: utf-8 -*-
"""
Pack 37.0-C — Fix handlers.

Каждый handler принимает (AuditFinding, Session) и применяет один тип
исправления. Сами таблицы не пишет напрямую — использует ORM-методы.

Архитектура whitelist:
- LLM возвращает finding с fix_action = "update_applicant_field" и
  fix_payload = {"field": "last_name_native", "value": "Шахин"}.
- Backend смотрит fix_action в FIX_HANDLERS dict.
- Если есть — вызывает handler, который валидирует payload через Pydantic
  (защита от мусора и prompt injection), затем делает UPDATE.
- Если нет — finding показывается без кнопки «Принять», только
  Dismiss / Manual fix.

Pydantic-валидация важна потому что field_path из LLM нельзя слепо
прокидывать в setattr — LLM может галлюцинировать «update _password_hash»
или несуществующее поле.

При успехе handler возвращает FixResult с diff (old → new) для аудит-лога.

Pack 37.0-C важно: применение фикса НЕ перегенерирует пакет 16 файлов.
Менеджер пересобирает пакет отдельной кнопкой когда все нужные фиксы
применены. Это экономит время и деньги.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from pydantic import BaseModel, ValidationError, field_validator
from sqlmodel import Session

log = logging.getLogger(__name__)


# ====================================================================
# Whitelist полей, в которые разрешено писать
# ====================================================================

APPLICANT_WRITABLE_FIELDS = frozenset([
    "last_name_native",
    "first_name_native",
    "middle_name_native",
    "last_name_latin",
    "first_name_latin",
    "birth_date",
    "birth_place_latin",
    "birth_country",
    "nationality",
    "sex",
    "passport_number",
    "passport_series",
    "passport_issue_date",
    "passport_expiry_date",
    "passport_issuer",
    "passport_issuer_ru",
    "phone",
    "email",
    "home_address",
    "home_address_line2",
    "home_country",
    "inn",
])

COMPANY_WRITABLE_FIELDS = frozenset([
    "name",
    "tax_id_primary",
    "kpp",
    "ogrn",
    "address",
    "bank_account",
    "bank_bic",
    "bank_name",
    "director_name",
    "director_position",
    "phone",
    "email",
])


# ====================================================================
# Result container
# ====================================================================

@dataclass
class FixResult:
    """diff = {"field.path": [old_value, new_value]}"""
    success: bool
    diff: Dict[str, List[Any]] = field(default_factory=dict)
    message: Optional[str] = None
    error: Optional[str] = None


# ====================================================================
# Pydantic schemas
# ====================================================================

class UpdateApplicantFieldPayload(BaseModel):
    field: str
    value: Optional[str] = None

    @field_validator("field")
    @classmethod
    def field_in_whitelist(cls, v: str) -> str:
        if v not in APPLICANT_WRITABLE_FIELDS:
            raise ValueError(
                f"Field '{v}' is not in APPLICANT_WRITABLE_FIELDS whitelist"
            )
        return v


class UpdateCompanyFieldPayload(BaseModel):
    field: str
    value: Optional[str] = None

    @field_validator("field")
    @classmethod
    def field_in_whitelist(cls, v: str) -> str:
        if v not in COMPANY_WRITABLE_FIELDS:
            raise ValueError(
                f"Field '{v}' is not in COMPANY_WRITABLE_FIELDS whitelist"
            )
        return v


class UpdateEducationRecordPayload(BaseModel):
    index: int
    field: str
    value: Optional[str] = None

    @field_validator("index")
    @classmethod
    def index_positive(cls, v: int) -> int:
        if v < 0 or v > 20:
            raise ValueError(f"Index out of range: {v}")
        return v

    @field_validator("field")
    @classmethod
    def field_in_whitelist(cls, v: str) -> str:
        allowed = {"institution", "graduation_year", "degree", "specialty"}
        if v not in allowed:
            raise ValueError(f"Field '{v}' not allowed. Allowed: {allowed}")
        return v


# ====================================================================
# Загрузка related models
# ====================================================================

def _load_application_and_applicant(finding, session: Session):
    """Из finding.report_id → AuditReport → Application → Applicant."""
    from app.models import Application, AuditReport

    report = session.get(AuditReport, finding.report_id)
    if not report:
        raise ValueError(f"AuditReport {finding.report_id} not found")
    application = session.get(Application, report.application_id)
    if not application:
        raise ValueError(f"Application {report.application_id} not found")
    return application, application.applicant


def _load_company(finding, session: Session):
    from app.models import Application, AuditReport, Company

    report = session.get(AuditReport, finding.report_id)
    if not report:
        raise ValueError(f"AuditReport {finding.report_id} not found")
    application = session.get(Application, report.application_id)
    if not application or not getattr(application, "company_id", None):
        return None
    return session.get(Company, application.company_id)


# ====================================================================
# HANDLERS
# ====================================================================

def handle_update_applicant_field(finding, session: Session) -> FixResult:
    """
    fix_payload: {"field": "last_name_native", "value": "Шахин"}
    """
    try:
        payload = UpdateApplicantFieldPayload(**(finding.fix_payload or {}))
    except ValidationError as e:
        return FixResult(success=False, error=f"Invalid payload: {e}")

    _, applicant = _load_application_and_applicant(finding, session)
    if not applicant:
        return FixResult(success=False, error="Applicant not found")

    old_value = getattr(applicant, payload.field, None)

    # Спец-обработка для date-полей: payload приходит строкой, но в БД нужен date
    if payload.field in ("birth_date", "passport_issue_date", "passport_expiry_date") \
            and payload.value:
        from datetime import date
        try:
            new_value = date.fromisoformat(payload.value)
        except ValueError:
            return FixResult(
                success=False,
                error=f"Invalid date format for {payload.field}: '{payload.value}', expected YYYY-MM-DD",
            )
    else:
        new_value = payload.value

    setattr(applicant, payload.field, new_value)
    session.add(applicant)
    session.commit()

    log.info(
        f"[fix:update_applicant_field] applicant#{applicant.id}.{payload.field}: "
        f"{old_value!r} -> {new_value!r}"
    )

    return FixResult(
        success=True,
        diff={f"applicant.{payload.field}": [old_value, new_value]},
        message=f"Updated applicant.{payload.field}",
    )


def handle_update_company_field(finding, session: Session) -> FixResult:
    """fix_payload: {"field": "address", "value": "г. Москва, ул. Ленина, д. 1"}"""
    try:
        payload = UpdateCompanyFieldPayload(**(finding.fix_payload or {}))
    except ValidationError as e:
        return FixResult(success=False, error=f"Invalid payload: {e}")

    company = _load_company(finding, session)
    if not company:
        return FixResult(success=False, error="Company not found for this application")

    old_value = getattr(company, payload.field, None)
    setattr(company, payload.field, payload.value)
    session.add(company)
    session.commit()

    log.info(
        f"[fix:update_company_field] company#{company.id}.{payload.field}: "
        f"{old_value!r} -> {payload.value!r}"
    )

    return FixResult(
        success=True,
        diff={f"company.{payload.field}": [old_value, payload.value]},
        message=f"Updated company.{payload.field}",
    )


def handle_swap_first_and_last_name(finding, session: Session) -> FixResult:
    """
    Перепутаны местами фамилия и имя.
    Меняет native И latin (если оба заполнены).
    """
    _, applicant = _load_application_and_applicant(finding, session)
    if not applicant:
        return FixResult(success=False, error="Applicant not found")

    diff = {}

    # Native
    old_last_n = applicant.last_name_native
    old_first_n = applicant.first_name_native
    if old_last_n or old_first_n:
        applicant.last_name_native = old_first_n
        applicant.first_name_native = old_last_n
        diff["applicant.last_name_native"] = [old_last_n, old_first_n]
        diff["applicant.first_name_native"] = [old_first_n, old_last_n]

    # Latin
    old_last_l = applicant.last_name_latin
    old_first_l = applicant.first_name_latin
    if old_last_l or old_first_l:
        applicant.last_name_latin = old_first_l
        applicant.first_name_latin = old_last_l
        diff["applicant.last_name_latin"] = [old_last_l, old_first_l]
        diff["applicant.first_name_latin"] = [old_first_l, old_last_l]

    if not diff:
        return FixResult(success=False, error="No names to swap (both empty)")

    session.add(applicant)
    session.commit()

    log.info(f"[fix:swap_first_and_last_name] applicant#{applicant.id}: {diff}")

    return FixResult(
        success=True,
        diff=diff,
        message="Swapped first and last names",
    )


def handle_fix_transliteration(finding, session: Session) -> FixResult:
    """
    Перегенерация _latin из _native через проектный transliterate_name.
    Использует app/services/transliteration.py (Pack 19+).
    """
    try:
        from app.services.transliteration import transliterate_name
    except ImportError:
        return FixResult(
            success=False,
            error="transliterate_name not available in app.services.transliteration",
        )

    _, applicant = _load_application_and_applicant(finding, session)
    if not applicant:
        return FixResult(success=False, error="Applicant not found")

    diff = {}

    if applicant.last_name_native:
        new_last = transliterate_name(applicant.last_name_native)
        if new_last != applicant.last_name_latin:
            diff["applicant.last_name_latin"] = [applicant.last_name_latin, new_last]
            applicant.last_name_latin = new_last

    if applicant.first_name_native:
        new_first = transliterate_name(applicant.first_name_native)
        if new_first != applicant.first_name_latin:
            diff["applicant.first_name_latin"] = [applicant.first_name_latin, new_first]
            applicant.first_name_latin = new_first

    if applicant.middle_name_native:
        new_mid = transliterate_name(applicant.middle_name_native)
        # Middle latin может не быть отдельным полем — игнорим если нет
        old_mid_lat = getattr(applicant, "middle_name_latin", None)
        if hasattr(applicant, "middle_name_latin") and new_mid != old_mid_lat:
            diff["applicant.middle_name_latin"] = [old_mid_lat, new_mid]
            applicant.middle_name_latin = new_mid

    if not diff:
        return FixResult(
            success=False,
            error="Transliteration already matches native names — nothing to fix",
        )

    session.add(applicant)
    session.commit()

    log.info(f"[fix:fix_transliteration] applicant#{applicant.id}: {diff}")

    return FixResult(
        success=True,
        diff=diff,
        message="Re-generated latin names from native via GOST 7.79-2000",
    )


def handle_normalize_name_case(finding, session: Session) -> FixResult:
    """
    Title Case для _native, UPPER для _latin.
    """
    _, applicant = _load_application_and_applicant(finding, session)
    if not applicant:
        return FixResult(success=False, error="Applicant not found")

    diff = {}

    # Native → Title Case (первая буква каждого слова заглавная)
    for fld in ("last_name_native", "first_name_native", "middle_name_native"):
        old = getattr(applicant, fld, None)
        if old:
            # Python str.title() ломает «Оглы» → «Оглы», нужен smart-title
            normalized = " ".join(
                part[0].upper() + part[1:].lower() if part else part
                for part in old.split()
            )
            if normalized != old:
                diff[f"applicant.{fld}"] = [old, normalized]
                setattr(applicant, fld, normalized)

    # Latin → UPPER
    for fld in ("last_name_latin", "first_name_latin"):
        old = getattr(applicant, fld, None)
        if old:
            normalized = old.upper()
            if normalized != old:
                diff[f"applicant.{fld}"] = [old, normalized]
                setattr(applicant, fld, normalized)

    if not diff:
        return FixResult(success=False, error="Names already normalized")

    session.add(applicant)
    session.commit()

    log.info(f"[fix:normalize_name_case] applicant#{applicant.id}: {diff}")

    return FixResult(success=True, diff=diff, message="Normalized name case")


def handle_fix_passport_issuer_ru(finding, session: Session) -> FixResult:
    """
    Перегенерация passport_issuer_ru через Pack 35.2 resolver.
    """
    try:
        from app.services.passport_issuer_ru import resolve as resolve_issuer_ru
    except ImportError:
        try:
            # Alternative naming
            from app.services.passport_issuer_ru import resolve_passport_issuer_ru as resolve_issuer_ru
        except ImportError:
            return FixResult(
                success=False,
                error="passport_issuer_ru.resolve not available",
            )

    _, applicant = _load_application_and_applicant(finding, session)
    if not applicant:
        return FixResult(success=False, error="Applicant not found")

    if not applicant.passport_issuer:
        return FixResult(success=False, error="applicant.passport_issuer is empty")

    old_value = applicant.passport_issuer_ru
    # Pack 35.2 resolver принимает (passport_issuer, nationality)
    try:
        new_value = resolve_issuer_ru(
            applicant.passport_issuer,
            applicant.nationality,
        )
    except TypeError:
        # Fallback на однопараметрический вариант
        new_value = resolve_issuer_ru(applicant.passport_issuer)

    if new_value == old_value:
        return FixResult(
            success=False,
            error="passport_issuer_ru already up-to-date",
        )

    applicant.passport_issuer_ru = new_value
    session.add(applicant)
    session.commit()

    log.info(
        f"[fix:fix_passport_issuer_ru] applicant#{applicant.id}: "
        f"{old_value!r} -> {new_value!r}"
    )

    return FixResult(
        success=True,
        diff={"applicant.passport_issuer_ru": [old_value, new_value]},
        message="Resolved passport_issuer_ru via Pack 35.2",
    )


def handle_regenerate_applicant_inn(finding, session: Session) -> FixResult:
    """
    Берёт следующий валидный ИНН самозанятого из npd_candidate pool.
    Использует существующий механизм Pack 17.2.
    """
    from app.models import NpdCandidate
    from sqlmodel import select

    _, applicant = _load_application_and_applicant(finding, session)
    if not applicant:
        return FixResult(success=False, error="Applicant not found")

    # Берём первого available кандидата
    candidate = session.exec(
        select(NpdCandidate)
        .where(NpdCandidate.is_used == False)  # noqa: E712
        .limit(1)
    ).first()

    if not candidate:
        return FixResult(
            success=False,
            error="No available NPD candidates in pool — refill needed",
        )

    old_inn = applicant.inn
    new_inn = candidate.inn

    applicant.inn = new_inn
    candidate.is_used = True
    candidate.used_by_applicant_id = applicant.id

    session.add(applicant)
    session.add(candidate)
    session.commit()

    log.info(
        f"[fix:regenerate_applicant_inn] applicant#{applicant.id}: "
        f"{old_inn!r} -> {new_inn!r}"
    )

    return FixResult(
        success=True,
        diff={"applicant.inn": [old_inn, new_inn]},
        message=f"Allocated new INN from pool: {new_inn}",
    )


def handle_update_education_record(finding, session: Session) -> FixResult:
    """
    Patch одной записи в applicant.education JSON-массиве.
    fix_payload: {"index": 0, "field": "institution", "value": "МГУ им. М.В. Ломоносова"}
    """
    try:
        payload = UpdateEducationRecordPayload(**(finding.fix_payload or {}))
    except ValidationError as e:
        return FixResult(success=False, error=f"Invalid payload: {e}")

    _, applicant = _load_application_and_applicant(finding, session)
    if not applicant:
        return FixResult(success=False, error="Applicant not found")

    education = list(applicant.education or [])
    if payload.index >= len(education):
        return FixResult(
            success=False,
            error=f"Education index {payload.index} out of range (have {len(education)} records)",
        )

    record = dict(education[payload.index])
    old_value = record.get(payload.field)
    record[payload.field] = payload.value
    education[payload.index] = record

    applicant.education = education
    session.add(applicant)
    session.commit()

    log.info(
        f"[fix:update_education_record] applicant#{applicant.id}.education[{payload.index}].{payload.field}: "
        f"{old_value!r} -> {payload.value!r}"
    )

    return FixResult(
        success=True,
        diff={f"applicant.education[{payload.index}].{payload.field}": [old_value, payload.value]},
        message=f"Updated education[{payload.index}].{payload.field}",
    )


# ====================================================================
# Whitelist реестр — public API
# ====================================================================

FIX_HANDLERS: Dict[str, Callable] = {
    "update_applicant_field": handle_update_applicant_field,
    "update_company_field": handle_update_company_field,
    "swap_first_and_last_name": handle_swap_first_and_last_name,
    "fix_transliteration": handle_fix_transliteration,
    "normalize_name_case": handle_normalize_name_case,
    "fix_passport_issuer_ru": handle_fix_passport_issuer_ru,
    "regenerate_applicant_inn": handle_regenerate_applicant_inn,
    "update_education_record": handle_update_education_record,
}


def get_supported_fix_actions() -> frozenset:
    """Для UI — можно ли показывать кнопку «Принять»."""
    return frozenset(FIX_HANDLERS.keys())


def apply_fix(finding, session: Session) -> FixResult:
    """
    Главная точка входа. Вызывается из api/audit.py для accept_finding.

    Если fix_action не в whitelist — возвращает FixResult(success=False).
    Иначе вызывает соответствующий handler.
    """
    if not finding.fix_action:
        return FixResult(
            success=False,
            error="Finding has no fix_action — only manual_fix or dismiss available",
        )

    handler = FIX_HANDLERS.get(finding.fix_action)
    if not handler:
        return FixResult(
            success=False,
            error=(
                f"fix_action '{finding.fix_action}' not in whitelist. "
                f"Supported: {sorted(FIX_HANDLERS.keys())}"
            ),
        )

    try:
        return handler(finding, session)
    except Exception as e:
        log.exception(f"[fix:apply_fix] Handler {finding.fix_action} crashed")
        return FixResult(success=False, error=f"Handler crashed: {e}")
