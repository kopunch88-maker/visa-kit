"""
OCR recognizer — оркестратор для распознавания документов.

Принимает image bytes + doc_type → возвращает распознанный JSON.

Использует:
- LLM Vision client (universal: OpenRouter / Anthropic Direct)
- Промпты из prompts.py
- HEIC → JPEG конвертацию для iPhone-фото

Pack 14b/c additions:
- classify_document() — определение типа документа по первой странице
- generate_declensions() — генерация русских склонений ФИО директора (text-only)
"""

import io
import json
import logging
import re
from typing import Optional

from app.services.llm import get_llm_client

from .prompts import (
    PROMPT_BY_DOC_TYPE,
    DOCUMENT_CLASSIFIER_PROMPT,
    DECLENSIONS_PROMPT,
)

log = logging.getLogger(__name__)


class OCRError(Exception):
    """OCR не смог распознать документ."""
    pass


def _normalize_image(
    image_bytes: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    """
    Нормализует изображение перед отправкой в LLM.

    - HEIC/HEIF → JPEG (LLM не принимает HEIC)
    - PDF → НЕ ПОДДЕРЖИВАЕТСЯ для OCR в этой версии
    - JPEG/PNG/WebP → как есть

    Returns:
        (нормализованные_bytes, итоговый_media_type)
    """
    ct = (content_type or "").lower()

    if ct == "application/pdf":
        raise OCRError(
            "PDF documents are not supported for OCR yet. "
            "Please upload a photo (JPG/PNG) instead."
        )

    if ct in ("image/heic", "image/heif"):
        try:
            from PIL import Image
            import pillow_heif
            pillow_heif.register_heif_opener()

            img = Image.open(io.BytesIO(image_bytes))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=92)
            return buf.getvalue(), "image/jpeg"
        except ImportError:
            raise OCRError(
                "HEIC support not installed on server. "
                "Please convert to JPG/PNG and re-upload."
            )
        except Exception as e:
            raise OCRError(f"Failed to convert HEIC image: {e}")

    if ct in ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"):
        if ct == "image/jpg":
            return image_bytes, "image/jpeg"
        return image_bytes, ct

    log.warning(f"Unknown content_type {ct}, treating as image/jpeg")
    return image_bytes, "image/jpeg"


def _extract_json(text: str) -> dict:
    """
    Парсит JSON из ответа LLM.

    Иногда LLM оборачивает JSON в ```json ... ``` несмотря на инструкции —
    обрабатываем этот случай.
    """
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace : last_brace + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise OCRError(f"Failed to parse LLM response as JSON: {e}\nResponse: {text[:500]}")


def _resize_if_needed(image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
    """Уменьшает изображение если оно слишком большое для LLM API."""
    MAX_LLM_IMAGE_SIZE = 8 * 1024 * 1024  # 8 MB
    if len(image_bytes) <= MAX_LLM_IMAGE_SIZE:
        return image_bytes, media_type

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=88)
        new_bytes = buf.getvalue()
        log.info(f"Resized large image to {len(new_bytes)} bytes")
        return new_bytes, "image/jpeg"
    except Exception as e:
        log.warning(f"Failed to resize: {e} — sending as-is")
        return image_bytes, media_type


async def recognize_document(
    doc_type: str,
    image_bytes: bytes,
    content_type: str,
) -> dict:
    """
    Распознаёт документ через LLM Vision.

    Args:
        doc_type: тип документа (например "passport_internal_main")
        image_bytes: байты изображения
        content_type: MIME type (image/jpeg, image/heic, и т.д.)

    Returns:
        dict с распознанными полями

    Raises:
        OCRError: при невозможности распознать
    """
    prompt = PROMPT_BY_DOC_TYPE.get(doc_type)
    if not prompt:
        raise OCRError(
            f"OCR not supported for document type: {doc_type}. "
            f"Supported: {list(PROMPT_BY_DOC_TYPE.keys())}"
        )

    try:
        normalized_bytes, normalized_media_type = _normalize_image(image_bytes, content_type)
    except OCRError:
        raise

    normalized_bytes, normalized_media_type = _resize_if_needed(normalized_bytes, normalized_media_type)

    client = get_llm_client()

    log.info(
        f"OCR request: doc_type={doc_type} "
        f"size={len(normalized_bytes)} type={normalized_media_type}"
    )

    try:
        response_text = await client.complete_vision(
            system="You are a precise OCR assistant. Always return strict JSON.",
            user=prompt,
            image_bytes=normalized_bytes,
            image_media_type=normalized_media_type,
            max_tokens=2048,
            temperature=0.0,
        )
    except Exception as e:
        log.error(f"LLM API error during OCR: {e}", exc_info=True)
        raise OCRError(f"LLM API error: {e}")

    log.info(f"OCR raw response (first 500 chars): {response_text[:500]}")

    parsed = _extract_json(response_text)

    if not isinstance(parsed, dict):
        raise OCRError(f"Expected JSON object, got {type(parsed).__name__}")

    log.info(f"OCR parsed fields: {list(parsed.keys())}")

    return parsed


# ============================================================================
# Pack 14c — ИИ-классификатор: определяет тип документа по первой странице
# ============================================================================

VALID_CLASSIFIER_TYPES = {
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
}

VALID_CONFIDENCE = {"high", "medium", "low"}


