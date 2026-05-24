# -*- coding: utf-8 -*-
"""
Pack 47.15 — генератор PNG плашки электронной подписи (ЭП) Сбербанка.

Используется в render_bank_statement для замены маркера __EP_BADGE__ на
inline-картинку с актуальной датой подписи и реквизитами сертификата.

Зачем PNG, а не таблица DOCX:
  В Pack 47.0–47.14 плашка ЭП собиралась как 4 вложенные таблицы (top-band,
  blue-header, cert-table, outer-frame). python-docx + LibreOffice / Word
  систематически вставляли пустые <w:p/> между таблицами, давая видимые
  ~12pt пустоты. Никакие "_strip_empty_paragraphs_*" комбинации не убирали
  все промежутки без побочных эффектов (см. Pack 47.9, 47.10). Также шапка
  "Документ подписан / электронной подписью*" с лого СБЕР занимала ширину
  больше нужного, и не поджималась к синей полосе "СВЕДЕНИЯ О СЕРТИФИКАТЕ ЭП".

Runtime-PNG решает проблему НАВСЕГДА: визуал 1-в-1, отступы под полным
контролем PIL, фон, шрифты, рамка — всё точно как в эталоне Сбера.

Технически — Pillow уже установлен как транзитивная зависимость python-docx
(тот использует Pillow для add_picture). Дополнительных зависимостей нет.

Шрифты: используем системный DejaVu Sans (есть в любом Linux-окружении
включая Railway). На локальной Windows-разработке (Костя) — PIL найдёт
Arial автоматически (PIL делает fallback на arial.ttf при ImportError).
"""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Цвета по эталону Сбера
_SBER_BLUE = (0x29, 0x6F, 0xCE)
_SBER_LIGHT_BLUE = (0xEA, 0xF3, 0xFA)
_DARK = (0x1A, 0x1A, 0x1A)
_WHITE = (0xFF, 0xFF, 0xFF)

# Размеры PNG (200 DPI чтобы при печати на A4 не пикселило)
# 80mm × 60mm = 630 × 472px при 200 DPI
_PNG_WIDTH = 630
_PNG_HEIGHT = 300  # Pack 47.15: compact — без пустоты внизу

# Высоты секций
_TOP_BAND_H = 70       # голубая шапка с лого + "Документ подписан..."
_BLUE_HEAD_H = 38      # синяя полоса "СВЕДЕНИЯ О СЕРТИФИКАТЕ ЭП"
_BORDER_W = 2          # ширина внешней рамки

# Путь к логотипу Сбера (PNG прозрачный)
_SBER_LOGO_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "templates" / "docx" / "sber_logo.png"
)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Загружает шрифт с fallback'ом на разные ОС."""
    paths_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    paths_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    paths = paths_bold if bold else paths_regular
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    # Последний fallback — встроенный шрифт PIL (некрасивый, но не упадёт)
    return ImageFont.load_default()


def render_ep_badge_png(
    statement_date_str: str,
    cert_no: str = "40601D00C08FCE2CD999F93A68651986",
    owner: str = "ПАО Сбербанк России",
    valid_from: str = "02.07.2025",
    valid_to: str = "02.10.2026",
) -> bytes:
    """
    Рендерит PNG плашки ЭП Сбера с динамической датой подписи.

    Args:
        statement_date_str: дата формирования документа = дата подписи
            (формат "DD.MM.YYYY").
        cert_no: номер сертификата ЭП (HEX 32 символа, hardcoded по
            эталону Сбера).
        owner: владелец сертификата (по умолчанию "ПАО Сбербанк России").
        valid_from, valid_to: период валидности сертификата
            (даты в формате "DD.MM.YYYY").

    Returns:
        bytes — содержимое PNG-файла (для вставки через doc.add_picture).
    """
    img = Image.new("RGB", (_PNG_WIDTH, _PNG_HEIGHT), _WHITE)
    draw = ImageDraw.Draw(img)

    # === Внешняя рамка ===
    draw.rectangle(
        [0, 0, _PNG_WIDTH - 1, _PNG_HEIGHT - 1],
        outline=_SBER_BLUE,
        width=_BORDER_W,
    )

    # === Шапка: голубой фон + лого СБЕР + "Документ подписан / электронной подписью*" ===
    draw.rectangle(
        [_BORDER_W, _BORDER_W, _PNG_WIDTH - _BORDER_W - 1, _TOP_BAND_H],
        fill=_SBER_LIGHT_BLUE,
    )

    # Лого
    logo_h = 40
    logo_x = 25
    if _SBER_LOGO_PATH.exists():
        try:
            logo = Image.open(_SBER_LOGO_PATH).convert("RGBA")
            ratio = logo_h / logo.height
            logo_w = int(logo.width * ratio)
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
            img.paste(logo, (logo_x, (_TOP_BAND_H - logo_h) // 2 + 5), logo)
            text_x = logo_x + logo_w + 15
        except Exception:
            text_x = logo_x  # без лого
    else:
        text_x = logo_x

    # Текст "Документ подписан / электронной подписью*"
    font_bold_18 = _load_font(18, bold=True)
    font_reg_14 = _load_font(14, bold=False)
    font_bold_14 = _load_font(14, bold=True)

    draw.text((text_x, 12), "Документ подписан", fill=_SBER_BLUE, font=font_bold_18)
    draw.text((text_x, 35), "электронной подписью*", fill=_SBER_BLUE, font=font_bold_18)

    # === Синяя полоса заголовка ===
    head_top = _TOP_BAND_H
    draw.rectangle(
        [_BORDER_W, head_top, _PNG_WIDTH - _BORDER_W - 1, head_top + _BLUE_HEAD_H],
        fill=_SBER_BLUE,
    )
    title = "СВЕДЕНИЯ О СЕРТИФИКАТЕ ЭП"
    bbox = draw.textbbox((0, 0), title, font=font_bold_18)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((_PNG_WIDTH - tw) / 2, head_top + (_BLUE_HEAD_H - th) / 2 - 2),
        title,
        fill=_WHITE,
        font=font_bold_18,
    )

    # === Таблица сертификата (фон голубой) ===
    cert_top = head_top + _BLUE_HEAD_H
    draw.rectangle(
        [_BORDER_W, cert_top, _PNG_WIDTH - _BORDER_W - 1, _PNG_HEIGHT - _BORDER_W - 1],
        fill=_SBER_LIGHT_BLUE,
    )

    rows = [
        ("Сертификат:", cert_no, False),
        ("Владелец:", owner, True),  # bold
        ("Действителен:", f"с {valid_from} по {valid_to}", False),
        ("Дата подписи:", statement_date_str or "—", False),
    ]
    row_h = 36
    label_x = 25
    value_x = 175
    for i, (label, value, value_bold) in enumerate(rows):
        y = cert_top + 20 + i * row_h
        draw.text((label_x, y), label, fill=_SBER_BLUE, font=font_reg_14)
        f = font_bold_14 if value_bold else font_reg_14
        draw.text((value_x, y), value, fill=_DARK, font=f)

    buf = BytesIO()
    img.save(buf, format="PNG", dpi=(200, 200))
    return buf.getvalue()
