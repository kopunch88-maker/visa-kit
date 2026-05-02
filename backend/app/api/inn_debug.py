"""
Pack 17.1.3 — диагностические endpoints с УЛУЧШЕННЫМ логированием ошибок.

Назначение: понять почему RMSP и NPD endpoints перестали отвечать.
Гипотезы:
- ФНС забанила Railway IP за частые запросы
- Временный сбой ФНС
- Сетевая проблема Railway

Этот файл добавляет:
1. /admin/inn-debug/connectivity-check — простой ping к nalog.ru хостам
   Показывает: статус, заголовки ответа, точную ошибку
2. /admin/inn-debug/rmsp-search — с детальным логированием ошибок
3. /admin/inn-debug/npd-check — с детальным логированием ошибок
4. Прежние endpoints оставлены для совместимости

Использование:
1. Сначала вызвать /connectivity-check — увидеть может ли Railway достучаться
2. Если nalog.ru отвечает — анализировать каждый endpoint отдельно
3. Если nalog.ru НЕ отвечает — Railway IP забанен, нужно ждать или менять подход
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

import httpx
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


# ============================================================================
# CONNECTIVITY CHECK — для определения причины проблем
# ============================================================================

@router.get(
    "/connectivity-check",
    summary="Проверка доступности хостов nalog.ru с Railway",
)
async def connectivity_check(_user=Depends(require_manager)):
    """
    Делает простые GET-запросы на главные страницы nalog.ru хостов.
    Показывает доступен ли каждый хост и какие ответы приходят.

    Это ПЕРВЫЙ тест который надо делать когда что-то идёт не так — он покажет
    проблема ли в сети или в коде клиента.
    """
    targets = [
        ("rmsp-pp.nalog.ru main", "https://rmsp-pp.nalog.ru/"),
        ("rmsp-pp.nalog.ru search.html", "https://rmsp-pp.nalog.ru/search.html?sk=SZ&kladr=2300000700000"),
        ("statusnpd.nalog.ru main", "https://statusnpd.nalog.ru/"),
        ("npd.nalog.ru main", "https://npd.nalog.ru/"),
        ("nalog.ru main", "https://www.nalog.ru/"),
        ("google.com (control)", "https://www.google.com/"),
    ]

    results = []
    timeout = httpx.Timeout(15.0, connect=10.0)
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": user_agent},
    ) as client:
        for name, url in targets:
            try:
                response = await client.get(url)
                results.append({
                    "name": name,
                    "url": url,
                    "ok": True,
                    "status_code": response.status_code,
                    "headers_sample": {
                        k: v for k, v in list(response.headers.items())[:8]
                    },
                    "body_size_bytes": len(response.content),
                    "body_preview": response.text[:200] if response.text else None,
                })
            except httpx.TimeoutException as e:
                results.append({
                    "name": name,
                    "url": url,
                    "ok": False,
                    "error_type": "TimeoutException",
                    "error_message": str(e),
                })
            except httpx.ConnectError as e:
                results.append({
                    "name": name,
                    "url": url,
                    "ok": False,
                    "error_type": "ConnectError",
                    "error_message": str(e) or "(empty — возможно RST или DNS)",
                })
            except httpx.HTTPError as e:
                results.append({
                    "name": name,
                    "url": url,
                    "ok": False,
                    "error_type": e.__class__.__name__,
                    "error_message": str(e) or "(empty)",
                })
            except Exception as e:
                results.append({
                    "name": name,
                    "url": url,
                    "ok": False,
                    "error_type": e.__class__.__name__,
                    "error_message": str(e) or "(empty)",
                    "traceback": traceback.format_exc()[-500:],
                })

    return {
        "results": results,
        "interpretation": (
            "Если nalog.ru хосты отвечают (status 2xx или 3xx) — сеть в порядке, "
            "проблема в коде клиента. "
            "Если ConnectError/Timeout на nalog.ru но Google работает — Railway IP "
            "забанен на ФНС (или nalog.ru банит датацентры/ботов). "
            "Если ВСЕ хосты падают — проблема с сетью Railway."
        ),
    }


# ============================================================================
# RMSP SEARCH — с детальным error reporting
# ============================================================================

class RmspCandidateOut(BaseModel):
    inn: str
    full_name: str
    nptype: str
    category: int
    region_code: str
    ogrn: Optional[str] = None
    is_self_employed: bool
    dt_create: Optional[str] = None
    dt_support_begin: Optional[str] = None
    dt_support_period: Optional[str] = None
    estimated_npd_start: Optional[str] = None


@router.get("/rmsp-search", summary="Тест поиска самозанятых")
async def test_rmsp_search(
    kladr_code: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20),
    strict_region: bool = Query(True),
    _user=Depends(require_manager),
):
    """
    С детальным error reporting в ответе.
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
        log.exception("[inn-debug] RMSP error")
        return {
            "ok": False,
            "error_type": "RmspError",
            "error_message": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1500:],
        }
    except Exception as e:
        log.exception("[inn-debug] Unexpected RMSP error")
        return {
            "ok": False,
            "error_type": e.__class__.__name__,
            "error_message": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1500:],
        }

    return {
        "ok": True,
        "kladr_code": kladr_code,
        "page": page,
        "page_size": page_size,
        "strict_region_filter": strict_region,
        "count": len(candidates),
        "candidates": [
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
            ).model_dump()
            for c in candidates
        ],
    }