async def classify_document(
    image_bytes: bytes,
    content_type: str,
) -> dict:
    """
    Классифицирует документ — определяет его тип по первой странице.

    Args:
        image_bytes: байты первой страницы документа (JPEG/PNG)
        content_type: MIME type

    Returns:
        dict с полями:
        - type: один из VALID_CLASSIFIER_TYPES (default: "other")
        - confidence: "high" | "medium" | "low" (default: "low")
        - country_hint: ISO 3-letter code или None
        - reasoning: короткое объяснение

    Raises:
        OCRError: если не удалось вызвать LLM или распарсить ответ.
        Валидация типа НЕ кидает ошибку — fallback на "other"/"low".
    """
    try:
        normalized_bytes, normalized_media_type = _normalize_image(image_bytes, content_type)
    except OCRError:
        raise

    normalized_bytes, normalized_media_type = _resize_if_needed(normalized_bytes, normalized_media_type)

    client = get_llm_client()

    log.info(
        f"Classify request: size={len(normalized_bytes)} type={normalized_media_type}"
    )

    try:
        response_text = await client.complete_vision(
            system="You are a precise document classifier. Always return strict JSON.",
            user=DOCUMENT_CLASSIFIER_PROMPT,
            image_bytes=normalized_bytes,
            image_media_type=normalized_media_type,
            max_tokens=512,
            temperature=0.0,
        )
    except Exception as e:
        log.error(f"LLM API error during classification: {e}", exc_info=True)
        raise OCRError(f"Classifier LLM error: {e}")

    log.info(f"Classifier raw response: {response_text[:300]}")

    try:
        parsed = _extract_json(response_text)
    except OCRError:
        # Fallback: не смогли распарсить JSON
        log.warning("Classifier returned unparseable response — fallback to other/low")
        return {
            "type": "other",
            "confidence": "low",
            "country_hint": None,
            "reasoning": "Could not parse classifier response",
        }

    # Валидация и normalization
    doc_type = parsed.get("type")
    if doc_type not in VALID_CLASSIFIER_TYPES:
        log.warning(f"Classifier returned invalid type '{doc_type}' — fallback to other")
        doc_type = "other"

    confidence = parsed.get("confidence")
    if confidence not in VALID_CONFIDENCE:
        confidence = "low"

    country_hint = parsed.get("country_hint")
    if country_hint and (not isinstance(country_hint, str) or len(country_hint) != 3):
        country_hint = None

    return {
        "type": doc_type,
        "confidence": confidence,
        "country_hint": country_hint,
        "reasoning": parsed.get("reasoning", "")[:300],
    }


# ============================================================================
# Pack 14b — генерация склонений ФИО (text-only LLM запрос)
# ============================================================================

async def generate_declensions(full_name_ru: str) -> dict:
    """
    Генерирует русские склонения ФИО (Им., Род., Дат., Вин., Тв., Пред. + short_form).

    Используется при добавлении новой компании из ЕГРЮЛ — для склонений директора.

    Args:
        full_name_ru: ФИО в именительном падеже (например "Иванов Сергей Петрович")

    Returns:
        dict со всеми падежами + short_form. Если не удалось — возвращает все
        поля заполненные nominative (т.е. как fallback менеджер видит исходное имя
        во всех ячейках и сам поправит).
    """
    if not full_name_ru or not full_name_ru.strip():
        return {
            "nominative": "",
            "genitive": "",
            "dative": "",
            "accusative": "",
            "instrumental": "",
            "prepositional": "",
            "short_form": "",
        }

    full_name_ru = full_name_ru.strip()
    fallback = {
        "nominative": full_name_ru,
        "genitive": full_name_ru,
        "dative": full_name_ru,
        "accusative": full_name_ru,
        "instrumental": full_name_ru,
        "prepositional": full_name_ru,
        "short_form": full_name_ru,
    }

    client = get_llm_client()
    user_message = f"{DECLENSIONS_PROMPT}\n\nInput: \"{full_name_ru}\"\n\nGenerate the declensions JSON for this input."

    try:
        # Используем complete_vision БЕЗ image — это text-only запрос.
        # Если в LLM client нет text-only метода, используем vision с заглушкой.
        # Но проще: попробуем complete_text если такой метод есть, иначе сделаем text-only через complete_vision.
        if hasattr(client, "complete_text"):
            response_text = await client.complete_text(
                system="You are a Russian language expert. Always return strict JSON.",
                user=user_message,
                max_tokens=512,
                temperature=0.0,
            )
        else:
            # Fallback: LLM client не имеет complete_text — используем vision с пустым изображением.
            # Создаём 1×1 белый JPEG (минимальный валидный) — LLM просто проигнорирует его и ответит по тексту.
            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (1, 1), color="white").save(buf, format="JPEG")
            response_text = await client.complete_vision(
                system="You are a Russian language expert. Always return strict JSON.",
                user=user_message,
                image_bytes=buf.getvalue(),
                image_media_type="image/jpeg",
                max_tokens=512,
                temperature=0.0,
            )
    except Exception as e:
        log.warning(f"Declensions LLM call failed: {e} — using fallback (nominative for all)")
        return fallback

    try:
        parsed = _extract_json(response_text)
    except OCRError:
        log.warning(f"Failed to parse declensions response: {response_text[:300]}")
        return fallback

    # Validation: ensure all keys present
    required_keys = ["nominative", "genitive", "dative", "accusative", "instrumental", "prepositional", "short_form"]
    result = dict(fallback)  # start with fallback
    for key in required_keys:
        value = parsed.get(key)
        if value and isinstance(value, str) and value.strip():
            result[key] = value.strip()

    log.info(f"Declensions generated: {result.get('genitive')[:50]}...")

    return result
