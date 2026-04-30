"""
Client portal — эндпоинты для самого клиента.

Авторизация — по токену в URL.

Pack 13.1: реальный OCR через LLM Vision + endpoint apply-to-applicant.
"""

import logging
import time
from datetime import datetime
from typing import Optional, List
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
from app.services.ocr import recognize_document, OCRError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/client", tags=["client-portal"])


# ============================================================================
# Helpers
# ============================================================================

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ
MIN_FILE_SIZE = 100 * 1024  # 100 КБ

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
# Profile (Applicant)
# ============================================================================

@router.get("/{token}/me")
def get_my_profile(token: str, session: Session = Depends(get_session)):
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
                detail={"message": "Cannot create profile", "error": str(e)},
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


@router.get("/{token}/application")
def get_my_application(token: str, session: Session = Depends(get_session)):
    application = _get_application_by_token(token, session)
    return _enrich_application(application)


# ============================================================================
# Pack 13: Documents
# ============================================================================

@router.get("/{token}/documents")
def list_my_documents(token: str, session: Session = Depends(get_session)):
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
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    application = _get_application_by_token(token, session)

    try:
        doc_type_enum = ApplicantDocumentType(doc_type)
    except ValueError:
        raise HTTPException(422, f"Invalid doc_type: {doc_type}")

    contents = await file.read()
    file_size = len(contents)

    if file_size == 0:
        raise HTTPException(422, "Empty file")
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large: {file_size} bytes (max 10 MB)")
    if file_size < MIN_FILE_SIZE:
        raise HTTPException(
            422,
            "File too small (less than 100 KB). Please use a higher quality photo."
        )

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, f"Unsupported file type: {content_type}")

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
            log.warning(f"Failed to delete old file: {e}")
        session.delete(existing)
        session.flush()

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
        f"type={doc_type} size={file_size}"
    )

    return _enrich_document(doc)


@router.delete("/{token}/documents/{doc_id}")
def delete_document(
    token: str,
    doc_id: int,
    session: Session = Depends(get_session),
):
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

    return {"deleted": True, "id": doc_id}


# ============================================================================
# Pack 13.1: Real OCR
# ============================================================================

@router.post("/{token}/documents/{doc_id}/recognize")
async def recognize_one_document(
    token: str,
    doc_id: int,
    session: Session = Depends(get_session),
):
    """
    Запустить OCR для одного документа.

    Возвращает обновлённый документ с parsed_data или с ocr_error.
    """
    application = _get_application_by_token(token, session)

    doc = session.get(ApplicantDocument, doc_id)
    if not doc or doc.application_id != application.id:
        raise HTTPException(404, "Document not found")

    # Для diploma_apostille — OCR не нужен, но мы возвращаем 200 с пустым parsed_data
    if doc.doc_type == ApplicantDocumentType.DIPLOMA_APOSTILLE:
        doc.status = ApplicantDocumentStatus.OCR_DONE
        doc.parsed_data = {}
        doc.ocr_error = None
        doc.ocr_completed_at = datetime.utcnow()
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return _enrich_document(doc)

    # Помечаем что OCR в процессе (на случай если клиент сразу обновит список)
    doc.status = ApplicantDocumentStatus.OCR_PENDING
    doc.ocr_error = None
    session.add(doc)
    session.commit()

    # Загружаем файл из storage
    storage = get_storage()
    try:
        image_bytes = storage.read(doc.storage_key)
    except Exception as e:
        log.error(f"Failed to read from storage: {e}")
        doc.status = ApplicantDocumentStatus.OCR_FAILED
        doc.ocr_error = f"Failed to read file: {e}"
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return _enrich_document(doc)

    # Вызываем OCR
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
    except OCRError as e:
        log.warning(f"OCR failed for doc {doc_id}: {e}")
        doc.status = ApplicantDocumentStatus.OCR_FAILED
        doc.ocr_error = str(e)[:500]
        doc.parsed_data = {}
    except Exception as e:
        log.error(f"Unexpected OCR error for doc {doc_id}: {e}", exc_info=True)
        doc.status = ApplicantDocumentStatus.OCR_FAILED
        doc.ocr_error = f"Unexpected error: {str(e)[:200]}"
        doc.parsed_data = {}

    session.add(doc)
    session.commit()
    session.refresh(doc)

    return _enrich_document(doc)


