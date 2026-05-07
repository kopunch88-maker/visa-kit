"""
Pack 28 Часть 2 — admin endpoints для управления пулом самозанятых.

Endpoints:
  GET  /admin/npd-pool/stats              — стата пула (всего, по статусам, по регионам)
  GET  /admin/npd-pool/tasks/{task_id}    — статус задачи refill (для поллинга)
  POST /admin/npd-pool/refill-all         — глобальный refill (Manager auth)
  POST /admin/npd-pool/cron-refill        — то же самое но с Bearer-токеном (для GitHub Actions)

Часть Б добавит UI на /admin/settings/npd-pool с кнопкой "Обновить весь пул"
и таблицей статистики по регионам.

GitHub Actions воркфлоу .github/workflows/npd-pool-refill.yml зовёт
cron-refill по расписанию (вс 03:00 UTC) с секретом NPD_POOL_CRON_TOKEN
из переменных окружения Railway.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    status,
)
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import engine, get_session
from app.models import NpdPoolStats, NpdRefillTask
from app.services.inn_generator.npd_pool import (
    KEY_REGIONS,
    get_pool_stats,
    run_global_refill,
    run_lazy_region_refill,
)

from .dependencies import require_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/npd-pool", tags=["npd-pool"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NpdRefillTaskResponse(BaseModel):
    id: int
    kind: str
    status: str
    region_code: Optional[str] = None

    progress_text: Optional[str] = None
    progress_current: int = 0
    progress_total: int = 0

    result_inn: Optional[str] = None
    result_region_code: Optional[str] = None

    verified_added: int = 0
    egrul_rejected: int = 0
    npd_rejected: int = 0
    revalidated_total: int = 0
    revalidated_invalidated: int = 0

    error: Optional[str] = None

    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, task: NpdRefillTask) -> "NpdRefillTaskResponse":
        return cls(
            id=task.id or 0,
            kind=task.kind,
            status=task.status,
            region_code=task.region_code,
            progress_text=task.progress_text,
            progress_current=task.progress_current,
            progress_total=task.progress_total,
            result_inn=task.result_inn,
            result_region_code=task.result_region_code,
            verified_added=task.verified_added,
            egrul_rejected=task.egrul_rejected,
            npd_rejected=task.npd_rejected,
            revalidated_total=task.revalidated_total,
            revalidated_invalidated=task.revalidated_invalidated,
            error=task.error,
            created_at=task.created_at,
            started_at=task.started_at,
            finished_at=task.finished_at,
        )


class GlobalRefillRequest(BaseModel):
    target_per_region: int = 5
    revalidate_first: bool = True
    regions: Optional[list[str]] = None  # None = KEY_REGIONS


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=NpdPoolStats)
def npd_pool_stats(
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> NpdPoolStats:
    """Сводная статистика по пулу: всего, по статусам, verified по регионам."""
    return get_pool_stats(session)


# ---------------------------------------------------------------------------
# GET /tasks/{task_id}
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}", response_model=NpdRefillTaskResponse)
def get_npd_refill_task(
    task_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> NpdRefillTaskResponse:
    """Статус задачи refill — для поллинга из фронта."""
    task = session.get(NpdRefillTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return NpdRefillTaskResponse.from_model(task)


# ---------------------------------------------------------------------------
# POST /refill-all (Manager auth)
# ---------------------------------------------------------------------------


@router.post("/refill-all", response_model=NpdRefillTaskResponse)
def npd_pool_refill_all(
    payload: GlobalRefillRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user=Depends(require_manager),
) -> NpdRefillTaskResponse:
    """
    Запустить глобальный refill в BackgroundTask.
    Возвращает task_id, фронт поллит /tasks/{id} до завершения.

    Шаги (внутри run_global_refill):
      1. Ревалидация всех verified (если revalidate_first=True): EGRUL+NPD
         перепроверка → invalid → status='rejected_*'
      2. Для каждого региона из regions (или KEY_REGIONS):
         если verified < target_per_region → refill_pool_for_region до target
    """
    regions = payload.regions or list(KEY_REGIONS)

    task = NpdRefillTask(
        kind="global",
        status="pending",
        progress_text="Подготовка...",
        progress_total=len(regions),
        triggered_by=f"manager:{getattr(user, 'id', '?')}",
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    log.info(
        "[npd-pool] starting global refill task_id=%s regions=%d revalidate=%s",
        task.id, len(regions), payload.revalidate_first,
    )

    background_tasks.add_task(
        _run_global_refill_bg,
        task_id=task.id,
        regions=regions,
        target_per_region=payload.target_per_region,
        revalidate_first=payload.revalidate_first,
    )

    return NpdRefillTaskResponse.from_model(task)


# ---------------------------------------------------------------------------
# POST /cron-refill (Bearer-token auth для GitHub Actions)
# ---------------------------------------------------------------------------


@router.post("/cron-refill", response_model=NpdRefillTaskResponse)
def npd_pool_cron_refill(
    background_tasks: BackgroundTasks,
    x_cron_token: Optional[str] = Header(default=None, alias="X-Cron-Token"),
    session: Session = Depends(get_session),
) -> NpdRefillTaskResponse:
    """
    Тот же refill-all но с проверкой токена вместо Manager auth.
    GitHub Actions присылает заголовок X-Cron-Token = NPD_POOL_CRON_TOKEN.

    Если переменная окружения NPD_POOL_CRON_TOKEN не задана — endpoint
    отвечает 503 (отключён в этом окружении).
    """
    expected = os.getenv("NPD_POOL_CRON_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cron refill disabled (NPD_POOL_CRON_TOKEN not set)",
        )
    if not x_cron_token or x_cron_token.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron token",
        )

    task = NpdRefillTask(
        kind="global",
        status="pending",
        progress_text="Подготовка (cron)...",
        progress_total=len(KEY_REGIONS),
        triggered_by="github_actions_cron",
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    log.info("[npd-pool] starting CRON global refill task_id=%s", task.id)

    background_tasks.add_task(
        _run_global_refill_bg,
        task_id=task.id,
        regions=list(KEY_REGIONS),
        target_per_region=5,
        revalidate_first=True,
    )

    return NpdRefillTaskResponse.from_model(task)


# ---------------------------------------------------------------------------
# Background task wrapper
# ---------------------------------------------------------------------------


def _run_global_refill_bg(
    task_id: int,
    regions: list[str],
    target_per_region: int,
    revalidate_first: bool,
) -> None:
    """
    Sync wrapper для BackgroundTasks (FastAPI ожидает sync ИЛИ async, мы делаем
    sync с собственной session т.к. BackgroundTasks выполняется ВНЕ HTTP контекста
    после возврата response — get_session уже сделал commit и закрыл session).

    run_global_refill сам делает asyncio.run() внутри.
    """
    import asyncio

    log.info("[npd-pool] BG task_id=%s starting", task_id)
    try:
        with Session(engine) as session:
            asyncio.run(
                run_global_refill(
                    session=session,
                    task_id=task_id,
                    regions=regions,
                    target_per_region=target_per_region,
                    revalidate_first=revalidate_first,
                )
            )
        log.info("[npd-pool] BG task_id=%s finished", task_id)
    except Exception as e:
        log.exception("[npd-pool] BG task_id=%s FAILED: %s", task_id, e)
        # Помечаем task как failed (если ещё не успел сам)
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
            log.exception("[npd-pool] failed to mark task as failed")


# ============================================================================
# Pack 28.6 — кнопка "+ Добавить" по региону
# ============================================================================

@router.post(
    "/region/{region_code}/refill",
    response_model=NpdRefillTaskResponse,
)
async def refill_region(
    region_code: str,
    background_tasks: BackgroundTasks,
    add_target: int = 5,
    session: Session = Depends(get_session),
    user=Depends(require_manager),
):
    """
    Pack 28.6: запустить lazy refill для конкретного региона из админки.

    Параметр add_target — сколько ДОПОЛНИТЕЛЬНО verified кандидатов искать
    (поверх текущего количества). По умолчанию +5.

    Idempotency: если для этого региона уже есть pending/running task младше
    30 мин — переиспользуем её (не дублируем refill).
    """
    # Валидация region_code (2 цифры)
    if not (region_code.isdigit() and len(region_code) == 2):
        raise HTTPException(400, f"region_code должен быть 2 цифрами, получено: {region_code!r}")

    if add_target < 1 or add_target > 20:
        raise HTTPException(400, "add_target должен быть от 1 до 20")

    # Считаем текущее количество verified в регионе
    from sqlmodel import select
    current_verified = session.exec(
        select(NpdCandidate)
        .where(NpdCandidate.region_code == region_code)
        .where(NpdCandidate.status == "verified")
    ).all()
    current_count = len(current_verified)
    absolute_target = current_count + add_target

    log.info(
        f"[refill_region] region={region_code} current={current_count} "
        f"add={add_target} absolute_target={absolute_target}"
    )

    # Idempotency: ищем активную lazy_region task на этот регион младше 30 мин
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    existing = session.exec(
        select(NpdRefillTask)
        .where(NpdRefillTask.kind == "lazy_region")
        .where(NpdRefillTask.region_code == region_code)
        .where(NpdRefillTask.created_at >= cutoff)
        .where(NpdRefillTask.status.in_(["pending", "running"]))
        .order_by(NpdRefillTask.created_at.desc())
    ).first()

    if existing:
        log.info(
            f"[refill_region] reusing existing task {existing.id} for region={region_code}"
        )
        return existing

    # Создаём новую задачу
    task = NpdRefillTask(
        kind="lazy_region",
        status="pending",
        region_code=region_code,
        progress_text=f"Поиск чистых самозанятых (регион {region_code}, +{add_target})...",
        progress_total=absolute_target,
        progress_current=current_count,
        triggered_by=f"admin_refill_region:{getattr(user, 'id', '?')}",
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    # Запускаем background task с absolute_target
    background_tasks.add_task(
        _run_region_refill_bg,
        task_id=task.id,
        region_code=region_code,
        absolute_target=absolute_target,
    )

    return task


def _run_region_refill_bg(task_id: int, region_code: str, absolute_target: int) -> None:
    """
    Pack 28.6: sync wrapper для BackgroundTasks (вызывает run_lazy_region_refill
    с заданным absolute_target). Копирует паттерн из inn_generation._run_lazy_refill_bg.
    """
    import asyncio
    from app.db.session import engine
    from sqlmodel import Session

    log.info(
        f"[refill_region] BG task_id={task_id} region={region_code} target={absolute_target} starting"
    )
    try:
        with Session(engine) as session:
            asyncio.run(
                run_lazy_region_refill(
                    session=session,
                    task_id=task_id,
                    region_code=region_code,
                    target=absolute_target,
                )
            )
    except Exception as e:
        log.exception(
            f"[refill_region] BG task_id={task_id} FAILED: {e}"
        )
        # Помечаем task как failed
        try:
            with Session(engine) as session:
                from app.models import NpdRefillTask
                t = session.get(NpdRefillTask, task_id)
                if t:
                    t.status = "failed"
                    t.error = f"{type(e).__name__}: {str(e)[:512]}"
                    t.finished_at = datetime.utcnow()
                    session.add(t)
                    session.commit()
        except Exception:
            pass

