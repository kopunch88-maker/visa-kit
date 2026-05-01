"""
Pack 14a/b/c — импорт пакета документов через ZIP/RAR архив.

Pack 14a: ручная классификация менеджером + базовый импорт
Pack 14b: ЕГРЮЛ → автодобавление компании в справочник
Pack 14c: ИИ-классификатор автоматически определяет типы документов

Workflow:
1. POST /upload — менеджер загружает архив
   → backend распаковывает в temp R2 directory
   → запускает классификатор для каждого файла
   → возвращает session_id + список файлов с classified_type / confidence

2. POST /{session_id}/finalize — менеджер указал типы документов
   → если в файлах есть EGRYL и компания НЕ найдена в БД:
     → распознаём ЕГРЮЛ, генерим склонения директора
     → возвращаем pending_company БЕЗ создания заявки
   → если EGRYL найден в БД (по ИНН/ОГРН):
     → привязываем заявку к существующей компании
     → создаём заявку + документы клиента
   → если EGRYL нет в архиве:
     → создаём заявку без компании (как сейчас в Pack 14a)

3. POST /{session_id}/finalize/with-company — менеджер дозаполнил форму компании
   → создаём компанию в справочнике
   → создаём заявку с привязкой к новой компании
   → создаём документы клиента + EGRYL
   → запускаем OCR

4. POST /{session_id}/cancel — отменить, удалить временные файлы
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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import Application, ApplicationStatus, Company
from app.models.applicant_document import (
    ApplicantDocument,
    ApplicantDocumentType,
    ApplicantDocumentStatus,
)
from app.services.storage import get_storage
from app.services.ocr import (
    recognize_document,
    classify_document,
    generate_declensions,
    OCRError,
)

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

MAX_ARCHIVE_SIZE = 100 * 1024 * 1024
MAX_FILES_IN_ARCHIVE = 30
MAX_FILE_SIZE_IN_ARCHIVE = 20 * 1024 * 1024

SUPPORTED_FILE_EXTENSIONS = {
    ".pdf",
    ".jpg", ".jpeg", ".png", ".webp",
    ".heic", ".heif",
}

EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

SELECTABLE_DOC_TYPES = [
    "passport_internal_main",
    "passport_internal_address",
    "passport_foreign",
    "passport_national",
    "residence_card",
    "criminal_record",
    "diploma_main",
    "diploma_apostille",
    "egryl_extract",
    "other",
]


# ============================================================================
# In-memory session storage (per-instance, не в Redis — пока хватает)
# ============================================================================

import_sessions: dict[str, dict] = {}
SESSION_TTL_SECONDS = 3600


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
            storage = get_storage()
            for file_info in sess.get("files", []):
                temp_key = file_info.get("temp_storage_key")
                if temp_key:
                    try:
                        storage.delete(temp_key)
                    except Exception:
                        pass


# ============================================================================
# Helpers — extraction (ZIP/RAR)
# ============================================================================

def _extract_zip(archive_bytes: bytes) -> List[dict]:
    result = []
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            for info in zf.infolist():
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
                    log.warning(f"Skipping too-large file: {name} ({info.file_size} bytes)")
                    continue
                with zf.open(info) as f:
                    data = f.read()
                result.append({"name": base_name, "data": data, "size": info.file_size})
    except zipfile.BadZipFile as e:
        raise HTTPException(422, f"Invalid ZIP archive: {e}")
    return result


def _extract_rar(archive_bytes: bytes) -> List[dict]:
    try:
        import rarfile
    except ImportError:
        raise HTTPException(
            500,
            "RAR support is not installed on server. "
            "Please ask client to send a ZIP archive instead."
        )

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
                    continue
                if info.file_size > MAX_FILE_SIZE_IN_ARCHIVE:
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
# PDF page conversion (server-side, через pypdfium2)
# ============================================================================

def _pdf_page_to_jpeg(pdf_bytes: bytes, page_num: int, dpi: int = 200) -> bytes:
    """Конвертирует страницу PDF в JPEG bytes. page_num: 1-based."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError("pypdfium2 not installed. Add 'pypdfium2' to requirements.txt")

    pdf = pdfium.PdfDocument(pdf_bytes)
    total_pages = len(pdf)
    if page_num < 1 or page_num > total_pages:
        page_num = 1

    page = pdf[page_num - 1]
    scale = dpi / 72.0
    pil_image = page.render(scale=scale).to_pil()

    buf = io.BytesIO()
    pil_image.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _file_to_classifier_image(file_bytes: bytes, ext: str) -> tuple[bytes, str]:
    """
    Подготавливает байты для отправки в классификатор.
    Если PDF — конвертирует первую страницу в JPEG.
    Если изображение — возвращает как есть.
    """
    if ext == ".pdf":
        try:
            jpeg = _pdf_page_to_jpeg(file_bytes, page_num=1, dpi=120)
            return jpeg, "image/jpeg"
        except Exception as e:
            log.warning(f"Failed to convert PDF first page for classifier: {e}")
            # fallback: nothing — classifier won't work on this file
            raise OCRError(f"Could not extract first page of PDF: {e}")
    return file_bytes, EXTENSION_TO_MIME.get(ext, "image/jpeg")


