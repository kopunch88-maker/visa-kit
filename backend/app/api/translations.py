"""
Pack 15 — Translation API endpoints.

Endpoints для управления переводами документов на испанский.

POST   /admin/applications/{id}/translate            — старт перевода пакета
POST   /admin/applications/{id}/translate/{kind}     — перевод одного документа
GET    /admin/applications/{id}/translations         — список со статусами
GET    /admin/applications/{id}/translations/zip     — все DONE одним архивом
GET    /admin/applications/{id}/translations/{kind}/download — один файл
DELETE /admin/applications/{id}/translations         — удалить все (для retry)
"""

import io
import logging
import zipfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import (
    Application,
    Translation,
    TranslationKind,
    TranslationStatus,
)
from app.services.storage import get_storage
from app.services.translation import (
    run_translate_package,
    ALL_KINDS,
    KIND_CONFIG,
)

from .dependencies import require_manager

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/applications",
    tags=["translations"],
    dependencies=[Depends(require_manager)],
)


# ============================================================================
# Helpers
# ============================================================================

def _enrich_translation(tr: Translation) -> dict:
    """Превращает Translation в JSON-ответ с signed URL (если DONE)."""
    download_url: Optional[str] = None
    if tr.status == TranslationStatus.DONE and tr.storage_key:
        try:
            storage = get_storage()
            download_url = storage.get_url(tr.storage_key, expires_in=3600)
        except Exception as e:
            log.warning(f"Failed to generate URL for {tr.storage_key}: {e}")

    return {
        "id": tr.id,
        "kind": tr.kind,
        "status": tr.status,
        "file_name": tr.file_name,
        "file_size": tr.file_size,
        "error_message": tr.error_message,
        "created_at": tr.created_at,
        "completed_at": tr.completed_at,
        "download_url": download_url,
    }


def _delete_translation_files(translations: list[Translation]) -> None:
    """Удаляет R2-объекты для списка переводов. Ошибки логируются, не пробрасываются."""
    storage = get_storage()
    for tr in translations:
        if tr.storage_key:
            try:
                storage.delete(tr.storage_key)
                log.info(f"[translations] Deleted R2 object {tr.storage_key}")
            except Exception as e:
                log.warning(f"[translations] Failed to delete {tr.storage_key}: {e}")


def _has_active_translations(session: Session, application_id: int) -> bool:
    """True если есть записи в статусе PENDING или IN_PROGRESS."""
    active = session.exec(
        select(Translation)
        .where(Translation.application_id == application_id)
        .where(Translation.status.in_([
            TranslationStatus.PENDING,
            TranslationStatus.IN_PROGRESS,
        ]))
    ).first()
    return active is not None


# ============================================================================
# POST: старт перевода всего пакета
# ============================================================================

