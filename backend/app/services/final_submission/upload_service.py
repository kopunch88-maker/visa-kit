# -*- coding: utf-8 -*-
"""
Pack 39.0-B — Upload service для финальной проверки документов.

Реализует:
- compute_sha256(content) — хэш для дедупликации
- validate_extension(filename) — whitelist по расширению
- guess_mime(filename) — определение mime по расширению (fallback если UploadFile.content_type пуст)
- build_storage_key(applicant_id, ext) — ключ в R2: applicants/{id}/final_submission/{uuid}.{ext}
- extract_zip_recursive(zip_bytes, depth, max_depth) — распаковка с защитой от bomb
- save_one_file(session, storage, applicant_id, application_id, ...) — сохранить один файл:
    1. вычислить SHA256
    2. проверить дубль (UNIQUE среди is_active=TRUE)
    3. загрузить в R2
    4. создать запись FinalSubmissionDocument
"""
import hashlib
import io
import logging
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from sqlmodel import Session, select

from app.models import FinalSubmissionDocument


log = logging.getLogger(__name__)


# ====================================================================
# Лимиты (Pack 39.0-B)
# ====================================================================

MAX_FILE_SIZE_FS = 200 * 1024 * 1024       # 200 MB на один файл
MAX_TOTAL_UPLOAD_FS = 400 * 1024 * 1024    # 400 MB на весь запрос
MAX_ZIP_DEPTH_FS = 2                       # zip-в-zip ок, zip-в-zip-в-zip нет

SUPPORTED_FS_EXTENSIONS = {
    ".pdf",
    ".jpg", ".jpeg", ".png", ".webp",
    ".heic", ".heif",
    ".zip",
    ".docx",
}

EXTENSION_TO_MIME_FS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".zip": "application/zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ====================================================================
# Хэш / extension / mime
# ====================================================================

def compute_sha256(content: bytes) -> str:
    """SHA256 hex для content."""
    return hashlib.sha256(content).hexdigest()


