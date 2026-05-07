"""
Pack 28.5 — endpoint'ы для уточнения реальной даты регистрации НПД.

POST /admin/applicants/{id}/refine-inn-date
    Стартует BackgroundTask: бинпоиск даты регистрации НПД через ФНС API.
    Возвращает task_id (NpdRefillTask с kind='refine_date'). UI поллит
    /admin/refine-tasks/{id} каждые 5-10 сек до status='done'.

    После успеха:
      - applicant.inn_registration_date обновляется на найденную дату
      - applicant.inn_source меняется с 'npd_pool_synthetic' на 'npd_pool_real'
      - Если соответствующий npd_candidate ещё в БД (used_by_applicant_id=this) —
        у него тоже обновляется registration_date

GET /admin/refine-tasks/{task_id}
    Возвращает текущий статус задачи (pending/running/done/failed) +
    progress_text/progress_current/progress_total для прогресс-бара.

Idempotency: если для этого applicant'а уже есть refine-задача младше 30 мин
со статусом pending/running — переиспользуем её task_id.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import Applicant, NpdCandidate, NpdRefillTask
from .dependencies import require_manager
from app.services.inn_generator.npd_date_finder import (
    binary_search_registration_date,
    NPD_LAW_START,
    ESTIMATED_TOTAL_STEPS,
)
from app.services.inn_generator.npd_status import NpdStatusChecker, NpdStatusError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["inn-date-refine"])


# === Response models ===

class RefineTaskResponse(BaseModel):
    """Ответ для UI поллинга — те же поля что NpdRefillTaskResponse."""
    id: int
    kind: str
    status: str
    region_code: Optional[str] = None

    progress_text: Optional[str] = None
    progress_current: int = 0
    progress_total: int = 0

    result_inn: Optional[str] = None
    result_region_code: Optional[str] = None
    result_registration_date: Optional[date] = None  # Pack 28.5

    verified_added: int = 0
    egrul_rejected: int = 0
    npd_rejected: int = 0
    revalidated_total: int = 0
    revalidated_invalidated: int = 0

    error: Optional[str] = None

    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# === Background runner ===

async def _run_refine_task(task_id: int, applicant_id: int, inn: str) -> None:
    """
    Background task: запускает бинпоиск даты, обновляет npd_refill_task
    и applicant.inn_registration_date по результату.

    Создаёт собственную Session — за пределами HTTP request контекста
    (Правило 36: использовать Session(engine), не get_session()).
    """
    from app.db.session import engine
    from sqlmodel import Session

    log.info(f"[refine_task:{task_id}] starting for applicant={applicant_id} inn={inn}")

    with Session(engine) as session:
        task = session.get(NpdRefillTask, task_id)
        if not task:
            log.error(f"[refine_task:{task_id}] task not found in DB")
            return

        task.status = "running"
        task.started_at = datetime.utcnow()
        task.progress_text = "Подключаюсь к ФНС..."
        task.progress_current = 0
        task.progress_total = ESTIMATED_TOTAL_STEPS
        session.add(task)
        session.commit()

        # Прогресс-callback пишет в БД при каждом шаге.
        # Используем замыкание чтобы захватить session.
        async def on_progress(step: int, total: int, left: date, right: date, mid: date):
            # Re-fetch task — Session мог быть зафиксирован, нужна свежая копия
            with Session(engine) as s:
                t = s.get(NpdRefillTask, task_id)
                if t is None:
                    return
                range_days = (right - left).days
                t.progress_current = step
                t.progress_total = total
                t.progress_text = (
                    f"Шаг {step}/{total}: проверяю {mid.isoformat()} "
                    f"(диапазон {range_days} дн.)"
                )
                s.add(t)
                s.commit()

        try:
            async with NpdStatusChecker() as checker:
                registration_date = await binary_search_registration_date(
                    checker,
                    inn,
                    on_progress=on_progress,
                )
        except NpdStatusError as e:
            log.exception(f"[refine_task:{task_id}] NpdStatusError: {e}")
            with Session(engine) as s:
                t = s.get(NpdRefillTask, task_id)
                if t:
                    t.status = "failed"
                    t.error = f"FNS API error: {str(e)[:512]}"
                    t.finished_at = datetime.utcnow()
                    s.add(t)
                    s.commit()
            return
        except Exception as e:
            log.exception(f"[refine_task:{task_id}] unexpected error")
            with Session(engine) as s:
                t = s.get(NpdRefillTask, task_id)
                if t:
                    t.status = "failed"
                    t.error = f"{type(e).__name__}: {str(e)[:512]}"
                    t.finished_at = datetime.utcnow()
                    s.add(t)
                    s.commit()
            return

        # === Успех — обновляем applicant и candidate
        with Session(engine) as s:
            t = s.get(NpdRefillTask, task_id)
            if not t:
                return

            if registration_date is None:
                t.status = "failed"
                t.error = (
                    "Бинпоиск завершился: ИНН не активен в НПД сегодня. "
                    "Возможно человек снялся с учёта."
                )
                t.finished_at = datetime.utcnow()
                s.add(t)
                s.commit()
                return

            # Обновляем applicant
            applicant = s.get(Applicant, applicant_id)
            if applicant:
                old_date = applicant.inn_registration_date
                applicant.inn_registration_date = registration_date
                applicant.inn_source = "npd_pool_real"
                s.add(applicant)
                log.info(
                    f"[refine_task:{task_id}] applicant {applicant_id}: "
                    f"date {old_date} → {registration_date}, source → npd_pool_real"
                )

            # Обновляем candidate (если ещё в БД — used_by_applicant_id=applicant_id)
            cand = s.exec(
                select(NpdCandidate).where(NpdCandidate.inn == inn)
            ).first()
            if cand:
                cand.registration_date = registration_date
                s.add(cand)
                log.info(
                    f"[refine_task:{task_id}] candidate {inn}: "
                    f"registration_date → {registration_date}"
                )

            # Финал task'а
            t.status = "done"
            t.result_inn = inn
            t.result_registration_date = registration_date
            t.progress_text = f"Готово. Реальная дата: {registration_date.isoformat()}"
            t.progress_current = t.progress_total
            t.finished_at = datetime.utcnow()
            s.add(t)
            s.commit()

        log.info(
            f"[refine_task:{task_id}] DONE: applicant={applicant_id} "
            f"inn={inn} registration_date={registration_date}"
        )


# === Endpoints ===

@router.post(
    "/applicants/{applicant_id}/refine-inn-date",
    response_model=RefineTaskResponse,
)
async def refine_inn_date(
    applicant_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Pack 28.5: запустить бинпоиск точной даты регистрации НПД.

    Длительность ~6-7 минут (12 запросов × 31 сек).
    UI поллит /admin/refine-tasks/{task_id} каждые 5-10 сек.

    Idempotency: если для этого applicant'а уже есть pending/running refine-task
    младше 30 мин — переиспользуем её task_id (не дублируем бинпоиск).
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(404, f"Applicant {applicant_id} not found")
    if not applicant.inn:
        raise HTTPException(
            400,
            "У applicant нет ИНН — сначала сгенерируйте через ✨ ИНН"
        )

    # Idempotency check
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    existing = session.exec(
        select(NpdRefillTask)
        .where(NpdRefillTask.kind == "refine_date")
        .where(NpdRefillTask.result_inn == applicant.inn)
        .where(NpdRefillTask.created_at >= cutoff)
        .where(NpdRefillTask.status.in_(["pending", "running"]))
        .order_by(NpdRefillTask.created_at.desc())
    ).first()

    if existing:
        log.info(
            f"[refine_endpoint] reusing existing task {existing.id} "
            f"for applicant={applicant_id} inn={applicant.inn}"
        )
        return existing

    # Создаём новую задачу
    task = NpdRefillTask(
        kind="refine_date",
        status="pending",
        result_inn=applicant.inn,  # для idempotency lookup
        progress_text="Задача поставлена в очередь...",
        progress_current=0,
        progress_total=ESTIMATED_TOTAL_STEPS,
        triggered_by=f"manager_refine_applicant_{applicant_id}",
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    log.info(
        f"[refine_endpoint] created task {task.id} for applicant={applicant_id} "
        f"inn={applicant.inn}"
    )

    # Запускаем background task
    background_tasks.add_task(_run_refine_task, task.id, applicant_id, applicant.inn)

    return task


@router.get(
    "/refine-tasks/{task_id}",
    response_model=RefineTaskResponse,
)
async def get_refine_task(
    task_id: int = Path(..., gt=0),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """Pack 28.5: получить статус refine-задачи (для поллинга UI)."""
    task = session.get(NpdRefillTask, task_id)
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    return task
