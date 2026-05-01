"""
Pack 14a — импорт пакета документов через ZIP/RAR архив.

Менеджер загружает архив с документами клиента (паспорт, ВНЖ, справки и т.д.)
→ система распаковывает → получает список файлов с превью →
менеджер вручную выбирает тип каждого файла →
система загружает их как ApplicantDocument и запускает OCR.

В Pack 14b добавится автодобавление компании из ЕГРЮЛ.
В Pack 14c добавится ИИ-классификатор (автоматическое определение типа).

Workflow:
1. POST /admin/import-package/upload — менеджер загружает архив
   → backend распаковывает в temp R2 директорию
   → возвращает session_id + список файлов с метаданными и превью
2. POST /admin/import-package/{session_id}/finalize — менеджер указал типы документов
   → backend создаёт/привязывает к Application
   → конвертирует PDF → JPEG (как в Pack 13.1.3)
   → загружает в основное хранилище
   → создаёт ApplicantDocument записи
   → запускает OCR в фоне (или синхронно — в простой версии)
3. POST /admin/import-package/{session_id}/cancel — отменить импорт, удалить временные файлы
"""

import io
import logging
import secrets
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path as PathLib
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import Application, ApplicationStatus, Applicant
from app.models.applicant_document import (
    ApplicantDocument,
    ApplicantDocumentType,
    ApplicantDocumentStatus,
)
from app.services.storage import get_storage
from app.services.ocr import recognize_document, OCRError

from .dependencies import require_manager

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/import-package",
    tags=["admin-import"],
    dependencies=[Depends(require_manager)],
)


# ============================================================================
# Constants
# ============================================================================

MAX_ARCHIVE_SIZE = 100 * 1024 * 1024  # 100 MB на архив
MAX_FILES_IN_ARCHIVE = 30
MAX_FILE_SIZE_IN_ARCHIVE = 20 * 1024 * 1024  # 20 MB на файл

ALLOWED_ARCHIVE_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/x-rar-compressed",
    "application/vnd.rar",
    "application/x-rar",
}
ALLOWED_ARCHIVE_EXTENSIONS = {".zip", ".rar"}

# Какие файлы внутри архива нас интересуют (остальные игнорируем)
SUPPORTED_FILE_EXTENSIONS = {
    ".pdf",
    ".jpg", ".jpeg", ".png", ".webp",
    ".heic", ".heif",
}

# Соответствие расширения → MIME type
EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


# ============================================================================
# In-memory session storage
# ============================================================================
# Каждая сессия импорта живёт максимум 1 час.
# В production это можно заменить на Redis, но для начала достаточно in-memory.
# (Поскольку backend на Railway пока в одном инстансе.)

import_sessions: dict[str, dict] = {}
SESSION_TTL_SECONDS = 3600  # 1 час