def validate_extension(filename: str) -> str:
    """
    Возвращает расширение в нижнем регистре с точкой (например ".pdf").
    Raises ValueError если расширение не в whitelist.
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_FS_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension '{ext}'. "
            f"Allowed: {sorted(SUPPORTED_FS_EXTENSIONS)}"
        )
    return ext


def guess_mime(filename: str) -> str:
    """Mime по расширению."""
    ext = Path(filename).suffix.lower()
    return EXTENSION_TO_MIME_FS.get(ext, "application/octet-stream")


def build_storage_key(applicant_id: int, ext: str) -> str:
    """
    R2 ключ: applicants/{applicant_id}/final_submission/{uuid}.{ext}

    UUID гарантирует уникальность; если менеджер заменяет файл и старый
    остаётся в R2 (для истории версий) — новый имеет свой uuid.
    """
    file_uuid = uuid.uuid4().hex
    ext_clean = ext.lstrip(".")
    return f"applicants/{applicant_id}/final_submission/{file_uuid}.{ext_clean}"


# ====================================================================
# ZIP unpack
# ====================================================================

def extract_zip_recursive(
    zip_bytes: bytes,
    *,
    current_depth: int = 0,
    max_depth: int = MAX_ZIP_DEPTH_FS,
    accumulated_size: int = 0,
) -> List[Tuple[str, bytes]]:
    """
    Распаковка ZIP с защитой от zip-bomb.

    Возвращает список (filename, content_bytes). Вложенные ZIP распаковываются
    рекурсивно до max_depth. На каждом шаге проверяется суммарный размер,
    чтобы не взорвать память.

    Не-supported расширения внутри ZIP — пропускаются с warning.
    """
    if current_depth > max_depth:
        log.warning(f"ZIP depth {current_depth} exceeds max {max_depth}, skipping")
        return []

    extracted: List[Tuple[str, bytes]] = []
    total_size = accumulated_size

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                if not name:
                    continue
                ext = Path(name).suffix.lower()

                # Проверка размера до распаковки
                total_size += info.file_size
                if total_size > MAX_TOTAL_UPLOAD_FS * 2:  # запас x2 на распакованное
                    log.warning(
                        f"ZIP bomb suspected: total size {total_size} > {MAX_TOTAL_UPLOAD_FS * 2}"
                    )
                    raise ValueError("Archive too large after extraction")

                try:
                    content = zf.read(info.filename)
                except Exception as e:
                    log.warning(f"Failed to read {info.filename} from zip: {e}")
                    continue

                if ext == ".zip":
                    # Рекурсия
                    extracted.extend(
                        extract_zip_recursive(
                            content,
                            current_depth=current_depth + 1,
                            max_depth=max_depth,
                            accumulated_size=total_size,
                        )
                    )
                elif ext in SUPPORTED_FS_EXTENSIONS:
                    extracted.append((name, content))
                else:
                    log.info(f"Skip unsupported in ZIP: {name} (ext={ext})")
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP archive")

    return extracted


# ====================================================================
# Save single file
# ====================================================================

def find_active_by_sha256(
    session: Session,
    applicant_id: int,
    sha256: str,
) -> Optional[FinalSubmissionDocument]:
    """
    Ищет активный документ клиента с таким же SHA256.
    Возвращает запись если дубль найден, None если нет.
    """
    stmt = (
        select(FinalSubmissionDocument)
        .where(FinalSubmissionDocument.applicant_id == applicant_id)
        .where(FinalSubmissionDocument.sha256 == sha256)
        .where(FinalSubmissionDocument.is_active == True)  # noqa: E712
    )
    return session.exec(stmt).first()


def save_one_file(
    *,
    session: Session,
    storage,  # StorageBackend instance from get_storage()
    applicant_id: int,
    application_id: Optional[int],
    filename: str,
    content: bytes,
    uploaded_by: Optional[str] = None,
) -> Tuple[Optional[FinalSubmissionDocument], Optional[str]]:
    """
    Сохранить один файл в R2 + создать запись в БД.

    Returns:
      (document, None)         — если сохранено успешно
      (None, "duplicate")      — если файл уже есть среди активных (SHA256 совпал)
      (None, "<error_msg>")    — если ошибка валидации/сохранения

    NB: не делает commit — caller сам решает когда коммитить
    (для batch upload одной транзакцией).
    """
    if len(content) > MAX_FILE_SIZE_FS:
        return None, f"File too large: {len(content)} bytes > {MAX_FILE_SIZE_FS}"

    try:
        ext = validate_extension(filename)
    except ValueError as e:
        return None, str(e)

    sha256 = compute_sha256(content)

    # Проверка дубля среди активных
    existing = find_active_by_sha256(session, applicant_id, sha256)
    if existing:
        log.info(f"Duplicate SHA256 {sha256[:8]}... for applicant {applicant_id}, skip")
        return None, "duplicate"

    # Storage
    storage_key = build_storage_key(applicant_id, ext)
    mime_type = guess_mime(filename)
    try:
        storage.save(storage_key, content, content_type=mime_type)
    except Exception as e:
        log.error(f"Storage save failed for {filename}: {e}")
        return None, f"Storage error: {e}"

    # DB
    doc = FinalSubmissionDocument(
        applicant_id=applicant_id,
        application_id=application_id,
        original_filename=filename,
        mime_type=mime_type,
        file_size_bytes=len(content),
        storage_key=storage_key,
        sha256=sha256,
        is_active=True,
        uploaded_by=uploaded_by,
    )
    session.add(doc)
    session.flush()  # чтобы получить doc.id, но без commit

    log.info(
        f"Saved final_submission_document id={doc.id} applicant={applicant_id} "
        f"file={filename} size={len(content)} sha={sha256[:8]}..."
    )
    return doc, None