# ============================================================================
# Endpoint: /upload
# ============================================================================

@router.post("/upload")
async def upload_archive(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Шаг 1 — загрузить архив, распаковать, классифицировать через ИИ, вернуть список файлов.
    """
    _cleanup_old_sessions()

    contents = await file.read()
    archive_size = len(contents)

    if archive_size == 0:
        raise HTTPException(422, "Empty archive")
    if archive_size > MAX_ARCHIVE_SIZE:
        raise HTTPException(
            413, f"Archive too large: {archive_size} bytes (max {MAX_ARCHIVE_SIZE // 1024 // 1024} MB)"
        )

    archive_type = _detect_archive_type(file.filename or "", file.content_type or "")

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

    # === Сохраняем во временный storage + запускаем классификатор ===
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

        preview_url = None
        try:
            preview_url = storage.get_url(temp_key, expires_in=3600)
        except Exception as e:
            log.warning(f"Failed to generate preview URL: {e}")

        # === Классификация через ИИ ===
        classified_type = None
        classifier_confidence = None
        classifier_country = None
        classifier_reasoning = None
        classifier_error = None

        try:
            classifier_image, classifier_mime = _file_to_classifier_image(data, ext)
            classification = await classify_document(classifier_image, classifier_mime)
            classified_type = classification.get("type")
            classifier_confidence = classification.get("confidence")
            classifier_country = classification.get("country_hint")
            classifier_reasoning = classification.get("reasoning")
            log.info(
                f"Classified {name}: {classified_type} "
                f"({classifier_confidence}, country={classifier_country})"
            )
        except OCRError as e:
            classifier_error = str(e)[:200]
            log.warning(f"Classification failed for {name}: {e}")
        except Exception as e:
            classifier_error = f"Unexpected: {str(e)[:200]}"
            log.error(f"Unexpected classifier error for {name}: {e}", exc_info=True)

        file_metas.append({
            "file_id": uuid.uuid4().hex,
            "name": name,
            "size": size,
            "mime": mime,
            "extension": ext,
            "is_pdf": ext == ".pdf",
            "temp_storage_key": temp_key,
            "preview_url": preview_url,
            # Pack 14c: ИИ-классификация
            "classified_type": classified_type,
            "classifier_confidence": classifier_confidence,
            "classifier_country": classifier_country,
            "classifier_reasoning": classifier_reasoning,
            "classifier_error": classifier_error,
        })

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


# ============================================================================
# Helpers — finding/creating Application + ApplicantDocument
# ============================================================================

def _create_new_application(session: Session, internal_notes: str) -> Application:
    """Создаёт новую заявку и возвращает её."""
    from sqlalchemy import func
    token = secrets.token_urlsafe(24)
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
    return application


def _process_uploaded_file(
    session: Session,
    application_id: int,
    file_info: dict,
    doc_type_enum: ApplicantDocumentType,
    pdf_page: Optional[int],
) -> Optional[ApplicantDocument]:
    """
    Обрабатывает один файл из временного storage:
    - Если PDF — конвертирует выбранную страницу в JPEG, сохраняет оригинал
    - Если изображение — просто перемещает в постоянное хранилище
    - Удаляет существующий документ того же типа в этой заявке (replace)

    Returns: созданный ApplicantDocument или None при ошибке.
    """
    storage = get_storage()
    doc_type_str = doc_type_enum.value

    # Удаляем существующий документ того же типа
    existing = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application_id)
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

    # === Случай 1: изображение ===
    if not file_info["is_pdf"]:
        try:
            temp_data = storage.read(file_info["temp_storage_key"])
        except Exception as e:
            log.error(f"Failed to read temp file: {e}")
            return None

        timestamp = int(time.time())
        ext = file_info["extension"]
        permanent_key = (
            f"applications/{application_id}/documents/"
            f"{doc_type_str}_{timestamp}{ext}"
        )
        try:
            storage.save(permanent_key, temp_data, content_type=file_info["mime"])
        except Exception as e:
            log.error(f"Failed to save permanent file: {e}")
            return None

        doc = ApplicantDocument(
            application_id=application_id,
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
        return doc

    # === Случай 2: PDF ===
    page_num = int(pdf_page) if pdf_page else 1

    try:
        pdf_data = storage.read(file_info["temp_storage_key"])
    except Exception as e:
        log.error(f"Failed to read temp PDF: {e}")
        return None

    try:
        jpeg_data = _pdf_page_to_jpeg(pdf_data, page_num)
    except Exception as e:
        log.error(f"Failed to convert PDF page {page_num}: {e}")
        jpeg_data = None

    timestamp = int(time.time())
    base_pdf_name = file_info["name"]
    primary_name_jpeg = base_pdf_name.replace(".pdf", "").replace(".PDF", "") + f"_page{page_num}.jpg"

    original_key = (
        f"applications/{application_id}/documents/"
        f"{doc_type_str}_{timestamp}_original.pdf"
    )
    try:
        storage.save(original_key, pdf_data, content_type="application/pdf")
    except Exception as e:
        log.error(f"Failed to save original PDF: {e}")
        return None

    if jpeg_data:
        primary_key = (
            f"applications/{application_id}/documents/"
            f"{doc_type_str}_{timestamp}.jpg"
        )
        try:
            storage.save(primary_key, jpeg_data, content_type="image/jpeg")
        except Exception as e:
            log.error(f"Failed to save JPEG: {e}")
            storage.delete(original_key)
            return None

        primary_size = len(jpeg_data)
        primary_mime = "image/jpeg"
        status = ApplicantDocumentStatus.UPLOADED
    else:
        primary_key = original_key
        primary_size = file_info["size"]
        primary_mime = "application/pdf"
        status = ApplicantDocumentStatus.OCR_FAILED

    doc = ApplicantDocument(
        application_id=application_id,
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
    return doc


async def _run_ocr_on_document(session: Session, doc: ApplicantDocument) -> dict:
    """Запускает OCR на одном документе, обновляет status/parsed_data."""
    if doc.status == ApplicantDocumentStatus.OCR_FAILED:
        return {"doc_id": doc.id, "doc_type": doc.doc_type.value, "ok": False, "error": doc.ocr_error}
    if doc.doc_type == ApplicantDocumentType.DIPLOMA_APOSTILLE:
        doc.status = ApplicantDocumentStatus.OCR_DONE
        doc.parsed_data = {}
        doc.ocr_completed_at = datetime.utcnow()
        session.add(doc)
        return {"doc_id": doc.id, "doc_type": doc.doc_type.value, "ok": True, "skipped": True}
    if doc.doc_type == ApplicantDocumentType.OTHER:
        return {"doc_id": doc.id, "doc_type": doc.doc_type.value, "ok": True, "skipped": True}

    storage = get_storage()
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
        session.add(doc)
        session.commit()
        return {"doc_id": doc.id, "doc_type": doc.doc_type.value, "ok": True, "fields": list(parsed.keys())}
    except OCRError as e:
        log.warning(f"OCR failed for doc {doc.id}: {e}")
        doc.status = ApplicantDocumentStatus.OCR_FAILED
        doc.ocr_error = str(e)[:500]
        session.add(doc)
        session.commit()
        return {"doc_id": doc.id, "doc_type": doc.doc_type.value, "ok": False, "error": str(e)[:200]}
    except Exception as e:
        log.error(f"OCR unexpected error for doc {doc.id}: {e}", exc_info=True)
        doc.status = ApplicantDocumentStatus.OCR_FAILED
        doc.ocr_error = f"Unexpected: {str(e)[:200]}"
        session.add(doc)
        session.commit()
        return {"doc_id": doc.id, "doc_type": doc.doc_type.value, "ok": False, "error": str(e)[:200]}


def _find_company_by_inn_or_ogrn(session: Session, inn: Optional[str], ogrn: Optional[str]) -> Optional[Company]:
    """Ищет компанию в справочнике по ИНН или ОГРН (любое совпадение)."""
    if not inn and not ogrn:
        return None

    # Чистим от пробелов
    inn_clean = (inn or "").strip()
    ogrn_clean = (ogrn or "").strip()

    # Сначала по ИНН
    if inn_clean:
        company = session.exec(
            select(Company).where(Company.tax_id_primary == inn_clean)
        ).first()
        if company:
            log.info(f"Found existing company by INN: {company.short_name} (id={company.id})")
            return company

    # Потом по ОГРН (хранится в notes? В нашей модели нет отдельного поля!)
    # В текущей модели Company нет поля ogrn — оно может попасть в notes или нигде.
    # Поэтому возвращаем None если по ИНН не нашли.
    # TODO: возможно стоит добавить поле ogrn в модель Company в будущем.
    if ogrn_clean:
        log.info(f"OGRN {ogrn_clean} provided but Company model has no ogrn field — only INN search performed")

    return None


# ============================================================================
# Endpoint: /finalize
# ============================================================================

@router.post("/{session_id}/finalize")
async def finalize_import(
    session_id: str,
    body: dict = Body(...),
    session: Session = Depends(get_session),
):
    """
    Шаг 2 — финализация.

    Body:
    {
        "application_id": int | null,
        "internal_notes": str | null,
        "files": [
            {"file_id": str, "doc_type": "...", "pdf_page": int | null},
            ...
        ],
        "run_ocr": bool
    }

    Возможные результаты:

    A) Если EGRYL обнаружен и компания НЕ найдена:
       Возвращаем {"requires_company_creation": true, "pending_company": {...}, ...}
       Заявка НЕ создаётся, файлы остаются в session.
       Менеджер дозаполняет форму и вызывает /finalize/with-company.

    B) Если EGRYL обнаружен И компания найдена в БД:
       Создаём заявку, привязываем к найденной компании, обрабатываем все документы.
       Возвращаем {"application_id": ..., "company_attached": {...}, ...}.

    C) Если EGRYL не обнаружен:
       Создаём заявку без компании (как Pack 14a).
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

    files_info = {f["file_id"]: f for f in sess["files"]}
    storage = get_storage()

    # === Этап 1: ищем EGRYL среди assignment'ов ===
    egryl_assignment = None
    egryl_data = None
    for a in file_assignments:
        if a.get("doc_type") == "egryl_extract":
            egryl_assignment = a
            break

    found_company: Optional[Company] = None
    pending_company: Optional[dict] = None

    if egryl_assignment:
        file_info = files_info.get(egryl_assignment["file_id"])
        if not file_info:
            raise HTTPException(422, "EGRYL file_id not found in session")

        # === Распознаём ЕГРЮЛ ===
        try:
            ext = file_info["extension"]
            data = storage.read(file_info["temp_storage_key"])

            if ext == ".pdf":
                page_num = int(egryl_assignment.get("pdf_page") or 1)
                jpeg_for_ocr = _pdf_page_to_jpeg(data, page_num)
                ocr_data = await recognize_document(
                    doc_type="egryl_extract",
                    image_bytes=jpeg_for_ocr,
                    content_type="image/jpeg",
                )
            else:
                ocr_data = await recognize_document(
                    doc_type="egryl_extract",
                    image_bytes=data,
                    content_type=file_info["mime"],
                )
            egryl_data = ocr_data
            log.info(f"EGRYL parsed: INN={ocr_data.get('inn')} OGRN={ocr_data.get('ogrn')}")
        except OCRError as e:
            log.warning(f"EGRYL OCR failed: {e}")
            raise HTTPException(
                422,
                f"Failed to recognize EGRYL extract: {e}. "
                f"Please skip this file and add company manually."
            )
        except Exception as e:
            log.error(f"EGRYL OCR unexpected error: {e}", exc_info=True)
            raise HTTPException(500, f"Unexpected error processing EGRYL: {e}")

        # === Поиск существующей компании ===
        found_company = _find_company_by_inn_or_ogrn(
            session,
            inn=ocr_data.get("inn"),
            ogrn=ocr_data.get("ogrn"),
        )

        if not found_company:
            # === Готовим pending_company для менеджера ===
            director_name = ocr_data.get("director_full_name_ru") or ""
            declensions = await generate_declensions(director_name) if director_name else {}

            pending_company = {
                "ocr_data": ocr_data,
                "director_declensions": declensions,
                "egryl_file_id": egryl_assignment["file_id"],
                "egryl_pdf_page": egryl_assignment.get("pdf_page"),
            }

            log.info("EGRYL detected, company NOT found → returning pending_company for manager")
            return {
                "requires_company_creation": True,
                "pending_company": pending_company,
                "session_id": session_id,
            }

    # === Этап 2: создание/получение Application ===
    if application_id:
        application = session.get(Application, application_id)
        if not application:
            raise HTTPException(404, "Application not found")
    else:
        application = _create_new_application(session, internal_notes)

    # Привязываем компанию если найдена
    if found_company:
        application.company_id = found_company.id
        session.add(application)
        session.flush()
        log.info(f"Attached existing company {found_company.short_name} to application {application.id}")

    # === Этап 3: обработка файлов ===
    created_documents = []
    for assignment in file_assignments:
        file_id = assignment.get("file_id")
        doc_type_str = assignment.get("doc_type")
        pdf_page = assignment.get("pdf_page")

        if not file_id or not doc_type_str or doc_type_str == "skip":
            continue
        if doc_type_str not in SELECTABLE_DOC_TYPES:
            log.warning(f"Invalid doc_type from frontend: {doc_type_str}, skipping")
            continue

        try:
            doc_type_enum = ApplicantDocumentType(doc_type_str)
        except ValueError:
            continue

        file_info = files_info.get(file_id)
        if not file_info:
            continue

        doc = _process_uploaded_file(session, application.id, file_info, doc_type_enum, pdf_page)
        if doc:
            # Если это EGRYL и мы УЖЕ распознали его — переиспользуем результат
            if doc_type_enum == ApplicantDocumentType.EGRYL_EXTRACT and egryl_data:
                doc.parsed_data = egryl_data
                doc.status = ApplicantDocumentStatus.OCR_DONE
                doc.ocr_completed_at = datetime.utcnow()
                session.add(doc)
            created_documents.append(doc)

    session.commit()

    # === Очистка временных файлов ===
    for f in sess["files"]:
        try:
            storage.delete(f["temp_storage_key"])
        except Exception:
            pass
    import_sessions.pop(session_id, None)

    # === OCR для остальных документов (кроме EGRYL который уже обработан) ===
    ocr_results = []
    if run_ocr_now:
        for doc in created_documents:
            if doc.doc_type == ApplicantDocumentType.EGRYL_EXTRACT and egryl_data:
                ocr_results.append({"doc_id": doc.id, "doc_type": doc.doc_type.value, "ok": True, "skipped": True})
                continue
            result = await _run_ocr_on_document(session, doc)
            ocr_results.append(result)

    return {
        "requires_company_creation": False,
        "application_id": application.id,
        "application_reference": application.reference,
        "documents_created": len(created_documents),
        "company_attached": (
            {"id": found_company.id, "short_name": found_company.short_name}
            if found_company else None
        ),
        "ocr_results": ocr_results,
    }


