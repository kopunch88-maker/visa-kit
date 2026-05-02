"""
Pack 17.1 — диагностические endpoints для тестирования сервисов автогенерации ИНН.

Эти endpoints НЕ предназначены для production использования. Они нужны только
менеджеру/разработчику чтобы быстро проверить что:
- rmsp-pp.nalog.ru отвечает
- npd.nalog.ru отвечает
- Адрес-генератор работает

В Pack 17.2 будут production endpoints `/inn-suggest` и `/inn-accept` которые
используют эти же сервисы но через pipeline orchestrator.

Все endpoints под /api/admin/inn-debug/* требуют авторизации менеджера.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app.api.dependencies import require_manager
from app.services.inn_generator import (
    RmspClient,
    RmspError,
    NpdStatusChecker,
    NpdStatusError,
    generate_address,
    KNOWN_REGIONS,
)


log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/inn-debug",
    tags=["inn-debug"],
)


# === Модели ответов ===

class RmspCandidateOut(BaseModel):
    inn: str
    full_name: str
    nptype: str
    category: int
    region_code: str
    ogrn: Optional[str] = None
    is_self_employed: bool


class RmspSearchResponse(BaseModel):
    kladr_code: str
    page: int
    page_size: int
    candidates: list[RmspCandidateOut]
    count: int
    note: str


class NpdCheckResponse(BaseModel):
    inn: str
    is_active: bool
    request_date: str
    registration_date: Optional[str] = None
    full_name: Optional[str] = None
    message: Optional[str] = None
    raw: Optional[dict] = None


class GeneratedAddressOut(BaseModel):
    full: str
    postal_code: str
    region_name: str
    city_name: str
    street: str
    house: str
    apartment: str
    kladr_code: str


# === Endpoints ===

@router.get(
    "/rmsp-search",
    response_model=RmspSearchResponse,
    summary="Тест поиска самозанятых в реестре rmsp-pp.nalog.ru",
)
async def test_rmsp_search(
    kladr_code: str = Query(
        ...,
        description="13-значный KLADR код региона. Например 2300000700000 для Сочи.",
    ),
    page: int = Query(1, ge=1, description="Номер страницы (1-based)"),
    page_size: int = Query(
        20,
        description="Размер страницы (10/20/50/100)",
    ),
    _user=Depends(require_manager),
):
    """
    Делает запрос к rmsp-pp.nalog.ru и возвращает список самозанятых
    отфильтрованных по KLADR региона.

    Используется для диагностики что:
    1. Налоговая отвечает с прода Railway
    2. Структура ответа не изменилась
    3. Данные приходят и парсятся

    Если возвращает пустой список — проверь kladr_code (должен быть из реестра
    `Region` с правильным форматом).
    """
    if page_size not in (10, 20, 50, 100):
        raise HTTPException(
            status_code=422,
            detail=f"page_size must be 10/20/50/100, got {page_size}",
        )

    try:
        async with RmspClient() as client:
            candidates = await client.search_self_employed(
                kladr_code=kladr_code,
                page=page,
                page_size=page_size,
            )
    except RmspError as e:
        log.error(f"[inn-debug] RMSP error: {e}")
        raise HTTPException(status_code=502, detail=f"RMSP error: {e}")
    except Exception as e:
        log.exception(f"[inn-debug] Unexpected RMSP error")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    return RmspSearchResponse(
        kladr_code=kladr_code,
        page=page,
        page_size=page_size,
        candidates=[
            RmspCandidateOut(
                inn=c.inn,
                full_name=c.full_name,
                nptype=c.nptype,
                category=c.category,
                region_code=c.region_code,
                ogrn=c.ogrn,
                is_self_employed=c.is_self_employed,
            )
            for c in candidates
        ],
        count=len(candidates),
        note=(
            "Если list пустой — налоговая фильтрует по сессии после initial GET. "
            "Это нормально для первого запроса с новым cookie."
        ),
    )


@router.get(
    "/npd-check",
    response_model=NpdCheckResponse,
    summary="Тест проверки статуса самозанятого через npd.nalog.ru",
)
async def test_npd_check(
    inn: str = Query(..., description="12-значный ИНН физлица"),
    _user=Depends(require_manager),
):
    """
    Проверяет статус НПД через ФНС API.

    ВНИМАНИЕ: ФНС лимитирует 2 запроса/минуту с одного IP.
    Если делать чаще — клиент будет ждать (видно в логах Railway).
    """
    if not inn or len(inn) != 12 or not inn.isdigit():
        raise HTTPException(
            status_code=422,
            detail="ИНН должен быть из 12 цифр (физлицо)",
        )

    try:
        async with NpdStatusChecker() as checker:
            result = await checker.check(inn=inn)
    except NpdStatusError as e:
        log.error(f"[inn-debug] NPD error: {e}")
        raise HTTPException(status_code=502, detail=f"NPD error: {e}")
    except Exception as e:
        log.exception(f"[inn-debug] Unexpected NPD error")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    return NpdCheckResponse(
        inn=result.inn,
        is_active=result.is_active,
        request_date=result.request_date.isoformat(),
        registration_date=(
            result.registration_date.isoformat()
            if result.registration_date
            else None
        ),
        full_name=result.full_name or None,
        message=result.message,
        raw=result.raw,
    )


@router.get(
    "/generate-address",
    response_model=GeneratedAddressOut,
    summary="Тест генератора адресов",
)
def test_generate_address(
    kladr_code: str = Query(
        ...,
        description="13-значный KLADR код региона из KNOWN_REGIONS",
    ),
    _user=Depends(require_manager),
):
    """
    Генерирует случайный адрес для региона.

    Поддерживаемые регионы: 10 базовых (Москва, СПб, Сочи, Краснодар,
    Ростов-на-Дону, Махачкала, Грозный, Казань, Уфа, Нижний Новгород).

    Если KLADR региона не поддержан — возвращает 422 со списком известных регионов.
    """
    if kladr_code not in KNOWN_REGIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"Region with kladr_code={kladr_code} not supported",
                "supported_regions": [
                    {"kladr_code": k, "city": v.city_short}
                    for k, v in sorted(KNOWN_REGIONS.items())
                ],
            },
        )

    addr = generate_address(kladr_code)

    return GeneratedAddressOut(
        full=addr.full,
        postal_code=addr.postal_code,
        region_name=addr.region_name,
        city_name=addr.city_name,
        street=addr.street,
        house=addr.house,
        apartment=addr.apartment,
        kladr_code=addr.kladr_code,
    )


@router.get(
    "/known-regions",
    summary="Список регионов поддерживаемых address-generator'ом",
)
def list_supported_regions(_user=Depends(require_manager)):
    """
    Возвращает 10 регионов для которых есть захардкоженная база улиц.
    """
    return [
        {
            "kladr_code": k,
            "region_full_name": v.region_full_name,
            "city_short": v.city_short,
            "street_count": len(v.streets),
            "postal_code_count": len(v.postal_codes),
        }
        for k, v in sorted(KNOWN_REGIONS.items())
    ]
