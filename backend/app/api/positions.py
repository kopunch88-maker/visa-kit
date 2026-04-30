"""
Positions CRUD — типовые должности в наших компаниях.
Каждая должность привязана к одной Company.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.models import (
    Position, PositionCreate, PositionUpdate, PositionRead,
    Company, Application,
)
from .dependencies import require_manager

router = APIRouter(prefix="/admin/positions", tags=["positions"])


def _enrich(position: Position, session: Session) -> PositionRead:
    """Add computed fields: application_count and company_short_name."""
    app_count = session.exec(
        select(func.count(Application.id)).where(Application.position_id == position.id)
    ).one()

    # Pull company short name in one tiny query (or use the relationship if loaded)
    company_short = session.exec(
        select(Company.short_name).where(Company.id == position.company_id)
    ).first()

    return PositionRead(
        **position.model_dump(),
        application_count=app_count,
        company_short_name=company_short,
    )


@router.get("", response_model=List[PositionRead])
def list_positions(
    company_id: int | None = Query(None, description="Filter by company"),
    include_inactive: bool = Query(False),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> List[PositionRead]:
    query = select(Position)
    if company_id is not None:
        query = query.where(Position.company_id == company_id)
    if not include_inactive:
        query = query.where(Position.is_active == True)  # noqa: E712
    query = query.order_by(Position.title_ru)

    positions = session.exec(query).all()
    return [_enrich(p, session) for p in positions]


@router.get("/{position_id}", response_model=PositionRead)
def get_position(
    position_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> PositionRead:
    position = session.get(Position, position_id)
    if not position:
        raise HTTPException(404, "Position not found")
    return _enrich(position, session)


@router.post("", response_model=PositionRead, status_code=201)
def create_position(
    payload: PositionCreate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> PositionRead:
    # Validate company exists and is active
    company = session.get(Company, payload.company_id)
    if not company:
        raise HTTPException(422, f"Company id={payload.company_id} not found")
    if not company.is_active:
        raise HTTPException(422, f"Company '{company.short_name}' is inactive")

    position = Position(**payload.model_dump())
    session.add(position)
    session.flush()
    session.refresh(position)
    return _enrich(position, session)


@router.patch("/{position_id}", response_model=PositionRead)
def update_position(
    position_id: int,
    payload: PositionUpdate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> PositionRead:
    position = session.get(Position, position_id)
    if not position:
        raise HTTPException(404, "Position not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(position, key, value)

    session.add(position)
    session.flush()
    session.refresh(position)
    return _enrich(position, session)


@router.delete("/{position_id}", status_code=204)
def delete_position(
    position_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> None:
    position = session.get(Position, position_id)
    if not position:
        raise HTTPException(404, "Position not found")
    position.is_active = False
    session.add(position)
    session.flush()
    return None