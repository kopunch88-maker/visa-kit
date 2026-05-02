"""
Pack 17.2 — production endpoints для автогенерации ИНН самозанятого.

Endpoints:
    POST /api/admin/applicants/{id}/inn-suggest
        → подбирает ИНН + адрес + дату через pipeline
        → возвращает InnSuggestion (не сохраняет в БД)

    POST /api/admin/applicants/{id}/inn-accept
        body: { inn, registration_date, home_address, kladr_code }
        → сохраняет данные в applicant
        → ставит inn_source='auto-generated'

Workflow в UI:
    1. Менеджер кликает ✨ возле ИНН
    2. Frontend → POST /inn-suggest → получает InnSuggestion
    3. Менеджер видит модал: ИНН, ФИО (для проверки), адрес, дата + ссылка на Яндекс
    4. Если устраивает — клик «Принять» → POST /inn-accept → сохранение
    5. Если хочет другого — клик «Другой кандидат» → снова POST /inn-suggest
       (исключит уже выбранный ИНН через used_inns)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.dependencies import require_manager
from app.db.session import get_session
from app.models import Applicant, Application, Company
from app.services.inn_generator import (
    suggest_inn_for_applicant,
    InnPipelineError,
    InnSuggestion,
)


log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/applicants",
    tags=["inn-generation"],
)


# === Pydantic модели ===

class InnSuggestionOut(BaseModel):
    """Что возвращаем менеджеру в модал «Сгенерировать ИНН»."""

    inn: str
    full_name_rmsp: str
    region_code: str

    home_address: str
    address_was_generated: bool

    estimated_npd_start: Optional[date] = None
    estimated_npd_start_raw: Optional[str] = None

    target_kladr_code: str
    target_region_name: str

    region_pick_source: str
    region_pick_explanation: str

    # Готовая ссылка на Яндекс для проверки «не светится ли»
    yandex_search_url: str

    # Готовая ссылка на Rusprofile для дополнительной проверки
    rusprofile_url: str


class InnAcceptPayload(BaseModel):
    """Что менеджер присылает при клике «Принять»."""

    inn: str
    registration_date: Optional[date] = None
    home_address: str
    kladr_code: str

    # Опционально — для аудита и отчёта
    region_pick_source: Optional[str] = None


class InnAcceptResult(BaseModel):
    """Что возвращаем после успешного сохранения."""

    applicant_id: int
    inn: str
    inn_registration_date: Optional[date]
    inn_source: str
    inn_kladr_code: str
    home_address: str


# === Endpoints ===

@router.post(
    "/{applicant_id}/inn-suggest",
    response_model=InnSuggestionOut,
    summary="Подобрать ИНН + адрес + дату для заявителя",
)
async def inn_suggest(
    applicant_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Запускает pipeline:
    1. Определяет регион (home_address → contract.sign_city → company → диаспоры → Москва)
    2. Запрашивает rmsp-pp реестр самозанятых (5 страниц, до 500 кандидатов)
    3. Исключает уже использованные ИНН из БД (применённые ранее другим клиентам)
    4. Берёт самый «старый» ИНН (по сортировке возрастающей — статистически зрелый)
    5. Генерирует адрес если у заявителя его нет
    6. Возвращает результат для отображения в модале

    Сохранение в БД делает /inn-accept после подтверждения менеджером.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    # Получаем последнюю Application заявителя (если есть)
    application: Optional[Application] = session.exec(
        select(Application)
        .where(Application.applicant_id == applicant_id)
        .order_by(Application.id.desc())
    ).first()

    # И компанию-Заказчика этой заявки
    company: Optional[Company] = None
    if application and application.company_id:
        company = session.get(Company, application.company_id)

    # === Запуск pipeline ===
    import traceback
    try:
        suggestion: InnSuggestion = await suggest_inn_for_applicant(
            session=session,
            applicant=applicant,
            application=application,
            company=company,
        )
    except InnPipelineError as e:
        log.error(f"[inn-suggest] Pipeline error for applicant_id={applicant_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail={
                "error_type": "InnPipelineError",
                "message": str(e),
                "hint": (
                    "Если 'RMSP недоступен' — это burst-rate-limit ФНС. "
                    "Подожди 1-2 минуты и попробуй снова. "
                    "ФНС блокирует на 1-5 минут когда видит более 3-5 запросов за 10 секунд."
                ),
            },
        )
    except Exception as e:
        log.exception(f"[inn-suggest] Unexpected error for applicant_id={applicant_id}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": e.__class__.__name__,
                "message": str(e) or "(empty)",
                "traceback": traceback.format_exc()[-1500:],
            },
        )

    # === Готовим ссылки для финальной проверки менеджером ===
    # Яндекс — поиск имени из реестра + ИНН (увидит ли там что-то светящееся)
    yandex_query = f"{suggestion.full_name_rmsp} {suggestion.inn}"
    yandex_url = f"https://yandex.ru/search/?text={_url_encode(yandex_query)}"

    # Rusprofile — поиск по ИНН (видна ли карточка человека как ИП/гендира)
    rusprofile_url = f"https://www.rusprofile.ru/search?query={suggestion.inn}"

    return InnSuggestionOut(
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
    )


@router.post(
    "/{applicant_id}/inn-accept",
    response_model=InnAcceptResult,
    summary="Сохранить выбранный ИНН + адрес + дату в applicant",
)
def inn_accept(
    applicant_id: int,
    payload: InnAcceptPayload,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Сохраняет результат подбора в БД:
    - applicant.inn = payload.inn
    - applicant.inn_registration_date = payload.registration_date
    - applicant.inn_source = 'auto-generated'
    - applicant.inn_kladr_code = payload.kladr_code
    - applicant.home_address = payload.home_address (если был сгенерирован)

    После сохранения этот ИНН попадает в used_inns и не будет предложен
    другому клиенту.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    # Валидация ИНН
    inn = (payload.inn or "").strip()
    if not inn or len(inn) != 12 or not inn.isdigit():
        raise HTTPException(
            status_code=422,
            detail=f"ИНН должен быть из 12 цифр, получено: {inn!r}",
        )

    # Валидация KLADR
    kladr = (payload.kladr_code or "").strip()
    if not kladr or len(kladr) != 13 or not kladr.isdigit():
        raise HTTPException(
            status_code=422,
            detail=f"kladr_code должен быть из 13 цифр",
        )

    # Валидация home_address
    address = (payload.home_address or "").strip()
    if not address:
        raise HTTPException(
            status_code=422,
            detail="home_address не может быть пустым",
        )

    # Проверка что этот ИНН не используется другим заявителем
    existing = session.exec(
        select(Applicant)
        .where(Applicant.inn == inn)
        .where(Applicant.id != applicant_id)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"ИНН {inn} уже привязан к другому заявителю "
                f"(id={existing.id}). Сгенерируйте другого кандидата."
            ),
        )

    # === Сохранение ===
    applicant.inn = inn
    applicant.inn_registration_date = payload.registration_date
    applicant.inn_source = "auto-generated"
    applicant.inn_kladr_code = kladr
    applicant.home_address = address

    session.add(applicant)
    session.commit()
    session.refresh(applicant)

    log.info(
        f"[inn-accept] Saved INN {inn} for applicant_id={applicant_id}, "
        f"kladr={kladr}, source={payload.region_pick_source}"
    )

    return InnAcceptResult(
        applicant_id=applicant.id,
        inn=applicant.inn,
        inn_registration_date=applicant.inn_registration_date,
        inn_source=applicant.inn_source,
        inn_kladr_code=applicant.inn_kladr_code,
        home_address=applicant.home_address,
    )


# === Helpers ===

def _url_encode(text: str) -> str:
    """URL-кодирование строки для query параметров."""
    from urllib.parse import quote
    return quote(text, safe="")