@router.post("/{app_id}/translate")
def start_package_translation(
    app_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Стартует перевод всего пакета (10 документов) в фоне.

    Поведение:
    - Если есть PENDING/IN_PROGRESS — 409 (уже запущено)
    - Если есть DONE/FAILED — 409 (нужно сначала /translate/retry для очистки)
    - Иначе создаёт 10 записей PENDING + запускает BackgroundTasks
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    # Проверка: нет ли вообще никаких переводов?
    existing = session.exec(
        select(Translation).where(Translation.application_id == app_id)
    ).all()

    if existing:
        active_count = sum(
            1 for t in existing
            if t.status in (TranslationStatus.PENDING, TranslationStatus.IN_PROGRESS)
        )
        if active_count > 0:
            raise HTTPException(
                409,
                detail=f"Translation already in progress ({active_count} pending/in_progress)",
            )
        raise HTTPException(
            409,
            detail="Translations already exist. Use DELETE /translations first to retry.",
        )

    # Создаём 10 записей PENDING
    now = datetime.utcnow()
    for kind in ALL_KINDS:
        tr = Translation(
            application_id=app_id,
            kind=kind,
            status=TranslationStatus.PENDING,
            created_at=now,
        )
        session.add(tr)
    session.commit()

    log.info(f"[translations] Created {len(ALL_KINDS)} PENDING records for app {app_id}")

    # Запускаем фоновую задачу
    background_tasks.add_task(run_translate_package, app_id, None)

    return {
        "status": "started",
        "kinds_count": len(ALL_KINDS),
    }


# ============================================================================
# POST: перевод одного документа (или повторный для одного kind)
# ============================================================================

@router.post("/{app_id}/translate/{kind}")
def translate_single_document(
    app_id: int,
    kind: TranslationKind,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Переводит один документ указанного типа.

    Поведение:
    - Если для этого kind есть PENDING/IN_PROGRESS — 409
    - Если есть DONE/FAILED — удаляем (включая R2-объект) и создаём заново
    - Если нет записи — создаём PENDING

    Запускает BackgroundTasks только для одного kind.
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    # Существующая запись для этого kind?
    existing = session.exec(
        select(Translation)
        .where(Translation.application_id == app_id)
        .where(Translation.kind == kind)
    ).first()

    if existing:
        if existing.status in (TranslationStatus.PENDING, TranslationStatus.IN_PROGRESS):
            raise HTTPException(
                409,
                detail=f"Translation for {kind.value} is already in progress",
            )
        # DONE или FAILED — удаляем (вместе с R2-объектом)
        _delete_translation_files([existing])
        session.delete(existing)
        session.commit()

    # Создаём свежую PENDING-запись
    tr = Translation(
        application_id=app_id,
        kind=kind,
        status=TranslationStatus.PENDING,
        created_at=datetime.utcnow(),
    )
    session.add(tr)
    session.commit()

    log.info(f"[translations] Created PENDING for app {app_id} kind {kind.value}")

    # Запускаем фоновую задачу только для одного kind
    background_tasks.add_task(run_translate_package, app_id, [kind])

    return {
        "status": "started",
        "kind": kind.value,
    }


# ============================================================================
# GET: список переводов
# ============================================================================

@router.get("/{app_id}/translations")
def list_translations(
    app_id: int,
    session: Session = Depends(get_session),
):
    """
    Возвращает все переводы для заявки + общую сводку по статусам.

    Используется фронтом для polling — пока есть pending/in_progress, фронт
    повторяет запрос каждые 3 секунды.
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    translations = session.exec(
        select(Translation)
        .where(Translation.application_id == app_id)
        .order_by(Translation.kind)
    ).all()

    items = [_enrich_translation(t) for t in translations]

    # Сводка
    summary = {
        "total": len(items),
        "pending": sum(1 for i in items if i["status"] == TranslationStatus.PENDING),
        "in_progress": sum(1 for i in items if i["status"] == TranslationStatus.IN_PROGRESS),
        "done": sum(1 for i in items if i["status"] == TranslationStatus.DONE),
        "failed": sum(1 for i in items if i["status"] == TranslationStatus.FAILED),
    }
    summary["is_active"] = (summary["pending"] + summary["in_progress"]) > 0
    summary["has_any"] = summary["total"] > 0

    return {
        "translations": items,
        "summary": summary,
    }


# ============================================================================
# GET: ZIP всех DONE-переводов
# ============================================================================

@router.get("/{app_id}/translations/zip")
def download_translations_zip(
    app_id: int,
    session: Session = Depends(get_session),
):
    """
    Собирает ZIP из всех DONE-переводов и отдаёт на скачивание.
    FAILED и PENDING пропускаются (если их вообще нет — 404).
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    done = session.exec(
        select(Translation)
        .where(Translation.application_id == app_id)
        .where(Translation.status == TranslationStatus.DONE)
        .order_by(Translation.kind)
    ).all()

    if not done:
        raise HTTPException(404, "No completed translations to archive")

    storage = get_storage()
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for tr in done:
            if not tr.storage_key or not tr.file_name:
                continue
            try:
                content = storage.read(tr.storage_key)
                zf.writestr(tr.file_name, content)
            except Exception as e:
                log.warning(f"[translations] Failed to add {tr.file_name} to zip: {e}")

    zip_buffer.seek(0)
    download_name = f"translations_{application.reference}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
        },
    )


# ============================================================================
# GET: один файл
# ============================================================================

@router.get("/{app_id}/translations/{kind}/download")
def download_single_translation(
    app_id: int,
    kind: TranslationKind,
    session: Session = Depends(get_session),
):
    """
    Скачивает переведённый файл одного типа.

    Возвращает поток DOCX (не редирект на signed URL — единообразно
    с remaining download endpoints в проекте).
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    tr = session.exec(
        select(Translation)
        .where(Translation.application_id == app_id)
        .where(Translation.kind == kind)
        .where(Translation.status == TranslationStatus.DONE)
    ).first()

    if not tr or not tr.storage_key:
        raise HTTPException(404, f"Translation for {kind.value} not found or not completed")

    try:
        storage = get_storage()
        content = storage.read(tr.storage_key)
    except Exception as e:
        log.error(f"[translations] R2 read failed: {e}", exc_info=True)
        raise HTTPException(500, "Failed to read translation from storage")

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{tr.file_name}"',
        },
    )


# ============================================================================
# DELETE: удалить все переводы (для «Перевести заново»)
# ============================================================================

@router.delete("/{app_id}/translations", status_code=204)
def delete_all_translations(
    app_id: int,
    session: Session = Depends(get_session),
):
    """
    Удаляет все записи Translation + R2-объекты для заявки.

    Используется кнопкой «Перевести заново» — пользователь сначала чистит,
    потом снова жмёт «Перевести пакет».

    Если есть PENDING/IN_PROGRESS — 409 (нельзя удалять активные).
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    if _has_active_translations(session, app_id):
        raise HTTPException(
            409,
            detail="Cannot delete: translations are currently in progress",
        )

    translations = session.exec(
        select(Translation).where(Translation.application_id == app_id)
    ).all()

    if not translations:
        return  # 204, ничего удалять

    # Удаляем R2-объекты
    _delete_translation_files(translations)

    # Удаляем записи в БД
    for tr in translations:
        session.delete(tr)
    session.commit()

    log.info(f"[translations] Deleted {len(translations)} translations for app {app_id}")
