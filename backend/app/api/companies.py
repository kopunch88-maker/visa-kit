"""
Companies CRUD — reference implementation for all directory entities.

Pattern: copy this file as-is for new directory entities (Position, Representative,
SpainAddress). Replace Company → YourEntity, /companies → /your-entities,
companies → your_entities.

Endpoints:
    GET    /api/admin/companies                    list
    GET    /api/admin/companies/{id}                detail
    POST   /api/admin/companies                    create
    PATCH  /api/admin/companies/{id}                update
    DELETE /api/admin/companies/{id}                soft-delete
    POST   /api/admin/companies/translit-suggest    Pack 15.1: GOST translit helper
"""

from datetime import date, timedelta
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.models import Company, CompanyCreate, CompanyUpdate, CompanyRead, Application
from app.services.transliteration import transliterate_name
from .dependencies import require_manager  # JWT + role check

router = APIRouter(prefix="/admin/companies", tags=["companies"])


# ============================================================================
# Helpers
# ============================================================================

def _enrich(company: Company, session: Session) -> CompanyRead:
    """
    Convert ORM model → API response with computed fields.

    Computed:
    - egryl_is_fresh: True if EGRYL extract is younger than 30 days
    - application_count: number of applications using this company
    """
    egryl_is_fresh = None
    if company.egryl_extract_date:
        age = (date.today() - company.egryl_extract_date).days
        egryl_is_fresh = age <= 30

    app_count = session.exec(
        select(func.count(Application.id)).where(Application.company_id == company.id)
    ).one()

    return CompanyRead(
        **company.model_dump(),
        egryl_is_fresh=egryl_is_fresh,
        application_count=app_count,
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=List[CompanyRead])
def list_companies(
    include_inactive: bool = Query(False),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> List[CompanyRead]:
    """List all companies. By default returns active only."""
    query = select(Company)
    if not include_inactive:
        query = query.where(Company.is_active == True)  # noqa: E712
    query = query.order_by(Company.short_name)

    companies = session.exec(query).all()
    return [_enrich(c, session) for c in companies]


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(
    company_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> CompanyRead:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    return _enrich(company, session)


@router.post("", response_model=CompanyRead, status_code=201)
def create_company(
    payload: CompanyCreate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> CompanyRead:
    """Create new company. Short_name must be unique."""
    existing = session.exec(
        select(Company).where(Company.short_name == payload.short_name)
    ).first()
    if existing:
        raise HTTPException(409, f"Company '{payload.short_name}' already exists")

    company = Company(**payload.model_dump())
    session.add(company)
    session.flush()
    session.refresh(company)
    return _enrich(company, session)


@router.patch("/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> CompanyRead:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(company, key, value)

    session.add(company)
    session.flush()
    session.refresh(company)
    return _enrich(company, session)


@router.delete("/{company_id}", status_code=204)
def delete_company(
    company_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> None:
    """Soft delete: set is_active=False."""
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    company.is_active = False
    session.add(company)
    session.flush()
    return None


# ============================================================================
# Pack 15.1 — translit-suggest helper
# ============================================================================

class TranslitSuggestRequest(BaseModel):
    text: str
    field: Literal["director_name", "company_name"] = "director_name"


class TranslitSuggestResponse(BaseModel):
    text: str
    suggestion: str


@router.post("/translit-suggest", response_model=TranslitSuggestResponse)
def translit_suggest(
    payload: TranslitSuggestRequest,
    _user=Depends(require_manager),
) -> TranslitSuggestResponse:
    """
    Pack 15.1: GOST 52535.1-2006 транслит для черновика латинского имени.

    Менеджер потом может подправить — это только starting point.

    Используется кнопками ✨ в CompanyContractDrawer для двух полей:
    - director_full_name_latin (из director_full_name_ru)
    - full_name_es (из full_name_ru, обычно просто транслит ядра)
    """
    suggestion = transliterate_name(payload.text)
    return TranslitSuggestResponse(text=payload.text, suggestion=suggestion)
