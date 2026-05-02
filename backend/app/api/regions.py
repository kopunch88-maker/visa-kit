"""
Pack 17.0: CRUD регионов РФ для системы автогенерации ИНН самозанятого.

Endpoints:
    GET    /api/admin/regions              — список всех регионов
    GET    /api/admin/regions/{id}         — один регион
    POST   /api/admin/regions              — создать
    PATCH  /api/admin/regions/{id}         — обновить
    DELETE /api/admin/regions/{id}         — удалить

Регионы используются:
- В UI «Сгенерировать ИНН» (Pack 17.3) — автовыбор по applicant.nationality
- В service.region_picker (Pack 17.2) — определение KLADR кода для запроса в rmsp-pp

Менеджер настраивает регионы через /admin/settings/regions:
- Добавляет новые регионы (KLADR код берётся с kladr-rf.ru)
- Маркирует «диаспоры» для каждой страны клиентов
- Деактивирует регионы которые временно не использовать (is_active=False)
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.region import Region, RegionCreate, RegionRead, RegionUpdate


router = APIRouter(prefix="/admin/regions", tags=["regions"])


@router.get("", response_model=List[RegionRead])
def list_regions(
    session: Session = Depends(get_session),
    is_active: Optional[bool] = Query(
        None, description="Фильтр по активности. None = все регионы"
    ),
    country: Optional[str] = Query(
        None,
        description="ISO-3 код страны. Если задан — фильтр по диаспоре. "
                    "Например ?country=TUR вернёт только регионы для турецкой диаспоры."
    ),
):
    """
    Список регионов. По умолчанию возвращает ВСЕ регионы (включая неактивные)
    для отображения в UI настроек.

    Для авто-pipeline (region_picker) используется ?is_active=true&country=...
    """
    statement = select(Region)

    if is_active is not None:
        statement = statement.where(Region.is_active == is_active)

    statement = statement.order_by(Region.name)
    regions = session.exec(statement).all()

    if country:
        # Фильтрация по JSON массиву на стороне Python (compatibility SQLite + PG)
        country_upper = country.upper()
        regions = [
            r for r in regions
            if r.diaspora_for_countries and country_upper in r.diaspora_for_countries
        ]

    return regions


@router.get("/{region_id}", response_model=RegionRead)
def get_region(region_id: int, session: Session = Depends(get_session)):
    region = session.get(Region, region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    return region


@router.post("", response_model=RegionRead, status_code=201)
def create_region(
    payload: RegionCreate,
    session: Session = Depends(get_session),
):
    """
    Создать новый регион. KLADR-код должен быть уникальным.

    Пример payload:
        {
          "kladr_code": "5000001500000",
          "region_code": "50",
          "name": "Подольск",
          "name_full": "Московская область, городской округ Подольск",
          "type": "city",
          "is_active": true,
          "diaspora_for_countries": ["TUR"]
        }
    """
    # Валидация KLADR
    if not payload.kladr_code or len(payload.kladr_code) != 13:
        raise HTTPException(
            status_code=422,
            detail="kladr_code должен быть строкой из 13 цифр"
        )
    if not payload.kladr_code.isdigit():
        raise HTTPException(
            status_code=422,
            detail="kladr_code должен содержать только цифры"
        )

    # Валидация region_code (первые 2 цифры KLADR)
    if not payload.region_code or len(payload.region_code) != 2:
        raise HTTPException(
            status_code=422,
            detail="region_code должен быть из 2 цифр"
        )

    # Проверка уникальности KLADR
    existing = session.exec(
        select(Region).where(Region.kladr_code == payload.kladr_code)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Регион с KLADR {payload.kladr_code} уже существует "
                   f"(id={existing.id}, name={existing.name})"
        )

    # Нормализация: коды стран в верхний регистр
    diaspora = [c.upper() for c in (payload.diaspora_for_countries or [])]

    region = Region(
        kladr_code=payload.kladr_code,
        region_code=payload.region_code,
        name=payload.name,
        name_full=payload.name_full,
        type=payload.type or "city",
        is_active=payload.is_active,
        diaspora_for_countries=diaspora,
        notes=payload.notes,
    )
    session.add(region)
    session.commit()
    session.refresh(region)
    return region


@router.patch("/{region_id}", response_model=RegionRead)
def update_region(
    region_id: int,
    payload: RegionUpdate,
    session: Session = Depends(get_session),
):
    region = session.get(Region, region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Валидация и нормализация
    if "kladr_code" in update_data:
        kladr = update_data["kladr_code"]
        if not kladr or len(kladr) != 13 or not kladr.isdigit():
            raise HTTPException(
                status_code=422,
                detail="kladr_code должен быть строкой из 13 цифр"
            )
        # Проверка уникальности при изменении
        if kladr != region.kladr_code:
            existing = session.exec(
                select(Region).where(Region.kladr_code == kladr)
            ).first()
            if existing and existing.id != region_id:
                raise HTTPException(
                    status_code=409,
                    detail=f"Регион с KLADR {kladr} уже существует"
                )

    if "region_code" in update_data:
        rc = update_data["region_code"]
        if not rc or len(rc) != 2:
            raise HTTPException(
                status_code=422,
                detail="region_code должен быть из 2 цифр"
            )

    if "diaspora_for_countries" in update_data:
        update_data["diaspora_for_countries"] = [
            c.upper() for c in (update_data["diaspora_for_countries"] or [])
        ]

    for key, value in update_data.items():
        setattr(region, key, value)

    session.add(region)
    session.commit()
    session.refresh(region)
    return region


@router.delete("/{region_id}", status_code=204)
def delete_region(region_id: int, session: Session = Depends(get_session)):
    """
    Удалить регион. ВНИМАНИЕ: если у applicants есть inn_kladr_code равный
    этому региону, это просто оставит «осиротевшую» ссылку — это OK,
    KLADR код самостоятельно валиден и без записи в region.

    Безопаснее: установить is_active=False через PATCH вместо удаления.
    """
    region = session.get(Region, region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    session.delete(region)
    session.commit()
    return None