# ============================================================================
# RMSP MULTIPAGE
# ============================================================================

@router.get("/rmsp-multipage", summary="Multipage поиск с агрегацией")
async def test_rmsp_multipage(
    kladr_code: str = Query(...),
    max_candidates: int = Query(50, ge=1, le=200),
    max_pages: int = Query(5, ge=1, le=10),
    strict_region: bool = Query(True),
    _user=Depends(require_manager),
):
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
        log.exception("[inn-debug] RMSP error")
        return {
            "ok": False,
            "error_type": "RmspError",
            "error_message": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1500:],
        }
    except Exception as e:
        log.exception("[inn-debug] Unexpected RMSP error")
        return {
            "ok": False,
            "error_type": e.__class__.__name__,
            "error_message": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1500:],
        }

    return {
        "ok": True,
        "kladr_code": kladr_code,
        "count": len(candidates),
        "candidates": [
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
            ).model_dump()
            for c in candidates
        ],
    }


# ============================================================================
# NPD CHECK
# ============================================================================

@router.get("/npd-check", summary="Тест проверки статуса НПД")
async def test_npd_check(
    inn: str = Query(...),
    _user=Depends(require_manager),
):
    if not inn or len(inn) != 12 or not inn.isdigit():
        raise HTTPException(
            status_code=422, detail="ИНН должен быть из 12 цифр (физлицо)",
        )

    try:
        async with NpdStatusChecker() as checker:
            result = await checker.check(inn=inn)
    except NpdStatusError as e:
        log.exception("[inn-debug] NPD error")
        return {
            "ok": False,
            "error_type": "NpdStatusError",
            "error_message": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1500:],
        }
    except Exception as e:
        log.exception("[inn-debug] Unexpected NPD error")
        return {
            "ok": False,
            "error_type": e.__class__.__name__,
            "error_message": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1500:],
        }

    return {
        "ok": True,
        "inn": result.inn,
        "is_active": result.is_active,
        "request_date": result.request_date.isoformat(),
        "registration_date": (
            result.registration_date.isoformat()
            if result.registration_date else None
        ),
        "full_name": result.full_name or None,
        "message": result.message,
        "raw": result.raw,
    }


# ============================================================================
# ADDRESS GEN + KNOWN REGIONS (без сети, всегда работают)
# ============================================================================

@router.get("/generate-address")
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
    return {
        "full": addr.full,
        "postal_code": addr.postal_code,
        "region_name": addr.region_name,
        "city_name": addr.city_name,
        "street": addr.street,
        "house": addr.house,
        "apartment": addr.apartment,
        "kladr_code": addr.kladr_code,
    }


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
