"""
Client portal — эндпоинты для самого клиента.

Авторизация — по токену в URL.

Pack 13: добавлены endpoints для загрузки документов клиента (паспорт/диплом)
и для последующего OCR через LLM Vision.
"""

import logging
import time
from datetime import datetime
from typing import Optional
from pathlib import Path as PathLib

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import (
    Application, ApplicationStatus,
    Applicant, ApplicantUpdate,
)
from app.models.applicant_document import (
    ApplicantDocument,
    ApplicantDocumentType,
    ApplicantDocumentStatus,
)
from app.services.storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/client", tags=["client-portal"])


# ============================================================================
# Helpers
# ============================================================================

# Максимальный размер файла — 10 МБ
MAX_FILE_SIZE = 10 * 1024 * 1024

# Минимальный размер для качества — 100 КБ
MIN_FILE_SIZE = 100 * 1024

# Разрешённые форматы
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/pdf",
}


def _get_application_by_token(token: str, session: Session) -> Application:
    application = session.exec(
        select(Application).where(Application.client_access_token == token)
    ).first()
    if not application:
        raise HTTPException(404, "Invalid or expired token")
    return application


def _enrich_applicant(applicant: Applicant) -> dict:
    parts = [applicant.last_name_native, applicant.first_name_native]
    if applicant.middle_name_native:
        parts.append(applicant.middle_name_native)
    full_name = " ".join(p for p in parts if p)

    initials = ""
    if applicant.last_name_native and applicant.first_name_native:
        initials = f"{applicant.last_name_native} {applicant.first_name_native[0]}."
        if applicant.middle_name_native:
            initials += f"{applicant.middle_name_native[0]}."

    data = applicant.model_dump()
    data["full_name_native"] = full_name
    data["initials_native"] = initials
    return data


def _enrich_application(application: Application) -> dict:
    data = application.model_dump(exclude={
        "family_members", "uploaded_files",
        "generated_documents", "previous_residences",
    })
    data["has_family"] = False
    data["family_size"] = 0
    data["business_rule_problems"] = application.validate_business_rules()
    return data


def _enrich_document(doc: ApplicantDocument) -> dict:
    """Готовит документ для возврата клиенту, включая URL для скачивания."""
    storage = get_storage()
    download_url = None
    try:
        download_url = storage.get_url(doc.storage_key, expires_in=3600)
    except Exception as e:
        log.warning(f"Failed to generate URL for {doc.storage_key}: {e}")

    return {
        "id": doc.id,
        "doc_type": doc.doc_type,
        "file_name": doc.file_name,
        "file_size": doc.file_size,
        "content_type": doc.content_type,
        "status": doc.status,
        "parsed_data": doc.parsed_data,
        "ocr_error": doc.ocr_error,
        "ocr_completed_at": doc.ocr_completed_at,
        "applied_to_applicant": doc.applied_to_applicant,
        "created_at": doc.created_at,
        "download_url": download_url,
    }


# ============================================================================
# Profile (Applicant) — без изменений
# ============================================================================

@router.get("/{token}/me")
def get_my_profile(
    token: str,
    session: Session = Depends(get_session),
):
    application = _get_application_by_token(token, session)
    if not application.applicant_id:
        return None

    applicant = session.get(Applicant, application.applicant_id)
    if not applicant:
        return None
    return _enrich_applicant(applicant)


@router.patch("/{token}/me")
def update_my_profile(
    token: str,
    payload: ApplicantUpdate,
    session: Session = Depends(get_session),
):
    application = _get_application_by_token(token, session)

    update_data = payload.model_dump(exclude_unset=True)

    if "education" in update_data and update_data["education"] is not None:
        update_data["education"] = [
            e.model_dump() if hasattr(e, "model_dump") else e
            for e in update_data["education"]
        ]
    if "work_history" in update_data and update_data["work_history"] is not None:
        update_data["work_history"] = [
            w.model_dump() if hasattr(w, "model_dump") else w
            for w in update_data["work_history"]
        ]

    if not application.applicant_id:
        try:
            applicant = Applicant(**update_data)
        except Exception as e:
            raise HTTPException(
                422,
                detail={
                    "message": "Cannot create profile",
                    "error": str(e),
                },
            )
        session.add(applicant)
        session.flush()
        session.refresh(applicant)
        application.applicant_id = applicant.id
        session.add(application)
    else:
        applicant = session.get(Applicant, application.applicant_id)
        if not applicant:
            raise HTTPException(500, "Applicant linked but not found in DB")
        for key, value in update_data.items():
            setattr(applicant, key, value)
        session.add(applicant)

    if (application.status == ApplicationStatus.AWAITING_DATA
            and applicant.last_name_native
            and applicant.first_name_native
            and applicant.passport_number):
        application.status = ApplicationStatus.READY_TO_ASSIGN
        session.add(application)

    session.commit()
    session.refresh(applicant)

    return _enrich_applicant(applicant)


