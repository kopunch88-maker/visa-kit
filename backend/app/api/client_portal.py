"""
Client portal — эндпоинты для самого клиента.

Авторизация — по токену в URL.

Ключевые особенности (Pack 7.5+):
- session.commit() для надёжного сохранения данных
- Возврат dict (не ApplicantRead) чтобы не валидировать None-поля
  во время постепенного заполнения wizard'а
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import (
    Application, ApplicationStatus,
    Applicant, ApplicantUpdate,
)

router = APIRouter(prefix="/client", tags=["client-portal"])


# ============================================================================
# Helpers
# ============================================================================

def _get_application_by_token(token: str, session: Session) -> Application:
    application = session.exec(
        select(Application).where(Application.client_access_token == token)
    ).first()
    if not application:
        raise HTTPException(404, "Invalid or expired token")
    return application


def _enrich_applicant(applicant: Applicant) -> dict:
    """Возвращает данные клиента в виде dict (без валидации через ApplicantRead)."""
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
    return data


def _enrich_application(application: Application) -> dict:
    """Возвращает данные заявки в виде dict (без валидации через ApplicationRead)."""
    data = application.model_dump(exclude={
        "family_members", "uploaded_files",
        "generated_documents", "previous_residences",
    })
    data["has_family"] = False
    data["family_size"] = 0
    data["business_rule_problems"] = application.validate_business_rules()
    return data


# ============================================================================
# Profile (Applicant)
# ============================================================================

@router.get("/{token}/me")
def get_my_profile(
    token: str,
    session: Session = Depends(get_session),
):
    """Клиент получает свой профиль (или null если не создан)."""
    application = _get_application_by_token(token, session)
    if not application.applicant_id:
        return None

    applicant = session.get(Applicant, application.applicant_id)
    if not applicant:
        return None
    return _enrich_applicant(applicant)


@router.patch("/{token}/me")
def update_my_profile(
    token: str,
    payload: ApplicantUpdate,
    session: Session = Depends(get_session),
):
    """Клиент сохраняет/обновляет свой профиль."""
    application = _get_application_by_token(token, session)

    update_data = payload.model_dump(exclude_unset=True)

    if "education" in update_data and update_data["education"] is not None:
        update_data["education"] = [
            e.model_dump() if hasattr(e, "model_dump") else e
            for e in update_data["education"]
        ]
    if "work_history" in update_data and update_data["work_history"] is not None:
        update_data["work_history"] = [
            w.model_dump() if hasattr(w, "model_dump") else w
            for w in update_data["work_history"]
        ]

    if not application.applicant_id:
        try:
            applicant = Applicant(**update_data)
        except Exception as e:
            raise HTTPException(
                422,
                detail={
                    "message": "Cannot create profile",
                    "error": str(e),
                },
            )
        session.add(applicant)
        session.flush()
        session.refresh(applicant)
        application.applicant_id = applicant.id
        session.add(application)
    else:
        applicant = session.get(Applicant, application.applicant_id)
        if not applicant:
            raise HTTPException(500, "Applicant linked but not found in DB")
        for key, value in update_data.items():
            setattr(applicant, key, value)
        session.add(applicant)

    # Авто-переход AWAITING_DATA → READY_TO_ASSIGN
    if (application.status == ApplicationStatus.AWAITING_DATA
            and applicant.last_name_native
            and applicant.first_name_native
            and applicant.passport_number):
        application.status = ApplicationStatus.READY_TO_ASSIGN
        session.add(application)

    session.commit()
    session.refresh(applicant)

    return _enrich_applicant(applicant)


# ============================================================================
# Application status
# ============================================================================

@router.get("/{token}/application")
def get_my_application(
    token: str,
    session: Session = Depends(get_session),
):
    """Клиент видит статус своей заявки."""
    application = _get_application_by_token(token, session)
    return _enrich_application(application)