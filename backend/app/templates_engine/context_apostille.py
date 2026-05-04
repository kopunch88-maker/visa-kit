"""
Pack 18.9 — Контекст для DOCX-шаблона `apostille_template.docx`
(апостиль к справке НПД, формат МФЦ).

Логика:
1. Подписант справки НПД (signer_npd_short) — берётся из того же МФЦ что в
   справке (Pack 18.9.0 универсальный МФЦ Новоясеневский). Детерминистично
   по applicant.id % len(staff_names). Формат "Фамилия И.О."
2. Подписант апостиля (signer_apostille_*) — берётся из applicant'а если
   менеджер задал, иначе хардкод-дефолт «Байрамов Н.А.».
3. Дата апостиля = date выдачи справки + рандом(5-7 рабочих дней).
   Стабильна при перегенерации (seed=applicant.id).
4. Номер апостиля = "77-{NNNNN}/26", рандомный N (seed=applicant.id).
5. aposId для QR-URL = UUID4-подобная строка (seed=applicant.id).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from random import Random
from typing import Optional

from sqlmodel import Session

from app.models import Application

from .context_npd_certificate import (
    build_npd_certificate_context,
)

log = logging.getLogger(__name__)


# ============================================================
# Дефолты подписанта апостиля (используются если applicant не задал)
# ============================================================
DEFAULT_APOSTILLE_SIGNER_SHORT = "Байрамов Н.А."
DEFAULT_APOSTILLE_SIGNER_SIGNATURE = "Н.А. Байрамов"
DEFAULT_APOSTILLE_SIGNER_POSITION = (
    "Заместитель начальника отдела международной правовой помощи "
    "и предоставления апостиля Главного управления Министерства "
    "юстиции Российской Федерации по Москве  "
)


# ============================================================
# Helpers
# ============================================================

def _format_date_short(d) -> str:
    """date(2026, 4, 21) → '21.04.2026'."""
    if not d:
        return ""
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _add_business_days(start: date, days: int) -> date:
    """Прибавляет N рабочих дней к дате (пропускает субботы и воскресенья)."""
    current = start
    added = 0
    while added < days:
        current = current + timedelta(days=1)
        # weekday(): 0=пн, 6=вс. Sat=5, Sun=6.
        if current.weekday() < 5:
            added += 1
    return current


def _full_to_short(full_name: str) -> str:
    """
    Pack 18.9: 'Иваничкина Ольга Николаевна' → 'Иваничкина О.Н.'.
    Если parsing не удался — возвращаем как есть.
    """
    if not full_name:
        return ""
    parts = full_name.strip().split()
    if len(parts) < 2:
        return full_name.strip()
    last = parts[0]
    first_initial = parts[1][0] if parts[1] else ""
    middle_initial = parts[2][0] if len(parts) >= 3 and parts[2] else ""
    if middle_initial:
        return f"{last} {first_initial}.{middle_initial}."
    return f"{last} {first_initial}."


def _generate_apostille_number(applicant_id: int) -> str:
    """
    Pack 18.9: '77-{NNNNN}/26' где NNNNN — стабильное число от applicant_id.
    Диапазон NNNNN: 03000-04500 (приближен к примеру 77-03404/26).
    """
    rng = Random(applicant_id or 0)
    n = rng.randint(3000, 4500)
    return f"77-{n:05d}/26"


def _generate_qr_apos_id(applicant_id: int) -> str:
    """
    Pack 18.9: стабильный UUID-подобный aposId на applicant_id.
    Формат как в шаблоне: 'c0d5bf90-4c73-4e20-b5df7b54dhh5' — на самом деле
    это не валидный UUID4 (есть буквы 'h'), но мы повторим тот же
    8-4-4-4-12 формат через random hex.
    """
    rng = Random(applicant_id or 0)
    hex_chars = "0123456789abcdef"
    parts = [
        ''.join(rng.choices(hex_chars, k=8)),
        ''.join(rng.choices(hex_chars, k=4)),
        ''.join(rng.choices(hex_chars, k=4)),
        ''.join(rng.choices(hex_chars, k=4)),
        ''.join(rng.choices(hex_chars, k=12)),
    ]
    return '-'.join(parts)


def _resolve_apostille_signer(applicant) -> dict:
    """
    Pack 18.9: возвращает dict с тремя полями подписанта апостиля.
    Если applicant.apostille_signer_* заданы — берёт их.
    Иначе — дефолты Байрамова.
    """
    short = (getattr(applicant, 'apostille_signer_short', None) or '').strip()
    signature = (getattr(applicant, 'apostille_signer_signature', None) or '').strip()
    position = (getattr(applicant, 'apostille_signer_position', None) or '').strip()

    return {
        "short": short or DEFAULT_APOSTILLE_SIGNER_SHORT,
        "signature": signature or DEFAULT_APOSTILLE_SIGNER_SIGNATURE,
        "position": position or DEFAULT_APOSTILLE_SIGNER_POSITION,
    }


# ============================================================
# Главный entry point
# ============================================================

def build_apostille_context(
    application: Application,
    session: Session,
    *,
    today: Optional[date] = None,
) -> dict:
    """
    Собирает context для DOCX-шаблона `apostille_template.docx`.

    Зависит от Pack 18.3 контекста справки НПД — берёт оттуда подписанта МФЦ
    (signer_npd_short) и дату выдачи справки (от которой считаем +5-7 рабочих).
    """
    if today is None:
        today = date.today()

    # 1. Получаем контекст справки НПД (там уже подписант МФЦ + дата выдачи)
    npd_ctx = build_npd_certificate_context(application, session, today=today)

    applicant_id = application.applicant_id or 0
    applicant = npd_ctx['applicant'].get('_obj') if isinstance(
        npd_ctx['applicant'], dict
    ) and '_obj' in npd_ctx['applicant'] else None
    # Если в context нет ссылки на объект — достаём из БД
    if applicant is None:
        from app.models import Applicant
        applicant = session.get(Applicant, applicant_id)

    # 2. Подписант справки (signer_npd_short)
    mfc_full_name = npd_ctx['mfc'].get('employee_name', '')
    signer_npd_short = _full_to_short(mfc_full_name)

    # 3. Дата апостиля = дата справки + рандом(5-7 рабочих дней)
    issued_short = npd_ctx['certificate'].get('issued_date_short', '')
    # парсим обратно в date
    m = re.match(r'^(\d{2})\.(\d{2})\.(\d{4})$', issued_short)
    if m:
        issued_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    else:
        log.warning(
            "build_apostille_context: cannot parse issued_date_short=%r, "
            "fallback to today",
            issued_short,
        )
        issued_date = today

    rng = Random(applicant_id)
    business_days = rng.randint(5, 7)
    apostille_date = _add_business_days(issued_date, business_days)

    # 4. Номер
    apostille_number = _generate_apostille_number(applicant_id)

    # 5. aposId
    qr_apos_id = _generate_qr_apos_id(applicant_id)

    # 6. Подписант апостиля
    signer_apostille = _resolve_apostille_signer(applicant)

    log.info(
        "build_apostille_context: applicant_id=%s "
        "date=%s number=%s aposId=%s signer_npd=%r signer_apostille=%r",
        applicant_id,
        apostille_date,
        apostille_number,
        qr_apos_id,
        signer_npd_short,
        signer_apostille["short"],
    )

    return {
        "apostille": {
            "signer_npd_short": signer_npd_short,
            "signer_apostille_short": signer_apostille["short"],
            "signer_apostille_signature": signer_apostille["signature"],
            "signer_apostille_position": signer_apostille["position"],
            "date_short": _format_date_short(apostille_date),
            "number": apostille_number,
            "qr_apos_id": qr_apos_id,
        },
    }
