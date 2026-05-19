# -*- coding: utf-8 -*-
"""
Pack 39.0-C — Document text extractor для финальной проверки.

Гибридная стратегия:
- PDF с extractable text (>= MIN_TEXT_PER_PAGE_HEURISTIC символов на стр.)
  → pypdf, метод='pypdf', cost=0
- PDF-скан (text слабый) → pypdfium2 рендер каждой страницы в JPEG
  → Vision (claude-sonnet-4-5), метод='vision', cost учитывается
- DOCX → docx2txt, метод='docx2txt', cost=0
- JPG/PNG/HEIC/WEBP → Vision напрямую, метод='vision'

Лимит: MAX_PAGES_PER_DOC страниц. Если документ больше — берём первые N
и логируем warning.

Возвращает ExtractionResult:
  text: str                    — итоговый извлечённый текст
  method: str                  — 'pypdf' | 'vision' | 'docx2txt' | 'mixed'
  cost_usd: Decimal            — стоимость Vision вызовов
  page_count: int              — количество страниц обработано
  pages_skipped: int           — сколько страниц обрезано из-за лимита
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


# ====================================================================
# Конфиг
# ====================================================================

# Максимум страниц на один документ. Большая банковская выписка влезает,
# документы > 30 страниц обрезаются (берём первые 30).
MAX_PAGES_PER_DOC = 30

# Минимум символов на страницу при pypdf, чтобы считать PDF "текстовым".
# Если меньше — это скан и надо гонять Vision.
MIN_TEXT_PER_PAGE_HEURISTIC = 80

# Максимум символов на итоговый extracted_text (защита от взрывов).
MAX_CHARS_PER_DOCUMENT = 100_000

# DPI для PDF → JPEG конверсии (для Vision).
PDF_RENDER_DPI = 150

# Модель для extraction (нужно точное чтение текста, особенно русский).
VISION_EXTRACTION_MODEL = "anthropic/claude-sonnet-4-5"

# Приближённая стоимость Vision-вызова на одну страницу.
# claude-sonnet-4-5: ~$3/MTok input, средняя страница JPEG ~1500 input tokens
# + промпт ~500 input + ответ ~800 output × $15/MTok = ~$0.018/страницу.
# Округляем в большую сторону для консервативной оценки.
APPROX_COST_PER_VISION_PAGE_USD = Decimal("0.020")


VISION_EXTRACTION_PROMPT = """\
Extract ALL text content from this document image.

Rules:
- Return PLAIN TEXT only, no markdown, no commentary.
- Preserve original language(s) - do NOT translate.
- Preserve structure: paragraphs separated by blank lines.
- For tables, use simple "Column: Value" lines or pipe-separated rows.
- Include stamps, signatures, headers, footers, page numbers if visible.
- For unreadable parts, write [unreadable].
- Skip decorative elements (logos, borders).

Return ONLY the extracted text, nothing else.
"""


@dataclass
class ExtractionResult:
    text: str
    method: str  # 'pypdf' | 'vision' | 'docx2txt' | 'mixed' | 'failed'
    cost_usd: Decimal
    page_count: int
    pages_skipped: int = 0
    error: Optional[str] = None


# ====================================================================
# DOCX → text
# ====================================================================

def _extract_docx(content: bytes) -> ExtractionResult:
    try:
        import docx2txt
    except ImportError:
        return ExtractionResult(
            text="", method="failed", cost_usd=Decimal("0"), page_count=0,
            error="docx2txt not installed",
        )

    try:
        # docx2txt принимает либо путь, либо file-like
        text = docx2txt.process(io.BytesIO(content))
        text = _normalize_text(text)
        return ExtractionResult(
            text=text[:MAX_CHARS_PER_DOCUMENT],
            method="docx2txt",
            cost_usd=Decimal("0"),
            page_count=1,
        )
    except Exception as e:
        log.error(f"docx2txt failed: {e}")
        return ExtractionResult(
            text="", method="failed", cost_usd=Decimal("0"), page_count=0,
            error=f"docx2txt error: {e}",
        )


# ====================================================================
# PDF → text (try pypdf first, fallback Vision)
# ====================================================================

def _try_pypdf(content: bytes) -> tuple[str, int]:
    """
    Извлекает текст из PDF через pypdf. Возвращает (text, page_count).
    Если PDF — скан, текст будет очень короткий или пустой.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf not installed")
        return "", 0

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = reader.pages
        total = len(pages)
        if total == 0:
            return "", 0

        pages_to_read = min(total, MAX_PAGES_PER_DOC)
        chunks = []
        for i in range(pages_to_read):
            try:
                t = pages[i].extract_text() or ""
                chunks.append(t)
            except Exception as e:
                log.warning(f"pypdf page {i+1} extract failed: {e}")

        text = "\n\n".join(chunks)
        return _normalize_text(text), total
    except Exception as e:
        log.error(f"pypdf failed: {e}")
        return "", 0


