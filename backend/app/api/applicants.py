"""
Applicants admin endpoints — для админки чтобы получать и редактировать данные клиента.
Pack 8: эндпоинты возвращают dict (без валидации Pydantic), как в client_portal.
Pack 14 finishing: добавлены PATCH endpoint и /transliterate для иностранцев.
Pack 16.1: добавлены банковские поля (bank_id, bank_account, ...) в whitelist
для редактирования через ApplicantDrawer.
Pack 18.5: _enrich теперь делает join с self_employed_registry чтобы вернуть
npd_check_status и npd_last_check_at — фронт показывает значок «Проверен ФНС» /
«Не действителен» / «Не проверен» рядом с полем ИНН в ApplicantDrawer.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session

from app.db.session import get_session
from app.models import Applicant
from app.models.self_employed_registry import SelfEmployedRegistry
from app.services.transliteration import transliterate_lat_to_ru, normalize_russian_case
from .dependencies import require_manager

router = APIRouter(prefix="/admin/applicants", tags=["applicants"])


def _compute_npd_check_status(
    applicant: Applicant, session: Session
) -> tuple[str, Optional[datetime]]:
    """
    Pack 18.5: вычисляет статус проверки ИНН через ФНС API на основе
    данных в self_employed_registry.

    Возвращает (status, last_check_at):
      - 'no_inn' — у applicant'а нет ИНН (значок не показывается)
      - 'verified' — last_npd_check_at установлен, is_invalid=False (зелёный ✓)
      - 'invalid' — is_invalid=True (красный ✗) — ФНС подтвердил отзыв статуса
      - 'not_checked' — есть ИНН, но проверка не выполнялась (серый —)
                       (например, ИНН выдан до Pack 18.2 или ФНС был недоступен)
    """
    if not applicant.inn:
        return "no_inn", None

    cand = session.get(SelfEmployedRegistry, applicant.inn)
    if not cand:
        # ИНН в applicant'е есть, но в реестре его нет — странная ситуация
        return "not_checked", None

    if cand.is_invalid:
        return "invalid", cand.last_npd_check_at

    if cand.last_npd_check_at is not None:
        return "verified", cand.last_npd_check_at

    return "not_checked", None


def _enrich(applicant: Applicant, session: Session) -> dict:
    """
    Pack 18.5: добавлен параметр session чтобы можно было подгрузить запись
    из self_employed_registry для вычисления npd_check_status.
    """
    parts = [applicant.last_name_native, applicant.first_name_native]
    if applicant.middle_name_native:
        parts.append(applicant.middle_name_native)
    full_name = " ".join(p for p in parts if p)

    initials = ""
    if applicant.last_name_native and applicant.first_name_native:
        initials = f"{applicant.last_name_native} {applicant.first_name_native[0]}."
        if applicant.middle_name_native:
            initials += f"{applicant.middle_name_native[0]}."

    data = applicant.model_dump()
    data["full_name_native"] = full_name
    data["initials_native"] = initials

    # Pack 18.5: статус проверки НПД через ФНС API
    npd_status, npd_last_check = _compute_npd_check_status(applicant, session)
    data["npd_check_status"] = npd_status
    data["npd_last_check_at"] = npd_last_check.isoformat() if npd_last_check else None

    return data


@router.get("/{applicant_id}")
def get_applicant(
    applicant_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(404, "Applicant not found")
    return _enrich(applicant, session)


# ============================================================================
# Pack 14 finishing — PATCH endpoint
# ============================================================================

# Поля которые менеджер может редактировать через ApplicantDrawer.
# Pack 16.1: добавлены bank_* поля.
_PATCHABLE_FIELDS = {
    "last_name_native", "first_name_native", "middle_name_native",
    "last_name_latin", "first_name_latin",
    "birth_date", "birth_place_latin",
    "birth_country",  # Pack 18.10
    "nationality", "sex",
    "passport_number", "passport_issue_date", "passport_expiry_date", "passport_issuer",
    "inn",
    # Pack 17 — INN auto-generation поля
    "inn_registration_date",
    "inn_source",
    "inn_kladr_code",
    "home_address", "home_address_line1", "home_address_line2",
    "home_country",
    "email", "phone",
    # Pack 16.1 — банковские поля
    "bank_id",
    "bank_account",
    "bank_name",
    "bank_bic",
    "bank_correspondent_account",
    # Имена родителей для анкеты MI-T (Nombre del padre / Nombre de la madre)
    "father_name_latin",
    "mother_name_latin",
    # Pack 18.9 — переопределение подписанта апостиля (если null — backend
    # подставляет дефолт «Байрамов Н.А.» / стандартная должность Минюста)
    "apostille_signer_short",
    "apostille_signer_signature",
    "apostille_signer_position",
}

# Поля русского ФИО — к ним применяется normalize_russian_case при сохранении
_NATIVE_NAME_FIELDS = {"last_name_native", "first_name_native", "middle_name_native"}

# Поля латинского ФИО — оставляем uppercase как в паспорте
_LATIN_NAME_FIELDS = {"last_name_latin", "first_name_latin"}

# Pack 16.1: целочисленные поля — приводим к int
_INT_FIELDS = {"bank_id"}


@router.patch("/{applicant_id}")
def update_applicant(
    applicant_id: int,
    patch: dict = Body(...),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    """
    Обновляет данные кандидата от имени менеджера.

    Pack 14 finishing: позволяет менеджеру вписать русские ФИО для иностранцев,
    исправить гражданство и т.д.
    Pack 16.1: + банковские поля (bank_id, bank_account, ...).

    Применяет нормализацию:
    - Русские ФИО → Title Case (Иванов, не ИВАНОВ)
    - Латинские ФИО → как есть, но trim (паспорт обычно UPPERCASE — оставляем)
    - bank_id → приводим к int (frontend может прислать строкой "1")

    Body — dict с любыми полями из _PATCHABLE_FIELDS.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(404, "Applicant not found")

    if not isinstance(patch, dict):
        raise HTTPException(400, "Body must be a JSON object")

    # Валидация — только разрешённые поля
    unknown = set(patch.keys()) - _PATCHABLE_FIELDS
    if unknown:
        raise HTTPException(400, f"Unknown fields: {sorted(unknown)}")

    # Применяем изменения
    for field, value in patch.items():
        if value is None or value == "":
            # Пустое значение → null (для опциональных полей)
            # КРОМЕ обязательных
            if field in ("last_name_native", "first_name_native",
                          "last_name_latin", "first_name_latin"):
                # Не позволяем затирать обязательные поля
                continue
            setattr(applicant, field, None)
            continue

        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue

            # Нормализация русских ФИО
            if field in _NATIVE_NAME_FIELDS:
                value = normalize_russian_case(value)

            # Pack 16.1: bank_id может прийти как строка — приводим к int
            if field in _INT_FIELDS:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    raise HTTPException(400, f"Field {field} must be an integer")

            # Латинские ФИО — оставляем как менеджер ввёл, только trim
            # (обычно UPPERCASE, как в паспорте)

        # Pack 16.1: bank_id может прийти как число напрямую — это ок
        setattr(applicant, field, value)

    session.add(applicant)
    session.commit()
    session.refresh(applicant)

    return _enrich(applicant, session)


# ============================================================================
# Pack 14 finishing — Транслитерация Latin → русский (черновик для менеджера)
# ============================================================================

@router.post("/transliterate")
def transliterate(
    body: dict = Body(...),
    _user=Depends(require_manager),
) -> dict:
    """
    Транслитерирует латинское ФИО в русский черновик с учётом языка.
    """
    last_lat = (body.get("last_name_latin") or "").strip()
    first_lat = (body.get("first_name_latin") or "").strip()
    nationality = (body.get("nationality") or "").strip().upper() or None

    if not last_lat or not first_lat:
        raise HTTPException(400, "Both last_name_latin and first_name_latin are required")

    last_ru = transliterate_lat_to_ru(last_lat, nationality)
    first_ru = transliterate_lat_to_ru(first_lat, nationality)

    return {
        "last_name_native": last_ru,
        "first_name_native": first_ru,
        "warning": "Автоматический черновик транслитерации. Проверьте и поправьте если нужно.",
    }
