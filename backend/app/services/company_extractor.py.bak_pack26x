"""
Pack 26.0 — Извлечение реквизитов компании из DOCX (или plaintext).

Используется для UI «Загрузить реквизиты компании» в админке.

Pipeline:
1. DOCX → читаем все параграфы и таблицы python-docx → собираем plaintext
2. Plaintext → отправляем LLM с COMPANY_REQUISITES_PROMPT
3. Возвращаем dict готовый к создаию/обновлению Company через CompanyCreate/CompanyPatch

Преимущества vs Vision OCR:
- Текст из DOCX чистый (без OCR-шума, ошибок типа 7707038236 vs 7707038266)
- Дешевле в 5-10× (~500 vs ~3000 токенов)
- Быстрее (~2с vs ~10с)

Только DOCX в первой итерации. PDF/JPG — в следующих пакетах через Vision-путь.
"""
import io
import json
import logging
import re
from typing import Optional

from app.services.llm import get_llm_client
from app.services.ocr.prompts import COMPANY_REQUISITES_PROMPT

log = logging.getLogger(__name__)


class CompanyExtractError(Exception):
    """Не удалось извлечь реквизиты компании."""
    pass


def _read_docx_to_text(docx_bytes: bytes) -> str:
    """
    Читает DOCX и возвращает plaintext всех параграфов и ячеек таблиц.

    Сохраняет порядок чтения (как видит пользователь): параграфы → таблицы по строкам.
    Игнорирует пустые строки.
    """
    try:
        from docx import Document
    except ImportError:
        raise CompanyExtractError(
            "python-docx not installed. Run: pip install python-docx"
        )

    try:
        doc = Document(io.BytesIO(docx_bytes))
    except Exception as e:
        raise CompanyExtractError(f"Failed to read DOCX: {e}")

    parts: list[str] = []

    # Параграфы верхнего уровня
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            parts.append(t)

    # Таблицы — каждая ячейка как отдельная "строка"
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                t = cell.text.strip()
                if t and t not in parts[-3:]:  # дедупликация ячеек, повторяющихся в merged
                    parts.append(t)

    text = "\n".join(parts).strip()

    if not text:
        raise CompanyExtractError("DOCX file appears to be empty")

    if len(text) < 30:
        raise CompanyExtractError(
            f"DOCX content too short ({len(text)} chars) — likely not a requisites document"
        )

    return text


def _strip_json_fence(s: str) -> str:
    """Убирает ```json ... ``` обёртку если LLM её добавил, и ищет {...}."""
    s = s.strip()
    if s.startswith("```"):
        # снять ```json или ``` в начале и ``` в конце
        lines = s.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()

    first_brace = s.find("{")
    last_brace = s.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        s = s[first_brace : last_brace + 1]
    return s


def _normalize_extracted_fields(data: dict) -> dict:
    """
    Минимальная нормализация полей после LLM:
    - тримминг строк
    - удаление пробелов внутри ИНН/КПП/ОГРН/счетов/БИК
    - конверсия пустых строк в null

    LLM может возвращать "  " вместо null, или ИНН с пробелом — чистим.
    """
    cleaned: dict = {}
    for key, value in data.items():
        if value is None:
            cleaned[key] = None
            continue
        if isinstance(value, str):
            v = value.strip()
            if v == "":
                cleaned[key] = None
                continue
            # Числовые поля — убрать пробелы и не-цифры
            if key in ("ogrn", "inn", "kpp", "bank_account", "bank_bic", "bank_correspondent_account"):
                v = re.sub(r"[^0-9]", "", v)
                if v == "":
                    cleaned[key] = None
                    continue
            cleaned[key] = v
        else:
            cleaned[key] = value
    return cleaned


async def extract_company_from_docx(docx_bytes: bytes) -> dict:
    """
    Главная функция Pack 26.0.

    Args:
        docx_bytes: содержимое .docx файла

    Returns:
        dict с полями совместимыми с CompanyCreate (плюс доп. charter_capital в notes)

    Raises:
        CompanyExtractError при любой проблеме (плохой файл, плохой ответ LLM, и т.д.)
    """
    text = _read_docx_to_text(docx_bytes)

    log.info(f"Pack 26.0: extracted {len(text)} chars from DOCX, calling LLM...")

    client = get_llm_client()

    try:
        response_text = await client.complete(
            system="You are a precise data extraction assistant. Always return strict JSON.",
            user=f"{COMPANY_REQUISITES_PROMPT}\n\n--- DOCUMENT TEXT ---\n{text}\n--- END ---",
            max_tokens=2048,
            temperature=0.0,
        )
    except Exception as e:
        log.error(f"LLM error in company extraction: {e}", exc_info=True)
        raise CompanyExtractError(f"LLM error: {e}")

    cleaned_response = _strip_json_fence(response_text)

    try:
        parsed = json.loads(cleaned_response)
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse LLM JSON: {e}\nResponse head: {response_text[:500]}")
        raise CompanyExtractError(
            f"LLM returned invalid JSON. Head: {response_text[:200]}"
        )

    if not isinstance(parsed, dict):
        raise CompanyExtractError(f"LLM returned non-dict: {type(parsed).__name__}")

    normalized = _normalize_extracted_fields(parsed)

    log.info(
        f"Pack 26.0: extracted {sum(1 for v in normalized.values() if v is not None)}"
        f"/{len(normalized)} fields"
    )

    return normalized
