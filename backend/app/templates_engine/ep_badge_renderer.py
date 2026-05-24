# -*- coding: utf-8 -*-
"""
Pack 47.16 — генератор PNG плашки ЭП Сбербанка на основе static asset.

Архитектура (изменилась относительно Pack 47.15):
  - Pack 47.15 рендерил плашку С НУЛЯ через PIL — пытался воспроизвести
    дизайн Сбера (лого, синюю шапку, рамку). Получалось неидеально:
    шрифты на Linux Railway отличались от брендового Сбера, лого по-разному
    рендерилось, скруглённые углы вообще не получались.
  - Pack 47.16 использует ГОТОВУЮ PNG плашки (templates/docx/sber_ep_card.png),
    вырезанную пользователем из реальной выписки Сбера. Эта PNG содержит
    рамку с закруглёнными углами, лого, верхнюю синюю полосу — 1-в-1.
    Pack 47.16 только ДОРИСОВЫВАЕТ 4 строки реквизитов (Сертификат / Владелец /
    Действителен / Дата подписи) поверх в нижней пустой зоне PNG.

Зачем PIL поверх готовой PNG, а не overlay в DOCX:
  Overlay в DOCX (text frame, anchored picture с behindDoc) — ненадёжен:
  позиция текста зависит от шрифтовых метрик клиента (Word/LibreOffice),
  плавает между версиями. Через PIL мы получаем растровый PNG с фиксированным
  расположением — 100% воспроизводимо.

Шрифты:
  Используем DejaVu Sans (есть в Linux). На локальной разработке (Windows)
  PIL найдёт Arial. Для брендового вида можно положить ttf-файл в репо и
  использовать его — но даже Arial / DejaVu выглядит приемлемо.

Pillow уже на проде как транзитивная зависимость python-docx.
"""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Цвета — точно из эталонной PNG Сбера (тёмно-синий бренда)
_SBER_BLUE = (0, 0, 130)
_DARK = (26, 26, 26)

# Путь к фоновой PNG плашки (вырезана из эталонной выписки Сбера)
_SBER_EP_CARD_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "templates" / "docx" / "sber_ep_card.png"
)

# Координаты текстовых полей в PNG (привязаны к 1046x453 — размеру эталонной PNG).
# Если когда-то PNG заменим на другую — эти координаты нужно будет пересчитать.
_LABEL_X = 70
_VALUE_X = 320
_START_Y = 270
_ROW_GAP = 38


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Загружает шрифт с fallback'ом."""
    paths_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    paths_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    paths = paths_bold if bold else paths_regular
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
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

    Использует static PNG (templates/docx/sber_ep_card.png) как фон, поверх
    дорисовывает 4 строки реквизитов через PIL.

    Args:
        statement_date_str: дата подписи в формате "DD.MM.YYYY"
        cert_no: номер сертификата (HEX 32 символа, hardcoded — обновляется
            при смене сертификата Сбера, ориентировочно раз в 2 года)
        owner, valid_from, valid_to: реквизиты сертификата

    Returns:
        bytes — содержимое PNG-файла для вставки через doc.add_picture
    """
    if not _SBER_EP_CARD_PATH.exists():
        raise FileNotFoundError(
            f"Не найден static asset плашки ЭП: {_SBER_EP_CARD_PATH}\n"
            "Положи sber_ep_card.png в templates/docx/."
        )

    img = Image.open(_SBER_EP_CARD_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_regular = _load_font(22, bold=False)
    font_bold = _load_font(22, bold=True)

    rows = [
        ("Сертификат:",   cert_no,                              False),
        ("Владелец:",     owner,                                 True),
        ("Действителен:", f"с {valid_from} по {valid_to}",       False),
        ("Дата подписи:", statement_date_str or "—",             False),
    ]
    for i, (label, value, is_bold) in enumerate(rows):
        y = _START_Y + i * _ROW_GAP
        draw.text((_LABEL_X, y), label, fill=_SBER_BLUE, font=font_regular)
        f = font_bold if is_bold else font_regular
        draw.text((_VALUE_X, y), value, fill=_DARK, font=f)

    # Сохраняем PNG. Конвертируем RGBA -> RGB с белым фоном чтобы прозрачные
    # области (закругления углов) не оставались чёрными в Word/Mac превью.
    # Word корректно отображает прозрачные PNG, но Mac Preview / некоторые
    # email-клиенты могут показать чёрный фон. Безопаснее flatten.
    if img.mode == "RGBA":
        white_bg = Image.new("RGB", img.size, (255, 255, 255))
        white_bg.paste(img, mask=img.split()[3])
        img = white_bg

    buf = BytesIO()
    img.save(buf, format="PNG", dpi=(200, 200))
    return buf.getvalue()
