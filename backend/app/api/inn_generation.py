"""
Pack 17 / Pack 18.x / Pack 28 Часть 2 — endpoints автогенерации ИНН самозанятого.

ПЕРЕПИСАНО Pack 28 Часть 2 (08.05.2026):
- /inn-suggest теперь ASYNC. Если в пуле verified=0 для региона → возвращает
  202 Accepted с task_id и стартует BackgroundTask пополнения пула.
  Фронт показывает спиннер и поллит /admin/npd-pool/tasks/{task_id} раз в 3 сек.
- /inn-accept переписан на npd_candidate. SelfEmployedRegistry больше не
  используется в hot-path (старая таблица остаётся для обратной совместимости
  но новые ИНН в неё не пишутся).
- Источник INN в /inn-accept: NpdCandidate (status='allocated' от
  inn-suggest, переводится в 'used' с used_by_applicant_id).
- registration_date может быть None если Pack 28.5 ещё не сделан (ФНС API
  урезали). В этом случае applicant.inn_registration_date остаётся
  синтетической как в Pack 18.3.4.

ВАЖНО про async + ALLOCATED-бронь:
- inn-suggest помечает кандидата allocated_until = now+30мин
- Если менеджер закрыл модал и не нажал accept — через 30 мин кандидат
  автоматически возвращается в verified (см. _expire_stale_allocations
  в pipeline.py — вызывается на каждом suggest).
- inn-accept проверяет что candidate.status в ('verified', 'allocated') —
  оба валидны. Идемпотентность: если applicant.inn уже = inn → 200 OK.

УБРАНО:
- import SelfEmployedRegistry (больше не нужен)
- весь блок idempotent fix для SelfEmployedRegistry
- inn_source = "registry_snrip" по умолчанию (теперь "npd_pool")

ОСТАЛОСЬ КАК БЫЛО:
- /regen-address (Pack 18.8) — без изменений
- NPD-проверка через ФНС API в inn-accept (Pack 18.2) — без изменений,
  но если verified-кандидат уже свежепроверен (npd_checked_at < 1 day)
  то проверка ПРОПУСКАЕТСЯ (skip).

Pack 33.3 (10.05.2026):
- regen_work_history теперь различает 4 причины None из suggest_work_history:
  (a) специальность не определилась → старый текст 422
  (b) специальность определилась, но в legend_company нет компаний под неё
      ни в одном регионе → новый текст с указанием specialty_id
  (c) специальность определилась, есть компании, но нет Position под нужный level
      → новый текст с указанием specialty + level
  (d) другая внутренняя причина → generic 422
- Цель: убрать обманчивый текст "Pack 19.0 specialty-seed применён",
  который заставлял менеджера проверять не то место.
"""

from __future__ import annotations

import logging
import random  # для regen-address
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
)
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import engine, get_session
from app.models import (
    Applicant,
    Application,
    Company,
    NpdCandidate,
    NpdRefillTask,
    WorkHistorySuggestion,  # Pack 30.0
)
from app.services.inn_generator.kladr_address_gen import (
    KNOWN_REGIONS,
    generate_address,
)
from app.services.inn_generator.npd_pool import run_lazy_region_refill
from app.services.inn_generator.npd_status import (
    NpdStatusChecker,
    NpdStatusError,
)
from app.services.inn_generator.pipeline import (
    InnSuggestion,
    NeedsRefillError,
    suggest_inn_for_applicant,
)
from app.services.work_history_generator import suggest_work_history
# Pack 33.3: для диагностики причины None в /regen-work-history
from app.services.work_history_generator import (
    _resolve_specialty,
    _get_region_code,
)
from app.models import LegendCompany, Position
from .dependencies import require_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/applicants", tags=["inn-generation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InnSuggestImmediate(BaseModel):
    """Ответ inn-suggest когда verified нашёлся сразу."""
    kind: Literal["immediate"] = "immediate"

    inn: str
    full_name: str
    home_address: str
    kladr_code: str
    region_name: str
    region_code: str
    inn_registration_date: Optional[date] = None
    source: str = "unknown"

    # Pack 28 Часть 2: fallback больше не используется, поля для совместимости
    fallback_used: bool = False
    requested_region_name: Optional[str] = None
    requested_region_code: Optional[str] = None
    fallback_reason: Optional[str] = None


