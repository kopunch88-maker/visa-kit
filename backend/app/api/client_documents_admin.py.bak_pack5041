"""
Admin endpoints for viewing and managing client-uploaded documents.

Pack 13.2: даёт менеджеру доступ к документам клиента.
Pack 14b+c finishing:
- /recognize теперь принимает опциональный page_num (для PDF — выбор страницы)
- После успешного OCR автоматически применяет данные к Applicant
  (та же логика что в bulk import, для согласованности)
"""

import io
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from app.db.session import get_session, engine
from app.models import Application, Applicant
from app.models.applicant_document import (
    ApplicantDocument,
    ApplicantDocumentType,
    ApplicantDocumentStatus,
)
from app.services.storage import get_storage
from app.services.ocr import recognize_document, OCRError
from app.services.transliteration import transliterate_name
from app.services.applicant_passports import (
    upsert_by_number,
    reconcile_applicant_passports,
)  # Pack 41.0-C

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


def _pdf_page_to_jpeg(pdf_bytes: bytes, page_num: int, dpi: int = 200) -> bytes:
    """Конвертирует страницу PDF в JPEG bytes. page_num: 1-based."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError("pypdfium2 not installed")

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


# ============================================================================
# Pack 14b+c: автоприменение OCR данных к Applicant (после re-OCR)
# ============================================================================

def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False



# Pack 41.0-C: helper для извлечения PassportRecord из OCR parsed_data
def _extract_passport_from_ocr(parsed_data: dict, doc_type: "ApplicantDocumentType") -> Optional[dict]:
    """
    Pack 41.0-C: собирает PassportRecord-словарь из parsed_data OCR-документа.

    Возвращает dict готовый для upsert_by_number(), либо None если у документа
    нет валидного passport_number.

    Карта doc_type → passport_type:
      PASSPORT_INTERNAL_MAIN  → "RU_INTERNAL" (series+number склеивается)
      PASSPORT_FOREIGN        → "RU_FOREIGN"  (российский загранник)
      PASSPORT_NATIONAL       → берём из LLM (passport_type), fallback "FOREIGN"
      прочие                  → None (не паспорт)

    Не идёт в passports[]:
      PASSPORT_INTERNAL_ADDRESS — это страница регистрации, не сам паспорт
      RESIDENCE_CARD, CRIMINAL_RECORD — содержат имя/номер, но это НЕ паспорт
    """
    if not parsed_data:
        return None

    if doc_type == ApplicantDocumentType.PASSPORT_INTERNAL_MAIN:
        # Российский внутренний — склеиваем series + number
        series = (parsed_data.get("passport_series") or "").strip()
        number_only = (parsed_data.get("passport_number") or "").strip()
        if not (series and number_only):
            return None
        return {
            "number": f"{series}{number_only}",  # '4612' + '978898' → '4612978898'
            "issue_date": parsed_data.get("passport_issue_date"),
            "expiry_date": None,  # у внутреннего нет expiry
            "issuer": parsed_data.get("passport_issuer"),
            "issuer_ru": None,    # для RU_INTERNAL issuer и так на кириллице
            "passport_type": "RU_INTERNAL",
        }

    if doc_type == ApplicantDocumentType.PASSPORT_FOREIGN:
        # Российский загранник — passport_type всегда RU_FOREIGN (для P)
        number = (parsed_data.get("passport_number") or "").strip()
        if not number:
            return None
        return {
            "number": number,
            "issue_date": parsed_data.get("passport_issue_date"),
            "expiry_date": parsed_data.get("passport_expiry_date"),
            "issuer": parsed_data.get("passport_issuer"),
            "issuer_ru": None,
            "passport_type": "RU_FOREIGN",
        }

    if doc_type == ApplicantDocumentType.PASSPORT_NATIONAL:
        # Иностранный паспорт — passport_type из LLM (Pack 41.0-C OCR prompt),
        # fallback FOREIGN если LLM не вернул.
        number = (parsed_data.get("passport_number") or "").strip()
        if not number:
            return None
        llm_type = (parsed_data.get("passport_type") or "").strip().upper()
        if llm_type not in ("P", "PP", "D", "O"):
            llm_type = None
        # PassportRecord.passport_type — наш внутренний enum; P/PP/D/O — это
        # ICAO-категория паспорта, мы их все храним под "FOREIGN" для логики
        # primary, а сам ICAO-тип кладём в notes для информации.
        return {
            "number": number,
            "issue_date": parsed_data.get("passport_issue_date"),
            "expiry_date": parsed_data.get("passport_expiry_date"),
            "issuer": parsed_data.get("passport_issuer"),
            "issuer_ru": None,
            "passport_type": "FOREIGN",
            "notes": f"ICAO type: {llm_type}" if llm_type else None,
        }

    return None


def _collect_ocr_data_from_application(session: Session, application_id: int) -> tuple[dict, list[dict]]:
    """
    Pack 41.0-C: возвращает (scalar_data, passport_records).

    scalar_data — поля для применения к Applicant через setattr (имя, ДР, sex,
    nationality, и т.д.). Паспортные поля из scalar_data ИСКЛЮЧЕНЫ — они идут
    в passports[] через upsert_by_number.

    passport_records — список PassportRecord-словарей, по одному на каждый
    OCR'нутый паспорт (PASSPORT_INTERNAL_MAIN/FOREIGN/NATIONAL).
    """
    docs = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application_id)
        .where(ApplicantDocument.status == ApplicantDocumentStatus.OCR_DONE)
    ).all()

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
    sorted_docs = sorted(docs, key=lambda d: priority.get(d.doc_type, 99))
    result: dict = {}
    passport_records: list[dict] = []  # Pack 41.0-C

    for doc in sorted_docs:
        p = doc.parsed_data or {}
        if not p:
            continue

        # Pack 41.0-C: извлекаем PassportRecord (если документ — паспорт)
        passport_rec = _extract_passport_from_ocr(p, doc.doc_type)
        if passport_rec:
            passport_records.append(passport_rec)

        if doc.doc_type == ApplicantDocumentType.PASSPORT_INTERNAL_MAIN:
            for f in ["last_name_native", "first_name_native", "middle_name_native", "birth_date", "sex"]:
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

    return result, passport_records


# Pack 34.1 — нормализация degree (EN→RU + инженер по коду ОКСО)
from app.services.degree_mapper import normalize_degree, extract_specialty_code


def _build_education_from_diploma(session: Session, application_id: int) -> Optional[dict]:
    docs = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application_id)
        .where(ApplicantDocument.doc_type == ApplicantDocumentType.DIPLOMA_MAIN)
        .where(ApplicantDocument.status == ApplicantDocumentStatus.OCR_DONE)
    ).all()
    for doc in docs:
        p = doc.parsed_data or {}
        if not p:
            continue
        # Pack 34.1 — нормализуем degree (EN→RU + инженерные специальности
        # с кодом ОКСО 07-29 получают «Инженер» вместо «Специалист»)
        specialty_raw = p.get("specialty")
        specialty_code = extract_specialty_code(specialty_raw)
        degree_normalized = normalize_degree(p.get("degree"), specialty_code)
        record = {
            "institution": p.get("institution"),
            "graduation_year": p.get("graduation_year"),
            "degree": degree_normalized,
            "specialty": specialty_raw,
        }
        cleaned = {k: v for k, v in record.items() if not _is_empty(v)}
        if cleaned:
            return cleaned
    return None


def _auto_apply_ocr_to_applicant(application_id: int):
    """
    Применяет OCR данные ко всем документам заявки → Applicant.
    Создаёт нового Applicant если не было, обновляет ТОЛЬКО ПУСТЫЕ поля если был.
    Создаёт собственную сессию (для использования из любого endpoint).
    """
    with Session(engine) as session:
        application = session.get(Application, application_id)
        if not application:
            log.warning(f"Auto-apply: application {application_id} not found")
            return

        # Pack 41.0-C: collect_ocr_data возвращает кортеж
        ocr_data, passport_records = _collect_ocr_data_from_application(session, application_id)
        if not ocr_data:
            log.info(f"Auto-apply: no OCR data for app {application_id}")
            return

        existing = None
        if application.applicant_id:
            existing = session.get(Applicant, application.applicant_id)

        update_data = {}
        for field, value in ocr_data.items():
            if _is_empty(value):
                continue
            current = getattr(existing, field, None) if existing else None
            if _is_empty(current):
                update_data[field] = value

        # Авто-транслитерация
        for native_field, latin_field in [
            ("last_name_native", "last_name_latin"),
            ("first_name_native", "first_name_latin"),
        ]:
            if native_field in update_data and latin_field not in update_data:
                new_native = update_data[native_field]
                if not _is_empty(new_native):
                    current_latin = getattr(existing, latin_field, None) if existing else None
                    if _is_empty(current_latin):
                        update_data[latin_field] = transliterate_name(new_native)

        # Education — Pack 25.12: DIPLOMA_MAIN всегда замещает education
        # (реальный документ важнее легенды Pack 19.0)
        edu_record = _build_education_from_diploma(session, application_id)
        if edu_record:
            update_data["education"] = [edu_record]

        if not update_data and not passport_records:
            log.info(f"Auto-apply: nothing to update for app {application_id}")
            return

        log.info(f"Auto-apply: updating applicant for app {application_id}: fields={list(update_data.keys())}")

        if not application.applicant_id:
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
            log.info(f"Auto-apply: created new Applicant id={applicant.id}")
        else:
            applicant = existing
            for key, value in update_data.items():
                setattr(applicant, key, value)
            session.add(applicant)

        # Помечаем все OCR_DONE документы как applied
        all_docs = session.exec(
            select(ApplicantDocument)
            .where(ApplicantDocument.application_id == application_id)
            .where(ApplicantDocument.status == ApplicantDocumentStatus.OCR_DONE)
        ).all()
        for d in all_docs:
            d.applied_to_applicant = True
            session.add(d)

        # Pack 41.0-C: применяем passport_records через upsert + reconcile
        if passport_records:
            new_passports = list(applicant.passports or [])
            for rec in passport_records:
                if not rec.get("number"):
                    continue
                new_passports, _affected, created = upsert_by_number(
                    new_passports,
                    number=rec["number"],
                    issue_date=rec.get("issue_date"),
                    expiry_date=rec.get("expiry_date"),
                    issuer=rec.get("issuer"),
                    issuer_ru=rec.get("issuer_ru"),
                    passport_type=rec.get("passport_type"),
                    source="ocr",
                )
                log.info(
                    f"Pack 41.0-C: passport upsert num={rec['number']!r} "
                    f"type={rec.get('passport_type')} created={created}"
                )
            applicant.passports = new_passports
            reconcile_applicant_passports(applicant)
            session.add(applicant)

        session.commit()


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/{application_id}/client-documents")
def list_client_documents(
    application_id: int,
    session: Session = Depends(get_session),
):
    """Получить все документы клиента для заявки."""
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
    body: dict = Body(default={}),
    session: Session = Depends(get_session),
):
    """
    Запустить OCR заново для документа клиента.

    Body (опционально):
    {
        "page_num": int  # для PDF — выбрать другую страницу для OCR
                         # требует наличия original_storage_key
    }

    Если page_num передан и документ имеет original_storage_key (PDF):
    - читаем оригинал PDF из storage
    - конвертируем выбранную страницу в JPEG
    - заменяем storage_key на новый JPEG (старый удаляется)
    - запускаем OCR на новом JPEG
    Если page_num не передан:
    - стандартное поведение (OCR текущего файла)

    После успешного OCR — автоматически применяем данные к Applicant
    """
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")

    doc = session.get(ApplicantDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.application_id != application_id:
        raise HTTPException(403, "Document does not belong to this application")

    page_num = body.get("page_num") if isinstance(body, dict) else None
    if page_num is not None:
        try:
            page_num = int(page_num)
            if page_num < 1:
                page_num = None
        except (TypeError, ValueError):
            page_num = None

    # Apostille — без OCR
    if doc.doc_type == ApplicantDocumentType.DIPLOMA_APOSTILLE:
        doc.status = ApplicantDocumentStatus.OCR_DONE
        doc.parsed_data = {}
        doc.ocr_error = None
        doc.ocr_completed_at = datetime.utcnow()
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return _enrich_document(doc)

    storage = get_storage()

    # === Если page_num передан — пересобираем JPEG из оригинала PDF ===
    new_storage_key = None
    if page_num is not None:
        if not doc.original_storage_key:
            raise HTTPException(
                422,
                "Cannot select a different page — this document has no original PDF stored.",
            )

        log.info(f"Admin: re-rendering doc {doc_id} from PDF page {page_num}")

        try:
            pdf_bytes = storage.read(doc.original_storage_key)
        except Exception as e:
            log.error(f"Failed to read original PDF: {e}")
            raise HTTPException(500, f"Failed to read original PDF: {e}")

        try:
            jpeg_bytes = _pdf_page_to_jpeg(pdf_bytes, page_num)
        except Exception as e:
            log.error(f"Failed to convert PDF page {page_num}: {e}")
            raise HTTPException(500, f"Failed to convert PDF page: {e}")

        # Сохраняем новый JPEG и заменяем storage_key
        timestamp = int(time.time())
        doc_type_str = doc.doc_type.value
        new_storage_key = (
            f"applications/{application_id}/documents/"
            f"{doc_type_str}_{timestamp}_p{page_num}.jpg"
        )

        try:
            storage.save(new_storage_key, jpeg_bytes, content_type="image/jpeg")
        except Exception as e:
            log.error(f"Failed to save new JPEG: {e}")
            raise HTTPException(500, f"Failed to save new JPEG: {e}")

        # Удаляем старый JPEG (но НЕ оригинал PDF)
        old_jpeg_key = doc.storage_key
        if old_jpeg_key and old_jpeg_key != doc.original_storage_key:
            try:
                storage.delete(old_jpeg_key)
            except Exception as e:
                log.warning(f"Failed to delete old JPEG {old_jpeg_key}: {e}")

        # Обновляем поля документа
        doc.storage_key = new_storage_key
        doc.file_name = (doc.original_file_name or doc.file_name).replace(".pdf", "").replace(".PDF", "") + f"_page{page_num}.jpg"
        doc.file_size = len(jpeg_bytes)
        doc.content_type = "image/jpeg"

    # === Запускаем OCR ===
    doc.status = ApplicantDocumentStatus.OCR_PENDING
    doc.ocr_error = None
    session.add(doc)
    session.commit()

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
        # Сбрасываем applied_to_applicant — данные изменились, нужно применить заново
        doc.applied_to_applicant = False
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

    # === Автоприменение к Applicant если OCR прошёл ===
    if doc.status == ApplicantDocumentStatus.OCR_DONE:
        try:
            _auto_apply_ocr_to_applicant(application_id)
            # Перечитаем документ чтобы applied_to_applicant обновилось
            session.refresh(doc)
        except Exception as e:
            log.error(f"Auto-apply after re-OCR failed: {e}", exc_info=True)

    return _enrich_document(doc)
# =============================================================================
# Pack 42.1 — удаление документа клиента
# =============================================================================

@router.delete("/{application_id}/client-documents/{doc_id}")
def admin_delete_client_document(
    application_id: int,
    doc_id: int,
    session: Session = Depends(get_session),
):
    """
    Pack 42.1 — удалить документ клиента полностью (БД + R2 storage).

    Используется когда клиент ошибочно загрузил не тот файл и менеджер
    хочет очистить карточку перед повторной загрузкой.

    Удаляются:
      - Запись ApplicantDocument из БД
      - storage_key файл в R2 (текущая JPEG/изображение)
      - original_storage_key файл в R2 (оригинальный PDF, если был)

    Не сбрасывает applied данные на applicant — если документ был ранее
    распознан и применён, поля в applicant остаются. Это намеренно:
    менеджер может удалить ошибочный документ не теряя уже исправленные
    вручную данные клиента.
    """
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")

    doc = session.get(ApplicantDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.application_id != application_id:
        raise HTTPException(403, "Document does not belong to this application")

    storage = get_storage()

    # Удаляем оба storage-файла (молча игнорируем ошибки удаления,
    # чтобы не блокировать удаление из БД из-за уже-удалённого файла).
    if doc.storage_key:
        try:
            storage.delete(doc.storage_key)
            log.info(f"Pack 42.1: deleted storage {doc.storage_key}")
        except Exception as e:
            log.warning(f"Pack 42.1: failed to delete {doc.storage_key}: {e}")

    if doc.original_storage_key and doc.original_storage_key != doc.storage_key:
        try:
            storage.delete(doc.original_storage_key)
            log.info(f"Pack 42.1: deleted original storage {doc.original_storage_key}")
        except Exception as e:
            log.warning(f"Pack 42.1: failed to delete {doc.original_storage_key}: {e}")

    # Удаляем из БД
    session.delete(doc)
    session.commit()

    log.info(f"Pack 42.1: client document {doc_id} (app={application_id}) deleted")
    return {"deleted": True, "doc_id": doc_id}