def _cleanup_old_sessions():
    """Удаляет сессии старше 1 часа."""
    now = time.time()
    expired = [
        sid for sid, sess in import_sessions.items()
        if now - sess.get("created_at_ts", now) > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        sess = import_sessions.pop(sid, None)
        if sess:
            # Чистим временные файлы из R2
            storage = get_storage()
            for file_info in sess.get("files", []):
                temp_key = file_info.get("temp_storage_key")
                if temp_key:
                    try:
                        storage.delete(temp_key)
                    except Exception:
                        pass


# ============================================================================
# Helpers — extraction
# ============================================================================

def _extract_zip(archive_bytes: bytes) -> List[dict]:
    """
    Распаковать ZIP, вернуть список файлов: [{"name": ..., "data": bytes}, ...].

    Игнорирует:
    - Папки (служебные записи zip)
    - Файлы с неподдерживаемыми расширениями
    - Скрытые файлы (начинаются с . или __MACOSX)
    """
    result = []
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                # Skip hidden / OS-specific
                base_name = PathLib(name).name
                if base_name.startswith(".") or "__MACOSX" in name:
                    continue
                ext = PathLib(name).suffix.lower()
                if ext not in SUPPORTED_FILE_EXTENSIONS:
                    log.info(f"Skipping unsupported file in archive: {name}")
                    continue
                if info.file_size > MAX_FILE_SIZE_IN_ARCHIVE:
                    log.warning(f"Skipping too-large file in archive: {name} ({info.file_size} bytes)")
                    continue
                with zf.open(info) as f:
                    data = f.read()
                result.append({"name": base_name, "data": data, "size": info.file_size})
    except zipfile.BadZipFile as e:
        raise HTTPException(422, f"Invalid ZIP archive: {e}")

    return result


def _extract_rar(archive_bytes: bytes) -> List[dict]:
    """
    Распаковать RAR. Требует установленного `rarfile` + системный unrar.

    На Railway Docker — нужно добавить `unrar` в Dockerfile через apt-get install.
    Если rarfile не установлен — падает с понятным сообщением.
    """
    try:
        import rarfile
    except ImportError:
        raise HTTPException(
            500,
            "RAR support is not installed on server. "
            "Please ask client to send a ZIP archive instead."
        )

    # rarfile требует временный файл
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".rar", delete=False) as tmp:
        tmp.write(archive_bytes)
        tmp_path = tmp.name

    result = []
    try:
        with rarfile.RarFile(tmp_path) as rf:
            for info in rf.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                base_name = PathLib(name).name
                if base_name.startswith(".") or "__MACOSX" in name:
                    continue
                ext = PathLib(name).suffix.lower()
                if ext not in SUPPORTED_FILE_EXTENSIONS:
                    log.info(f"Skipping unsupported file in archive: {name}")
                    continue
                if info.file_size > MAX_FILE_SIZE_IN_ARCHIVE:
                    log.warning(f"Skipping too-large file: {name}")
                    continue
                with rf.open(info) as f:
                    data = f.read()
                result.append({"name": base_name, "data": data, "size": info.file_size})
    except rarfile.BadRarFile as e:
        raise HTTPException(422, f"Invalid RAR archive: {e}")
    except rarfile.Error as e:
        raise HTTPException(422, f"RAR error: {e}")
    finally:
        import os
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return result


