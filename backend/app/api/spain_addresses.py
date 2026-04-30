"""
Spain Addresses CRUD — типовые адреса в Испании для подачи заявок.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.models import (
    SpainAddress, SpainAddressCreate, SpainAddressUpdate, SpainAddressRead,
    Application,
)
from .dependencies import require_manager

router = APIRouter(prefix="/admin/spain-addresses", tags=["spain-addresses"])


def _enrich(addr: SpainAddress, session: Session) -> SpainAddressRead:
    app_count = session.exec(
        select(func.count(Application.id)).where(Application.spain_address_id == addr.id)
    ).one()

    return SpainAddressRead(
        **addr.model_dump(),
        application_count=app_count,
    )


@router.get("", response_model=List[SpainAddressRead])
def list_addresses(
    include_inactive: bool = Query(False),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> List[SpainAddressRead]:
    query = select(SpainAddress)
    if not include_inactive:
        query = query.where(SpainAddress.is_active == True)  # noqa: E712
    query = query.order_by(SpainAddress.label)

    addresses = session.exec(query).all()
    return [_enrich(a, session) for a in addresses]


@router.get("/{addr_id}", response_model=SpainAddressRead)
def get_address(
    addr_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> SpainAddressRead:
    addr = session.get(SpainAddress, addr_id)
    if not addr:
        raise HTTPException(404, "Spain address not found")
    return _enrich(addr, session)


@router.post("", response_model=SpainAddressRead, status_code=201)
def create_address(
    payload: SpainAddressCreate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> SpainAddressRead:
    addr = SpainAddress(**payload.model_dump())
    session.add(addr)
    session.flush()
    session.refresh(addr)
    return _enrich(addr, session)


@router.patch("/{addr_id}", response_model=SpainAddressRead)
def update_address(
    addr_id: int,
    payload: SpainAddressUpdate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> SpainAddressRead:
    addr = session.get(SpainAddress, addr_id)
    if not addr:
        raise HTTPException(404, "Spain address not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(addr, key, value)

    session.add(addr)
    session.flush()
    session.refresh(addr)
    return _enrich(addr, session)


@router.delete("/{addr_id}", status_code=204)
def delete_address(
    addr_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> None:
    addr = session.get(SpainAddress, addr_id)
    if not addr:
        raise HTTPException(404, "Spain address not found")
    addr.is_active = False
    session.add(addr)
    session.flush()
    return None