# -*- coding: utf-8 -*-
"""
Pack 46.0 — рендерер PDF "Диплом для хурадо".

Создаёт текстовую копию титульного листа диплома (без гербовых элементов и печатей).
Документ предназначен для передачи присяжному переводчику (хурадо) в Испании
как справочный source для перевода и заверения апостилем реального диплома клиента.

Координаты получены измерением эталона Кости (Джабраи_ллы_диплом-12.pdf).
Раскладка: 708.96 x 497.76 pt, A4 landscape-like, две колонки.

Зависимости: reportlab>=4.0.
Шрифты: Liberation Serif (TTF), путь /backend/app/fonts/ или системный fallback.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict

from reportlab.lib.colors import HexColor, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

log = logging.getLogger(__name__)


# ============================================================ FONT REGISTRATION

# Поиск шрифтов:
# 1) bundled в backend/app/fonts/
# 2) системные Liberation Serif (Linux Debian)
_FONTS_REGISTERED = False
_FONT_NORMAL = "Times-Roman"  # fallback на встроенный (нет кириллицы, но не падает)
_FONT_BOLD = "Times-Bold"
_FONT_ITALIC = "Times-Italic"


def _register_fonts() -> None:
    """Один раз регистрирует Liberation Serif в pdfmetrics."""
    global _FONTS_REGISTERED, _FONT_NORMAL, _FONT_BOLD, _FONT_ITALIC
    if _FONTS_REGISTERED:
        return

    here = Path(__file__).resolve()
    bundled = here.parent.parent / "fonts"
    system = Path("/usr/share/fonts/truetype/liberation")

    candidates = [bundled, system]
    chosen_dir = None
    for d in candidates:
        if (d / "LiberationSerif-Regular.ttf").exists():
            chosen_dir = d
            break

    if chosen_dir is None:
        log.warning(
            "Pack 46.0: Liberation Serif не найден ни в %s, ни в %s. "
            "PDF-диплом будет с дефолтным Times-Roman (без кириллицы — крякозябры).",
            bundled, system,
        )
        _FONTS_REGISTERED = True
        return

    try:
        pdfmetrics.registerFont(TTFont("LibSerif",        str(chosen_dir / "LiberationSerif-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("LibSerif-Bold",   str(chosen_dir / "LiberationSerif-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("LibSerif-Italic", str(chosen_dir / "LiberationSerif-Italic.ttf")))
        _FONT_NORMAL = "LibSerif"
        _FONT_BOLD = "LibSerif-Bold"
        _FONT_ITALIC = "LibSerif-Italic"
        log.info("Pack 46.0: Liberation Serif зарегистрирован из %s", chosen_dir)
    except Exception:
        log.exception("Pack 46.0: ошибка регистрации шрифтов")
    finally:
        _FONTS_REGISTERED = True


# ============================================================ ВСПОМОГАТЕЛЬНОЕ

_MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая",    6: "июня",    7: "июля",  8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def _format_date_ru(iso_date: str | None) -> str:
    """ISO '2015-06-28' → '28 июня 2015 года'."""
    if not iso_date:
        return ""
    try:
        y, m, d = iso_date.split("-")
        return f"{int(d)} {_MONTHS_RU[int(m)]} {y} года"
    except Exception:
        return iso_date or ""


def _format_protocol_date_parts(iso_date: str | None) -> tuple[str, str, str]:
    """ISO '2015-06-17' → ('17', 'июня', '2015')."""
    if not iso_date:
        return ("", "", "")
    try:
        y, m, d = iso_date.split("-")
        return (str(int(d)), _MONTHS_RU[int(m)], y)
    except Exception:
        return (iso_date, "", "")


def _extract_city_from_institution(institution: str) -> str:
    """Из 'НИУ ВШЭ, г. Москва' → 'г. Москва'. Если города нет в строке — пусто."""
    if not institution:
        return ""
    # Стандартные паттерны: "г. Москва", ", Москва", "(Москва)"
    import re
    m = re.search(r"г\.\s*([А-ЯЁA-Zа-яёa-z][А-ЯЁA-Zа-яёa-z\-\s]+)", institution)
    if m:
        return f"г. {m.group(1).strip()}"
    return ""


def _split_institution_lines(institution: str, max_chars: int = 50) -> list[str]:
    """Разбивает длинную строку названия ВУЗа на 4 строки заглавными буквами.
    Если institution уже содержит явные \n — используем их.
    """
    if not institution:
        return []
    # Убираем "г. Город" если есть в конце — он рендерится отдельно
    import re
    cleaned = re.sub(r",?\s*г\.\s*[А-ЯЁA-Zа-яёa-z\-\s]+$", "", institution).strip()
    cleaned = cleaned.upper()

    # Если есть \n — используем
    if "\n" in cleaned:
        return [line.strip() for line in cleaned.split("\n") if line.strip()]

    # Иначе разбиваем по словам стараясь не превысить max_chars
    words = cleaned.split()
    lines: list[str] = []
    current: list[str] = []
    for w in words:
        if current and sum(len(x) for x in current) + len(current) + len(w) > max_chars:
            lines.append(" ".join(current))
            current = [w]
        else:
            current.append(w)
    if current:
        lines.append(" ".join(current))
    # Если строк больше 4 — объединяем последние, если меньше 4 — оставляем как есть
    if len(lines) > 4:
        lines = lines[:3] + [" ".join(lines[3:])]
    return lines


# ============================================================ RENDER

# Размеры страницы из эталона
PAGE_W = 708.96
PAGE_H = 497.76

# Оси (из измерения эталона Кости)
LEFT_CX = 170      # центр левой колонки (ВУЗ, реквизиты)
RIGHT_CX = 536     # центр правой колонки (ФИО, специальность, БАКАЛАВР)
RIGHT_EDGE = 668.2 # правый край подписей


def _draw_centered(c: canvas.Canvas, text: str, cx: float, y_from_top: float,
                   font: str, size: float) -> None:
    """Центрирует text по cx, y_from_top измеряется СВЕРХУ страницы."""
    c.setFont(font, size)
    tw = c.stringWidth(text, font, size)
    y_baseline = PAGE_H - y_from_top - size
    c.drawString(cx - tw / 2, y_baseline, text)


def _draw_right(c: canvas.Canvas, text: str, x_right: float, y_from_top: float,
                font: str, size: float) -> None:
    """Выравнивает по правому краю x_right."""
    c.setFont(font, size)
    tw = c.stringWidth(text, font, size)
    y_baseline = PAGE_H - y_from_top - size
    c.drawString(x_right - tw, y_baseline, text)


def render_diploma_pdf(*, full_name_native: str, education: Dict[str, Any]) -> bytes:
    """Pack 46.0: главный entry — собирает PDF в память.

    Args:
        full_name_native: ФИО на русском, через пробелы. Будет разбито на 2 строки.
        education: dict с полями EducationRecord:
            - institution (str)
            - degree (str): "Бакалавр" / "Магистр" / "Специалист" / ...
            - graduation_year (int)
            - specialty (str): "38.03.05 Бизнес-информатика"
            - diploma_number (str): "107724 0170246"
            - registration_number (str): "2.10.3-13.1/423"
            - protocol_number (str): "1"
            - protocol_date (str ISO): "2015-06-17"
            - issue_date (str ISO): "2015-06-28"
            - signers (list[{name: str, position: str|null}])

    Returns: bytes PDF.
    """
    _register_fonts()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))

    # ====================================================== ПРАВАЯ КОЛОНКА
    # ФИО — разбиваем на 2 строки: фамилия | остальное
    fio_parts = (full_name_native or "").strip().split(None, 1)
    fio_line1 = fio_parts[0] if fio_parts else ""
    fio_line2 = fio_parts[1] if len(fio_parts) > 1 else ""

    _draw_centered(c, fio_line1, RIGHT_CX, 59, _FONT_NORMAL, 18)
    _draw_centered(c, fio_line2, RIGHT_CX, 78, _FONT_NORMAL, 18)

    # Специальность
    _draw_centered(c, education.get("specialty", "") or "",
                   RIGHT_CX, 162, _FONT_NORMAL, 11)

    # Степень — заглавными
    degree_upper = (education.get("degree", "") or "").upper()
    _draw_centered(c, degree_upper, RIGHT_CX, 275.8, _FONT_NORMAL, 12)

    # Протокол № X от « DD » MMMM YYYY г.
    pn = str(education.get("protocol_number", "") or "")
    pd, pm, py = _format_protocol_date_parts(education.get("protocol_date"))
    if pn or pd:
        # Собираем строку с теми же пробелами как в эталоне
        protocol_text = (
            f"Протокол №   {pn}    от «  {pd}  »   {pm}      {py}  г."
        )
        _draw_centered(c, protocol_text, RIGHT_CX, 311.8, _FONT_NORMAL, 11)

    # Подписи — по правому краю, до 2 имён (как в скане Джабраиллы)
    signers = education.get("signers") or []
    if signers and isinstance(signers, list):
        y_sign_positions = [402.5, 439.2]
        for i, signer in enumerate(signers[:2]):
            if isinstance(signer, dict):
                name = signer.get("name", "") or ""
            else:
                name = str(signer)
            if name:
                _draw_right(c, name, RIGHT_EDGE, y_sign_positions[i], _FONT_NORMAL, 11)

    # ====================================================== ЛЕВАЯ КОЛОНКА
    # ВУЗ — 4 строки (или сколько разобьётся)
    uni_lines = _split_institution_lines(education.get("institution", "") or "")
    y_uni = 151.2
    for line in uni_lines:
        _draw_centered(c, line, LEFT_CX, y_uni, _FONT_NORMAL, 10)
        y_uni += 13

    # Город (если выделился из institution)
    city = _extract_city_from_institution(education.get("institution", "") or "")
    if city:
        _draw_centered(c, city, LEFT_CX, max(203.8, y_uni), _FONT_NORMAL, 10)

    # Номер бланка — красным жирным
    diploma_num = education.get("diploma_number", "") or ""
    if diploma_num:
        c.setFillColor(HexColor("#B71C1C"))
        _draw_centered(c, diploma_num, LEFT_CX, 355, _FONT_BOLD, 14)
        c.setFillColor(black)

    # Регистрационный номер (значение)
    reg_num = education.get("registration_number", "") or ""
    if reg_num:
        _draw_centered(c, reg_num, LEFT_CX, 421.9, _FONT_NORMAL, 11)

    # Дата выдачи (значение)
    issue_str = _format_date_ru(education.get("issue_date"))
    if issue_str:
        _draw_centered(c, issue_str, LEFT_CX, 467.3, _FONT_NORMAL, 11)

    c.save()
    return buf.getvalue()