def _pdf_page_to_jpeg(pdf_bytes: bytes, page_num: int, dpi: int = PDF_RENDER_DPI) -> bytes:
    """
    Конвертирует страницу PDF в JPEG bytes. page_num: 1-based.
    Скопировано из import_package.py для консистентности.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    total = len(pdf)
    if page_num < 1 or page_num > total:
        raise ValueError(f"page_num {page_num} out of range (1..{total})")

    page = pdf[page_num - 1]
    scale = dpi / 72.0
    pil_image = page.render(scale=scale).to_pil()
    buf = io.BytesIO()
    pil_image.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue()


async def _extract_pdf_via_vision(content: bytes) -> ExtractionResult:
    """
    Рендерит каждую страницу PDF в JPEG и шлёт в Vision.
    Объединяет тексты страниц.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return ExtractionResult(
            text="", method="failed", cost_usd=Decimal("0"), page_count=0,
            error="pypdfium2 not installed",
        )

    try:
        pdf = pdfium.PdfDocument(content)
        total = len(pdf)
    except Exception as e:
        return ExtractionResult(
            text="", method="failed", cost_usd=Decimal("0"), page_count=0,
            error=f"Cannot open PDF: {e}",
        )

    if total == 0:
        return ExtractionResult(
            text="", method="failed", cost_usd=Decimal("0"), page_count=0,
            error="PDF has 0 pages",
        )

    pages_to_process = min(total, MAX_PAGES_PER_DOC)
    pages_skipped = total - pages_to_process
    if pages_skipped > 0:
        log.warning(
            f"PDF has {total} pages, processing first {pages_to_process} "
            f"(skipping {pages_skipped})"
        )

    client = get_llm_client()
    page_texts = []
    cost_total = Decimal("0")

    for page_num in range(1, pages_to_process + 1):
        try:
            jpeg = _pdf_page_to_jpeg(content, page_num=page_num)
        except Exception as e:
            log.warning(f"Failed to render page {page_num}: {e}")
            page_texts.append(f"[page {page_num}: render failed]")
            continue

        try:
            response_text = await client.complete_vision(
                system="You are a precise OCR assistant. Extract all visible text.",
                user=VISION_EXTRACTION_PROMPT,
                image_bytes=jpeg,
                image_media_type="image/jpeg",
                model=VISION_EXTRACTION_MODEL,
                max_tokens=4096,
                temperature=0.0,
            )
            page_texts.append(f"=== Page {page_num} ===\n{response_text.strip()}")
            cost_total += APPROX_COST_PER_VISION_PAGE_USD
        except Exception as e:
            log.error(f"Vision extraction failed for page {page_num}: {e}")
            page_texts.append(f"[page {page_num}: vision failed: {e}]")

    text = "\n\n".join(page_texts)
    text = _normalize_text(text)[:MAX_CHARS_PER_DOCUMENT]

    return ExtractionResult(
        text=text,
        method="vision",
        cost_usd=cost_total,
        page_count=pages_to_process,
        pages_skipped=pages_skipped,
    )