def _detect_archive_type(filename: str, content_type: str) -> str:
    """Определяет тип архива по имени и MIME. Возвращает 'zip' или 'rar'."""
    ext = PathLib(filename or "").suffix.lower()
    if ext == ".zip" or "zip" in (content_type or "").lower():
        return "zip"
    if ext == ".rar" or "rar" in (content_type or "").lower():
        return "rar"
    raise HTTPException(
        422,
        f"Unsupported archive format. Use ZIP or RAR. Got: {filename} ({content_type})"
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/upload")
async def upload_archive(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Шаг 1 — загрузить архив, распаковать, вернуть список файлов с превью.

    Возвращает session_id для следующего шага.
    """
    _cleanup_old_sessions()

    # === Валидация архива ===
    contents = await file.read()
    archive_size = len(contents)

    if archive_size == 0:
        raise HTTPException(422, "Empty archive")
    if archive_size > MAX_ARCHIVE_SIZE:
        raise HTTPException(
            413, f"Archive too large: {archive_size} bytes (max {MAX_ARCHIVE_SIZE // 1024 // 1024} MB)"
        )

    archive_type = _detect_archive_type(file.filename or "", file.content_type or "")

    # === Распаковка ===
    if archive_type == "zip":
        files = _extract_zip(contents)
    else:
        files = _extract_rar(contents)

    if not files:
        raise HTTPException(
            422,
            "No supported files found in archive. "
            "Supported formats: PDF, JPEG, PNG, WebP, HEIC."
        )
    if len(files) > MAX_FILES_IN_ARCHIVE:
        raise HTTPException(
            413,
            f"Too many files in archive: {len(files)} (max {MAX_FILES_IN_ARCHIVE})"
        )

    # === Сохраняем во временный storage ===
    session_id = secrets.token_urlsafe(16)
    storage = get_storage()

    file_metas = []
    for file_data in files:
        name = file_data["name"]
        data = file_data["data"]
        size = file_data["size"]

        ext = PathLib(name).suffix.lower()
        mime = EXTENSION_TO_MIME.get(ext, "application/octet-stream")

        temp_key = f"_import_temp/{session_id}/{uuid.uuid4().hex}{ext}"
        try:
            storage.save(temp_key, data, content_type=mime)
        except Exception as e:
            log.error(f"Failed to save temp file: {e}")
            raise HTTPException(500, f"Storage error: {e}")

        # Превью URL — для PDF превью делается на фронте через PDF.js
        preview_url = None
        try:
            preview_url = storage.get_url(temp_key, expires_in=3600)
        except Exception as e:
            log.warning(f"Failed to generate preview URL: {e}")

        file_metas.append({
            "file_id": uuid.uuid4().hex,
            "name": name,
            "size": size,
            "mime": mime,
            "extension": ext,
            "is_pdf": ext == ".pdf",
            "temp_storage_key": temp_key,
            "preview_url": preview_url,
        })

    # === Сохраняем сессию ===
    import_sessions[session_id] = {
        "created_at_ts": time.time(),
        "files": file_metas,
        "archive_name": file.filename,
    }

    log.info(
        f"Import session created: id={session_id} "
        f"archive={file.filename} files={len(file_metas)}"
    )

    return {
        "session_id": session_id,
        "archive_name": file.filename,
        "files": file_metas,
    }


# Допустимые типы документов которые менеджер может выбрать
SELECTABLE_DOC_TYPES = [
    "passport_internal_main",
    "passport_internal_address",
    "passport_foreign",
    "passport_national",
    "residence_card",
    "criminal_record",
    "diploma_main",
    "diploma_apostille",
    "other",
]


@router.post("/{session_id}/finalize")
async def finalize_import(
    session_id: str,
    body: dict = Body(...),
    session: Session = Depends(get_session),
):
    """
    Шаг 2 — финализация: менеджер указал типы документов и заявку.

    Body:
    {
        "application_id": int | null,           // если null — создаём новую заявку
        "internal_notes": str | null,           // если создаём новую — заметка для неё
        "files": [
            {
                "file_id": str,                  // из upload response
                "doc_type": "passport_national" | ... | "skip",
                "pdf_page": int | null           // если PDF — какую страницу использовать (1-based)
            },
            ...
        ],
        "run_ocr": bool                          // запускать OCR сразу или нет
    }

    Returns: { application_id, application_reference, documents: [...], ocr_results: [...] }
    """
    _cleanup_old_sessions()

    sess = import_sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Import session not found or expired")

    application_id = body.get("application_id")
    internal_notes = (body.get("internal_notes") or "").strip()
    file_assignments = body.get("files") or []
    run_ocr_now = bool(body.get("run_ocr", True))

    if not file_assignments:
        raise HTTPException(422, "No file assignments provided")

    # === Application: получить или создать ===
    if application_id:
        application = session.get(Application, application_id)
        if not application:
            raise HTTPException(404, "Application not found")
    else:
        # Создаём новую
        token = secrets.token_urlsafe(24)
        # Генерация reference вида 2026-XXXX
        from sqlalchemy import func
        max_id = session.exec(
            select(func.coalesce(func.max(Application.id), 0))
        ).one()
        new_id_estimate = (max_id or 0) + 1
        year = datetime.utcnow().year
        reference = f"{year}-{new_id_estimate:04d}"

        application = Application(
            reference=reference,
            status=ApplicationStatus.AWAITING_DATA,
            client_access_token=token,
            internal_notes=internal_notes or "Импорт пакета",
        )
        session.add(application)
        session.flush()
        session.refresh(application)
        log.info(f"Created new application via import: id={application.id} ref={application.reference}")

    # === Обработка файлов ===
    storage = get_storage()
    files_info = {f["file_id"]: f for f in sess["files"]}
    created_documents = []
    pdf_conversion_needed = []

    for assignment in file_assignments:
        file_id = assignment.get("file_id")
        doc_type_str = assignment.get("doc_type")
        pdf_page = assignment.get("pdf_page")  # 1-based

        if not file_id or not doc_type_str:
            continue
        if doc_type_str == "skip":
            continue
        if doc_type_str not in SELECTABLE_DOC_TYPES:
            log.warning(f"Invalid doc_type from frontend: {doc_type_str}, skipping")
            continue

        try:
            doc_type_enum = ApplicantDocumentType(doc_type_str)
        except ValueError:
            log.warning(f"Cannot map to enum: {doc_type_str}")
            continue

        file_info = files_info.get(file_id)
        if not file_info:
            log.warning(f"File {file_id} not found in session, skipping")
            continue

        # Удаляем существующий документ того же типа в этой заявке (replace logic)
        existing = session.exec(
            select(ApplicantDocument)
            .where(ApplicantDocument.application_id == application.id)
            .where(ApplicantDocument.doc_type == doc_type_enum)
        ).first()
        if existing:
            try:
                storage.delete(existing.storage_key)
            except Exception as e:
                log.warning(f"Failed to delete old primary: {e}")
            if existing.original_storage_key:
                try:
                    storage.delete(existing.original_storage_key)
                except Exception as e:
                    log.warning(f"Failed to delete old original: {e}")
            session.delete(existing)
            session.flush()

        # === Случай 1: файл — изображение (JPEG/PNG/WebP) ===
        # Просто перемещаем в постоянное хранилище
        if not file_info["is_pdf"]:
            # HEIC: можно бы конвертировать но recognize_document это сделает сам через _normalize_image
            # Поэтому HEIC оставляем как есть, конвертация произойдёт при OCR
            try:
                temp_data = storage.read(file_info["temp_storage_key"])
            except Exception as e:
                log.error(f"Failed to read temp file: {e}")
                continue

            timestamp = int(time.time())
            ext = file_info["extension"]
            permanent_key = (
                f"applications/{application.id}/documents/"
                f"{doc_type_str}_{timestamp}{ext}"
            )
            try:
                storage.save(permanent_key, temp_data, content_type=file_info["mime"])
            except Exception as e:
                log.error(f"Failed to save permanent file: {e}")
                continue

            doc = ApplicantDocument(
                application_id=application.id,
                doc_type=doc_type_enum,
                storage_key=permanent_key,
                file_name=file_info["name"],
                file_size=file_info["size"],
                content_type=file_info["mime"],
                status=ApplicantDocumentStatus.UPLOADED,
                parsed_data={},
            )
            session.add(doc)
            session.flush()
            session.refresh(doc)
            created_documents.append(doc)

        # === Случай 2: PDF ===
        # Стратегия: оригинал PDF сохраняем как original_storage_key.
        # Конкретную страницу как JPEG будем конвертировать на бэкенде через pypdfium2.
        else:
            # PDF page selection (1-based, default = 1)
            page_num = int(pdf_page) if pdf_page else 1

            try:
                pdf_data = storage.read(file_info["temp_storage_key"])
            except Exception as e:
                log.error(f"Failed to read temp PDF: {e}")
                continue

            # Конвертируем выбранную страницу в JPEG
            try:
                jpeg_data = _pdf_page_to_jpeg(pdf_data, page_num)
            except Exception as e:
                log.error(f"Failed to convert PDF page {page_num}: {e}")
                # Помечаем как ocr_failed но сохраняем оригинал
                jpeg_data = None

            timestamp = int(time.time())
            base_pdf_name = file_info["name"]
            primary_name_jpeg = base_pdf_name.replace(".pdf", "").replace(".PDF", "") + f"_page{page_num}.jpg"

            # Сохраняем оригинальный PDF
            original_key = (
                f"applications/{application.id}/documents/"
                f"{doc_type_str}_{timestamp}_original.pdf"
            )
            try:
                storage.save(original_key, pdf_data, content_type="application/pdf")
            except Exception as e:
                log.error(f"Failed to save original PDF: {e}")
                continue

            # Сохраняем JPEG превью если получилось
            if jpeg_data:
                primary_key = (
                    f"applications/{application.id}/documents/"
                    f"{doc_type_str}_{timestamp}.jpg"
                )
                try:
                    storage.save(primary_key, jpeg_data, content_type="image/jpeg")
                except Exception as e:
                    log.error(f"Failed to save JPEG: {e}")
                    storage.delete(original_key)
                    continue

                primary_size = len(jpeg_data)
                primary_mime = "image/jpeg"
                status = ApplicantDocumentStatus.UPLOADED
            else:
                # JPEG не получился — используем PDF как primary, OCR упадёт но сохранение пройдёт
                primary_key = original_key
                primary_size = file_info["size"]
                primary_mime = "application/pdf"
                status = ApplicantDocumentStatus.OCR_FAILED

            doc = ApplicantDocument(
                application_id=application.id,
                doc_type=doc_type_enum,
                storage_key=primary_key,
                original_storage_key=original_key if jpeg_data else None,
                file_name=primary_name_jpeg if jpeg_data else file_info["name"],
                file_size=primary_size,
                content_type=primary_mime,
                original_file_name=file_info["name"] if jpeg_data else None,
                original_file_size=file_info["size"] if jpeg_data else None,
                original_content_type="application/pdf" if jpeg_data else None,
                status=status,
                ocr_error=("PDF→JPEG conversion failed" if not jpeg_data else None),
                parsed_data={},
            )
            session.add(doc)
            session.flush()
            session.refresh(doc)
            created_documents.append(doc)

    session.commit()

    # === Удаляем временные файлы и сессию ===
    for f in sess["files"]:
        try:
            storage.delete(f["temp_storage_key"])
        except Exception:
            pass
    import_sessions.pop(session_id, None)

    # === Запускаем OCR (синхронно для простоты Pack 14a) ===
    ocr_results = []
    if run_ocr_now:
        for doc in created_documents:
            if doc.status == ApplicantDocumentStatus.OCR_FAILED:
                ocr_results.append({"doc_id": doc.id, "doc_type": doc.doc_type, "ok": False, "error": doc.ocr_error})
                continue
            if doc.doc_type == ApplicantDocumentType.DIPLOMA_APOSTILLE:
                doc.status = ApplicantDocumentStatus.OCR_DONE
                doc.parsed_data = {}
                doc.ocr_completed_at = datetime.utcnow()
                session.add(doc)
                ocr_results.append({"doc_id": doc.id, "doc_type": doc.doc_type, "ok": True, "skipped": True})
                continue
            if doc.doc_type == ApplicantDocumentType.OTHER:
                # Не пытаемся распознать "other"
                ocr_results.append({"doc_id": doc.id, "doc_type": doc.doc_type, "ok": True, "skipped": True})
                continue

            doc.status = ApplicantDocumentStatus.OCR_PENDING
            session.add(doc)
            session.commit()

            try:
                image_bytes = storage.read(doc.storage_key)
                parsed = await recognize_document(
                    doc_type=doc.doc_type.value,
                    image_bytes=image_bytes,
                    content_type=doc.content_type,
                )
                doc.status = ApplicantDocumentStatus.OCR_DONE
                doc.parsed_data = parsed
                doc.ocr_error = None
                doc.ocr_completed_at = datetime.utcnow()
                ocr_results.append({"doc_id": doc.id, "doc_type": doc.doc_type, "ok": True, "fields": list(parsed.keys())})
            except OCRError as e:
                log.warning(f"Bulk import OCR failed for doc {doc.id}: {e}")
                doc.status = ApplicantDocumentStatus.OCR_FAILED
                doc.ocr_error = str(e)[:500]
                ocr_results.append({"doc_id": doc.id, "doc_type": doc.doc_type, "ok": False, "error": str(e)[:200]})
            except Exception as e:
                log.error(f"Bulk import OCR unexpected error for doc {doc.id}: {e}", exc_info=True)
                doc.status = ApplicantDocumentStatus.OCR_FAILED
                doc.ocr_error = f"Unexpected: {str(e)[:200]}"
                ocr_results.append({"doc_id": doc.id, "doc_type": doc.doc_type, "ok": False, "error": str(e)[:200]})

            session.add(doc)
            session.commit()

    log.info(
        f"Import finalized: session={session_id} "
        f"app={application.id} created_docs={len(created_documents)}"
    )

    return {
        "application_id": application.id,
        "application_reference": application.reference,
        "documents_created": len(created_documents),
        "ocr_results": ocr_results,
    }


@router.post("/{session_id}/cancel")
def cancel_import(session_id: str):
    """Отменить сессию импорта, удалить временные файлы."""
    sess = import_sessions.pop(session_id, None)
    if not sess:
        return {"cancelled": False, "reason": "session not found"}

    storage = get_storage()
    deleted = 0
    for f in sess.get("files", []):
        try:
            storage.delete(f["temp_storage_key"])
            deleted += 1
        except Exception as e:
            log.warning(f"Failed to delete temp file: {e}")

    return {"cancelled": True, "files_deleted": deleted}


# ============================================================================
# PDF page conversion (server-side, using pypdfium2)
# ============================================================================

def _pdf_page_to_jpeg(pdf_bytes: bytes, page_num: int, dpi: int = 200) -> bytes:
    """
    Конвертирует страницу PDF в JPEG bytes.

    Использует pypdfium2 — лёгкая библиотека, не требует системных зависимостей
    (в отличие от pdf2image который требует poppler).

    page_num: 1-based номер страницы.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError(
            "pypdfium2 not installed. Add 'pypdfium2' to requirements.txt"
        )

    pdf = pdfium.PdfDocument(pdf_bytes)
    total_pages = len(pdf)
    if page_num < 1 or page_num > total_pages:
        page_num = 1  # fallback

    page = pdf[page_num - 1]
    # scale = DPI / 72 (PDF native is 72 DPI)
    scale = dpi / 72.0
    pil_image = page.render(scale=scale).to_pil()

    # Save as JPEG
    buf = io.BytesIO()
    pil_image.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()
