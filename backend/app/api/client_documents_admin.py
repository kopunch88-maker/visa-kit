"""
Admin endpoints for viewing and managing client-uploaded documents.

Pack 13.2: даёт менеджеру доступ к документам клиента (загруженным через клиентский кабинет):
- Получить список документов любой заявки
- Скачать (через signed URL)
- Запустить OCR заново для документа со статусом ocr_failed (или uploaded)

Использует те же модели и storage что и client_portal.py — но защищён авторизацией менеджера.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import Application
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
    prefix="/admin/applications",
    tags=["admin-client-documents"],
    dependencies=[Depends(require_manager)],
)


def _enrich_document(doc: ApplicantDocument) -> dict:
    """Аналог enrichment из client_portal.py — единый формат ответа."""
    storage = get_storage()
    download_url = None
    original_download_url = None

    try:
        download_url = storage.get_url(doc.storage_key, expires_in=3600)
    except Exception as e:
        log.warning(f"Failed to generate URL for {doc.storage_key}: {e}")

    has_original = bool(doc.original_storage_key)
    if has_original:
        try:
            original_download_url = storage.get_url(doc.original_storage_key, expires_in=3600)
        except Exception as e:
            log.warning(f"Failed to generate URL for original {doc.original_storage_key}: {e}")

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
        "has_original": has_original,
        "original_download_url": original_download_url,
        "original_file_name": doc.original_file_name,
    }


@router.get("/{application_id}/client-documents")
def list_client_documents(
    application_id: int,
    session: Session = Depends(get_session),
):
    """
    Получить все документы, загруженные клиентом для данной заявки.

    Возвращает список с metadata + signed URLs для скачивания.
    """
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")

    docs = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application_id)
        .order_by(ApplicantDocument.created_at.desc())
    ).all()

    return [_enrich_document(d) for d in docs]


@router.post("/{application_id}/client-documents/{doc_id}/recognize")
async def admin_recognize_document(
    application_id: int,
    doc_id: int,
    session: Session = Depends(get_session),
):
    """
    Запустить OCR заново для документа клиента (например, если первый раз был fail).

    Использует ту же логику что endpoint клиента, но доступен из админки.
    """
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")

    doc = session.get(ApplicantDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.application_id != application_id:
        raise HTTPException(403, "Document does not belong to this application")

    # Apostille — без OCR, просто помечаем как done
    if doc.doc_type == ApplicantDocumentType.DIPLOMA_APOSTILLE:
        doc.status = ApplicantDocumentStatus.OCR_DONE
        doc.parsed_data = {}
        doc.ocr_error = None
        doc.ocr_completed_at = datetime.utcnow()
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return _enrich_document(doc)

    doc.status = ApplicantDocumentStatus.OCR_PENDING
    doc.ocr_error = None
    session.add(doc)
    session.commit()

    storage = get_storage()
    try:
        image_bytes = storage.read(doc.storage_key)
    except Exception as e:
        log.error(f"Admin: failed to read from storage: {e}")
        doc.status = ApplicantDocumentStatus.OCR_FAILED
        doc.ocr_error = f"Failed to read file: {e}"
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return _enrich_document(doc)

    try:
        parsed = await recognize_document(
            doc_type=doc.doc_type.value,
            image_bytes=image_bytes,
            content_type=doc.content_type,
        )
        doc.status = ApplicantDocumentStatus.OCR_DONE
        doc.parsed_data = parsed
        doc.ocr_error = None
        doc.ocr_completed_at = datetime.utcnow()
        log.info(f"Admin: OCR done for doc {doc_id}, fields={list(parsed.keys())}")
    except OCRError as e:
        log.warning(f"Admin: OCR failed for doc {doc_id}: {e}")
        doc.status = ApplicantDocumentStatus.OCR_FAILED
        doc.ocr_error = str(e)[:500]
        doc.parsed_data = {}
    except Exception as e:
        log.error(f"Admin: unexpected OCR error for doc {doc_id}: {e}", exc_info=True)
        doc.status = ApplicantDocumentStatus.OCR_FAILED
        doc.ocr_error = f"Unexpected error: {str(e)[:200]}"
        doc.parsed_data = {}

    session.add(doc)
    session.commit()
    session.refresh(doc)

    return _enrich_document(doc)
