"""
Applicants admin endpoints — для админки чтобы получать данные клиента.

Pack 8: эндпоинты возвращают dict (без валидации Pydantic), как в client_portal.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.session import get_session
from app.models import Applicant
from .dependencies import require_manager

router = APIRouter(prefix="/admin/applicants", tags=["applicants"])


def _enrich(applicant: Applicant) -> dict:
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


@router.get("/{applicant_id}")
def get_applicant(
    applicant_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(404, "Applicant not found")
    return _enrich(applicant)
