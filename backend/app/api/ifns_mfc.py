"""
Pack 18.0 — CRUD endpoints для справочников ИФНС и МФЦ.

Используется в админке для просмотра/правки справочников.
В будущем (Pack 18.4) при ручном добавлении кандидата из необычного региона
менеджер сможет добавить новую ИФНС/МФЦ через UI.

Сейчас минимальный CRUD: GET (list), GET (one), POST (create), PATCH (update),
DELETE (soft — is_active=FALSE).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.ifns_mfc import IfnsOffice, MfcOffice
from app.security import get_current_admin_user  # adjust import to actual path

router = APIRouter(prefix="/api/admin", tags=["ifns-mfc"])


# ============================================================================
# IFNS schemas
# ============================================================================

class IfnsOut(BaseModel):
    id: int
    code: str
    region_code: int
    full_name: str
    short_name: str
    address: Optional[str] = None
    is_default: bool
    is_active: bool

    class Config:
        from_attributes = True


class IfnsCreate(BaseModel):
    code: str = Field(min_length=4, max_length=4)
    region_code: int
    full_name: str
    short_name: str
    address: Optional[str] = None
    is_default: bool = False
    is_active: bool = True


class IfnsPatch(BaseModel):
    full_name: Optional[str] = None
    short_name: Optional[str] = None
    address: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


# ============================================================================
# MFC schemas
# ============================================================================

class MfcOut(BaseModel):
    id: int
    region_code: int
    city: str
    name: str
    address: str
    staff_names: list[str]
    is_active: bool

    class Config:
        from_attributes = True


class MfcCreate(BaseModel):
    region_code: int
    city: str
    name: str
    address: str
    staff_names: list[str] = Field(default_factory=list)
    is_active: bool = True


class MfcPatch(BaseModel):
    city: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    staff_names: Optional[list[str]] = None
    is_active: Optional[bool] = None


# ============================================================================
# IFNS endpoints
# ============================================================================

@router.get("/ifns", response_model=list[IfnsOut])
def list_ifns(
    region_code: Optional[int] = Query(None, description="Filter by subject code"),
    only_active: bool = Query(True),
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    q = select(IfnsOffice).order_by(IfnsOffice.region_code, IfnsOffice.code)
    if region_code is not None:
        q = q.where(IfnsOffice.region_code == region_code)
    if only_active:
        q = q.where(IfnsOffice.is_active == True)  # noqa: E712
    return s.exec(q).all()


@router.get("/ifns/{ifns_id}", response_model=IfnsOut)
def get_ifns(
    ifns_id: int,
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    obj = s.get(IfnsOffice, ifns_id)
    if not obj:
        raise HTTPException(404, "IFNS not found")
    return obj


@router.post("/ifns", response_model=IfnsOut, status_code=201)
def create_ifns(
    body: IfnsCreate,
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    if body.is_default:
        # Снимаем is_default с других в том же регионе
        existing = s.exec(
            select(IfnsOffice).where(
                IfnsOffice.region_code == body.region_code,
                IfnsOffice.is_default == True,  # noqa: E712
            )
        ).all()
        for e in existing:
            e.is_default = False
            s.add(e)

    obj = IfnsOffice(**body.model_dump())
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


@router.patch("/ifns/{ifns_id}", response_model=IfnsOut)
def patch_ifns(
    ifns_id: int,
    body: IfnsPatch,
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    obj = s.get(IfnsOffice, ifns_id)
    if not obj:
        raise HTTPException(404, "IFNS not found")

    # Если включаем is_default — снимаем с других в том же регионе
    if body.is_default is True and not obj.is_default:
        others = s.exec(
            select(IfnsOffice).where(
                IfnsOffice.region_code == obj.region_code,
                IfnsOffice.is_default == True,  # noqa: E712
                IfnsOffice.id != obj.id,
            )
        ).all()
        for o in others:
            o.is_default = False
            s.add(o)

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    obj.updated_at = datetime.utcnow()
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


@router.delete("/ifns/{ifns_id}", status_code=204)
def delete_ifns(
    ifns_id: int,
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    obj = s.get(IfnsOffice, ifns_id)
    if not obj:
        raise HTTPException(404, "IFNS not found")
    # Soft delete
    obj.is_active = False
    obj.updated_at = datetime.utcnow()
    s.add(obj)
    s.commit()
    return None


# ============================================================================
# MFC endpoints
# ============================================================================

@router.get("/mfc", response_model=list[MfcOut])
def list_mfc(
    region_code: Optional[int] = Query(None),
    only_active: bool = Query(True),
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    q = select(MfcOffice).order_by(MfcOffice.region_code, MfcOffice.city, MfcOffice.name)
    if region_code is not None:
        q = q.where(MfcOffice.region_code == region_code)
    if only_active:
        q = q.where(MfcOffice.is_active == True)  # noqa: E712
    return s.exec(q).all()


@router.get("/mfc/{mfc_id}", response_model=MfcOut)
def get_mfc(
    mfc_id: int,
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    obj = s.get(MfcOffice, mfc_id)
    if not obj:
        raise HTTPException(404, "MFC not found")
    return obj


@router.post("/mfc", response_model=MfcOut, status_code=201)
def create_mfc(
    body: MfcCreate,
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    obj = MfcOffice(**body.model_dump())
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


@router.patch("/mfc/{mfc_id}", response_model=MfcOut)
def patch_mfc(
    mfc_id: int,
    body: MfcPatch,
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    obj = s.get(MfcOffice, mfc_id)
    if not obj:
        raise HTTPException(404, "MFC not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    obj.updated_at = datetime.utcnow()
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


@router.delete("/mfc/{mfc_id}", status_code=204)
def delete_mfc(
    mfc_id: int,
    s: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    obj = s.get(MfcOffice, mfc_id)
    if not obj:
        raise HTTPException(404, "MFC not found")
    obj.is_active = False
    obj.updated_at = datetime.utcnow()
    s.add(obj)
    s.commit()
    return None
