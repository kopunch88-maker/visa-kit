"""
Pack 15 — DOCX translator.

Берёт готовый русский DOCX (bytes), извлекает текст из всех параграфов
(включая ячейки таблиц), переводит через LLM батчами, раскладывает обратно
с сохранением форматирования на уровне параграфа.

Стратегия сохранения формата:
- Заголовки, выравнивание, шрифты, размеры, цвета — сохраняются (это свойства параграфа)
- Таблицы, списки, отступы — сохраняются (структура XML не трогается)
- Внутри-абзацный жирный/курсив — теряется (текст всех run'ов параграфа
  объединяется и кладётся в первый run; остальные run'ы зачищаются)

Это компромисс варианта B из плана. Для legal/business документов нормально —
жирные слова посреди абзаца встречаются редко.
"""

import asyncio
import io
import json
import logging
import re
from typing import Optional

from docx import Document
from docx.text.paragraph import Paragraph

from app.services.llm import get_llm_client

log = logging.getLogger(__name__)


# Сколько параграфов отправляем за один LLM-вызов.
# Слишком мало = много вызовов и накладных расходов.
# Слишком много = риск превышения context window и ошибок ответа.
BATCH_SIZE = 30

# Маркер пропуска перевода — числа, даты, реквизиты остаются как есть
_SKIP_PATTERNS = [
    re.compile(r"^\s*$"),                           # пустые
    re.compile(r"^[\d\s.,\-/:]+$"),                 # только цифры/даты/спецсимволы
    re.compile(r"^[A-Z]{2,5}\s*\d{6,}$"),           # типа "RUS 1234567"
]


SYSTEM_PROMPT = """You are a professional legal/business translator from Russian to Spanish.

You will receive a JSON array of text fragments from a Russian business document
(employment contract, invoice, certificate, CV, employer letter, bank statement).

Your task: translate each fragment to professional Spanish, preserving the EXACT
structure and order of the array.

CRITICAL RULES:
1. Output MUST be a valid JSON array of strings, same length as input.
2. Do NOT translate, change, or reformat:
   - Numbers (1234.56, 100 000)
   - Dates (any format: 04.05.2025, «04» мая 2025 г., 2025-05-04)
   - Tax IDs (ИНН, ОГРН, КПП, БИК, account numbers)
   - Latin-script names of people and places (keep them as-is)
   - Email addresses, phone numbers, URLs
   - Document reference codes (#2026-0003, etc.)
3. DO translate:
   - Russian-language proper nouns describing roles/positions
   - Citizenship phrases: "Гражданин Российской Федерации" → "Ciudadano de la Federación de Rusia"
   - Headings, labels, free-form text
   - Russian month names in dates KEEP date structure but translate month
     («04» мая 2025 г. → «04» de mayo de 2025)
4. Use formal/legal Spanish register (Spain Spanish, not Latin American).
5. Common terms:
   - "Договор" → "Contrato"
   - "Акт об оказании услуг" → "Acta de prestación de servicios"
   - "Счёт" → "Factura"
   - "Резюме" → "Currículum vítae"
   - "Письмо" → "Carta"
   - "Выписка по счёту" → "Extracto de cuenta"
   - "ИНН" → keep "ИНН" (Russian tax ID, no Spanish equivalent)
   - "ООО" → "S.L." (Sociedad Limitada — closest equivalent)
6. If a fragment is ALREADY in Spanish or English — return it unchanged.
7. If a fragment looks like a marker/code (e.g. "__TX_DATE__", "{{var}}") — return it unchanged.

Return ONLY the JSON array. No commentary, no markdown fences, no explanation.
"""


def _should_skip(text: str) -> bool:
    """Быстрая проверка: нужно ли вообще отправлять текст в LLM."""
    if not text or not text.strip():
        return True
    for pattern in _SKIP_PATTERNS:
        if pattern.match(text):
            return True
    # Если в тексте нет ни одной кириллической буквы — не переводим
    if not re.search(r"[А-Яа-яЁё]", text):
        return True
    return False


def _extract_paragraph_text(p: Paragraph) -> str:
    """Собирает текст параграфа из всех runs (включая пустые)."""
    return "".join(run.text for run in p.runs)


def _set_paragraph_text(p: Paragraph, new_text: str) -> None:
    """
    Кладёт переведённый текст в первый run, остальные зачищает.
    Сохраняет форматирование первого run (шрифт, размер, цвет, жирность)
    и структуру параграфа (выравнивание, отступы, list-bullet).
    """
    if not p.runs:
        # У параграфа нет run'ов — добавим один (редкий случай, например пустые
        # параграфы для отступов). Просто пропускаем — нечего класть.
        return

    p.runs[0].text = new_text
    for run in p.runs[1:]:
        run.text = ""