class InnSuggestTaskStarted(BaseModel):
    """Ответ inn-suggest когда пул пуст и стартовал refill task."""
    kind: Literal["task"] = "task"

    task_id: int
    region_code: str
    region_name: str
    estimated_seconds: int = 240  # ~4 мин на полный refill 5 кандидатов


# Union: фронт смотрит на kind и выбирает что показывать
InnSuggestResponse = InnSuggestImmediate | InnSuggestTaskStarted


class InnAcceptRequest(BaseModel):
    inn: str
    inn_registration_date: Optional[date] = None
    home_address: Optional[str] = None
    kladr_code: Optional[str] = None
    inn_source: Optional[str] = None


class InnAcceptResponse(BaseModel):
    ok: bool
    applicant_id: int
    inn: str
    npd_check_status: Literal[
        "confirmed",
        "skipped_fns_unavailable",
        "skipped_already_checked",
        "skipped_recently_verified",
    ]
    manual_check_url: Optional[str] = None
    npd_check_message: Optional[str] = None


class RegenAddressRequest(BaseModel):
    kladr_code: Optional[str] = None


class RegenAddressResponse(BaseModel):
    home_address: str
    kladr_code: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_application_for_applicant(
    session: Session, applicant_id: int,
) -> Optional[Application]:
    """Самая свежая активная заявка для applicant'а (для контекста suggest)."""
    return session.exec(
        select(Application)
        .where(Application.applicant_id == applicant_id)
        .where(Application.deleted_at == None)  # noqa: E711
        .order_by(Application.id.desc())
        .limit(1)
    ).first()


def _get_company_for_application(
    session: Session, application: Optional[Application],
) -> Optional[Company]:
    if application is None or application.company_id is None:
        return None
    return session.get(Company, application.company_id)


def _make_manual_check_url(inn: str) -> str:
    """Прямая ссылка на ФНС НПД проверку статуса."""
    return f"https://npd.nalog.ru/check-status/?inn={inn}"


# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/inn-suggest
# ---------------------------------------------------------------------------


