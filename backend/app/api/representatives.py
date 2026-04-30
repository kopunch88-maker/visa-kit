"""
Representatives CRUD — наши представители в Испании.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.models import (
    Representative, RepresentativeCreate, RepresentativeUpdate, RepresentativeRead,
    Application,
)
from .dependencies import require_manager

router = APIRouter(prefix="/admin/representatives", tags=["representatives"])


def _enrich(rep: Representative, session: Session) -> RepresentativeRead:
    app_count = session.exec(
        select(func.count(Application.id)).where(Application.representative_id == rep.id)
    ).one()

    return RepresentativeRead(
        **rep.model_dump(),
        application_count=app_count,
        full_name=f"{rep.first_name} {rep.last_name}",
    )


@router.get("", response_model=List[RepresentativeRead])
def list_representatives(
    include_inactive: bool = Query(False),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> List[RepresentativeRead]:
    query = select(Representative)
    if not include_inactive:
        query = query.where(Representative.is_active == True)  # noqa: E712
    query = query.order_by(Representative.last_name)

    reps = session.exec(query).all()
    return [_enrich(r, session) for r in reps]


@router.get("/{rep_id}", response_model=RepresentativeRead)
def get_representative(
    rep_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> RepresentativeRead:
    rep = session.get(Representative, rep_id)
    if not rep:
        raise HTTPException(404, "Representative not found")
    return _enrich(rep, session)


@router.post("", response_model=RepresentativeRead, status_code=201)
def create_representative(
    payload: RepresentativeCreate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> RepresentativeRead:
    # Optional: check NIE uniqueness
    existing = session.exec(
        select(Representative).where(Representative.nie == payload.nie)
    ).first()
    if existing:
        raise HTTPException(409, f"Representative with NIE '{payload.nie}' already exists")

    rep = Representative(**payload.model_dump())
    session.add(rep)
    session.flush()
    session.refresh(rep)
    return _enrich(rep, session)


@router.patch("/{rep_id}", response_model=RepresentativeRead)
def update_representative(
    rep_id: int,
    payload: RepresentativeUpdate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> RepresentativeRead:
    rep = session.get(Representative, rep_id)
    if not rep:
        raise HTTPException(404, "Representative not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rep, key, value)

    session.add(rep)
    session.flush()
    session.refresh(rep)
    return _enrich(rep, session)


@router.delete("/{rep_id}", status_code=204)
def delete_representative(
    rep_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> None:
    rep = session.get(Representative, rep_id)
    if not rep:
        raise HTTPException(404, "Representative not found")
    rep.is_active = False
    session.add(rep)
    session.flush()
    return None