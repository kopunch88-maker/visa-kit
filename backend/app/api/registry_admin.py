"""
Pack 17.2.4 — API endpoints для управления локальной БД реестра самозанятых.

Endpoints:
- POST /api/admin/registry/import-self-employed — запустить импорт дампа ФНС
- GET  /api/admin/registry/import-status — статистика + статус последнего импорта
- GET  /api/admin/registry/imports — история импортов
- GET  /api/admin/registry/preview — посмотреть несколько записей в БД (для отладки)

Импорт занимает 10-30 минут (~1-3 ГБ распакованного XML), поэтому запускается
в BackgroundTasks. Прогресс смотрим через /import-status.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.self_employed_registry import (
    SelfEmployedRegistryStats,
    RegistryImportLogRead,
    RegistryImportLog,
    StartImportRequest,
)
from app.services.inn_generator.dump_importer import (
    import_dump,
    resolve_latest_dump_url,
)
from app.services.inn_generator.pipeline import get_registry_stats

from .dependencies import require_manager


log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/registry",
    tags=["admin: self-employed registry"],
    dependencies=[Depends(require_manager)],
)


# ---------------------------------------------------------------------------
# POST /admin/registry/import-self-employed
# ---------------------------------------------------------------------------

@router.post("/import-self-employed", response_model=RegistryImportLogRead)
def start_import(
    payload: StartImportRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Запускает импорт открытого дампа ФНС.

    - Если payload.dump_url=None — берётся свежайший дамп с портала ФНС
    - purge_old=True (по умолчанию) — удаляет НЕиспользованные записи
      перед импортом. Использованные ИНН (is_used=true) не трогаются.
    - Импорт идёт в фоне (BackgroundTasks). Размер распакованного XML
      может быть до 3 ГБ, поэтому занимает 10-30 минут.

    Возвращает запись RegistryImportLog со статусом 'queued'.
    Чтобы узнать прогресс — GET /admin/registry/import-status или
    GET /admin/registry/imports.
    """
    # Проверяем что не запущен другой импорт
    running_q = session.execute(
        text("SELECT id FROM registry_import_log WHERE status = 'running' LIMIT 1")
    ).first()
    if running_q is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Уже запущен импорт (log_id={running_q[0]}). "
                f"Дождитесь завершения или проверьте логи Railway."
            ),
        )

    # Резолвим URL прямо сейчас (быстро) — чтобы вернуть его в ответе
    try:
        dump_url = payload.dump_url or resolve_latest_dump_url()
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось получить URL дампа с портала ФНС: {e}",
        )

    # Создаём предварительный лог чтобы вернуть его клиенту
    from datetime import datetime
    from app.services.inn_generator.dump_importer import parse_dump_date_from_url

    placeholder = RegistryImportLog(
        dump_url=dump_url,
        dump_date=parse_dump_date_from_url(dump_url),
        started_at=datetime.utcnow(),
        status="queued",
    )
    session.add(placeholder)
    session.commit()
    session.refresh(placeholder)

    # Запускаем в фоне
    background_tasks.add_task(
        _background_import_runner,
        dump_url=dump_url,
        purge_old=payload.purge_old,
        placeholder_id=placeholder.id,
    )

    return RegistryImportLogRead.model_validate(placeholder, from_attributes=True)


def _background_import_runner(
    dump_url: str,
    purge_old: bool,
    placeholder_id: int,
) -> None:
    """
    Запускается из BackgroundTasks. Создаёт собственную сессию БД
    (нельзя переиспользовать сессию из request — она уже закрыта).
    """
    from app.db.session import engine
    from sqlmodel import Session as SqlmodelSession

    log.info(f"[registry-import] BG task started for dump_url={dump_url}")

    with SqlmodelSession(engine) as session:
        # Удаляем placeholder (он создавался только чтобы вернуть id клиенту)
        session.execute(
            text("DELETE FROM registry_import_log WHERE id = :id"),
            {"id": placeholder_id},
        )
        session.commit()

        try:
            log_entry = import_dump(
                session=session,
                dump_url=dump_url,
                purge_old=purge_old,
            )
            log.info(f"[registry-import] BG task finished: log_id={log_entry.id}, status={log_entry.status}")
        except Exception as e:
            log.exception(f"[registry-import] BG task FAILED: {e}")


# ---------------------------------------------------------------------------
# GET /admin/registry/import-status
# ---------------------------------------------------------------------------

@router.get("/import-status", response_model=SelfEmployedRegistryStats)
def get_import_status(session: Session = Depends(get_session)):
    """
    Статистика реестра + статус последнего импорта.
    """
    stats = get_registry_stats(session)

    # Последний импорт (любой)
    last_log = session.exec(
        select(RegistryImportLog)
        .order_by(RegistryImportLog.started_at.desc())
        .limit(1)
    ).first()

    return SelfEmployedRegistryStats(
        total_records=stats["total_records"],
        available_records=stats["available_records"],
        used_records=stats["used_records"],
        last_import_date=last_log.started_at if last_log else None,
        last_import_status=last_log.status if last_log else None,
        last_import_dump_date=last_log.dump_date if last_log else None,
    )


# ---------------------------------------------------------------------------
# GET /admin/registry/imports
# ---------------------------------------------------------------------------

@router.get("/imports", response_model=List[RegistryImportLogRead])
def list_imports(
    limit: int = 20,
    session: Session = Depends(get_session),
):
    """История последних импортов (новые сверху)."""
    rows = session.exec(
        select(RegistryImportLog)
        .order_by(RegistryImportLog.started_at.desc())
        .limit(limit)
    ).all()
    return [
        RegistryImportLogRead.model_validate(r, from_attributes=True)
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /admin/registry/preview
# ---------------------------------------------------------------------------

@router.get("/preview")
def preview_records(
    limit: int = 5,
    only_unused: bool = True,
    session: Session = Depends(get_session),
):
    """
    Предпросмотр нескольких записей в self_employed_registry.
    Для отладки/проверки что импорт правильно отработал.
    """
    where = "WHERE is_used = FALSE" if only_unused else ""
    rows = session.execute(
        text(f"""
            SELECT inn, region_code, full_name, support_begin_date,
                   registry_create_date, imported_at, is_used
            FROM self_employed_registry
            {where}
            ORDER BY imported_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()

    return {
        "count": len(rows),
        "records": [
            {
                "inn": r[0],
                "region_code": r[1],
                "full_name": r[2],
                "support_begin_date": r[3].isoformat() if r[3] else None,
                "registry_create_date": r[4].isoformat() if r[4] else None,
                "imported_at": r[5].isoformat() if r[5] else None,
                "is_used": r[6],
            }
            for r in rows
        ],
    }
