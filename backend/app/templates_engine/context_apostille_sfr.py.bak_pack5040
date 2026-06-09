"""
Pack 50.20 — Контекст для DOCX-шаблона `apostille_sfr_template.docx`
(апостиль Минфина/СФР, формат для НАЙМА).

По аналогии с context_apostille.py (апостиль самозанятого к справке НПД), но:
  - опорная дата = дата СОО (soo_date) или приказ Т-9, а НЕ справка НПД
    (у найма справки НПД нет).
  - подписант СФР (signer_sfr_short) — фикс по эталону «Высоцкая Ю.В.»
  - подписант апостиля (Байрамов) — тот же дефолт Минюста, что и у самозанятого
    (берётся из applicant.apostille_signer_* если задан).
  - дата = опорная + 5-7 рабочих дней (seed=applicant.id, стабильна).
  - номер = "77-NNNNN/26", aposId QR — те же генераторы (seed=applicant.id).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from random import Random
from typing import Optional

from sqlmodel import Session

from app.models import Application, Applicant

log = logging.getLogger(__name__)


# ============================================================
# Дефолты (по эталону Минфина/СФР)
# ============================================================
DEFAULT_SFR_SIGNER_SHORT = "Высоцкая Ю.В."

DEFAULT_APOSTILLE_SIGNER_SHORT = "Байрамов Н.А."
DEFAULT_APOSTILLE_SIGNER_SIGNATURE = "Н.А. Байрамов"
DEFAULT_APOSTILLE_SIGNER_POSITION = (
    "Заместитель начальника отдела международной правовой помощи "
    "и предоставления апостиля Главного управления Министерства "
    "юстиции Российской Федерации по Москве  "
)


# ============================================================
# Helpers (повтор логики context_apostille.py)
# ============================================================

def _format_date_short(d) -> str:
    if not d:
        return ""
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _add_business_days(start: date, days: int) -> date:
    current = start
    added = 0
    while added < days:
        current = current + timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def _generate_apostille_number(applicant_id: int) -> str:
    rng = Random(applicant_id or 0)
    n = rng.randint(3000, 4500)
    return f"77-{n:05d}/26"


def _generate_qr_apos_id(applicant_id: int) -> str:
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
    short = (getattr(applicant, 'apostille_signer_short', None) or '').strip()
    signature = (getattr(applicant, 'apostille_signer_signature', None) or '').strip()
    position = (getattr(applicant, 'apostille_signer_position', None) or '').strip()
    return {
        "short": short or DEFAULT_APOSTILLE_SIGNER_SHORT,
        "signature": signature or DEFAULT_APOSTILLE_SIGNER_SIGNATURE,
        "position": position or DEFAULT_APOSTILLE_SIGNER_POSITION,
    }


def _resolve_anchor_date(application, today: date) -> date:
    """Опорная дата для расчёта даты апостиля (вместо даты справки НПД).

    Приоритет: soo_date (свидетельство об отъезде) -> business_trip_order_date
    (приказ Т-9) -> today. СОО — профильный документ СФР, логично привязать к нему.
    """
    for attr in ("soo_date", "business_trip_order_date"):
        v = getattr(application, attr, None)
        if v:
            return v
    return today


# ============================================================
# Главный entry point
# ============================================================

def build_apostille_sfr_context(
    application: Application,
    session: Session,
    *,
    today: Optional[date] = None,
) -> dict:
    """Собирает context для DOCX-шаблона `apostille_sfr_template.docx`."""
    if today is None:
        today = date.today()

    applicant_id = application.applicant_id or 0
    applicant = session.get(Applicant, applicant_id) if applicant_id else None

    # 1. Опорная дата (СОО / приказ / сегодня)
    anchor = _resolve_anchor_date(application, today)

    # 2. Дата апостиля = опорная + рандом(5-7 рабочих дней), seed=applicant_id
    rng = Random(applicant_id)
    business_days = rng.randint(5, 7)
    apostille_date = _add_business_days(anchor, business_days)

    # 3. Номер + aposId (те же генераторы)
    apostille_number = _generate_apostille_number(applicant_id)
    qr_apos_id = _generate_qr_apos_id(applicant_id)

    # 4. Подписант апостиля (Байрамов / из applicant)
    signer_apostille = _resolve_apostille_signer(applicant)

    # 5. Многострочный блок подписанта апостиля (как в эталоне: ФИО + должность)
    signer_apostille_block = f"{signer_apostille['short']}\n{signer_apostille['position']}"

    log.info(
        "build_apostille_sfr_context: applicant_id=%s anchor=%s date=%s number=%s",
        applicant_id, anchor, apostille_date, apostille_number,
    )

    return {
        "apostille": {
            "signer_sfr_short": DEFAULT_SFR_SIGNER_SHORT,
            "signer_apostille_short": signer_apostille["short"],
            "signer_apostille_signature": signer_apostille["signature"],
            "signer_apostille_position": signer_apostille["position"],
            "signer_apostille_block": signer_apostille_block,
            "date_short": _format_date_short(apostille_date),
            "number": apostille_number,
            "qr_apos_id": qr_apos_id,
        },
    }
