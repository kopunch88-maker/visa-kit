"""
Pack 14a/b/c — импорт пакета документов через ZIP/RAR архив.

Pack 14a: ручная классификация менеджером + базовый импорт
Pack 14b: ЕГРЮЛ → автодобавление компании в справочник
Pack 14c: ИИ-классификатор автоматически определяет типы документов

Pack 14b+c FIX: OCR запускается в BackgroundTasks (асинхронно),
                чтобы избежать таймаута Vercel/Cloudflare на длинных импортах.
                Ответ возвращается сразу после создания записей в БД.

Также добавлен endpoint /finalize/skip-company —
менеджер может пропустить создание компании и оформить заявку без неё.

Workflow:
1. POST /upload — загрузка архива + ИИ-классификация
2. POST /{session_id}/finalize — финализация
   - Если нашли EGRYL и компанию НЕТ в БД → возвращаем pending_company
   - Иначе создаём заявку + документы, OCR в фоне
3. POST /{session_id}/finalize/with-company — менеджер дозаполнил форму компании
4. POST /{session_id}/finalize/skip-company — менеджер пропустил создание компании
5. POST /{session_id}/cancel — отменить, удалить временные файлы
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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Body
from sqlmodel import Session, select

from app.db.session import get_session, engine
from app.models import Application, ApplicationStatus, Company, Applicant
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
from app.services.transliteration import transliterate_name

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
# In-memory session storage
# ============================================================================

import_sessions: dict[str, dict] = {}
SESSION_TTL_SECONDS = 3600


def _cleanup_old_sessions():
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
# PDF page conversion
# ============================================================================

def _pdf_page_to_jpeg(pdf_bytes: bytes, page_num: int, dpi: int = 200) -> bytes:
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
    if ext == ".pdf":
        try:
            jpeg = _pdf_page_to_jpeg(file_bytes, page_num=1, dpi=120)
            return jpeg, "image/jpeg"
        except Exception as e:
            log.warning(f"Failed to convert PDF first page for classifier: {e}")
            raise OCRError(f"Could not extract first page of PDF: {e}")
    return file_bytes, EXTENSION_TO_MIME.get(ext, "image/jpeg")


# ============================================================================
# Endpoint: /upload
# ============================================================================

@router.post("/upload")
async def upload_archive(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    session: Session = Depends(get_session),
):
    """
    Шаг 1 — загрузить пакет, классифицировать через ИИ.

    Pack 27.0: принимает ДВА варианта входа:
    - file (legacy): один файл — архив ZIP/RAR ИЛИ один PDF/JPG/PNG/WebP/HEIC
    - files (новое): список файлов — каждый PDF/JPG/PNG/WebP/HEIC

    Если на входе 1 файл с расширением .zip/.rar — распаковываем как раньше.
    Иначе — собираем список напрямую, пропуская невалидные расширения.
    """
    _cleanup_old_sessions()

    # Нормализуем вход: всегда работаем со списком UploadFile
    upload_list: List[UploadFile] = []
    if files:
        upload_list = [f for f in files if f and f.filename]
    elif file and file.filename:
        upload_list = [file]
    if not upload_list:
        raise HTTPException(422, "No files uploaded")

    # Определяем сценарий: один файл-архив ИЛИ список файлов
    is_single_archive = False
    if len(upload_list) == 1:
        only = upload_list[0]
        ext = PathLib(only.filename or "").suffix.lower()
        if ext in (".zip", ".rar"):
            is_single_archive = True

    # Имя «архива» / «пакета» для session metadata
    archive_name: str
    extracted_files: List[dict]
    total_size = 0

    if is_single_archive:
        # === Старая ветка: распаковка ZIP/RAR ===
        only = upload_list[0]
        contents = await only.read()
        archive_size = len(contents)
        total_size = archive_size

        if archive_size == 0:
            raise HTTPException(422, "Empty archive")
        if archive_size > MAX_ARCHIVE_SIZE:
            raise HTTPException(
                413,
                f"Archive too large: {archive_size} bytes "
                f"(max {MAX_ARCHIVE_SIZE // 1024 // 1024} MB)"
            )

        archive_type = _detect_archive_type(only.filename or "", only.content_type or "")
        if archive_type == "zip":
            extracted_files = _extract_zip(contents)
        else:
            extracted_files = _extract_rar(contents)

        if not extracted_files:
            raise HTTPException(
                422,
                "No supported files found in archive. "
                "Supported formats: PDF, JPEG, PNG, WebP, HEIC."
            )
        archive_name = only.filename or "archive"
    else:
        # === Pack 27.0 новая ветка: список одиночных файлов ===
        extracted_files = []
        skipped: List[str] = []

        for uf in upload_list:
            data = await uf.read()
            sz = len(data)
            base_name = PathLib(uf.filename or "").name
            ext = PathLib(base_name).suffix.lower()

            if not base_name:
                continue
            if ext not in SUPPORTED_FILE_EXTENSIONS:
                skipped.append(f"{base_name} (неподдерживаемое расширение)")
                continue
            if sz == 0:
                skipped.append(f"{base_name} (пустой файл)")
                continue
            if sz > MAX_FILE_SIZE_IN_ARCHIVE:
                skipped.append(
                    f"{base_name} ({sz // 1024 // 1024} МБ — больше "
                    f"{MAX_FILE_SIZE_IN_ARCHIVE // 1024 // 1024} МБ лимита)"
                )
                continue

            total_size += sz
            if total_size > MAX_ARCHIVE_SIZE:
                raise HTTPException(
                    413,
                    f"Total upload size exceeds {MAX_ARCHIVE_SIZE // 1024 // 1024} MB"
                )

            extracted_files.append({"name": base_name, "data": data, "size": sz})

        if not extracted_files:
            detail = (
                "No valid files. Supported formats: PDF, JPEG, PNG, WebP, HEIC."
            )
            if skipped:
                detail += " Skipped: " + "; ".join(skipped[:5])
            raise HTTPException(422, detail)

        if skipped:
            log.warning(f"Pack 27.0 upload — skipped files: {skipped}")

        archive_name = (
            f"{len(extracted_files)} файл(ов): "
            + ", ".join(f["name"] for f in extracted_files[:3])
            + ("..." if len(extracted_files) > 3 else "")
        )

    if len(extracted_files) > MAX_FILES_IN_ARCHIVE:
        raise HTTPException(
            413,
            f"Too many files: {len(extracted_files)} (max {MAX_FILES_IN_ARCHIVE})"
        )

    # Дальше вся логика как была — переиспользуем имя `files` для совместимости
    files = extracted_files
    # noinspection PyUnusedLocal
    file = None  # legacy var, дальше не используется (защита от опечатки)

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

        # ИИ-классификация
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
            "classified_type": classified_type,
            "classifier_confidence": classifier_confidence,
            "classifier_country": classifier_country,
            "classifier_reasoning": classifier_reasoning,
            "classifier_error": classifier_error,
        })

    import_sessions[session_id] = {
        "created_at_ts": time.time(),
        "files": file_metas,
        "archive_name": archive_name,
    }

    log.info(
        f"Import session created: id={session_id} "
        f"archive={archive_name} files={len(file_metas)}"
    )

    return {
        "session_id": session_id,
        "archive_name": archive_name,
        "files": file_metas,
    }


# ============================================================================
# Helpers — Application + ApplicantDocument
# ============================================================================

def _create_new_application(session: Session, internal_notes: str) -> Application:
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
    storage = get_storage()
    doc_type_str = doc_type_enum.value

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

    # === Изображение ===
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

    # === PDF ===
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


def _find_company_by_inn(session: Session, inn: Optional[str]) -> Optional[Company]:
    """Ищет компанию в справочнике по ИНН."""
    if not inn:
        return None
    inn_clean = inn.strip()
    if not inn_clean:
        return None
    company = session.exec(
        select(Company).where(Company.tax_id_primary == inn_clean)
    ).first()
    if company:
        log.info(f"Found existing company by INN: {company.short_name} (id={company.id})")
    return company


# ============================================================================
# Pack 14b+c: Сборщик OCR данных для применения к Applicant
# ============================================================================

def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def collect_ocr_data(documents: List["ApplicantDocument"]) -> dict:
    """
    Собирает данные из всех OCR_DONE документов с учётом приоритетов.

    Приоритет источников (от высшего к низшему):
    - PASSPORT_INTERNAL_MAIN  — приоритет для русских данных
    - PASSPORT_FOREIGN         — приоритет для latin
    - PASSPORT_NATIONAL        — приоритет для иностранцев
    - PASSPORT_INTERNAL_ADDRESS — только адрес/прописка
    - RESIDENCE_CARD           — fallback
    - CRIMINAL_RECORD          — fallback
    - DIPLOMA_MAIN             — только education

    Поля заполняются из документа с наивысшим приоритетом, который их содержит.
    """
    priority = {
        ApplicantDocumentType.PASSPORT_INTERNAL_MAIN: 1,
        ApplicantDocumentType.PASSPORT_FOREIGN: 2,
        ApplicantDocumentType.PASSPORT_NATIONAL: 3,
        ApplicantDocumentType.PASSPORT_INTERNAL_ADDRESS: 4,
        ApplicantDocumentType.RESIDENCE_CARD: 5,
        ApplicantDocumentType.CRIMINAL_RECORD: 6,
        ApplicantDocumentType.DIPLOMA_MAIN: 7,
        ApplicantDocumentType.DIPLOMA_APOSTILLE: 99,
        ApplicantDocumentType.EGRYL_EXTRACT: 99,
        ApplicantDocumentType.OTHER: 99,
    }
    sorted_docs = sorted(documents, key=lambda d: priority.get(d.doc_type, 99))
    result = {}

    for doc in sorted_docs:
        if doc.status != ApplicantDocumentStatus.OCR_DONE:
            continue
        p = doc.parsed_data or {}
        if not p:
            continue

        if doc.doc_type == ApplicantDocumentType.PASSPORT_INTERNAL_MAIN:
            for f in [
                "last_name_native", "first_name_native", "middle_name_native",
                "birth_date", "sex",
            ]:
                if f not in result and not _is_empty(p.get(f)):
                    result[f] = p[f]
            if "nationality" not in result:
                result["nationality"] = "RUS"
            if "home_country" not in result:
                result["home_country"] = "RUS"

        elif doc.doc_type == ApplicantDocumentType.PASSPORT_INTERNAL_ADDRESS:
            if "home_address" not in result and not _is_empty(p.get("registration_address")):
                result["home_address"] = p["registration_address"]

        elif doc.doc_type == ApplicantDocumentType.PASSPORT_FOREIGN:
            for src_field, dst_field in [
                ("last_name_latin", "last_name_latin"),
                ("first_name_latin", "first_name_latin"),
                ("birth_place_latin", "birth_place_latin"),
                ("passport_number", "passport_number"),
                ("passport_issue_date", "passport_issue_date"),
                ("passport_issuer", "passport_issuer"),
                ("nationality", "nationality"),
                ("last_name_native", "last_name_native"),
                ("first_name_native", "first_name_native"),
                ("birth_date", "birth_date"),
                ("sex", "sex"),
            ]:
                if dst_field not in result and not _is_empty(p.get(src_field)):
                    result[dst_field] = p[src_field]

        elif doc.doc_type == ApplicantDocumentType.PASSPORT_NATIONAL:
            for src_field, dst_field in [
                ("last_name_latin", "last_name_latin"),
                ("first_name_latin", "first_name_latin"),
                ("last_name_native", "last_name_native"),
                ("first_name_native", "first_name_native"),
                ("birth_date", "birth_date"),
                ("birth_place", "birth_place_latin"),
                ("sex", "sex"),
                ("nationality", "nationality"),
                ("passport_number", "passport_number"),
                ("passport_issue_date", "passport_issue_date"),
                ("passport_issuer", "passport_issuer"),
            ]:
                if dst_field not in result and not _is_empty(p.get(src_field)):
                    result[dst_field] = p[src_field]
            if "home_country" not in result and not _is_empty(p.get("nationality")):
                result["home_country"] = p["nationality"]

        elif doc.doc_type == ApplicantDocumentType.RESIDENCE_CARD:
            for src_field, dst_field in [
                ("last_name_latin", "last_name_latin"),
                ("first_name_latin", "first_name_latin"),
                ("birth_date", "birth_date"),
                ("sex", "sex"),
                ("nationality", "nationality"),
            ]:
                if dst_field not in result and not _is_empty(p.get(src_field)):
                    result[dst_field] = p[src_field]
            # ВНЖ перебивает home_country (клиент живёт в стране ВНЖ)
            if not _is_empty(p.get("residence_country")):
                result["home_country"] = p["residence_country"]

        elif doc.doc_type == ApplicantDocumentType.CRIMINAL_RECORD:
            for src_field, dst_field in [
                ("last_name_latin", "last_name_latin"),
                ("first_name_latin", "first_name_latin"),
                ("last_name_native", "last_name_native"),
                ("first_name_native", "first_name_native"),
                ("birth_date", "birth_date"),
                ("nationality", "nationality"),
            ]:
                if dst_field not in result and not _is_empty(p.get(src_field)):
                    result[dst_field] = p[src_field]

    return result


def build_education_from_diploma(documents: List["ApplicantDocument"]) -> Optional[dict]:
    """Строит запись education из распознанного диплома."""
    for doc in documents:
        if (doc.doc_type == ApplicantDocumentType.DIPLOMA_MAIN
                and doc.status == ApplicantDocumentStatus.OCR_DONE):
            p = doc.parsed_data or {}
            if not p:
                continue
            record = {
                "institution": p.get("institution"),
                "graduation_year": p.get("graduation_year"),
                "degree": p.get("degree"),
                "specialty": p.get("specialty"),
            }
            cleaned = {k: v for k, v in record.items() if not _is_empty(v)}
            if cleaned:
                return cleaned
    return None


# ============================================================================
# Background OCR — запускается ПОСЛЕ возврата ответа клиенту
# ============================================================================

async def _run_ocr_for_doc(doc_id: int):
    """
    Запускает OCR для одного документа в фоновой задаче.
    Создаёт собственную сессию (вне HTTP context).
    """
    with Session(engine) as session:
        doc = session.get(ApplicantDocument, doc_id)
        if not doc:
            log.warning(f"Background OCR: doc {doc_id} not found")
            return

        # Apostille — без OCR
        if doc.doc_type == ApplicantDocumentType.DIPLOMA_APOSTILLE:
            doc.status = ApplicantDocumentStatus.OCR_DONE
            doc.parsed_data = {}
            doc.ocr_completed_at = datetime.utcnow()
            session.add(doc)
            session.commit()
            return

        # OTHER — пропускаем
        if doc.doc_type == ApplicantDocumentType.OTHER:
            return

        # EGRYL — может быть уже распознан (мы делаем это inline в /finalize)
        if doc.doc_type == ApplicantDocumentType.EGRYL_EXTRACT and doc.status == ApplicantDocumentStatus.OCR_DONE:
            return

        # Если уже OCR_FAILED при upload (PDF→JPEG не удался) — не пытаемся
        if doc.status == ApplicantDocumentStatus.OCR_FAILED:
            return

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
            log.info(f"Background OCR done for doc {doc_id}: fields={list(parsed.keys())}")
        except OCRError as e:
            log.warning(f"Background OCR failed for doc {doc_id}: {e}")
            doc.status = ApplicantDocumentStatus.OCR_FAILED
            doc.ocr_error = str(e)[:500]
        except Exception as e:
            log.error(f"Background OCR unexpected error for doc {doc_id}: {e}", exc_info=True)
            doc.status = ApplicantDocumentStatus.OCR_FAILED
            doc.ocr_error = f"Unexpected: {str(e)[:200]}"

        session.add(doc)
        session.commit()


async def _run_ocr_for_docs_batch(doc_ids: List[int], application_id: int):
    """
    Запускает OCR для всех документов последовательно.
    После завершения OCR — автоматически применяет распознанные данные к Applicant
    (создаёт нового или обновляет пустые поля существующего).
    """
    log.info(f"Background OCR batch starting: {len(doc_ids)} docs for app {application_id}")
    for doc_id in doc_ids:
        try:
            await _run_ocr_for_doc(doc_id)
        except Exception as e:
            log.error(f"Background OCR error for {doc_id}: {e}", exc_info=True)
    log.info(f"Background OCR batch finished: {len(doc_ids)} docs")

    # === Pack 14b+c: автоприменение OCR данных к Applicant ===
    try:
        _auto_apply_ocr_to_applicant(application_id)
    except Exception as e:
        log.error(f"Auto-apply OCR to applicant failed for app {application_id}: {e}", exc_info=True)


def _auto_apply_ocr_to_applicant(application_id: int):
    """
    Применяет OCR данные ко всем документам этой заявки → Applicant.

    Логика:
    - Собирает данные через collect_ocr_data() с приоритетами
    - Если у Application нет applicant_id — создаёт нового Applicant
    - Если есть — обновляет ТОЛЬКО ПУСТЫЕ поля (не перезаписывает то что менеджер уже заполнил)
    - Авто-транслитерация *_native → *_latin (как в Pack 13.1.2)
    - Education из диплома если есть
    - Помечает все документы как applied_to_applicant=True
    """
    with Session(engine) as session:
        application = session.get(Application, application_id)
        if not application:
            log.warning(f"Auto-apply: application {application_id} not found")
            return

        docs = session.exec(
            select(ApplicantDocument)
            .where(ApplicantDocument.application_id == application_id)
            .where(ApplicantDocument.status == ApplicantDocumentStatus.OCR_DONE)
        ).all()

        if not docs:
            log.info(f"Auto-apply: no OCR_DONE docs for app {application_id}, skip")
            return

        ocr_data = collect_ocr_data(docs)
        if not ocr_data:
            log.info(f"Auto-apply: collect_ocr_data returned empty for app {application_id}")
            return

        existing = None
        if application.applicant_id:
            existing = session.get(Applicant, application.applicant_id)

        # Заполняем только пустые поля
        update_data = {}
        for field, value in ocr_data.items():
            if _is_empty(value):
                continue
            current = getattr(existing, field, None) if existing else None
            if _is_empty(current):
                update_data[field] = value

        # Авто-транслитерация native → latin (как в Pack 13.1.2)
        NATIVE_TO_LATIN_PAIRS = [
            ("last_name_native", "last_name_latin"),
            ("first_name_native", "first_name_latin"),
        ]
        for native_field, latin_field in NATIVE_TO_LATIN_PAIRS:
            native_will_change = native_field in update_data
            latin_will_change = latin_field in update_data
            if native_will_change and not latin_will_change:
                new_native = update_data[native_field]
                if not _is_empty(new_native):
                    current_latin = getattr(existing, latin_field, None) if existing else None
                    if _is_empty(current_latin):
                        update_data[latin_field] = transliterate_name(new_native)

        # Education
        edu_record = build_education_from_diploma(docs)
        if edu_record:
            existing_edu = (existing.education if existing else []) or []
            if not existing_edu:
                update_data["education"] = [edu_record]

        if not update_data:
            log.info(f"Auto-apply: nothing to update for app {application_id}")
            # Всё равно помечаем документы как applied
            for d in docs:
                d.applied_to_applicant = True
                session.add(d)
            session.commit()
            return

        log.info(
            f"Auto-apply: updating applicant for app {application_id}: "
            f"fields={list(update_data.keys())}"
        )

        if not application.applicant_id:
            # Создаём нового Applicant
            # Critical: last_name_native, first_name_native, last_name_latin, first_name_latin —
            # обязательные. Подставляем placeholder если что-то пустое (чтобы NOT NULL constraint не упал).
            for required in ("last_name_native", "first_name_native", "last_name_latin", "first_name_latin"):
                if not update_data.get(required):
                    update_data[required] = "—"

            try:
                applicant = Applicant(**update_data)
            except Exception as e:
                log.error(f"Auto-apply: cannot create Applicant: {e}", exc_info=True)
                return

            session.add(applicant)
            session.flush()
            session.refresh(applicant)
            application.applicant_id = applicant.id
            session.add(application)
            log.info(f"Auto-apply: created new Applicant id={applicant.id} for app {application_id}")
        else:
            applicant = existing
            for key, value in update_data.items():
                setattr(applicant, key, value)
            session.add(applicant)
            log.info(f"Auto-apply: updated existing Applicant id={applicant.id}")

        # Помечаем все документы как applied
        for d in docs:
            d.applied_to_applicant = True
            session.add(d)

        session.commit()


# ============================================================================
# Endpoint: /finalize
# ============================================================================

@router.post("/{session_id}/finalize")
async def finalize_import(
    session_id: str,
    background_tasks: BackgroundTasks,
    body: dict = Body(...),
    session: Session = Depends(get_session),
):
    """
    Финализация — создаём заявку, привязываем документы, OCR в фоне.

    Если есть EGRYL и компания НЕ найдена → возвращаем pending_company
    """
    _cleanup_old_sessions()

    sess = import_sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Import session not found or expired")

    application_id = body.get("application_id")
    internal_notes = (body.get("internal_notes") or "").strip()
    file_assignments = body.get("files") or []

    if not file_assignments:
        raise HTTPException(422, "No file assignments provided")

    files_info = {f["file_id"]: f for f in sess["files"]}
    storage = get_storage()

    # === Этап 1: ищем EGRYL ===
    egryl_assignment = None
    egryl_data = None
    for a in file_assignments:
        if a.get("doc_type") == "egryl_extract":
            egryl_assignment = a
            break

    found_company: Optional[Company] = None

    if egryl_assignment:
        file_info = files_info.get(egryl_assignment["file_id"])
        if not file_info:
            raise HTTPException(422, "EGRYL file_id not found in session")

        # Распознаём ЕГРЮЛ inline (нужен для решения о следующем шаге)
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

        # Поиск компании
        found_company = _find_company_by_inn(session, ocr_data.get("inn"))

        if not found_company:
            # Готовим pending_company
            director_name = ocr_data.get("director_full_name_ru") or ""
            declensions = await generate_declensions(director_name) if director_name else {}

            return {
                "requires_company_creation": True,
                "pending_company": {
                    "ocr_data": ocr_data,
                    "director_declensions": declensions,
                    "egryl_file_id": egryl_assignment["file_id"],
                    "egryl_pdf_page": egryl_assignment.get("pdf_page"),
                },
                "session_id": session_id,
            }

    # === Этап 2: создание/получение Application ===
    if application_id:
        application = session.get(Application, application_id)
        if not application:
            raise HTTPException(404, "Application not found")
    else:
        application = _create_new_application(session, internal_notes)

    if found_company:
        application.company_id = found_company.id
        session.add(application)
        session.flush()

    # === Этап 3: обработка файлов ===
    created_doc_ids = []
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
            # EGRYL уже распознан — переиспользуем результат
            if doc_type_enum == ApplicantDocumentType.EGRYL_EXTRACT and egryl_data:
                doc.parsed_data = egryl_data
                doc.status = ApplicantDocumentStatus.OCR_DONE
                doc.ocr_completed_at = datetime.utcnow()
                session.add(doc)
            created_doc_ids.append(doc.id)

    session.commit()

    # === Очистка временных файлов ===
    for f in sess["files"]:
        try:
            storage.delete(f["temp_storage_key"])
        except Exception:
            pass
    import_sessions.pop(session_id, None)

    # === OCR в фоне (после возврата ответа клиенту) ===
    background_tasks.add_task(_run_ocr_for_docs_batch, created_doc_ids, application.id)

    return {
        "requires_company_creation": False,
        "application_id": application.id,
        "application_reference": application.reference,
        "documents_created": len(created_doc_ids),
        "company_attached": (
            {"id": found_company.id, "short_name": found_company.short_name}
            if found_company else None
        ),
        "ocr_running_in_background": True,
        "ocr_results": [],
    }


# ============================================================================
# Endpoint: /finalize/with-company
# ============================================================================

@router.post("/{session_id}/finalize/with-company")
async def finalize_with_company(
    session_id: str,
    background_tasks: BackgroundTasks,
    body: dict = Body(...),
    session: Session = Depends(get_session),
):
    """Менеджер дозаполнил форму компании после ЕГРЮЛ. OCR в фоне."""
    _cleanup_old_sessions()

    sess = import_sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Import session not found or expired")

    company_data = body.get("company") or {}
    application_id = body.get("application_id")
    internal_notes = (body.get("internal_notes") or "").strip()
    file_assignments = body.get("files") or []

    if not file_assignments:
        raise HTTPException(422, "No file assignments provided")

    # Валидация
    required_fields = [
        "short_name", "full_name_ru", "full_name_es",
        "tax_id_primary", "legal_address",
        "director_full_name_ru", "director_full_name_genitive_ru", "director_short_ru",
        "bank_name", "bank_account", "bank_bic",
    ]
    missing = [f for f in required_fields if not str(company_data.get(f) or "").strip()]
    if missing:
        raise HTTPException(422, f"Missing required company fields: {', '.join(missing)}")

    # Защита от дубликата
    existing_company = _find_company_by_inn(session, company_data.get("tax_id_primary"))
    if existing_company:
        log.info(f"Company with same INN exists → using {existing_company.short_name}")
        company = existing_company
    else:
        # Создаём компанию
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

    # Заявка
    if application_id:
        application = session.get(Application, application_id)
        if not application:
            raise HTTPException(404, "Application not found")
    else:
        application = _create_new_application(session, internal_notes)

    application.company_id = company.id
    session.add(application)
    session.flush()

    # Файлы
    files_info = {f["file_id"]: f for f in sess["files"]}
    storage = get_storage()
    created_doc_ids = []

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
            created_doc_ids.append(doc.id)

    session.commit()

    # Очистка
    for f in sess["files"]:
        try:
            storage.delete(f["temp_storage_key"])
        except Exception:
            pass
    import_sessions.pop(session_id, None)

    # OCR в фоне
    background_tasks.add_task(_run_ocr_for_docs_batch, created_doc_ids, application.id)

    return {
        "requires_company_creation": False,
        "application_id": application.id,
        "application_reference": application.reference,
        "documents_created": len(created_doc_ids),
        "company_attached": {"id": company.id, "short_name": company.short_name},
        "ocr_running_in_background": True,
        "ocr_results": [],
    }


# ============================================================================
# Endpoint: /finalize/skip-company (NEW)
# ============================================================================

@router.post("/{session_id}/finalize/skip-company")
async def finalize_skip_company(
    session_id: str,
    background_tasks: BackgroundTasks,
    body: dict = Body(...),
    session: Session = Depends(get_session),
):
    """
    Менеджер пропустил создание компании.
    Создаём заявку без company_id, документы клиента всё равно загружаем.
    OCR в фоне.

    Body: то же что у /finalize, но БЕЗ привязки к ЕГРЮЛ.
    """
    _cleanup_old_sessions()

    sess = import_sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Import session not found or expired")

    application_id = body.get("application_id")
    internal_notes = (body.get("internal_notes") or "").strip()
    file_assignments = body.get("files") or []

    if not file_assignments:
        raise HTTPException(422, "No file assignments provided")

    # Получаем/создаём заявку (без компании)
    if application_id:
        application = session.get(Application, application_id)
        if not application:
            raise HTTPException(404, "Application not found")
    else:
        application = _create_new_application(session, internal_notes)

    files_info = {f["file_id"]: f for f in sess["files"]}
    storage = get_storage()
    created_doc_ids = []

    for assignment in file_assignments:
        file_id = assignment.get("file_id")
        doc_type_str = assignment.get("doc_type")
        pdf_page = assignment.get("pdf_page")

        if not file_id or not doc_type_str or doc_type_str == "skip":
            continue
        # ВАЖНО: пропускаем egryl_extract — раз менеджер решил не создавать компанию,
        # ЕГРЮЛ как документ нам не нужен
        if doc_type_str == "egryl_extract":
            log.info(f"Skipping EGRYL file in skip-company mode")
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
            created_doc_ids.append(doc.id)

    session.commit()

    # Очистка
    for f in sess["files"]:
        try:
            storage.delete(f["temp_storage_key"])
        except Exception:
            pass
    import_sessions.pop(session_id, None)

    # OCR в фоне
    background_tasks.add_task(_run_ocr_for_docs_batch, created_doc_ids, application.id)

    log.info(f"Import (skip-company) finalized: app={application.id} docs={len(created_doc_ids)}")

    return {
        "requires_company_creation": False,
        "application_id": application.id,
        "application_reference": application.reference,
        "documents_created": len(created_doc_ids),
        "company_attached": None,
        "ocr_running_in_background": True,
        "ocr_results": [],
    }


# ============================================================================
# Endpoint: /cancel
# ============================================================================

@router.post("/{session_id}/cancel")
def cancel_import(session_id: str):
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
