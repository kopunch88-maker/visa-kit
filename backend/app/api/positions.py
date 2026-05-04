"""
Positions CRUD.

Pack 20.0 (04.05.2026): Position отвязан от Company. Position теперь
шаблон должности, переиспользуемый между разными компаниями. Связь
Company↔Position идёт через Application (application.company_id +
application.position_id, оба независимо).

Изменения относительно прежней версии:
- _enrich больше не подтягивает company_short_name (поля нет в PositionRead).
- list_positions: query-параметр company_id остался для обратной
  совместимости фронта, но игнорируется (фильтрация по компании теперь
  бессмысленна — позиция не привязана к одной компании). При следующем
  рефакторе фронта (Pack 20.1) параметр можно удалить.
- create_position: валидация компании удалена, PositionCreate больше не
  содержит company_id.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.models import (
    Position, PositionCreate, PositionUpdate, PositionRead,
    Application,
)
from .dependencies import require_manager

router = APIRouter(prefix="/admin/positions", tags=["positions"])


def _enrich(position: Position, session: Session) -> PositionRead:
    """Add computed field: application_count.

    Pack 20.0: company_short_name удалено — Position больше не привязан
    к одной компании.
    """
    app_count = session.exec(
        select(func.count(Application.id)).where(Application.position_id == position.id)
    ).one()

    return PositionRead(
        **position.model_dump(),
        application_count=app_count,
    )


@router.get("", response_model=List[PositionRead])
def list_positions(
    company_id: Optional[int] = Query(
        None,
        description="Pack 20.0: deprecated. Параметр сохранён для обратной "
                    "совместимости фронта, но игнорируется — Position больше "
                    "не привязан к компании.",
    ),
    include_inactive: bool = Query(False),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> List[PositionRead]:
    query = select(Position)
    # Pack 20.0: company_id в фильтре игнорируется (см. описание параметра).
    # Если в будущем понадобится «компании где использовалась эта позиция»
    # — JOIN через Application: WHERE Application.company_id = X
    # AND Application.position_id = Position.id.
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
    """Pack 20.0: валидация компании удалена — Position больше не имеет company_id."""
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
