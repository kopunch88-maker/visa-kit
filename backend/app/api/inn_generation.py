"""
Pack 17.3 — Production endpoints для генерации ИНН.

ИЗМЕНЕНИЯ vs 17.2.4:
- DEFENSIVE FIX: Application получаем через обратный запрос
  (Applicant НЕ имеет поля application_id; связь идёт от Application.applicant_id).
- Все unexpected ошибки превращаются в HTTPException 500 с понятным detail
  (тип ошибки + сообщение + traceback в логах Railway).
- /inn-accept помечает ИНН в self_employed_registry как is_used=TRUE.
"""

from __future__ import annotations

import logging
import traceback
import urllib.parse
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import Applicant, Application, Company
from app.services.inn_generator.pipeline import (
    InnPipelineError,
    suggest_inn_for_applicant,
    mark_inn_as_used,
)

from .dependencies import require_manager


log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/applicants",
    tags=["admin: applicants — INN generation"],
    dependencies=[Depends(require_manager)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class InnSuggestResponse(BaseModel):
    inn: str
    full_name_rmsp: Optional[str]
    region_code: Optional[str]

    home_address: str
    address_was_generated: bool

    estimated_npd_start: Optional[date]
    estimated_npd_start_raw: Optional[str]

    target_kladr_code: str
    target_region_name: str

    region_pick_source: str
    region_pick_explanation: str

    yandex_search_url: str
    rusprofile_url: str

    rmsp_raw: dict


class InnAcceptRequest(BaseModel):
    """
    Тело запроса к /inn-accept.

    Принимает ОБА варианта именования полей (для совместимости
    с возможным старым кодом в frontend):
    - inn_registration_date / registration_date
    - region_kladr_code / kladr_code
    """
    inn: str
    inn_registration_date: Optional[date] = None
    registration_date: Optional[date] = None  # alias
    home_address: Optional[str] = None
    region_kladr_code: Optional[str] = None
    kladr_code: Optional[str] = None  # alias
    region_pick_source: Optional[str] = None  # для логов

    def get_registration_date(self) -> Optional[date]:
        return self.inn_registration_date or self.registration_date

    def get_kladr_code(self) -> Optional[str]:
        return self.region_kladr_code or self.kladr_code


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_application_for_applicant(
    session: Session, applicant_id: int
) -> Optional[Application]:
    """
    Ищет Application у которой applicant_id = заданному.

    В нашей модели связь обратная (Application имеет applicant_id, не наоборот).
    Если у заявителя несколько заявок — берём самую свежую (id DESC).
    """
    stmt = (
        select(Application)
        .where(Application.applicant_id == applicant_id)
        .order_by(Application.id.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


# ---------------------------------------------------------------------------
# POST /admin/applicants/{id}/inn-suggest
# ---------------------------------------------------------------------------

@router.post("/{applicant_id}/inn-suggest", response_model=InnSuggestResponse)
def suggest_inn(
    applicant_id: int,
    filter_by_region: bool = False,
    session: Session = Depends(get_session),
):
    """
    Подбирает ИНН + адрес + дату для заявителя из локальной БД.

    По умолчанию ищет любого свободного самозанятого (filter_by_region=false),
    адрес генерируется под регион клиента отдельно.
    """
    applicant = session.get(Applicant, applicant_id)
    if applicant is None:
        raise HTTPException(404, "Applicant not found")

    # Pack 17.3 fix: ищем Application через обратный запрос
    application = _find_application_for_applicant(session, applicant_id)

    company = None
    if application and application.company_id:
        company = session.get(Company, application.company_id)

    log.info(
        f"[inn-suggest] applicant_id={applicant_id} "
        f"home_address={applicant.home_address!r} "
        f"nationality={applicant.nationality!r} "
        f"application_found={application is not None} "
        f"contract_sign_city={application.contract_sign_city if application else None!r} "
        f"company_found={company is not None}"
    )

    try:
        suggestion = suggest_inn_for_applicant(
            session=session,
            applicant=applicant,
            application=application,
            company=company,
            filter_by_region=filter_by_region,
        )
    except InnPipelineError as e:
        # Это ОЖИДАЕМАЯ бизнес-ошибка (БД пустая, регион не поддерживается и т.п.)
        log.warning(f"[inn-suggest] pipeline error: {e}")
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        # Любая неожиданная ошибка — лог трейсбека + понятный 500 для клиента
        tb = traceback.format_exc()
        log.error(f"[inn-suggest] UNEXPECTED ERROR for applicant_id={applicant_id}:\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=(
                f"Внутренняя ошибка генерации ИНН: {type(e).__name__}: {e}. "
                "Подробности в логах Railway."
            ),
        )

    # Готовим вспомогательные ссылки для менеджера
    yandex_query = f"{suggestion.full_name_rmsp or ''} {suggestion.inn}".strip()
    yandex_url = (
        "https://yandex.ru/search/?text="
        + urllib.parse.quote(yandex_query)
    )
    rusprofile_url = f"https://www.rusprofile.ru/search?query={suggestion.inn}"

    return InnSuggestResponse(
        inn=suggestion.inn,
        full_name_rmsp=suggestion.full_name_rmsp,
        region_code=suggestion.region_code,
        home_address=suggestion.home_address,
        address_was_generated=suggestion.address_was_generated,
        estimated_npd_start=suggestion.estimated_npd_start,
        estimated_npd_start_raw=suggestion.estimated_npd_start_raw,
        target_kladr_code=suggestion.target_kladr_code,
        target_region_name=suggestion.target_region_name,
        region_pick_source=suggestion.region_pick_source,
        region_pick_explanation=suggestion.region_pick_explanation,
        yandex_search_url=yandex_url,
        rusprofile_url=rusprofile_url,
        rmsp_raw=suggestion.rmsp_raw,
    )


# ---------------------------------------------------------------------------
# POST /admin/applicants/{id}/inn-accept
# ---------------------------------------------------------------------------

@router.post("/{applicant_id}/inn-accept")
def accept_inn(
    applicant_id: int,
    payload: InnAcceptRequest,
    session: Session = Depends(get_session),
):
    """
    Сохраняет принятое менеджером ИНН в applicant + помечает запись
    в self_employed_registry как использованную.
    """
    applicant = session.get(Applicant, applicant_id)
    if applicant is None:
        raise HTTPException(404, "Applicant not found")

    # Сохраняем в applicant
    applicant.inn = payload.inn

    reg_date = payload.get_registration_date()
    if reg_date is not None:
        applicant.inn_registration_date = reg_date

    applicant.inn_source = "auto-generated"

    kladr_code = payload.get_kladr_code()
    if kladr_code is not None:
        applicant.inn_kladr_code = kladr_code

    if payload.home_address is not None and payload.home_address.strip():
        applicant.home_address = payload.home_address.strip()

    session.add(applicant)
    session.commit()
    session.refresh(applicant)

    # Помечаем ИНН в реестре как использованный
    try:
        mark_inn_as_used(session=session, inn=payload.inn, applicant_id=applicant_id)
    except Exception as e:
        log.warning(f"[inn-accept] mark_inn_as_used failed for {payload.inn}: {e}")
        # Не падаем — applicant уже сохранён

    return {
        "ok": True,
        "applicant_id": applicant.id,
        "inn": applicant.inn,
        "inn_registration_date": applicant.inn_registration_date,
        "inn_source": applicant.inn_source,
        "inn_kladr_code": applicant.inn_kladr_code,
        "home_address": applicant.home_address,
    }
