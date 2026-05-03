"""
Pack 17 / Pack 18.1 — endpoints автогенерации ИНН самозанятого.

Pack 18.1 изменения:
- В response /inn-suggest добавлены поля fallback_used / requested_region_name /
  requested_region_code / fallback_reason / region_code — фронт показывает
  warning менеджеру при сдвиге региона.
- Удалён query-параметр filter_by_region (всегда фильтруем по региону, fallback
  гарантирует что кандидат найдётся).
- В /inn-accept проставляется used_at=utcnow() помимо is_used=True.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import (
    Applicant,
    Application,
    Company,
    SelfEmployedRegistry,
)
from app.services.inn_generator.pipeline import (
    InnSuggestion,
    suggest_inn_for_applicant,
)
from .dependencies import require_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/applicants", tags=["inn-generation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InnSuggestResponse(BaseModel):
    """
    Ответ /inn-suggest. Старые поля (Pack 17) сохранены, добавлены новые
    region_code и fallback_* поля (Pack 18.1).
    """

    inn: str
    full_name: str
    home_address: str
    kladr_code: str
    region_name: str
    region_code: str  # NEW: 2-значный код субъекта ('77', '02', ...)
    inn_registration_date: date
    source: str

    # Pack 18.1: warning-поля
    fallback_used: bool = False
    requested_region_name: Optional[str] = None
    requested_region_code: Optional[str] = None
    fallback_reason: Optional[str] = None


class InnAcceptRequest(BaseModel):
    inn: str
    home_address: Optional[str] = None
    kladr_code: Optional[str] = None
    inn_registration_date: Optional[date] = None
    inn_source: Optional[str] = "registry_snrip"


class InnAcceptResponse(BaseModel):
    ok: bool
    applicant_id: int
    inn: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_application_for_applicant(
    session: Session, applicant_id: int
) -> Optional[Application]:
    """
    Pack 17.3 defensive fix: Applicant НЕ имеет поля application_id, поэтому ищем
    обратным SELECT'ом по Application.applicant_id.
    Берём последнюю заявку (ORDER BY id DESC) — обычно одна, но если их несколько
    хотим самую свежую.
    """
    stmt = (
        select(Application)
        .where(Application.applicant_id == applicant_id)
        .order_by(Application.id.desc())  # type: ignore[union-attr]
    )
    return session.exec(stmt).first()


def _get_company_for_application(
    session: Session, application: Optional[Application]
) -> Optional[Company]:
    if not application or not application.company_id:
        return None
    return session.get(Company, application.company_id)


# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/inn-suggest
# ---------------------------------------------------------------------------


@router.post(
    "/{applicant_id}/inn-suggest",
    response_model=InnSuggestResponse,
    summary="Подобрать ИНН самозанятого для заявителя",
)
def inn_suggest(
    applicant_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> InnSuggestResponse:
    """
    Pack 18.1: подбор ИНН с tier-fallback.
    Параметр filter_by_region удалён — всегда фильтруем по региону, гарантия
    результата обеспечивается fallback'ом на диаспоры → Москву.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    application = _find_application_for_applicant(session, applicant_id)
    company = _get_company_for_application(session, application)

    log.info(
        "inn-suggest: applicant_id=%s nationality=%s home_addr=%r contract_city=%r company_legal=%r",
        applicant_id,
        applicant.nationality,
        applicant.home_address,
        application.contract_sign_city if application else None,
        company.legal_address if company else None,
    )

    try:
        suggestion: InnSuggestion = suggest_inn_for_applicant(
            session,
            applicant=applicant,
            application=application,
            company=company,
        )
    except RuntimeError as e:
        # Реестр исчерпан или другая нерешаемая проблема
        log.error("inn-suggest: pipeline failure for applicant_id=%s: %s", applicant_id, e)
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # pragma: no cover
        log.exception("inn-suggest: unexpected error")
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")

    return InnSuggestResponse(
        inn=suggestion.inn,
        full_name=suggestion.full_name,
        home_address=suggestion.home_address,
        kladr_code=suggestion.kladr_code,
        region_name=suggestion.region_name,
        region_code=suggestion.region_code,
        inn_registration_date=suggestion.inn_registration_date,
        source=suggestion.source,
        fallback_used=suggestion.fallback_used,
        requested_region_name=suggestion.requested_region_name,
        requested_region_code=suggestion.requested_region_code,
        fallback_reason=suggestion.fallback_reason,
    )


# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/inn-accept
# ---------------------------------------------------------------------------


@router.post(
    "/{applicant_id}/inn-accept",
    response_model=InnAcceptResponse,
    summary="Принять ИНН: сохранить в applicant + пометить is_used в реестре",
)
def inn_accept(
    applicant_id: int,
    payload: InnAcceptRequest,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> InnAcceptResponse:
    """
    Сохраняет выбранный ИНН в applicant'е и помечает запись в реестре как использованную.
    Идемпотентно: если applicant.inn уже совпадает с переданным — просто 200 OK
    (но если запись в реестре по какой-то причине is_used=False — починим).
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    inn = (payload.inn or "").strip()
    if not inn:
        raise HTTPException(status_code=400, detail="inn is required")

    # Идемпотентность
    if applicant.inn == inn:
        cand = session.get(SelfEmployedRegistry, inn)
        if cand and not cand.is_used:
            cand.is_used = True
            cand.used_by_applicant_id = applicant.id
            cand.used_at = datetime.utcnow()
            session.add(cand)
            session.commit()
            log.info("inn-accept: marked candidate inn=%s as used (idempotent fix)", inn)
        return InnAcceptResponse(ok=True, applicant_id=applicant.id, inn=inn)

    # Проверяем что такой кандидат есть в реестре и свободен
    cand = session.get(SelfEmployedRegistry, inn)
    if not cand:
        raise HTTPException(
            status_code=404,
            detail=f"INN {inn} not found in registry. Refuse to write unknown INN.",
        )
    if cand.is_used and cand.used_by_applicant_id != applicant.id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"INN {inn} уже использован заявителем id={cand.used_by_applicant_id}. "
                "Подберите другого кандидата."
            ),
        )

    # Транзакционная запись
    applicant.inn = inn
    if payload.home_address:
        applicant.home_address = payload.home_address
    if payload.kladr_code:
        applicant.inn_kladr_code = payload.kladr_code
    if payload.inn_registration_date:
        applicant.inn_registration_date = payload.inn_registration_date
    if payload.inn_source:
        applicant.inn_source = payload.inn_source

    cand.is_used = True
    cand.used_by_applicant_id = applicant.id
    cand.used_at = datetime.utcnow()

    session.add(applicant)
    session.add(cand)
    session.commit()

    log.info(
        "inn-accept: SUCCESS applicant_id=%s inn=%s region_kladr=%s",
        applicant_id,
        inn,
        payload.kladr_code,
    )
    return InnAcceptResponse(ok=True, applicant_id=applicant.id, inn=inn)
