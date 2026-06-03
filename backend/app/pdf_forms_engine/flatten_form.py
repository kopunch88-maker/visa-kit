"""
PDF AcroForm post-processing: text appearance + flatten для всех viewer'ов.

ПРОБЛЕМА:
    Шаблоны Минюста Испании (MI_T.pdf, DESIGNACION...) — AcroForm-формы.
    После заполнения через pypdf:
      - pypdf использует /Helv с auto-size (≈10.5pt вместо положенных 9pt),
        baseline на 1pt от низа поля вместо 3.117pt — текст крупный и низкий
      - pypdf ставит /AcroForm/NeedAppearances = True
      - mobile viewer'ы (Telegram preview, iOS Files, Android system viewer)
        игнорируют этот флаг и НЕ рисуют /AP /N appearances → чекбоксы
        и текст не видны

РЕШЕНИЕ:
    1. Для каждого Tx-виджета построить свой /AP /N content stream:
       9pt Helvetica, baseline 3.117pt над низом, x_offset 2.0pt,
       центрирование/право для полей с /Q. Реальная ширина символов
       Helvetica из AFM-таблицы для аккуратного центрирования.
    2. Для всех Btn-виджетов вызвать pikepdf.generate_appearance_streams()
       (он умеет radio/checkbox).
    3. flatten_annotations() — впечатывает appearances в content stream
       страницы и удаляет AcroForm. Результат — статичный PDF, идентично
       рендерится в Adobe, Chrome, iOS preview, Telegram, Android.

ИСПОЛЬЗОВАНИЕ:
    from pdf_forms_engine.flatten_form import flatten_pdf_form
    bytes_out = flatten_pdf_form(bytes_in)

Идемпотентно: повторный вызов на flattened PDF (без AcroForm) — no-op.
"""

from __future__ import annotations

import io
import logging

import pikepdf
from pikepdf import Name

log = logging.getLogger(__name__)


# AFM Helvetica widths (units per 1000-em). Для центрирования текста
# в полях с /Q = 1 (например FIR_PROV в MI-T).
_HELV_WIDTHS = {
    'A': 667, 'B': 667, 'C': 722, 'D': 722, 'E': 667, 'F': 611, 'G': 778,
    'H': 722, 'I': 278, 'J': 500, 'K': 667, 'L': 556, 'M': 833, 'N': 722,
    'O': 778, 'P': 667, 'Q': 778, 'R': 722, 'S': 667, 'T': 611, 'U': 722,
    'V': 667, 'W': 944, 'X': 667, 'Y': 667, 'Z': 611,
    'a': 556, 'b': 556, 'c': 500, 'd': 556, 'e': 556, 'f': 278, 'g': 556,
    'h': 556, 'i': 222, 'j': 222, 'k': 500, 'l': 222, 'm': 833, 'n': 556,
    'o': 556, 'p': 556, 'q': 556, 'r': 333, 's': 500, 't': 278, 'u': 556,
    'v': 500, 'w': 722, 'x': 500, 'y': 500, 'z': 500,
    '0': 556, '1': 556, '2': 556, '3': 556, '4': 556, '5': 556, '6': 556,
    '7': 556, '8': 556, '9': 556,
    ' ': 278, '.': 278, ',': 278, '-': 333, '_': 556, '+': 584,
    '/': 278, '\\': 278, '@': 1015, '(': 333, ')': 333,
    ':': 278, ';': 278, '?': 556, '!': 278, '*': 389, '#': 556, '&': 667,
    '=': 584, "'": 191, '"': 355,
}

# Параметры рендера — подобраны эмпирически по эталону Adobe Reader на
# официальном шаблоне Минюста (см. инцидент 35 в PROJECT_STATE).
_FONT_SIZE = 9.0
_Y_BASELINE = 3.117  # pt над низом поля
_X_MARGIN = 2.0      # pt от левого/правого края поля
_MIN_FONT_SIZE = 5.0  # Pack 51.0: минимальный кегль при auto-shrink длинных значений


def _text_width(text: str, font_size: float = _FONT_SIZE) -> float:
    """Ширина строки в Helvetica указанного размера (pt)."""
    return sum(_HELV_WIDTHS.get(ch, 556) for ch in text) * font_size / 1000.0


def _fit_font_size(
    text: str,
    field_width: float,
    max_size: float = _FONT_SIZE,
    min_size: float = _MIN_FONT_SIZE,
    step: float = 0.25,
) -> float:
    """
    Pack 51.0: подбирает кегль Helvetica так, чтобы строка влезла в
    field_width (минус _X_MARGIN с обеих сторон). Стартует с max_size (9pt)
    и ужимает шагами step до min_size. Если строка влезает на max_size —
    возвращает max_size без изменений (no-op для коротких значений, рендер
    байт-в-байт как раньше). Нужно, чтобы длинные значения (NRC в MI-T,
    ~127pt на 9pt) не обрезались BBox'ом Form XObject.
    """
    avail = field_width - 2 * _X_MARGIN
    if avail <= 0:
        return max_size
    size = max_size
    while size > min_size and _text_width(text, size) > avail:
        size -= step
    return round(size, 2)