@router.post(
    "/{applicant_id}/inn-suggest",
    response_model=InnSuggestResponse,
    summary="Подобрать ИНН самозанятого (immediate или task если пул пуст)",
)
def inn_suggest(
    applicant_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user=Depends(require_manager),
) -> InnSuggestResponse:
    """
    Pack 28 Часть 2: новая логика.

    Если в пуле verified > 0 для региона applicant'а → InnSuggestImmediate
    (как раньше — мгновенный ответ).

    Если verified = 0 → стартуем BackgroundTask refill (5-10 мин), возвращаем
    InnSuggestTaskStarted с task_id. Фронт поллит /admin/npd-pool/tasks/{id}
    каждые 3 сек, после status='done' зовёт inn-suggest ещё раз → получает
    immediate.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    application = _find_application_for_applicant(session, applicant_id)
    company = _get_company_for_application(session, application)

    log.info(
        "inn-suggest: applicant_id=%s nationality=%s home_addr=%r "
        "contract_city=%r company_legal=%r",
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
    except NeedsRefillError as e:
        # Pool пуст для региона — стартуем lazy refill task
        log.info(
            "inn-suggest: pool empty for region=%s (%s) — starting lazy refill",
            e.region_code, e.region_name,
        )

        # Идемпотентность: если для этого региона уже есть pending/running
        # task младше 5 минут — переиспользуем его, не создаём дубль
        existing = session.exec(
            select(NpdRefillTask)
            .where(NpdRefillTask.region_code == e.region_code)
            .where(NpdRefillTask.kind == "lazy_region")
            .where(NpdRefillTask.status.in_(["pending", "running"]))  # type: ignore[attr-defined]
            .where(NpdRefillTask.created_at > datetime.utcnow() - timedelta(minutes=5))
            .order_by(NpdRefillTask.created_at.desc())
            .limit(1)
        ).first()

        if existing:
            log.info(
                "inn-suggest: reusing existing task_id=%s for region=%s",
                existing.id, e.region_code,
            )
            return InnSuggestTaskStarted(
                kind="task",
                task_id=existing.id or 0,
                region_code=e.region_code,
                region_name=e.region_name,
            )

        # Создаём новую task
        task = NpdRefillTask(
            kind="lazy_region",
            status="pending",
            region_code=e.region_code,
            progress_text=f"Поиск чистого самозанятого ({e.region_name})...",
            progress_total=5,
            triggered_by=f"manager:{getattr(user, 'id', '?')}",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        # Стартуем BackgroundTask
        background_tasks.add_task(
            _run_lazy_refill_bg,
            task_id=task.id,
            region_code=e.region_code,
        )

        return InnSuggestTaskStarted(
            kind="task",
            task_id=task.id or 0,
            region_code=e.region_code,
            region_name=e.region_name,
        )

    except RuntimeError as e:
        # Совместимость со старым кодом — на случай если region_picker упал
        log.error("inn-suggest: pipeline failure for applicant_id=%s: %s",
                  applicant_id, e)
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # pragma: no cover
        log.exception("inn-suggest: unexpected error")
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")

    return InnSuggestImmediate(
        kind="immediate",
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


def _run_lazy_refill_bg(task_id: int, region_code: str) -> None:
    """Sync wrapper для BackgroundTasks."""
    import asyncio

    log.info(
        "[inn-suggest] BG lazy refill task_id=%s region=%s starting",
        task_id, region_code,
    )
    try:
        with Session(engine) as session:
            asyncio.run(
                run_lazy_region_refill(
                    session=session,
                    task_id=task_id,
                    region_code=region_code,
                    target=5,
                )
            )
    except Exception as e:
        log.exception(
            "[inn-suggest] lazy refill BG task_id=%s FAILED: %s",
            task_id, e,
        )
        try:
            with Session(engine) as session:
                t = session.get(NpdRefillTask, task_id)
                if t and t.status not in ("done", "failed"):
                    t.status = "failed"
                    t.error = f"{type(e).__name__}: {e}"[:1024]
                    t.finished_at = datetime.utcnow()
                    session.add(t)
                    session.commit()
        except Exception:
            log.exception("[inn-suggest] failed to mark task as failed")


# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/inn-accept
# ---------------------------------------------------------------------------


@router.post(
    "/{applicant_id}/inn-accept",
    response_model=InnAcceptResponse,
    summary="Принять ИНН: проверить через ФНС, сохранить в applicant + пометить used",
)
async def inn_accept(
    applicant_id: int,
    payload: InnAcceptRequest,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> InnAcceptResponse:
    """
    Pack 28 Часть 2: переписан на NpdCandidate.

    Сценарии:
    1. ФНС подтвердил статус НПД (status=True) → сохраняем как раньше,
       npd_check_status=confirmed.
    2. ФНС вернул status=False (кандидат снялся) → переводим candidate
       в rejected_inactive, возвращаем 409.
    3. ФНС timeout → мягкий пропуск, npd_check_status=skipped_fns_unavailable.
    4. Pack 28 Часть 2 NEW: если candidate.npd_checked_at < 24 часа назад —
       пропускаем повторный запрос ФНС, npd_check_status=skipped_recently_verified.

    Идемпотентно: если applicant.inn == inn → 200 OK без перепроверки.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    inn = (payload.inn or "").strip()
    if not inn:
        raise HTTPException(status_code=400, detail="inn is required")

    # ----- Идемпотентность -----
    if applicant.inn == inn:
        cand = session.get(NpdCandidate, inn)
        if cand and cand.status in ("verified", "allocated"):
            cand.status = "used"
            cand.used_by_applicant_id = applicant.id
            cand.used_at = datetime.utcnow()
            cand.allocated_until = None
            session.add(cand)
            session.commit()
            log.info(
                "inn-accept: marked candidate inn=%s as used (idempotent fix)",
                inn,
            )
        return InnAcceptResponse(
            ok=True,
            applicant_id=applicant.id,
            inn=inn,
            npd_check_status="skipped_already_checked",
            npd_check_message="ИНН уже принят ранее, повторная проверка не выполнялась",
        )

    # ----- Поиск кандидата в npd_candidate -----
    cand = session.get(NpdCandidate, inn)
    if not cand:
        raise HTTPException(
            status_code=404,
            detail=(
                f"INN {inn} not found in npd_candidate pool. "
                "Refuse to write unknown INN. Возможно ИНН старый из SNRIP — "
                "Pack 28 Часть 2 их больше не выдаёт."
            ),
        )
    if cand.status == "used" and cand.used_by_applicant_id != applicant.id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"INN {inn} уже использован заявителем "
                f"id={cand.used_by_applicant_id}. Подберите другого кандидата."
            ),
        )
    if cand.status in ("rejected_ip", "rejected_inactive", "rejected_other"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Кандидат {inn} помечен как {cand.status} "
                f"(reason: {cand.rejection_reason or 'нет деталей'}). "
                "Подберите другого через ✨ ИНН."
            ),
        )

    # ----- Pack 18.2: проверка через ФНС API -----
    npd_check_status: Literal[
        "confirmed",
        "skipped_fns_unavailable",
        "skipped_already_checked",
        "skipped_recently_verified",
    ] = "confirmed"
    manual_check_url: Optional[str] = None
    npd_check_message: Optional[str] = None

    # Pack 28 Часть 2: пропускаем проверку если кандидат свежепроверен (<24 часов)
    if (
        cand.npd_checked_at
        and cand.npd_checked_at > datetime.utcnow() - timedelta(hours=24)
    ):
        npd_check_status = "skipped_recently_verified"
        npd_check_message = (
            f"Кандидат проверен через ФНС НПД API "
            f"{cand.npd_checked_at.isoformat()} — повторная проверка не нужна."
        )
        log.info(
            "inn-accept: skip ФНС re-check, candidate verified at %s",
            cand.npd_checked_at.isoformat(),
        )
    else:
        log.info("inn-accept: starting NPD check for inn=%s via ФНС API", inn)
        try:
            async with NpdStatusChecker() as checker:
                result = await checker.check(inn=inn)

            if not result.is_active:
                # ФНС подтвердил: НЕ плательщик. Переводим в rejected_inactive
                cand.status = "rejected_inactive"
                cand.npd_checked_at = datetime.utcnow()
                cand.npd_active = False
                cand.rejection_reason = (
                    f"ФНС at accept-time: {result.message or 'not active'}"
                )
                session.add(cand)
                session.commit()
                log.warning(
                    "inn-accept: ФНС вернул status=False для inn=%s "
                    "(сообщение: %s) — переведён в rejected_inactive",
                    inn, result.message,
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"ФНС сообщил что ИНН {inn} не является плательщиком "
                        f"НПД (сообщение: {result.message or 'нет деталей'}). "
                        "Кандидат помечен как rejected_inactive. "
                        "Подберите другого через ✨ ИНН."
                    ),
                )

            # ФНС подтвердил
            cand.npd_checked_at = datetime.utcnow()
            cand.npd_active = True
            log.info(
                "inn-accept: ФНС подтвердил статус НПД для inn=%s "
                "(registration_date=%s)",
                inn, result.registration_date,
            )

            # Если ФНС вернул реальную дату регистрации — обновляем candidate
            if result.registration_date and not cand.registration_date:
                cand.registration_date = result.registration_date

        except NpdStatusError as e:
            log.warning(
                "inn-accept: NpdStatusError для inn=%s, мягкий пропуск: %s",
                inn, e,
            )
            npd_check_status = "skipped_fns_unavailable"
            manual_check_url = _make_manual_check_url(inn)
            npd_check_message = (
                f"ФНС API временно недоступен ({e!s}). "
                f"ИНН выдан без проверки. Рекомендуем проверить вручную: "
                f"{manual_check_url}"
            )
        except HTTPException:
            raise
        except Exception as e:
            log.exception("inn-accept: unexpected error during NPD check")
            npd_check_status = "skipped_fns_unavailable"
            manual_check_url = _make_manual_check_url(inn)
            npd_check_message = (
                f"Не удалось выполнить проверку статуса НПД "
                f"({type(e).__name__}: {e}). ИНН выдан без проверки. "
                f"Рекомендуем проверить вручную: {manual_check_url}"
            )

    # ----- Транзакционная запись -----
    applicant.inn = inn
    if payload.home_address:
        applicant.home_address = payload.home_address
    if payload.kladr_code:
        applicant.inn_kladr_code = payload.kladr_code

    # Pack 28 Часть 2: registration_date берём из candidate если есть
    # (реальная дата из ФНС), иначе из payload (синтетическая из pipeline)
    if cand.registration_date:
        applicant.inn_registration_date = cand.registration_date
        log.info(
            "inn-accept: using REAL registration_date=%s from npd_candidate",
            cand.registration_date,
        )
    elif payload.inn_registration_date:
        applicant.inn_registration_date = payload.inn_registration_date

    if payload.inn_source:
        applicant.inn_source = payload.inn_source
    else:
        # Pack 32.0.3: always update inn_source on accept (was: elif not applicant.inn_source).
        # The previous elif left stale values when a manager regenerates an INN for an
        # applicant who already had inn_source set from a previous attempt.
        applicant.inn_source = (
            "npd_pool_real" if cand and cand.registration_date
            else "npd_pool_synthetic"
        )  # Pack 28.5: разделяем реальную/синтетическую дату

    cand.status = "used"
    cand.used_by_applicant_id = applicant.id
    cand.used_at = datetime.utcnow()
    cand.allocated_until = None

    session.add(applicant)
    session.add(cand)
    session.commit()

    log.info(
        "inn-accept: SUCCESS applicant_id=%s inn=%s region_kladr=%s npd_check=%s",
        applicant_id, inn, payload.kladr_code, npd_check_status,
    )
    return InnAcceptResponse(
        ok=True,
        applicant_id=applicant.id,
        inn=inn,
        npd_check_status=npd_check_status,
        manual_check_url=manual_check_url,
        npd_check_message=npd_check_message,
    )


# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/regen-address
# Pack 18.8: перегенерировать случайный адрес в том же городе что у ИНН
# (БЕЗ ИЗМЕНЕНИЙ в Pack 28 Часть 2)
# ---------------------------------------------------------------------------


@router.post(
    "/{applicant_id}/regen-address",
    response_model=RegenAddressResponse,
    summary="Сгенерировать новый случайный адрес из того же города куда привязан ИНН",
)
def regen_address(
    applicant_id: int,
    payload: RegenAddressRequest,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> RegenAddressResponse:
    """Pack 18.8: помогает менеджеру выдать клиенту другой адрес без перевыдачи ИНН."""
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    kladr_code = (payload.kladr_code or applicant.inn_kladr_code or "").strip()
    if not kladr_code:
        raise HTTPException(
            status_code=400,
            detail=(
                "Сначала сгенерируйте ИНН — без него неизвестно для какого "
                "города делать адрес."
            ),
        )
    if kladr_code not in KNOWN_REGIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"KLADR-код {kladr_code} не в списке поддерживаемых городов. "
                "Перевыдайте ИНН для актуального формата."
            ),
        )

    rng = random.Random()
    addr = generate_address(kladr_code, rng)
    return RegenAddressResponse(
        home_address=addr.full,
        kladr_code=addr.kladr_code,
    )


# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/regen-work-history
# Pack 30.0 (09.05.2026): endpoint-обёртка над suggest_work_history.
# Pack 33.3 (10.05.2026): честная диагностика причины None.
#
# Сервис suggest_work_history() из app.services.work_history_generator
# существует с Pack 19.1a и был расширен в Pack 20.3 (duties-snapshot).
# Импорт стоит наверху файла с момента Pack 19.1a, но сам endpoint
# никогда не был зарегистрирован — фронт получал 404. Pack 30.0 ровно
# одну вещь и сделал: дописал обёртку.
#
# Контракт совпадает с frontend/lib/api.ts:regenerateWorkHistory():
#   POST /api/admin/applicants/{applicant_id}/regen-work-history
#   → 200 WorkHistorySuggestion
#
# UX: сервис не пишет в БД. Фронт получает массив records[] и предлагает
# менеджеру нажать «Сохранить» (PATCH /admin/applicants/{id} с
# work_history[]).
# ---------------------------------------------------------------------------


def _diagnose_work_history_failure(
    applicant: Applicant, session: Session,
) -> str:
    """
    Pack 33.3: когда suggest_work_history вернул None, повторно прогоняем
    ключевые шаги резолва чтобы определить ТОЧНУЮ причину и выдать менеджеру
    осмысленную ошибку вместо дезориентирующего "Pack 19.0 не применён".

    Возможные причины:
      A. Specialty не определилась — действительно проблема с education /
         position_id / specialty-seed (как раньше)
      B. Specialty есть, но в legend_company НЕТ компаний под её
         primary_specialty_id ни в одном регионе → нужен seed под эту
         специальность (как Pack 33.3 для PR=42.03.01)
      C. Specialty есть, компании есть, но Position под этот (specialty, level)
         отсутствует → менеджер должен создать Position в админке
      D. Что-то другое внутри генератора (редко)

    Возвращает текст для HTTPException.detail. Не бросает исключений сам.
    """
    try:
        specialty, _pattern = _resolve_specialty(applicant, session)
    except Exception as e:
        log.warning(
            "regen_work_history diagnose: _resolve_specialty raised %r — "
            "fallback to generic 422", e,
        )
        return (
            "Внутренняя ошибка при определении специальности. "
            "Проверь логи Railway по applicant_id для деталей."
        )

    if specialty is None:
        # Причина A — старое поведение
        return (
            "Не удалось определить специальность для подбора опыта работы. "
            "Проверь что у клиента заполнено образование (applicant.education) "
            "или назначена должность в заявке (application.position_id), "
            "и что Pack 19.0 specialty-seed применён."
        )

    # Specialty определилась — проверяем legend_company
    companies_count = session.exec(
        select(LegendCompany)
        .where(LegendCompany.is_active == True)  # noqa: E712
        .where(LegendCompany.primary_specialty_id == specialty.id)
    ).all()
    if not companies_count:
        # Причина B — это случай Ся Инь до Pack 33.3 для PR
        return (
            f"Специальность определилась как «{specialty.code} {specialty.name}» "
            f"(specialty_id={specialty.id}), но в таблице legend_company "
            f"нет ни одной активной компании под эту специальность ни в одном "
            f"регионе. Нужен seed-патч под эту специальность "
            f"(как Pack 33.3 для PR/42.03.01). "
            f"После seed повторите попытку."
        )

    # Compute region for completeness
    region_code = _get_region_code(applicant)

    # Specialty есть, компании есть — значит проблема в Position под уровень.
    # Проверяем: есть ли вообще хоть одна Position под эту специальность.
    positions_for_specialty = session.exec(
        select(Position)
        .where(Position.is_active == True)  # noqa: E712
        .where(Position.primary_specialty_id == specialty.id)
    ).all()
    if not positions_for_specialty:
        # Причина C — нет Position под специальность вообще
        return (
            f"Специальность определилась как «{specialty.code} {specialty.name}» "
            f"(specialty_id={specialty.id}), компаний "
            f"{len(companies_count)} в БД, но нет ни одной активной Position "
            f"под эту специальность. Создайте Position в админке "
            f"(Настройки → Должности → Добавить должность с этой specialty) "
            f"либо засейте CareerTrack под specialty_id={specialty.id} "
            f"для всех 4 уровней."
        )

    # Position есть, но всё равно None — причина D (редкий случай)
    levels = sorted({p.level for p in positions_for_specialty if p.level})
    return (
        f"Специальность «{specialty.code} {specialty.name}» определилась, "
        f"в legend_company {len(companies_count)} компаний, "
        f"в position {len(positions_for_specialty)} должностей "
        f"(уровни {levels}), region_code={region_code!r}. "
        f"Но генератор work_history всё равно вернул None. "
        f"Это редкий внутренний случай — проверь логи Railway по applicant_id."
    )


@router.post(
    "/{applicant_id}/regen-work-history",
    response_model=WorkHistorySuggestion,
    summary="Подобрать опыт работы (work_history) на основе specialty + region клиента",
)
def regen_work_history(
    applicant_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> WorkHistorySuggestion:
    """
    Pack 30.0: обёртка над suggest_work_history().
    Pack 33.3: при None выдаёт честную причину (через _diagnose_work_history_failure).

    Возможные ошибки:
      - 404 если applicant не найден
      - 422 с разными текстами в зависимости от причины None
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    result = suggest_work_history(applicant, session)
    if result is None:
        # Pack 33.3: вместо одного дезориентирующего текста — точная диагностика
        detail = _diagnose_work_history_failure(applicant, session)
        log.warning(
            "regen_work_history: applicant_id=%s -> 422 %s",
            applicant_id, detail,
        )
        raise HTTPException(status_code=422, detail=detail)
    return result
