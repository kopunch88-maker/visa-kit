"""
Регистрация шрифтов для ReportLab.

По умолчанию ReportLab использует Helvetica — она НЕ поддерживает кириллицу.
В наших PDF (Compromiso, Declaración) ФИО клиента всегда на латинице (так
требует UGE), поэтому Helvetica справляется в 99% случаев.

Однако для устойчивости регистрируем DejaVu Sans (поддерживает кириллицу) как
fallback. Если шрифт DejaVu не найден в системе — продолжаем работать с
Helvetica (с риском квадратиков для кириллицы, но обычно это не нужно).

Использование в стилях:
    from .fonts import BODY_FONT, BODY_FONT_BOLD
    style = ParagraphStyle(..., fontName=BODY_FONT)
"""

import logging
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

log = logging.getLogger(__name__)


# По умолчанию используем Helvetica
BODY_FONT = "Helvetica"
BODY_FONT_BOLD = "Helvetica-Bold"

# Пытаемся найти и зарегистрировать DejaVu Sans
_DEJAVU_PATHS_REGULAR = [
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS (если установлен)
    "/Library/Fonts/DejaVuSans.ttf",
    # Windows: обычно нет, но проверим
    "C:/Windows/Fonts/DejaVuSans.ttf",
]
_DEJAVU_PATHS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
]


def _try_register_dejavu() -> bool:
    """Пытается зарегистрировать DejaVu. Возвращает True если успешно."""
    regular_path = next((p for p in _DEJAVU_PATHS_REGULAR if Path(p).exists()), None)
    bold_path = next((p for p in _DEJAVU_PATHS_BOLD if Path(p).exists()), None)

    if not regular_path or not bold_path:
        return False

    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", regular_path))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
        return True
    except Exception as e:
        log.warning(f"Failed to register DejaVu: {e}")
        return False


# Пытаемся переключиться на DejaVu при старте модуля
if _try_register_dejavu():
    BODY_FONT = "DejaVuSans"
    BODY_FONT_BOLD = "DejaVuSans-Bold"
    log.info("PDF forms: using DejaVu Sans (Cyrillic-compatible)")
else:
    log.info("PDF forms: DejaVu not found, using Helvetica (Latin only)")