def _pdf_string_escape(s: str) -> str:
    """Экранирует строку для PDF literal: \\, (, )."""
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _build_text_appearance_content(
    value: str, field_width: float, alignment: int
) -> bytes:
    """
    Content stream для /AP /N текстового виджета.
    alignment: 0=left, 1=center, 2=right (значение /Q из PDF поля).
    """
    font_size = _fit_font_size(value, field_width)  # Pack 51.0: auto-shrink длинных значений
    tw = _text_width(value, font_size)
    if alignment == 1:
        x = max(_X_MARGIN, (field_width - tw) / 2)
    elif alignment == 2:
        x = max(_X_MARGIN, field_width - tw - _X_MARGIN)
    else:
        x = _X_MARGIN

    safe = _pdf_string_escape(value)
    return (
        f"q\n"
        f"/Tx BMC\n"
        f"q\n"
        f"BT\n"
        f"0 g\n"
        f"{x:.4f} {_Y_BASELINE:.4f} Td\n"
        f"/Helv {font_size} Tf\n"
        f"({safe}) Tj\n"
        f"ET\n"
        f"Q\n"
        f"EMC\n"
        f"Q\n"
    ).encode("latin1")


def _rewrite_text_appearances(pdf: "pikepdf.Pdf") -> int:
    """
    Для каждого Tx-виджета на каждой странице переписывает /AP /N своим
    content stream с правильным шрифтом и offset'ом.
    Возвращает кол-во обработанных виджетов.
    """
    if Name.AcroForm not in pdf.Root:
        return 0

    dr = pdf.Root.AcroForm.get(Name.DR)
    if dr is None:
        log.warning("flatten_pdf_form: no /DR in AcroForm, skipping text rewrites")
        return 0
    dr_font = dr.get(Name.Font)
    if dr_font is None:
        log.warning("flatten_pdf_form: no /DR/Font in AcroForm, skipping text rewrites")
        return 0

    fixed = 0
    for page in pdf.pages:
        annots = page.get(Name.Annots)
        if not annots:
            continue
        for annot in annots:
            if annot.get(Name.Subtype) != Name.Widget:
                continue
            if annot.get(Name.FT) != Name.Tx:
                continue
            v = annot.get(Name.V)
            if v is None:
                continue
            val_str = str(v)
            if not val_str:
                continue

            rect = annot.get(Name.Rect)
            if rect is None or len(rect) != 4:
                continue
            x0, y0, x1, y1 = (float(rect[i]) for i in range(4))
            w_pt = x1 - x0
            h_pt = y1 - y0

            q = annot.get(Name.Q)
            alignment = int(q) if q is not None else 0

            content = _build_text_appearance_content(val_str, w_pt, alignment)

            new_n = pdf.make_stream(content)
            new_n[Name.Type] = Name.XObject
            new_n[Name.Subtype] = Name.Form
            new_n[Name.BBox] = pikepdf.Array([0, 0, w_pt, h_pt])
            new_n[Name.Resources] = pikepdf.Dictionary(Font=dr_font)
            annot[Name.AP] = pikepdf.Dictionary(N=new_n)
            fixed += 1
    return fixed


def flatten_pdf_form(pdf_bytes: bytes) -> bytes:
    """
    Заполненный AcroForm PDF → статичный PDF, рендерящийся одинаково
    во всех viewer'ах, включая iOS preview и Telegram.

    Args:
        pdf_bytes: PDF-контент в bytes (output после pypdf fill).

    Returns:
        Flattened PDF as bytes. Если на входе PDF без AcroForm —
        возвращает исходные bytes без изменений (no-op).

    Никогда не бросает исключения: при ошибках логирует warning и возвращает
    best-effort output.
    """
    try:
        pdf = pikepdf.Pdf.open(io.BytesIO(pdf_bytes))
    except Exception as e:
        log.warning(f"flatten_pdf_form: cannot open PDF, returning as-is: {e}")
        return pdf_bytes

    if Name.AcroForm not in pdf.Root:
        return pdf_bytes

    try:
        if Name.NeedAppearances in pdf.Root.AcroForm:
            del pdf.Root.AcroForm[Name.NeedAppearances]
    except Exception:
        pass

    try:
        n = _rewrite_text_appearances(pdf)
        log.debug(f"flatten_pdf_form: rewrote {n} text widget appearances")
    except Exception as e:
        log.warning(f"flatten_pdf_form: text rewrite failed: {e}")

    try:
        pdf.generate_appearance_streams()
    except Exception as e:
        log.warning(f"flatten_pdf_form: generate_appearance_streams failed: {e}")

    try:
        pdf.flatten_annotations()
    except Exception as e:
        log.warning(f"flatten_pdf_form: flatten_annotations failed: {e}")
        return pdf_bytes

    # 5) Удалить оставшиеся пустые Widget-аннотации (поля без /V — pikepdf
    # их не флэтит, оставляет как placeholder'ы; они визуально невидимы,
    # но мы убираем для чистоты)
    try:
        for page in pdf.pages:
            annots = page.get(Name.Annots)
            if not annots:
                continue
            keep = [
                a for a in annots
                if a.get(Name.Subtype) != Name.Widget
            ]
            if len(keep) != len(annots):
                page[Name.Annots] = pikepdf.Array(keep)
    except Exception as e:
        log.debug(f"flatten_pdf_form: cleanup of empty widgets skipped: {e}")

    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()