def _merge_parsed_to_applicant_data(
    documents: List[ApplicantDocument],
    existing: Optional[Applicant],
) -> dict:
    """
    Объединяет parsed_data из всех документов в единый dict для ApplicantData.

    Логика приоритета:
    - Поле уже заполнено в existing (НЕ пустое) → НЕ перезаписываем
    - Поле пустое → берём из parsed_data
    - Если несколько документов дают одно поле → приоритет:
      passport_internal_main > passport_foreign > passport_internal_address > diploma
      (ФИО кириллицей лучше извлекать из российского паспорта)

    Возвращает dict для подачи в ApplicantUpdate.
    """
    # Сортируем документы по приоритету
    priority = {
        ApplicantDocumentType.PASSPORT_INTERNAL_MAIN: 1,
        ApplicantDocumentType.PASSPORT_FOREIGN: 2,
        ApplicantDocumentType.PASSPORT_INTERNAL_ADDRESS: 3,
        ApplicantDocumentType.DIPLOMA_MAIN: 4,
        ApplicantDocumentType.DIPLOMA_APOSTILLE: 99,
        ApplicantDocumentType.OTHER: 99,
    }
    sorted_docs = sorted(documents, key=lambda d: priority.get(d.doc_type, 99))

    # Собираем результат
    result = {}

    def _set_if_empty(field: str, value):
        """Устанавливает поле если его ещё нет в result И в existing оно пустое."""
        if value is None or value == "":
            return
        if field in result:
            return  # уже взяли из более приоритетного документа
        # Проверка existing
        if existing is not None:
            existing_value = getattr(existing, field, None)
            if existing_value:  # уже заполнено клиентом — не трогаем
                return
        result[field] = value

    # Education — отдельно (это список, а не плоское поле)
    education_record = None

    for doc in sorted_docs:
        if doc.status != ApplicantDocumentStatus.OCR_DONE:
            continue
        p = doc.parsed_data or {}
        if not p:
            continue

        # Российский паспорт — главная
        if doc.doc_type == ApplicantDocumentType.PASSPORT_INTERNAL_MAIN:
            _set_if_empty("last_name_native", p.get("last_name_native"))
            _set_if_empty("first_name_native", p.get("first_name_native"))
            _set_if_empty("middle_name_native", p.get("middle_name_native"))
            _set_if_empty("birth_date", p.get("birth_date"))
            _set_if_empty("sex", p.get("sex"))
            # nationality — для РФ паспорта по умолчанию RUS
            if not result.get("nationality") and (existing is None or not existing.nationality):
                result["nationality"] = "RUS"
            if not result.get("home_country") and (existing is None or not existing.home_country):
                result["home_country"] = "RUS"

        # Российский паспорт — прописка
        elif doc.doc_type == ApplicantDocumentType.PASSPORT_INTERNAL_ADDRESS:
            _set_if_empty("home_address", p.get("registration_address"))

        # Загранпаспорт
        elif doc.doc_type == ApplicantDocumentType.PASSPORT_FOREIGN:
            _set_if_empty("last_name_latin", p.get("last_name_latin"))
            _set_if_empty("first_name_latin", p.get("first_name_latin"))
            _set_if_empty("birth_place_latin", p.get("birth_place_latin"))
            _set_if_empty("passport_number", p.get("passport_number"))
            _set_if_empty("passport_issue_date", p.get("passport_issue_date"))
            _set_if_empty("passport_issuer", p.get("passport_issuer"))
            _set_if_empty("nationality", p.get("nationality"))
            # ФИО кириллицей — из загранпаспорта если ещё нет (на всякий случай)
            _set_if_empty("last_name_native", p.get("last_name_native"))
            _set_if_empty("first_name_native", p.get("first_name_native"))
            _set_if_empty("birth_date", p.get("birth_date"))
            _set_if_empty("sex", p.get("sex"))

        # Диплом
        elif doc.doc_type == ApplicantDocumentType.DIPLOMA_MAIN:
            if education_record is None:
                education_record = {
                    "institution": p.get("institution"),
                    "graduation_year": p.get("graduation_year"),
                    "degree": p.get("degree"),
                    "specialty": p.get("specialty"),
                }
                # Только если в existing нет education — добавляем
                if existing is None or not existing.education:
                    # Очистим None-поля
                    cleaned = {k: v for k, v in education_record.items() if v}
                    if cleaned:
                        result["education"] = [cleaned]

    return result


@router.post("/{token}/documents/apply-to-applicant")
def apply_documents_to_applicant(
    token: str,
    session: Session = Depends(get_session),
):
    """
    Применить распознанные данные из всех документов к Applicant.

    Только пустые поля заполняются. Уже заполненные клиентом — не трогаются.
    """
    application = _get_application_by_token(token, session)

    docs = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application.id)
        .where(ApplicantDocument.status == ApplicantDocumentStatus.OCR_DONE)
    ).all()

    if not docs:
        raise HTTPException(
            422,
            "No recognized documents to apply. Run /recognize first."
        )

    # Получить существующий applicant если есть
    existing = None
    if application.applicant_id:
        existing = session.get(Applicant, application.applicant_id)

    # Собрать data из распознанных документов
    update_data = _merge_parsed_to_applicant_data(docs, existing)

    if not update_data:
        return {
            "applied_fields": [],
            "message": "Nothing to apply (all fields already filled or no new data)",
        }

    log.info(f"Applying OCR data to applicant: {list(update_data.keys())}")

    # Применить
    if not application.applicant_id:
        try:
            applicant = Applicant(**update_data)
        except Exception as e:
            raise HTTPException(
                422,
                detail={"message": "Cannot create applicant from OCR data", "error": str(e)},
            )
        session.add(applicant)
        session.flush()
        session.refresh(applicant)
        application.applicant_id = applicant.id
        session.add(application)
    else:
        applicant = existing
        for key, value in update_data.items():
            setattr(applicant, key, value)
        session.add(applicant)

    # Помечаем документы как применённые
    for d in docs:
        d.applied_to_applicant = True
        session.add(d)

    session.commit()
    session.refresh(applicant)

    return {
        "applied_fields": list(update_data.keys()),
        "applicant": _enrich_applicant(applicant),
    }