async def _extract_pdf(content: bytes) -> ExtractionResult:
    """
    PDF-стратегия:
    1. pypdf → если текст приличный (среднее >= MIN_TEXT_PER_PAGE_HEURISTIC) → выход
    2. Иначе → Vision по страницам
    """
    pypdf_text, total_pages = _try_pypdf(content)

    if total_pages == 0:
        return ExtractionResult(
            text="", method="failed", cost_usd=Decimal("0"), page_count=0,
            error="Cannot read PDF",
        )

    avg_chars_per_page = len(pypdf_text) / max(1, min(total_pages, MAX_PAGES_PER_DOC))
    log.info(
        f"PDF analysis: total_pages={total_pages}, "
        f"pypdf_chars={len(pypdf_text)}, avg_per_page={avg_chars_per_page:.0f}"
    )

    if avg_chars_per_page >= MIN_TEXT_PER_PAGE_HEURISTIC:
        # Текстовый PDF
        pages_skipped = max(0, total_pages - MAX_PAGES_PER_DOC)
        return ExtractionResult(
            text=pypdf_text[:MAX_CHARS_PER_DOCUMENT],
            method="pypdf",
            cost_usd=Decimal("0"),
            page_count=min(total_pages, MAX_PAGES_PER_DOC),
            pages_skipped=pages_skipped,
        )

    # Скан-PDF → Vision
    log.info(f"PDF looks like scan (avg {avg_chars_per_page:.0f} chars/page), using Vision")
    return await _extract_pdf_via_vision(content)


# ====================================================================
# Image → text (Vision напрямую)
# ====================================================================

async def _extract_image(content: bytes, mime_type: str) -> ExtractionResult:
    """Прямой Vision на одной картинке."""
    # Нормализация HEIC → JPEG (Vision не принимает HEIC)
    normalized_bytes, normalized_mime = _normalize_image_for_vision(content, mime_type)

    client = get_llm_client()
    try:
        response_text = await client.complete_vision(
            system="You are a precise OCR assistant. Extract all visible text.",
            user=VISION_EXTRACTION_PROMPT,
            image_bytes=normalized_bytes,
            image_media_type=normalized_mime,
            model=VISION_EXTRACTION_MODEL,
            max_tokens=4096,
            temperature=0.0,
        )
        text = _normalize_text(response_text)[:MAX_CHARS_PER_DOCUMENT]
        return ExtractionResult(
            text=text,
            method="vision",
            cost_usd=APPROX_COST_PER_VISION_PAGE_USD,
            page_count=1,
        )
    except Exception as e:
        log.error(f"Vision extraction failed for image: {e}")
        return ExtractionResult(
            text="", method="failed", cost_usd=Decimal("0"), page_count=0,
            error=f"Vision error: {e}",
        )


def _normalize_image_for_vision(content: bytes, mime: str) -> tuple[bytes, str]:
    """HEIC/HEIF → JPEG; крупные изображения уменьшаем до 8 МБ."""
    ct = (mime or "").lower()
    if ct in ("image/heic", "image/heif"):
        try:
            from PIL import Image
            import pillow_heif
            pillow_heif.register_heif_opener()
            img = Image.open(io.BytesIO(content))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=92)
            content = buf.getvalue()
            ct = "image/jpeg"
        except Exception as e:
            log.warning(f"HEIC conversion failed: {e} — sending as-is")

    MAX_LLM_IMAGE_SIZE = 8 * 1024 * 1024
    if len(content) > MAX_LLM_IMAGE_SIZE:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(content))
            img.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=88)
            content = buf.getvalue()
            ct = "image/jpeg"
        except Exception as e:
            log.warning(f"Image resize failed: {e}")

    return content, ct


# ====================================================================
# Главная функция
# ====================================================================

async def extract_document_text(
    content: bytes,
    filename: str,
    mime_type: str,
) -> ExtractionResult:
    """
    Главный entry point: определяет тип файла и выбирает стратегию.
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf" or mime_type == "application/pdf":
        return await _extract_pdf(content)
    elif ext == ".docx" or "wordprocessingml" in (mime_type or ""):
        return _extract_docx(content)
    elif ext in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"):
        return await _extract_image(content, mime_type)
    else:
        return ExtractionResult(
            text="", method="failed", cost_usd=Decimal("0"), page_count=0,
            error=f"Unsupported extension for extraction: {ext}",
        )


# ====================================================================
# Утилиты
# ====================================================================

def _normalize_text(text: str) -> str:
    """Нормализация пробелов и переводов строк."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # схлопываем 3+ переноса в 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # схлопываем горизонтальные пробелы (но не \n)
    text = re.sub(r"[ \t]+", " ", text)
    # trim каждой строки
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()