# ============================================================================
# Application status — без изменений
# ============================================================================

@router.get("/{token}/application")
def get_my_application(
    token: str,
    session: Session = Depends(get_session),
):
    application = _get_application_by_token(token, session)
    return _enrich_application(application)


# ============================================================================
# Pack 13: Documents
# ============================================================================

@router.get("/{token}/documents")
def list_my_documents(
    token: str,
    session: Session = Depends(get_session),
):
    """Список загруженных документов клиента."""
    application = _get_application_by_token(token, session)

    docs = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application.id)
        .order_by(ApplicantDocument.created_at.desc())
    ).all()

    return [_enrich_document(d) for d in docs]


@router.post("/{token}/documents/upload")
async def upload_document(
    token: str,
    doc_type: str = Form(..., description="Тип документа (passport_internal_main и т.д.)"),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Загрузка документа клиентом.

    Если документ такого типа уже есть — заменяется (старый удаляется из R2).
    """
    application = _get_application_by_token(token, session)

    # === Валидация типа ===
    try:
        doc_type_enum = ApplicantDocumentType(doc_type)
    except ValueError:
        raise HTTPException(422, f"Invalid doc_type: {doc_type}")

    # === Чтение и проверка размера ===
    contents = await file.read()
    file_size = len(contents)

    if file_size == 0:
        raise HTTPException(422, "Empty file")

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            413,
            f"File too large: {file_size} bytes (max {MAX_FILE_SIZE} bytes / 10 MB)"
        )

    if file_size < MIN_FILE_SIZE:
        raise HTTPException(
            422,
            "File too small (less than 100 KB). Please use a higher quality photo."
        )

    # === Content type ===
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            415,
            f"Unsupported file type: {content_type}. "
            f"Allowed: JPEG, PNG, WebP, HEIC, PDF"
        )

    # === Удаляем существующий документ того же типа ===
    existing = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application.id)
        .where(ApplicantDocument.doc_type == doc_type_enum)
    ).first()

    storage = get_storage()

    if existing:
        try:
            storage.delete(existing.storage_key)
        except Exception as e:
            log.warning(f"Failed to delete old file {existing.storage_key}: {e}")
        session.delete(existing)
        session.flush()

    # === Сохраняем новый файл ===
    timestamp = int(time.time())
    original_name = file.filename or f"{doc_type}.bin"
    extension = PathLib(original_name).suffix.lower() or ".bin"
    storage_key = (
        f"applications/{application.id}/documents/"
        f"{doc_type}_{timestamp}{extension}"
    )

    try:
        storage.save(storage_key, contents, content_type=content_type)
    except Exception as e:
        log.error(f"Failed to save to storage: {e}")
        raise HTTPException(500, f"Failed to save file: {e}")

    # === Создаём запись в БД ===
    doc = ApplicantDocument(
        application_id=application.id,
        doc_type=doc_type_enum,
        storage_key=storage_key,
        file_name=original_name,
        file_size=file_size,
        content_type=content_type,
        status=ApplicantDocumentStatus.UPLOADED,
        parsed_data={},
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    log.info(
        f"Uploaded document: app={application.id} "
        f"type={doc_type} size={file_size} key={storage_key}"
    )

    return _enrich_document(doc)


@router.delete("/{token}/documents/{doc_id}")
def delete_document(
    token: str,
    doc_id: int,
    session: Session = Depends(get_session),
):
    """Удаление документа клиентом."""
    application = _get_application_by_token(token, session)

    doc = session.get(ApplicantDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    if doc.application_id != application.id:
        raise HTTPException(403, "Document does not belong to this application")

    storage = get_storage()
    try:
        storage.delete(doc.storage_key)
    except Exception as e:
        log.warning(f"Failed to delete from storage: {e}")

    session.delete(doc)
    session.commit()

    log.info(f"Deleted document: app={application.id} doc_id={doc_id}")
    return {"deleted": True, "id": doc_id}


@router.post("/{token}/documents/{doc_id}/recognize")
async def recognize_document(
    token: str,
    doc_id: int,
    session: Session = Depends(get_session),
):
    """
    Запустить OCR для документа.

    Pack 13.0: ЗАГЛУШКА.
    Pack 13.1: реальный OCR через LLM Vision.
    """
    application = _get_application_by_token(token, session)

    doc = session.get(ApplicantDocument, doc_id)
    if not doc or doc.application_id != application.id:
        raise HTTPException(404, "Document not found")

    raise HTTPException(
        501,
        "OCR not implemented yet. Coming in Pack 13.1."
    )