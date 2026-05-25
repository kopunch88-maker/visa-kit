# -*- coding: utf-8 -*-
"""
Pack 47.21 — финальная подгонка overlay реквизитов под эталон Сбера.

Контекст: после Pack 47.20 текст реквизитов в плашке ЭП визуально не совпадал
с эталоном (вырезка из реальной выписки Сбера):
  - текст начинался слишком левее (под лого СБЕР), а не под левым краем
    синей полосы "СВЕДЕНИЯ О СЕРТИФИКАТЕ ЭП";
  - межстрочный интервал был слишком большой (плашка казалась "разреженной");
  - значения справа были чёрные (_DARK), а в эталоне — тёмно-синие как
    у лейблов слева и как сам бренд Сбера;
  - bold был только у строки "Владелец", а в эталоне жирные все значения.

Pack 47.21 — это **только overlay-правка**, фоновая PNG `sber_ep_card.png`
(1134×537, белый фон) от Pack 47.20 НЕ меняется.

Измерения по эталону (см. сессию 25.05.2026 в чате):
  - Левый край синей полосы в фоновой PNG: X=99 (исключая рамку карточки X=42)
  - Эталонные X строк текста: 99..101 (лейбл), 367..368 (значение)
  - Эталонные Y строк: 306, 343, 381, 418 → шаг 37-38px
  - Цвет всех символов в эталоне ≈ (0,0,130) (_SBER_BLUE), тот же оттенок
    что у самой синей полосы

Изменения в этом файле относительно Pack 47.20:
  _LABEL_X: 76  -> 99   (под левый край синей полосы)
  _VALUE_X: 347 -> 368  (точное X из эталона)
  _START_Y: 310 -> 306  (точное Y из эталона; разница 4px незаметна)
  _ROW_GAP: 45  -> 37   (плотный межстрочный интервал)
  Удалена константа _DARK (значения теперь _SBER_BLUE)
  В rows[] для всех 4 строк is_bold=True (было только Владелец)

Архитектура (без изменений, как в Pack 47.16):
  Static PNG `templates/docx/sber_ep_card.png` (вырезана из эталона Сбера) +
  PIL рисует 4 строки реквизитов поверх в нижней пустой зоне. Это надёжнее
  чем overlay в DOCX (где позиции плавают между Word/LibreOffice/версиями).
"""
from __future__ import annotations
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Тёмно-синий цвет бренда Сбера — используется И для лейблов, И для значений.
_SBER_BLUE = (0, 0, 130)

# Путь к фоновой PNG плашки (вырезана из эталонной выписки Сбера).
# Размер 1134×537, белый фон, не менялась с Pack 47.20.
_SBER_EP_CARD_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "templates" / "docx" / "sber_ep_card.png"
)

# Координаты overlay-текста (привязаны к 1134×537 — размеру эталонной PNG).
# Pack 47.21 — координаты подогнаны под эталон по измерениям из реального скрина.
_LABEL_X = 99   # ↔ левый край синей полосы "СВЕДЕНИЯ О СЕРТИФИКАТЕ ЭП"
_VALUE_X = 368  # ↔ начало значений в эталоне
_START_Y = 306  # ↔ верх первой строки в эталоне
_ROW_GAP = 37   # ↔ шаг между строками в эталоне (был 45 — слишком разрежено)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Загружает шрифт с fallback'ом (Linux Railway → Windows local → default)."""
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

    В Pack 47.21:
      - все 4 значения отрисовываются BOLD (как в эталоне Сбера);
      - все лейблы и значения — цветом _SBER_BLUE (раньше значения были
        чёрные _DARK, что не совпадало с брендом).

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

    font_regular = _load_font(24, bold=False)
    font_bold = _load_font(24, bold=True)

    # Pack 47.21: все значения bold (раньше только Владелец).
    rows = [
        ("Сертификат:",   cert_no),
        ("Владелец:",     owner),
        ("Действителен:", f"с {valid_from} по {valid_to}"),
        ("Дата подписи:", statement_date_str or "—"),
    ]
    for i, (label, value) in enumerate(rows):
        y = _START_Y + i * _ROW_GAP
        # Лейблы — regular, _SBER_BLUE
        draw.text((_LABEL_X, y), label, fill=_SBER_BLUE, font=font_regular)
        # Значения — bold, _SBER_BLUE (Pack 47.21: было _DARK + bold только у owner)
        draw.text((_VALUE_X, y), value, fill=_SBER_BLUE, font=font_bold)

    # Flatten RGBA → RGB на белом фоне. Word отрисует прозрачные PNG корректно,
    # но Mac Preview / некоторые email-клиенты могут показать чёрный фон
    # в зонах прозрачности (закруглённые углы). Безопаснее flatten.
    if img.mode == "RGBA":
        white_bg = Image.new("RGB", img.size, (255, 255, 255))
        white_bg.paste(img, mask=img.split()[3])
        img = white_bg

    buf = BytesIO()
    img.save(buf, format="PNG", dpi=(200, 200))
    return buf.getvalue()
