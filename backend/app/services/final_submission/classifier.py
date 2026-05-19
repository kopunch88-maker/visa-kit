# -*- coding: utf-8 -*-
"""
Pack 39.0-C — Classifier для финальной проверки документов.

В отличие от services.ocr.classify_document (Pack 14c) — там категории для
российских документов до подачи (паспорт/диплом/ЕГРЮЛ). Тут другие категории
для финального пакета на подачу в консульство.

Стратегия:
- Если есть extracted_text — классифицируем по тексту (text-only, дёшево)
- Если текста нет (скан без OCR) — классифицируем по первой странице (Vision)

Модель: claude-haiku-4-5 (классификация — простая задача, экономия 4-5x).
"""
import io
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

from app.services.llm import get_llm_client

log = logging.getLogger(__name__)


CLASSIFIER_MODEL = "anthropic/claude-haiku-4-5"

# Приближённая стоимость классификации (input ~1000 tok + output ~150 tok @ haiku)
APPROX_COST_PER_CLASSIFY_USD = Decimal("0.003")

# Валидные категории — должны совпадать с FinalSubmissionDocCategory enum в моделях.
VALID_CATEGORIES = {
    "passport_main",
    "passport_other",
    "apostille",
    "contract",
    "act",
    "invoice",
    "bank_statement",
    "cv",
    "npd_certificate",
    "diploma",
    "jurada_translation",
    "mi_t_form",
    "designacion",
    "compromiso",
    "declaracion",
    "ex17",
    "photo_3x4",
    "medical_insurance",
    "criminal_record",
    "marriage_certificate",
    "other",
}


CLASSIFIER_PROMPT = """\
You are classifying a document for a Spain Digital Nomad visa application.

Classify the document into ONE of these categories (use the exact string):

- passport_main: passport biographical page (photo, name, dates, document number)
- passport_other: other passport pages (visas, stamps, residence, registration)
- apostille: apostille certificate (typically Russian title "АПОСТИЛЬ" with stamp)
- contract: service contract / labour contract (договор оказания услуг, контракт)
- act: act of work delivery / completion (акт сдачи-приёмки выполненных работ/услуг)
- invoice: invoice / payment request (счёт, инвойс)
- bank_statement: bank account statement showing transactions (выписка из банка)
- cv: CV / resume (резюме, curriculum vitae)
- npd_certificate: self-employment income certificate from Russian FNS (справка о доходах НПД, самозанятость)
- diploma: educational diploma / degree certificate
- jurada_translation: certified Spanish translation (traducción jurada, signed by sworn translator)
- mi_t_form: form MI-T (Ministerio de Inclusión, Trabajo y Seguridad Social authorization)
- designacion: designación de representante form
- compromiso: compromiso de no trabajar form
- declaracion: declaración responsable form
- ex17: form EX-17 (TIE / residence card application)
- photo_3x4: passport-size photograph (typically 3x4 cm white background)
- medical_insurance: medical insurance certificate / policy
- criminal_record: criminal record certificate (apostilled, with translation)
- marriage_certificate: marriage / divorce certificate
- other: anything that doesn't fit above

Return STRICT JSON with these fields:
{
  "category": "<one of the values above>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<short explanation in Russian, max 200 chars>"
}

Confidence guide:
- 0.95+: title/structure clearly matches (e.g. "Договор оказания услуг №..." → contract)
- 0.7-0.94: strong signals but some ambiguity
- 0.4-0.69: weak match, could be several categories
- < 0.4: very uncertain, set "other" with low confidence

If you cannot determine the category, return "other" with confidence < 0.4.

Return ONLY JSON, no commentary or markdown.
"""


@dataclass
class ClassificationResult:
    category: str               # one of VALID_CATEGORIES
    confidence: Decimal         # 0.000-1.000
    reasoning: str
    method: str                 # 'text' | 'vision' | 'fallback'
    cost_usd: Decimal


