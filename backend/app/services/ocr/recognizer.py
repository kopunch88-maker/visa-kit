"""
OCR recognizer — оркестратор для распознавания документов.

Принимает image bytes + doc_type → возвращает распознанный JSON.

Использует:
- LLM Vision client (universal: OpenRouter / Anthropic Direct)
- Промпты из prompts.py
- HEIC → JPEG конвертацию для iPhone-фото
"""

import io
import json
import logging
import re
from typing import Optional

from app.services.llm import get_llm_client

from .prompts import PROMPT_BY_DOC_TYPE

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
    - PDF → НЕ ПОДДЕРЖИВАЕТСЯ для OCR в этой версии (можем потом)
    - JPEG/PNG/WebP → как есть

    Returns:
        (нормализованные_bytes, итоговый_media_type)
    """
    ct = (content_type or "").lower()

    # PDF — пока не поддерживаем
    if ct == "application/pdf":
        raise OCRError(
            "PDF documents are not supported for OCR yet. "
            "Please upload a photo (JPG/PNG) instead."
        )

    # HEIC/HEIF — конвертим в JPEG
    if ct in ("image/heic", "image/heif"):
        try:
            from PIL import Image
            import pillow_heif
            pillow_heif.register_heif_opener()

            img = Image.open(io.BytesIO(image_bytes))
            # Сохраняем как JPEG в память
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

    # Поддерживаемые форматы LLM: jpeg, png, webp, gif
    if ct in ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"):
        # JPG → jpeg для совместимости
        if ct == "image/jpg":
            return image_bytes, "image/jpeg"
        return image_bytes, ct

    # Неизвестный тип — попробуем как jpeg
    log.warning(f"Unknown content_type {ct}, treating as image/jpeg")
    return image_bytes, "image/jpeg"


def _extract_json(text: str) -> dict:
    """
    Парсит JSON из ответа LLM.

    Иногда LLM оборачивает JSON в ```json ... ``` несмотря на инструкции —
    обрабатываем этот случай.
    """
    text = text.strip()

    # Убираем markdown fences если есть
    if text.startswith("```"):
        # Найти первую новую строку после ``` и последнее ```
        lines = text.split("\n")
        # Удалить первую строку (```json или ```) и последнюю (```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Иногда LLM добавляет что-то типа "Here is the JSON:" перед — найдём первый {
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace : last_brace + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise OCRError(f"Failed to parse LLM response as JSON: {e}\nResponse: {text[:500]}")


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
        dict с распознанными полями (например {"last_name_native": "Иванов", ...})

    Raises:
        OCRError: при невозможности распознать
    """
    # Получаем промпт
    prompt = PROMPT_BY_DOC_TYPE.get(doc_type)
    if not prompt:
        raise OCRError(
            f"OCR not supported for document type: {doc_type}. "
            f"Supported: {list(PROMPT_BY_DOC_TYPE.keys())}"
        )

    # Нормализуем изображение (HEIC → JPEG)
    try:
        normalized_bytes, normalized_media_type = _normalize_image(
            image_bytes, content_type
        )
    except OCRError:
        raise

    # Защита от слишком больших файлов после конвертации
    # LLM API имеют лимиты — обычно ~5-10MB для inline images
    MAX_LLM_IMAGE_SIZE = 8 * 1024 * 1024  # 8 MB
    if len(normalized_bytes) > MAX_LLM_IMAGE_SIZE:
        # Уменьшаем разрешение
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(normalized_bytes))
            img.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=88)
            normalized_bytes = buf.getvalue()
            normalized_media_type = "image/jpeg"
            log.info(f"Resized large image to {len(normalized_bytes)} bytes")
        except Exception as e:
            log.warning(f"Failed to resize: {e} — sending as-is")

    # Запрос в LLM
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
            temperature=0.0,  # детерминистично
        )
    except Exception as e:
        log.error(f"LLM API error during OCR: {e}", exc_info=True)
        raise OCRError(f"LLM API error: {e}")

    log.info(f"OCR raw response (first 500 chars): {response_text[:500]}")

    # Парсим JSON
    parsed = _extract_json(response_text)

    if not isinstance(parsed, dict):
        raise OCRError(f"Expected JSON object, got {type(parsed).__name__}")

    log.info(f"OCR parsed fields: {list(parsed.keys())}")

    return parsed
