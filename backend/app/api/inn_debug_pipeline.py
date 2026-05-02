"""
Pack 17.2.2 — добавляет диагностический endpoint inn-suggest-debug
который показывает КАЖДЫЙ ШАГ pipeline с подробностями.

Используется ТОЛЬКО для разработки — даёт понять где именно что отвалилось.

После того как пайплайн заработает стабильно — в Pack 17.3 этот endpoint
можно убрать.
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.dependencies import require_manager
from app.db.session import get_session
from app.models import Applicant, Application, Company

from app.services.inn_generator import (
    RmspClient,
    RmspError,
    pick_region,
)


log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/applicants",
    tags=["inn-debug"],
)


@router.post(
    "/{applicant_id}/inn-suggest-debug",
    summary="DEBUG: пошаговый pipeline с подробностями",
)
async def inn_suggest_debug(
    applicant_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Возвращает детальный отчёт о каждом шаге pipeline:
    - какой регион выбран и почему
    - сколько кандидатов вернул RMSP (raw count)
    - сколько кандидатов после фильтра is_self_employed
    - сколько ИНН уже использовано в БД
    - какой итоговый кандидат
    """
    result = {
        "applicant_id": applicant_id,
        "steps": [],
    }

    # === Шаг 0: Загрузка applicant + application + company ===
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    application = session.exec(
        select(Application)
        .where(Application.applicant_id == applicant_id)
        .order_by(Application.id.desc())
    ).first()

    company: Optional[Company] = None
    if application and application.company_id:
        company = session.get(Company, application.company_id)

    result["steps"].append({
        "step": "0_loaded",
        "applicant": {
            "id": applicant.id,
            "full_name": f"{applicant.last_name_native} {applicant.first_name_native}",
            "nationality": applicant.nationality,
            "home_address": applicant.home_address,
            "current_inn": applicant.inn,
        },
        "application": {
            "id": application.id if application else None,
            "contract_sign_city": application.contract_sign_city if application else None,
            "company_id": application.company_id if application else None,
        } if application else None,
        "company": {
            "id": company.id,
            "short_name": company.short_name,
            "legal_address": company.legal_address,
        } if company else None,
    })

    # === Шаг 1: Region picker ===
    try:
        region_result = pick_region(
            session=session,
            applicant=applicant,
            application=application,
            company=company,
        )
        result["steps"].append({
            "step": "1_region_picked",
            "ok": True,
            "region_name": region_result.region.name,
            "region_full": region_result.region.name_full,
            "kladr_code": region_result.region.kladr_code,
            "source": region_result.source,
            "explanation": region_result.explanation,
            "use_existing_address": region_result.use_existing_address,
        })
    except Exception as e:
        result["steps"].append({
            "step": "1_region_picked",
            "ok": False,
            "error": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1000:],
        })
        return result

    # === Шаг 2: RMSP запрос (один) ===
    try:
        async with RmspClient() as client:
            candidates = await client.search_self_employed(
                kladr_code=region_result.region.kladr_code,
                page=1,
                page_size=100,
                strict_region_filter=False,  # хотим видеть ВСЕ что вернула ФНС
            )

        # Дополнительно: сколько в этой выборке из ожидаемого региона
        expected_region = region_result.region.kladr_code[:2]
        from_target_region = [c for c in candidates if c.region_code == expected_region]

        result["steps"].append({
            "step": "2_rmsp_fetched",
            "ok": True,
            "kladr_used": region_result.region.kladr_code,
            "expected_region_code": expected_region,
            "raw_candidate_count": len(candidates),
            "from_target_region_count": len(from_target_region),
            "first_5_candidates": [
                {
                    "inn": c.inn,
                    "full_name": c.full_name,
                    "region_code": c.region_code,
                    "nptype": c.nptype,
                    "category": c.category,
                    "ogrn": c.ogrn,
                    "is_self_employed": c.is_self_employed,
                    "dt_support_begin": c.dt_support_begin,
                }
                for c in candidates[:5]
            ],
            "regions_distribution": _count_by_region(candidates),
        })
    except RmspError as e:
        result["steps"].append({
            "step": "2_rmsp_fetched",
            "ok": False,
            "error_type": "RmspError",
            "error": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1000:],
        })
        return result
    except Exception as e:
        result["steps"].append({
            "step": "2_rmsp_fetched",
            "ok": False,
            "error_type": e.__class__.__name__,
            "error": str(e) or "(empty)",
            "traceback": traceback.format_exc()[-1000:],
        })
        return result

    # === Шаг 3: Used INNs ===
    used_inns_query = select(Applicant.inn).where(Applicant.inn != None)  # noqa: E711
    used_inns = {inn for inn in session.exec(used_inns_query).all() if inn}

    after_filter = [c for c in candidates if c.inn not in used_inns]

    result["steps"].append({
        "step": "3_used_inns_filtered",
        "used_inns_in_db_count": len(used_inns),
        "candidates_before": len(candidates),
        "candidates_after": len(after_filter),
        "removed_as_used": len(candidates) - len(after_filter),
    })

    # === Шаг 4: Финальный выбор ===
    if not after_filter:
        result["steps"].append({
            "step": "4_chosen",
            "ok": False,
            "error": (
                "После фильтра used_inns не осталось кандидатов. "
                "Возможно ФНС вернула малую выборку и все они уже в БД."
            ),
        })
    else:
        chosen = sorted(after_filter, key=lambda c: c.inn)[0]
        result["steps"].append({
            "step": "4_chosen",
            "ok": True,
            "inn": chosen.inn,
            "full_name": chosen.full_name,
            "region_code": chosen.region_code,
            "estimated_npd_start": chosen.estimated_npd_start,
        })

    return result


def _count_by_region(candidates) -> dict:
    """Сколько кандидатов в каком регионе."""
    by_region = {}
    for c in candidates:
        by_region[c.region_code] = by_region.get(c.region_code, 0) + 1
    return dict(sorted(by_region.items(), key=lambda x: -x[1]))
