"""
Pack 17.1.1 — диагностические endpoints для тестирования сервисов автогенерации ИНН.

Изменения от 17.1:
- В RmspCandidateOut добавлены dt_*  поля и estimated_npd_start
- Добавлен query параметр strict_region для теста с/без фильтра по региону
- Добавлен endpoint /rmsp-multipage для тестирования агрегации страниц
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


class RmspCandidateOut(BaseModel):
    inn: str
    full_name: str
    nptype: str
    category: int
    region_code: str
    ogrn: Optional[str] = None
    is_self_employed: bool
    # Pack 17.1.1
    dt_create: Optional[str] = None
    dt_support_begin: Optional[str] = None
    dt_support_period: Optional[str] = None
    estimated_npd_start: Optional[str] = None


class RmspSearchResponse(BaseModel):
    kladr_code: str
    page: int
    page_size: int
    strict_region_filter: bool
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


@router.get(
    "/rmsp-search",
    response_model=RmspSearchResponse,
    summary="Тест поиска самозанятых в реестре rmsp-pp.nalog.ru",
)
async def test_rmsp_search(
    kladr_code: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20),
    strict_region: bool = Query(
        True,
        description="Если True — пост-фильтр по region_code (первые 2 цифры KLADR). "
                    "Если False — возвращаем что отдаёт ФНС как есть.",
    ),
    _user=Depends(require_manager),
):
    """
    Делает запрос к rmsp-pp.nalog.ru и возвращает список самозанятых.

    Pack 17.1.1: kladr теперь передаётся И в URL И в body.
    Пост-фильтр по region_code (опционально через strict_region=false).
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
                strict_region_filter=strict_region,
            )
    except RmspError as e:
        log.error(f"[inn-debug] RMSP error: {e}")
        raise HTTPException(status_code=502, detail=f"RMSP error: {e}")
    except Exception as e:
        log.exception("[inn-debug] Unexpected RMSP error")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    return RmspSearchResponse(
        kladr_code=kladr_code,
        page=page,
        page_size=page_size,
        strict_region_filter=strict_region,
        candidates=[
            RmspCandidateOut(
                inn=c.inn,
                full_name=c.full_name,
                nptype=c.nptype,
                category=c.category,
                region_code=c.region_code,
                ogrn=c.ogrn,
                is_self_employed=c.is_self_employed,
                dt_create=c.dt_create,
                dt_support_begin=c.dt_support_begin,
                dt_support_period=c.dt_support_period,
                estimated_npd_start=c.estimated_npd_start,
            )
            for c in candidates
        ],
        count=len(candidates),
        note=(
            f"Region filter: {'STRICT (по первым 2 цифрам KLADR)' if strict_region else 'OFF'}. "
            f"Если count=0 при strict=true — попробуй strict_region=false "
            f"чтобы увидеть что налоговая возвращает без фильтрации."
        ),
    )


@router.get(
    "/rmsp-multipage",
    response_model=RmspSearchResponse,
    summary="Сбор кандидатов с нескольких страниц (агрегация)",
)
async def test_rmsp_multipage(
    kladr_code: str = Query(...),
    max_candidates: int = Query(50, ge=1, le=200),
    max_pages: int = Query(5, ge=1, le=10),
    strict_region: bool = Query(True),
    _user=Depends(require_manager),
):
    """
    Pack 17.1.1: пробивает несколько страниц подряд пока не наберём
    max_candidates самозанятых ИЗ НУЖНОГО РЕГИОНА.

    Полезно когда ФНС не применяет фильтр и нужно агрегировать.
    """
    try:
        async with RmspClient() as client:
            candidates = await client.search_multiple_pages(
                kladr_code=kladr_code,
                max_candidates=max_candidates,
                page_size=100,
                max_pages=max_pages,
                strict_region_filter=strict_region,
            )
    except RmspError as e:
        log.error(f"[inn-debug] RMSP error: {e}")
        raise HTTPException(status_code=502, detail=f"RMSP error: {e}")
    except Exception as e:
        log.exception("[inn-debug] Unexpected RMSP error")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    return RmspSearchResponse(
        kladr_code=kladr_code,
        page=0,  # multipage не имеет одной страницы
        page_size=100,
        strict_region_filter=strict_region,
        candidates=[
            RmspCandidateOut(
                inn=c.inn,
                full_name=c.full_name,
                nptype=c.nptype,
                category=c.category,
                region_code=c.region_code,
                ogrn=c.ogrn,
                is_self_employed=c.is_self_employed,
                dt_create=c.dt_create,
                dt_support_begin=c.dt_support_begin,
                dt_support_period=c.dt_support_period,
                estimated_npd_start=c.estimated_npd_start,
            )
            for c in candidates
        ],
        count=len(candidates),
        note=f"Multipage aggregation: max {max_pages} страниц по 100 записей.",
    )


@router.get(
    "/npd-check",
    response_model=NpdCheckResponse,
    summary="Тест проверки статуса самозанятого через npd.nalog.ru",
)
async def test_npd_check(
    inn: str = Query(...),
    _user=Depends(require_manager),
):
    """
    Проверка статуса НПД через ФНС API.
    Лимит 2 запроса/мин с одного IP — клиент ждёт автоматически.
    """
    if not inn or len(inn) != 12 or not inn.isdigit():
        raise HTTPException(
            status_code=422, detail="ИНН должен быть из 12 цифр (физлицо)",
        )

    try:
        async with NpdStatusChecker() as checker:
            result = await checker.check(inn=inn)
    except NpdStatusError as e:
        log.error(f"[inn-debug] NPD error: {e}")
        raise HTTPException(status_code=502, detail=f"NPD error: {e}")
    except Exception as e:
        log.exception("[inn-debug] Unexpected NPD error")
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
)
def test_generate_address(
    kladr_code: str = Query(...),
    _user=Depends(require_manager),
):
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


@router.get("/known-regions")
def list_supported_regions(_user=Depends(require_manager)):
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
