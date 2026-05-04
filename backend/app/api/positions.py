"""
Positions CRUD.

Pack 20.0 (04.05.2026): Position отвязан от Company. Position теперь
шаблон должности, переиспользуемый между разными компаниями. Связь
Company↔Position идёт через Application (application.company_id +
application.position_id, оба независимо).

Pack 20.1 (05.05.2026): _enrich теперь возвращает specialty_code и
specialty_name через JOIN на таблицу specialty — для группировки
в UI на странице /admin/settings (PositionsTab).

Изменения относительно Pack 20.0:
- Добавлены поля specialty_code и specialty_name в response через JOIN
- list_positions возвращает их в каждой записи без дополнительных запросов
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


def _enrich(position: Position, session: Session) -> dict:
    """Add computed fields: application_count + specialty_code + specialty_name.

    Pack 20.1: возвращает dict вместо PositionRead, чтобы можно было добавить
    денормализованные specialty поля без изменения SQLModel-схемы.
    """
    app_count = session.exec(
        select(func.count(Application.id)).where(Application.position_id == position.id)
    ).one()

    # Pack 20.1: подтянуть код и название специальности
    specialty_code = None
    specialty_name = None
    if position.primary_specialty_id is not None:
        # Импорт здесь чтобы избежать circular import на старте приложения
        from app.models import Specialty
        spec = session.get(Specialty, position.primary_specialty_id)
        if spec is not None:
            specialty_code = spec.code
            specialty_name = spec.name

    # Берём все поля Position через model_dump, потом добавляем computed
    data = position.model_dump()
    data["application_count"] = app_count
    data["specialty_code"] = specialty_code
    data["specialty_name"] = specialty_name
    return data


@router.get("")
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
) -> List[dict]:
    query = select(Position)
    if not include_inactive:
        query = query.where(Position.is_active == True)  # noqa: E712
    query = query.order_by(Position.title_ru)

    positions = session.exec(query).all()
    return [_enrich(p, session) for p in positions]


@router.get("/{position_id}")
def get_position(
    position_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    position = session.get(Position, position_id)
    if not position:
        raise HTTPException(404, "Position not found")
    return _enrich(position, session)


@router.post("", status_code=201)
def create_position(
    payload: PositionCreate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    """Pack 20.0: валидация компании удалена — Position больше не имеет company_id."""
    position = Position(**payload.model_dump())
    session.add(position)
    session.flush()
    session.refresh(position)
    return _enrich(position, session)


@router.patch("/{position_id}")
def update_position(
    position_id: int,
    payload: PositionUpdate,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
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