def _collect_all_paragraphs(doc: Document) -> list[Paragraph]:
    """
    Собирает ВСЕ параграфы документа: тело + ячейки таблиц + headers/footers.

    Порядок не важен — мы переводим каждый независимо и кладём обратно в свой объект.
    """
    paragraphs: list[Paragraph] = []

    # Тело документа
    paragraphs.extend(doc.paragraphs)

    # Параграфы внутри таблиц (рекурсивно — таблицы могут быть вложенными)
    def _walk_tables(tables):
        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    paragraphs.extend(cell.paragraphs)
                    _walk_tables(cell.tables)

    _walk_tables(doc.tables)

    # Headers/footers
    for section in doc.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            paragraphs.extend(header.paragraphs)
            _walk_tables(header.tables)
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            paragraphs.extend(footer.paragraphs)
            _walk_tables(footer.tables)

    return paragraphs


async def _translate_batch(texts: list[str]) -> list[str]:
    """
    Переводит батч строк через LLM. Возвращает массив переводов той же длины.
    Если LLM вернул не то количество — fallback на по-одному (медленно, но надёжно).
    """
    if not texts:
        return []

    client = get_llm_client()
    user_payload = json.dumps(texts, ensure_ascii=False)

    try:
        response = await client.complete(
            system=SYSTEM_PROMPT,
            user=user_payload,
            max_tokens=8192,
            temperature=0.0,
        )
    except Exception as e:
        log.warning(f"[translation] LLM call failed for batch of {len(texts)}: {e}")
        # Fallback: вернём оригиналы (лучше непереведённое, чем потеря текста)
        return list(texts)

    # Иногда LLM оборачивает ответ в markdown — снимаем
    cleaned = response.strip()
    if cleaned.startswith("```"):
        # Снимаем ```json ... ``` или ``` ... ```
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        translated = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.warning(f"[translation] LLM returned non-JSON: {e}. Response head: {cleaned[:300]}")
        return await _translate_one_by_one(texts)

    if not isinstance(translated, list) or len(translated) != len(texts):
        log.warning(
            f"[translation] LLM returned wrong shape: "
            f"expected list of {len(texts)}, got {type(translated).__name__} of "
            f"len={len(translated) if hasattr(translated, '__len__') else '?'}"
        )
        return await _translate_one_by_one(texts)

    # Каждый элемент должен быть строкой
    result = []
    for i, item in enumerate(translated):
        if isinstance(item, str):
            result.append(item)
        else:
            log.warning(f"[translation] item {i} is not a string: {type(item).__name__}, falling back")
            result.append(texts[i])
    return result


async def _translate_one_by_one(texts: list[str]) -> list[str]:
    """Fallback: переводит каждую строку отдельным LLM-вызовом."""
    log.info(f"[translation] Falling back to one-by-one translation for {len(texts)} fragments")
    client = get_llm_client()
    results = []
    single_system = (
        "Translate the following Russian business/legal text to formal Spanish (Spain). "
        "Return ONLY the translation, no commentary, no quotes, no markdown."
    )
    for text in texts:
        try:
            response = await client.complete(
                system=single_system,
                user=text,
                max_tokens=1024,
                temperature=0.0,
            )
            results.append(response.strip())
        except Exception as e:
            log.warning(f"[translation] one-by-one failed for text {text[:50]!r}: {e}")
            results.append(text)
    return results


async def translate_docx(docx_bytes: bytes) -> bytes:
    """
    Главная функция: переводит DOCX с русского на испанский.

    Args:
        docx_bytes: содержимое исходного DOCX

    Returns:
        bytes переведённого DOCX

    Raises:
        Exception: если LLM упал или DOCX невалидный (вверх по стеку — orchestrator
                   ловит и помечает Translation.status = FAILED)
    """
    doc = Document(io.BytesIO(docx_bytes))
    paragraphs = _collect_all_paragraphs(doc)
    log.info(f"[translation] DOCX has {len(paragraphs)} paragraphs (incl. tables/headers)")

    # Собираем индексы параграфов которые нужно переводить
    targets: list[tuple[int, str]] = []
    for idx, p in enumerate(paragraphs):
        text = _extract_paragraph_text(p)
        if not _should_skip(text):
            targets.append((idx, text))

    if not targets:
        log.info("[translation] Nothing to translate in this DOCX")
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()

    log.info(f"[translation] {len(targets)} fragments to translate")

    # Бьём на батчи и переводим
    all_translations: list[str] = []
    for batch_start in range(0, len(targets), BATCH_SIZE):
        batch = targets[batch_start:batch_start + BATCH_SIZE]
        batch_texts = [t[1] for t in batch]
        translated = await _translate_batch(batch_texts)
        all_translations.extend(translated)
        log.info(
            f"[translation] Batch {batch_start // BATCH_SIZE + 1} "
            f"({batch_start + 1}-{batch_start + len(batch)} / {len(targets)}) done"
        )

    # Раскладываем переводы обратно в параграфы
    for (paragraph_idx, _original), translated_text in zip(targets, all_translations):
        _set_paragraph_text(paragraphs[paragraph_idx], translated_text)

    # Сохраняем результат
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
