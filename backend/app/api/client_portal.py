"""
Client portal — эндпоинты для самого клиента.

Авторизация — по токену в URL.

Pack 13.1.1: preview-apply (показ конфликтов) и overrides
Pack 13.1.2: автоматическая ГОСТ-транслитерация *_native → *_latin при apply
Pack 13.1.3: хранение оригинального PDF + генерация JPEG для OCR на клиенте
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional, List
from pathlib import Path as PathLib

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
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
from app.services.transliteration import transliterate_name

log = logging.getLogger(__name__)

router = APIRouter(prefix="/client", tags=["client-portal"])


# ============================================================================
# Helpers
# ============================================================================

MAX_FILE_SIZE = 10 * 1024 * 1024
MIN_FILE_SIZE = 100 * 1024

# Pack 13.1.3: основной файл (для OCR + превью) — только изображения
ALLOWED_PRIMARY_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

# Оригинал — может быть PDF или HEIC (если клиент решил их сохранить как есть)
ALLOWED_ORIGINAL_CONTENT_TYPES = {
    "application/pdf",
    "image/heic",
    "image/heif",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
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
    """Pack 13.1.3: расширено полями про оригинал."""
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
        # Pack 13.1.3
        "has_original": has_original,
        "original_download_url": original_download_url,
        "original_file_name": doc.original_file_name,
    }


# ============================================================================
# Profile endpoints
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
# Documents
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
    # Pack 13.1.3: опциональный второй файл — оригинал PDF (или HEIC)
    original_file: Optional[UploadFile] = File(default=None),
    session: Session = Depends(get_session),
):
    """
    Загрузка документа клиентом.

    Pack 13.1.3:
    - file — основной (всегда JPEG/PNG/WebP, для OCR + превью).
      Если клиент загружает PDF, frontend сам конвертирует выбранную страницу
      в JPEG и отправляет её сюда.
    - original_file — опциональный оригинал (PDF), хранится для финальной
      отправки в инстанцию.

    Старые клиенты могут продолжать слать только один файл (без original_file) —
    это работает как раньше.
    """
    application = _get_application_by_token(token, session)

    try:
        doc_type_enum = ApplicantDocumentType(doc_type)
    except ValueError:
        raise HTTPException(422, f"Invalid doc_type: {doc_type}")

    # === Валидация основного файла ===
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
    if content_type not in ALLOWED_PRIMARY_CONTENT_TYPES:
        raise HTTPException(
            415,
            f"Primary file must be an image (JPEG/PNG/WebP). Got: {content_type}. "
            f"For PDF — frontend should convert it to JPEG before upload."
        )

    # === Валидация оригинала (опционально) ===
    original_contents = None
    original_size = None
    original_content_type = None
    original_name = None

    if original_file is not None:
        original_contents = await original_file.read()
        original_size = len(original_contents)

        if original_size == 0:
            # Пустой original — игнорируем
            original_contents = None
        else:
            if original_size > MAX_FILE_SIZE:
                raise HTTPException(
                    413,
                    f"Original file too large: {original_size} bytes (max 10 MB)"
                )

            original_content_type = original_file.content_type or "application/octet-stream"
            if original_content_type not in ALLOWED_ORIGINAL_CONTENT_TYPES:
                raise HTTPException(
                    415,
                    f"Original file type not supported: {original_content_type}"
                )
            original_name = original_file.filename or f"{doc_type}_original.bin"

    # === Удаление старого документа того же типа ===
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
            log.warning(f"Failed to delete old primary file: {e}")
        if existing.original_storage_key:
            try:
                storage.delete(existing.original_storage_key)
            except Exception as e:
                log.warning(f"Failed to delete old original file: {e}")
        session.delete(existing)
        session.flush()

    # === Сохраняем основной файл (JPEG для OCR) ===
    timestamp = int(time.time())
    primary_filename = file.filename or f"{doc_type}.jpg"
    primary_extension = PathLib(primary_filename).suffix.lower() or ".jpg"
    storage_key = (
        f"applications/{application.id}/documents/"
        f"{doc_type}_{timestamp}{primary_extension}"
    )

    try:
        storage.save(storage_key, contents, content_type=content_type)
    except Exception as e:
        log.error(f"Failed to save primary file: {e}")
        raise HTTPException(500, f"Failed to save file: {e}")

    # === Сохраняем оригинал (если был передан) ===
    original_storage_key = None
    if original_contents:
        original_extension = PathLib(original_name).suffix.lower() or ".pdf"
        original_storage_key = (
            f"applications/{application.id}/documents/"
            f"{doc_type}_{timestamp}_original{original_extension}"
        )
        try:
            storage.save(
                original_storage_key,
                original_contents,
                content_type=original_content_type,
            )
        except Exception as e:
            log.error(f"Failed to save original file: {e}")
            # Если оригинал не сохранился — удаляем и primary, чтобы не было рассинхрона
            try:
                storage.delete(storage_key)
            except Exception:
                pass
            raise HTTPException(500, f"Failed to save original file: {e}")

    # === Создаём запись в БД ===
    doc = ApplicantDocument(
        application_id=application.id,
        doc_type=doc_type_enum,
        storage_key=storage_key,
        file_name=primary_filename,
        file_size=file_size,
        content_type=content_type,
        original_storage_key=original_storage_key,
        original_file_name=original_name,
        original_file_size=original_size,
        original_content_type=original_content_type,
        status=ApplicantDocumentStatus.UPLOADED,
        parsed_data={},
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    log.info(
        f"Uploaded document: app={application.id} type={doc_type} "
        f"primary_size={file_size} original_size={original_size}"
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
        log.warning(f"Failed to delete primary from storage: {e}")
    if doc.original_storage_key:
        try:
            storage.delete(doc.original_storage_key)
        except Exception as e:
            log.warning(f"Failed to delete original from storage: {e}")

    session.delete(doc)
    session.commit()

    return {"deleted": True, "id": doc_id}


# ============================================================================
# OCR (без изменений — работает с storage_key — это всегда JPEG/PNG/WebP)
# ============================================================================

@router.post("/{token}/documents/{doc_id}/recognize")
async def recognize_one_document(
    token: str,
    doc_id: int,
    session: Session = Depends(get_session),
):
    application = _get_application_by_token(token, session)

    doc = session.get(ApplicantDocument, doc_id)
    if not doc or doc.application_id != application.id:
        raise HTTPException(404, "Document not found")

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
        log.error(f"Failed to read from storage: {e}")
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


# ============================================================================
# Field-by-field comparison helpers (без изменений из 13.1.1)
# ============================================================================

FLAT_OCR_FIELDS = [
    "last_name_native", "first_name_native", "middle_name_native",
    "last_name_latin", "first_name_latin",
    "birth_date", "birth_place_latin", "nationality", "sex",
    "passport_number", "passport_issue_date", "passport_issuer",
    "home_address", "home_country",
]


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _normalize_for_compare(field: str, value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if field in (
        "last_name_native", "first_name_native", "middle_name_native",
        "last_name_latin", "first_name_latin",
        "birth_place_latin", "passport_issuer", "home_address",
    ):
        return s.lower()
    if field in ("passport_number", "passport_series"):
        return re.sub(r"\D", "", s)
    return s


def _values_match(field: str, current, ocr) -> bool:
    if _is_empty(current) and _is_empty(ocr):
        return True
    if _is_empty(current) or _is_empty(ocr):
        return False
    return _normalize_for_compare(field, current) == _normalize_for_compare(field, ocr)


def _collect_ocr_data(documents: List[ApplicantDocument]) -> dict:
    priority = {
        ApplicantDocumentType.PASSPORT_INTERNAL_MAIN: 1,
        ApplicantDocumentType.PASSPORT_FOREIGN: 2,
        ApplicantDocumentType.PASSPORT_INTERNAL_ADDRESS: 3,
        ApplicantDocumentType.DIPLOMA_MAIN: 4,
        ApplicantDocumentType.DIPLOMA_APOSTILLE: 99,
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
            for f in ["last_name_native", "first_name_native", "middle_name_native",
                      "birth_date", "sex"]:
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

    return result


def _build_education_from_diploma(documents: List[ApplicantDocument]) -> Optional[dict]:
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
# Preview-apply
# ============================================================================

@router.post("/{token}/documents/preview-apply")
def preview_apply(
    token: str,
    session: Session = Depends(get_session),
):
    application = _get_application_by_token(token, session)

    docs = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application.id)
        .where(ApplicantDocument.status == ApplicantDocumentStatus.OCR_DONE)
    ).all()

    if not docs:
        return {"auto_fill": [], "conflicts": [], "same": [], "education": None}

    existing = None
    if application.applicant_id:
        existing = session.get(Applicant, application.applicant_id)

    ocr_data = _collect_ocr_data(docs)

    auto_fill = []
    conflicts = []
    same = []

    for field in FLAT_OCR_FIELDS:
        ocr_value = ocr_data.get(field)
        current_value = getattr(existing, field, None) if existing else None

        if _is_empty(ocr_value):
            continue

        if _is_empty(current_value):
            auto_fill.append({"field": field, "ocr_value": ocr_value})
        elif _values_match(field, current_value, ocr_value):
            same.append({"field": field, "value": current_value})
        else:
            conflicts.append({
                "field": field,
                "current_value": current_value,
                "ocr_value": ocr_value,
            })

    edu_record = _build_education_from_diploma(docs)
    education_info = None
    if edu_record:
        existing_edu = (existing.education if existing else []) or []
        if not existing_edu:
            education_info = {"type": "auto_fill", "ocr_value": edu_record}
        else:
            education_info = {
                "type": "conflict",
                "current_value": existing_edu[0],
                "ocr_value": edu_record,
                "current_count": len(existing_edu),
            }

    return {
        "auto_fill": auto_fill,
        "conflicts": conflicts,
        "same": same,
        "education": education_info,
    }


# ============================================================================
# Apply with overrides + auto-transliteration (Pack 13.1.2)
# ============================================================================

@router.post("/{token}/documents/apply-to-applicant")
def apply_documents_to_applicant(
    token: str,
    body: dict = Body(default={}),
    session: Session = Depends(get_session),
):
    application = _get_application_by_token(token, session)

    overrides = set(body.get("overrides") or [])
    education_action = body.get("education_action") or "auto"

    docs = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application.id)
        .where(ApplicantDocument.status == ApplicantDocumentStatus.OCR_DONE)
    ).all()

    if not docs:
        raise HTTPException(422, "No recognized documents to apply.")

    existing = None
    if application.applicant_id:
        existing = session.get(Applicant, application.applicant_id)

    ocr_data = _collect_ocr_data(docs)

    update_data = {}

    for field, ocr_value in ocr_data.items():
        if _is_empty(ocr_value):
            continue
        current_value = getattr(existing, field, None) if existing else None
        if _is_empty(current_value):
            update_data[field] = ocr_value
        elif field in overrides:
            update_data[field] = ocr_value

    # Pack 13.1.2: автотранслит
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
                generated_latin = transliterate_name(new_native)
                current_latin = getattr(existing, latin_field, None) if existing else None
                if _is_empty(current_latin):
                    update_data[latin_field] = generated_latin
                elif native_field in overrides:
                    update_data[latin_field] = generated_latin

    # Education
    edu_record = _build_education_from_diploma(docs)
    if edu_record:
        existing_edu = (existing.education if existing else []) or []
        if not existing_edu:
            update_data["education"] = [edu_record]
        elif education_action == "replace":
            update_data["education"] = [edu_record]
        elif education_action == "add":
            update_data["education"] = list(existing_edu) + [edu_record]

    if not update_data:
        return {
            "applied_fields": [],
            "message": "Nothing to apply (all fields already filled or no new data)",
        }

    log.info(
        f"Applying OCR data to applicant: fields={list(update_data.keys())} "
        f"overrides={overrides} education_action={education_action}"
    )

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

    for d in docs:
        d.applied_to_applicant = True
        session.add(d)

    session.commit()
    session.refresh(applicant)

    return {
        "applied_fields": list(update_data.keys()),
        "applicant": _enrich_applicant(applicant),
    }
