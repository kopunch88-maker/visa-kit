"""
Pack 16 — Banks CRUD + endpoint генерации уникального счёта.

Endpoints:
    GET    /api/admin/banks              list
    GET    /api/admin/banks/{id}         detail
    POST   /api/admin/banks              create
    PATCH  /api/admin/banks/{id}         update
    DELETE /api/admin/banks/{id}         soft-delete
    POST   /api/admin/banks/{id}/generate-account  выдать уникальный 20-значный счёт
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.models import Bank, BankCreate, BankUpdate, BankRead, Applicant
from app.services.account_generator import generate_unique_account

from .dependencies import require_manager

router = APIRouter(prefix="/admin/banks", tags=["banks"])


def _enrich(bank: Bank, session: Session) -> BankRead:
    count = session.exec(
        select(func.count(Applicant.id)).where(Applicant.bank_id == bank.id)
    ).one()
    return BankRead(**bank.model_dump(), applicant_count=count)


@router.get("", response_model=List[BankRead])
def list_banks(
    include_inactive: bool = Query(False),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> List[BankRead]:
    query = select(Bank)
    if not include_inactive:
        query = query.where(Bank.is_active == True)  # noqa: E712
    query = query.order_by(Bank.name)
    banks = session.exec(query).all()
    return [_enrich(b, session) for b in banks]


@router.get("/{bank_id}", response_model=BankRead)
def get_bank(
    bank_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> BankRead:
    bank = session.get(Bank, bank_id)
    if not bank:
        raise HTTPException(404, "Bank not found")
    return _enrich(bank, session)


@router.post("", response_model=BankRead, status_code=201)
def create_bank(
    payload: BankCreate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> BankRead:
    # Проверка БИК на уникальность
    existing = session.exec(
        select(Bank).where(Bank.bik == payload.bik)
    ).first()
    if existing:
        raise HTTPException(409, f"Bank with BIK {payload.bik} already exists")

    bank = Bank(**payload.model_dump())
    session.add(bank)
    session.flush()
    session.refresh(bank)
    return _enrich(bank, session)


@router.patch("/{bank_id}", response_model=BankRead)
def update_bank(
    bank_id: int,
    payload: BankUpdate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> BankRead:
    bank = session.get(Bank, bank_id)
    if not bank:
        raise HTTPException(404, "Bank not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(bank, key, value)

    session.add(bank)
    session.flush()
    session.refresh(bank)
    return _enrich(bank, session)


@router.delete("/{bank_id}", status_code=204)
def delete_bank(
    bank_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> None:
    bank = session.get(Bank, bank_id)
    if not bank:
        raise HTTPException(404, "Bank not found")
    bank.is_active = False
    session.add(bank)
    session.flush()
    return None


# ============================================================================
# Generate unique account number (CBR 579-P algorithm)
# ============================================================================

class GenerateAccountRequest(BaseModel):
    is_resident: bool = True
    """True = резидент РФ (40817), False = нерезидент (40820)"""


class GenerateAccountResponse(BaseModel):
    account: str
    bik: str
    bank_name: str


@router.post("/{bank_id}/generate-account", response_model=GenerateAccountResponse)
def generate_account_endpoint(
    bank_id: int,
    payload: GenerateAccountRequest,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> GenerateAccountResponse:
    """
    Pack 16: генерирует уникальный валидный 20-значный расчётный счёт
    физлица для указанного банка.

    Алгоритм ЦБ РФ № 579-П (контрольный разряд по БИК).
    Проверка уникальности — по таблице applicant.bank_account.
    """
    bank = session.get(Bank, bank_id)
    if not bank:
        raise HTTPException(404, "Bank not found")

    if len(bank.bik) != 9 or not bank.bik.isdigit():
        raise HTTPException(
            400,
            f"Bank BIK is invalid: {bank.bik!r} (must be 9 digits). Edit the bank first.",
        )

    try:
        account = generate_unique_account(
            session=session,
            bik=bank.bik,
            is_resident=payload.is_resident,
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    return GenerateAccountResponse(
        account=account,
        bik=bank.bik,
        bank_name=bank.name,
    )