# ============================================================================
# Endpoint: /finalize/with-company
# ============================================================================

@router.post("/{session_id}/finalize/with-company")
async def finalize_with_company(
    session_id: str,
    body: dict = Body(...),
    session: Session = Depends(get_session),
):
    """
    Шаг 2.5 — менеджер дозаполнил форму компании после ЕГРЮЛ.

    Body:
    {
        "company": {
            // Все обязательные поля Company:
            "short_name": "ИНЖГЕОСЕРВИС",
            "full_name_ru": "...",
            "full_name_es": "...",
            "country": "RUS",
            "tax_id_primary": "INN",
            "tax_id_secondary": "KPP" | null,
            "legal_address": "...",
            "postal_address": null,
            "director_full_name_ru": "...",
            "director_full_name_genitive_ru": "...",
            "director_short_ru": "...",
            "director_position_ru": "Генерального директора",
            "bank_name": "...",
            "bank_account": "...",
            "bank_bic": "...",
            "bank_correspondent_account": null,
            "egryl_extract_date": "2025-11-29" | null,
            "notes": null
        },
        "application_id": int | null,
        "internal_notes": str | null,
        "files": [{ file_id, doc_type, pdf_page }, ...],
        "run_ocr": true
    }
    """
    _cleanup_old_sessions()

    sess = import_sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Import session not found or expired")

    company_data = body.get("company") or {}
    application_id = body.get("application_id")
    internal_notes = (body.get("internal_notes") or "").strip()
    file_assignments = body.get("files") or []
    run_ocr_now = bool(body.get("run_ocr", True))

    if not file_assignments:
        raise HTTPException(422, "No file assignments provided")

    # === Валидация обязательных полей компании ===
    required_fields = [
        "short_name", "full_name_ru", "full_name_es",
        "tax_id_primary", "legal_address",
        "director_full_name_ru", "director_full_name_genitive_ru", "director_short_ru",
        "bank_name", "bank_account", "bank_bic",
    ]
    missing = [f for f in required_fields if not str(company_data.get(f) or "").strip()]
    if missing:
        raise HTTPException(422, f"Missing required company fields: {', '.join(missing)}")

    # === Защита от дубликата по ИНН ===
    existing_company = _find_company_by_inn_or_ogrn(
        session,
        inn=company_data.get("tax_id_primary"),
        ogrn=None,
    )
    if existing_company:
        log.info(f"Race: company with same INN appeared during form fill → using {existing_company.short_name}")
        company = existing_company
    else:
        # === Создаём новую компанию ===
        from datetime import date as date_type

        # Парсим egryl_extract_date если есть
        egryl_date = company_data.get("egryl_extract_date")
        parsed_egryl_date = None
        if egryl_date:
            try:
                parsed_egryl_date = datetime.strptime(egryl_date, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                parsed_egryl_date = None

        company = Company(
            short_name=str(company_data["short_name"]).strip(),
            full_name_ru=str(company_data["full_name_ru"]).strip(),
            full_name_es=str(company_data["full_name_es"]).strip(),
            country=company_data.get("country") or "RUS",
            tax_id_primary=str(company_data["tax_id_primary"]).strip(),
            tax_id_secondary=str(company_data.get("tax_id_secondary") or "").strip() or None,
            legal_address=str(company_data["legal_address"]).strip(),
            postal_address=str(company_data.get("postal_address") or "").strip() or None,
            director_full_name_ru=str(company_data["director_full_name_ru"]).strip(),
            director_full_name_genitive_ru=str(company_data["director_full_name_genitive_ru"]).strip(),
            director_short_ru=str(company_data["director_short_ru"]).strip(),
            director_position_ru=company_data.get("director_position_ru") or "Генерального директора",
            bank_name=str(company_data["bank_name"]).strip(),
            bank_account=str(company_data["bank_account"]).strip(),
            bank_bic=str(company_data["bank_bic"]).strip(),
            bank_correspondent_account=str(company_data.get("bank_correspondent_account") or "").strip() or None,
            egryl_extract_date=parsed_egryl_date,
            is_active=True,
            notes=company_data.get("notes"),
        )
        session.add(company)
        session.flush()
        session.refresh(company)
        log.info(f"Created new company from EGRYL: {company.short_name} (id={company.id})")

    # === Получаем/создаём заявку ===
    if application_id:
        application = session.get(Application, application_id)
        if not application:
            raise HTTPException(404, "Application not found")
    else:
        application = _create_new_application(session, internal_notes)

    application.company_id = company.id
    session.add(application)
    session.flush()

    # === Обработка файлов ===
    files_info = {f["file_id"]: f for f in sess["files"]}
    storage = get_storage()
    created_documents = []

    for assignment in file_assignments:
        file_id = assignment.get("file_id")
        doc_type_str = assignment.get("doc_type")
        pdf_page = assignment.get("pdf_page")

        if not file_id or not doc_type_str or doc_type_str == "skip":
            continue
        if doc_type_str not in SELECTABLE_DOC_TYPES:
            continue

        try:
            doc_type_enum = ApplicantDocumentType(doc_type_str)
        except ValueError:
            continue

        file_info = files_info.get(file_id)
        if not file_info:
            continue

        doc = _process_uploaded_file(session, application.id, file_info, doc_type_enum, pdf_page)
        if doc:
            created_documents.append(doc)

    session.commit()

    # === Очистка ===
    for f in sess["files"]:
        try:
            storage.delete(f["temp_storage_key"])
        except Exception:
            pass
    import_sessions.pop(session_id, None)

    # === OCR ===
    ocr_results = []
    if run_ocr_now:
        for doc in created_documents:
            result = await _run_ocr_on_document(session, doc)
            ocr_results.append(result)

    return {
        "requires_company_creation": False,
        "application_id": application.id,
        "application_reference": application.reference,
        "documents_created": len(created_documents),
        "company_attached": {"id": company.id, "short_name": company.short_name},
        "ocr_results": ocr_results,
    }


# ============================================================================
# Endpoint: /cancel
# ============================================================================

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
