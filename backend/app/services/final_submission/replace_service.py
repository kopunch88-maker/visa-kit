# -*- coding: utf-8 -*-
"""
Pack 39.0-B — Replace service для финальной проверки документов.

Атомарная замена файла с историей версий:
  1. Создаётся новая запись FinalSubmissionDocument (is_active=True)
  2. Старая запись: is_active=False, replaced_at=NOW
  3. У новой записи previous_version_id = id старой
  4. Если keep_category=True (default) — категория копируется со старой

Если новый файл идентичен старому (SHA256 совпал) — замена отклоняется
с ошибкой "no_change", чтобы не плодить псевдо-версии.
"""
import logging
from datetime import datetime
from typing import Optional, Tuple

from sqlmodel import Session

from app.models import FinalSubmissionDocument
from .upload_service import (
    compute_sha256,
    validate_extension,
    guess_mime,
    build_storage_key,
    MAX_FILE_SIZE_FS,
)


log = logging.getLogger(__name__)


def replace_document(
    *,
    session: Session,
    storage,
    old_doc: FinalSubmissionDocument,
    new_filename: str,
    new_content: bytes,
    keep_category: bool = True,
    uploaded_by: Optional[str] = None,
) -> Tuple[Optional[FinalSubmissionDocument], Optional[str]]:
    """
    Заменить документ новым файлом. Атомарно.

    Returns:
      (new_doc, None)               — успех
      (None, "<error_msg>")         — ошибка

    NB: не коммитит. Caller делает commit после успешного результата.
    """
    if not old_doc.is_active:
        return None, "Old document is not active (already replaced or deleted)"

    if len(new_content) > MAX_FILE_SIZE_FS:
        return None, f"File too large: {len(new_content)} > {MAX_FILE_SIZE_FS}"

    try:
        ext = validate_extension(new_filename)
    except ValueError as e:
        return None, str(e)

    new_sha = compute_sha256(new_content)
    if new_sha == old_doc.sha256:
        return None, "no_change"

    # Сохранить новый файл в R2
    new_storage_key = build_storage_key(old_doc.applicant_id, ext)
    new_mime = guess_mime(new_filename)
    try:
        storage.save(new_storage_key, new_content, content_type=new_mime)
    except Exception as e:
        log.error(f"Storage save failed during replace: {e}")
        return None, f"Storage error: {e}"

    # Создать новую запись
    new_doc = FinalSubmissionDocument(
        applicant_id=old_doc.applicant_id,
        application_id=old_doc.application_id,
        original_filename=new_filename,
        mime_type=new_mime,
        file_size_bytes=len(new_content),
        storage_key=new_storage_key,
        sha256=new_sha,
        doc_category=old_doc.doc_category if keep_category else None,
        doc_category_confidence=old_doc.doc_category_confidence if keep_category else None,
        doc_category_source=old_doc.doc_category_source if keep_category else "ai",
        is_active=True,
        previous_version_id=old_doc.id,
        uploaded_by=uploaded_by,
    )
    session.add(new_doc)

    # Деактивировать старую
    old_doc.is_active = False
    old_doc.replaced_at = datetime.utcnow()
    session.add(old_doc)
    session.flush()

    log.info(
        f"Replaced document id={old_doc.id} -> new id={new_doc.id} "
        f"applicant={old_doc.applicant_id} file={new_filename}"
    )
    return new_doc, None