async def classify_document_by_text(text: str) -> ClassificationResult:
    """
    Классификация по уже извлечённому тексту. Дешевле чем Vision.
    """
    if not text or len(text.strip()) < 30:
        return ClassificationResult(
            category="other",
            confidence=Decimal("0.0"),
            reasoning="Empty or too short text",
            method="fallback",
            cost_usd=Decimal("0"),
        )

    # Обрезаем длинный текст (хватит первых ~3000 символов для классификации)
    sample = text[:3000]
    user_message = f"{CLASSIFIER_PROMPT}\n\nDocument text:\n---\n{sample}\n---"

    client = get_llm_client()
    try:
        if hasattr(client, "complete_text"):
            response_text = await client.complete_text(
                system="You are a precise document classifier. Return strict JSON.",
                user=user_message,
                model=CLASSIFIER_MODEL,
                max_tokens=300,
                temperature=0.0,
            )
        else:
            # Fallback через complete_vision с 1×1 заглушкой
            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (1, 1), color="white").save(buf, format="JPEG")
            response_text = await client.complete_vision(
                system="You are a precise document classifier. Return strict JSON.",
                user=user_message,
                image_bytes=buf.getvalue(),
                image_media_type="image/jpeg",
                model=CLASSIFIER_MODEL,
                max_tokens=300,
                temperature=0.0,
            )
    except Exception as e:
        log.error(f"Classifier LLM call failed: {e}")
        return ClassificationResult(
            category="other",
            confidence=Decimal("0.0"),
            reasoning=f"LLM error: {e}",
            method="fallback",
            cost_usd=Decimal("0"),
        )

    return _parse_classifier_response(response_text, method="text", cost=APPROX_COST_PER_CLASSIFY_USD)


async def classify_document_by_image(image_bytes: bytes, mime_type: str) -> ClassificationResult:
    """Классификация по изображению первой страницы (для сканов без текста)."""
    client = get_llm_client()
    try:
        response_text = await client.complete_vision(
            system="You are a precise document classifier. Return strict JSON.",
            user=CLASSIFIER_PROMPT,
            image_bytes=image_bytes,
            image_media_type=mime_type,
            model=CLASSIFIER_MODEL,
            max_tokens=300,
            temperature=0.0,
        )
    except Exception as e:
        log.error(f"Classifier Vision call failed: {e}")
        return ClassificationResult(
            category="other",
            confidence=Decimal("0.0"),
            reasoning=f"Vision error: {e}",
            method="fallback",
            cost_usd=Decimal("0"),
        )

    return _parse_classifier_response(response_text, method="vision", cost=APPROX_COST_PER_CLASSIFY_USD)


def _parse_classifier_response(
    response_text: str,
    *,
    method: str,
    cost: Decimal,
) -> ClassificationResult:
    """Парсит JSON ответ classifier'а с валидацией."""
    import json

    text = response_text.strip()
    # снять markdown fence
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # взять только {...}
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        text = text[first:last + 1]

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning(f"Classifier returned invalid JSON: {response_text[:200]}")
        return ClassificationResult(
            category="other",
            confidence=Decimal("0.0"),
            reasoning=f"JSON parse error: {e}",
            method=method,
            cost_usd=cost,
        )

    raw_category = parsed.get("category", "other")
    if raw_category not in VALID_CATEGORIES:
        log.warning(f"Classifier returned invalid category '{raw_category}', fallback to other")
        raw_category = "other"

    raw_conf = parsed.get("confidence", 0.0)
    try:
        confidence = Decimal(str(round(float(raw_conf), 3)))
        if confidence < 0:
            confidence = Decimal("0")
        if confidence > 1:
            confidence = Decimal("1")
    except (ValueError, TypeError):
        confidence = Decimal("0")

    reasoning = str(parsed.get("reasoning", ""))[:300]

    return ClassificationResult(
        category=raw_category,
        confidence=confidence,
        reasoning=reasoning,
        method=method,
        cost_usd=cost,
    )
