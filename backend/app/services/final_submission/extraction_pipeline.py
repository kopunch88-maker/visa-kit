# -*- coding: utf-8 -*-
"""
Pack 39.0-C — Extraction pipeline для финальной проверки.

Оркестратор: для одного документа
1. читает файл из R2
2. вызывает extractor → extracted_text + method + cost + page_count
3. вызывает classifier (text-only если текст есть, иначе Vision на первой стр.)
4. UPDATE final_submission_document в БД

Запускается в BackgroundTask после upload. Ошибки логируются, документ
остаётся с пустыми полями (менеджер может вручную поправить категорию).

NB: создаёт собственную сессию БД, т.к. вызывается в фоне после ответа
эндпоинта (изначальная сессия закрыта).
"""
import logging
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.db.session import engine
from app.models import FinalSubmissionDocument
from app.services.storage import get_storage

from .extractor import extract_document_text, ExtractionResult
from .classifier import (
    classify_document_by_text,
    classify_document_by_image,
    ClassificationResult,
)

log = logging.getLogger(__name__)


async def run_extraction_pipeline(doc_id: int) -> None:
    """
    Извлекает текст + классифицирует + обновляет БД.
    Безопасна: все ошибки логируются, исключения наружу не пробрасываются.
    """
    log.info(f"[extraction_pipeline] start doc_id={doc_id}")

    storage = get_storage()

    with Session(engine) as session:
        doc = session.get(FinalSubmissionDocument, doc_id)
        if not doc:
            log.warning(f"[extraction_pipeline] doc_id={doc_id} not found, skip")
            return
        if doc.extracted_text:
            log.info(f"[extraction_pipeline] doc_id={doc_id} already has extracted_text, skip")
            return

        # 1. Скачать файл из R2
        try:
            content = storage.read(doc.storage_key)
        except Exception as e:
            log.error(f"[extraction_pipeline] R2 read failed for doc_id={doc_id}: {e}")
            return

        # 2. Extract text
        try:
            extr: ExtractionResult = await extract_document_text(
                content=content,
                filename=doc.original_filename,
                mime_type=doc.mime_type,
            )
        except Exception as e:
            log.exception(f"[extraction_pipeline] extract failed for doc_id={doc_id}: {e}")
            return

        log.info(
            f"[extraction_pipeline] doc_id={doc_id} extracted: method={extr.method}, "
            f"chars={len(extr.text)}, pages={extr.page_count}, cost=${extr.cost_usd}"
        )

        # 3. Classify
        cls: ClassificationResult
        if extr.text and len(extr.text.strip()) >= 30:
            # Text-only classify — дешевле
            try:
                cls = await classify_document_by_text(extr.text)
            except Exception as e:
                log.exception(f"[extraction_pipeline] text classify failed: {e}")
                cls = ClassificationResult(
                    category="other",
                    confidence=Decimal("0"),
                    reasoning=f"Classifier error: {e}",
                    method="fallback",
                    cost_usd=Decimal("0"),
                )
        else:
            # Нет текста (например, скан с failed extraction) — Vision-классификация
            # по первой странице. Перерендерим страницу.
            try:
                jpeg, mime = await _render_first_page_for_classify(content, doc.mime_type, doc.original_filename)
                if jpeg:
                    cls = await classify_document_by_image(jpeg, mime)
                else:
                    cls = ClassificationResult(
                        category="other",
                        confidence=Decimal("0"),
                        reasoning="No text and cannot render image",
                        method="fallback",
                        cost_usd=Decimal("0"),
                    )
            except Exception as e:
                log.exception(f"[extraction_pipeline] vision classify failed: {e}")
                cls = ClassificationResult(
                    category="other",
                    confidence=Decimal("0"),
                    reasoning=f"Vision classifier error: {e}",
                    method="fallback",
                    cost_usd=Decimal("0"),
                )

        log.info(
            f"[extraction_pipeline] doc_id={doc_id} classified: "
            f"category={cls.category}, conf={cls.confidence}, method={cls.method}"
        )

        # 4. UPDATE
        # Перечитываем doc свежим в той же сессии (на случай если был изменён)
        fresh_doc = session.get(FinalSubmissionDocument, doc_id)
        if not fresh_doc:
            log.warning(f"[extraction_pipeline] doc_id={doc_id} disappeared, skip update")
            return

        # Не перезаписываем категорию если менеджер уже руками поставил
        if fresh_doc.doc_category_source != "manual":
            fresh_doc.doc_category = cls.category
            fresh_doc.doc_category_confidence = cls.confidence
            fresh_doc.doc_category_source = "ai"

        fresh_doc.extracted_text = extr.text
        fresh_doc.extraction_method = extr.method if extr.method != "failed" else None
        fresh_doc.extraction_cost_usd = (extr.cost_usd + cls.cost_usd)
        fresh_doc.page_count = extr.page_count if extr.page_count > 0 else None

        session.add(fresh_doc)
        session.commit()
        log.info(f"[extraction_pipeline] doc_id={doc_id} updated successfully")


async def _render_first_page_for_classify(
    content: bytes,
    mime: str,
    filename: str,
) -> tuple[Optional[bytes], str]:
    """Рендерит первую страницу для Vision-классификации."""
    from pathlib import Path
    ext = Path(filename).suffix.lower()

    if ext == ".pdf" or mime == "application/pdf":
        try:
            from .extractor import _pdf_page_to_jpeg
            jpeg = _pdf_page_to_jpeg(content, page_num=1, dpi=120)
            return jpeg, "image/jpeg"
        except Exception as e:
            log.warning(f"PDF render for classify failed: {e}")
            return None, ""

    if ext in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"):
        from .extractor import _normalize_image_for_vision
        return _normalize_image_for_vision(content, mime)

    # DOCX — нет смысла классифицировать по картинке
    return None, ""
