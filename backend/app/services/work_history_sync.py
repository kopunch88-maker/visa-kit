# -*- coding: utf-8 -*-
"""
Pack 37.2 — Sync applicant.work_history with DN employer.

Single source of truth для последней записи в work_history: когда заявке
назначена компания + позиция + дата подписания контракта, первая запись
work_history должна быть = DN-работодатель.

Эта логика дублирует _build_cv_work_history в templates_engine/context.py
(Pack 25.7), но НЕ как замену, а как upstream sync в БД. После вызова
этой функции _build_cv_work_history делает no-op (всё уже правильно).

Использование:
    from app.services.work_history_sync import sync_dn_work_record
    sync_dn_work_record(applicant, application, session, company=..., position=...)
    # БД обновлена. CV-генератор увидит уже синхронизированный work_history.

Зачем нужно (Pack 37.0 AI Audit):
    Аудитор сравнивает поля applicant с финальным CV. До Pack 37.2 в БД
    было одно, в CV — другое (рендерер подменял на лету). Аудит ругался
    на каждый кейс с DN-employer-ом. После Pack 37.2 БД = CV = админка.
"""
import logging
from typing import Optional

from sqlmodel import Session

log = logging.getLogger(__name__)

# Те же месяцы что и в templates_engine/context.py — для совместимости форматов.
_RU_MONTHS_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

_PRESENT_LABELS = {"по настоящее время", "настоящее время", "н.в.", "по н.в."}


def _previous_month_label(reference_date) -> str:
    """'Сентябрь 2025' если reference_date = 14.10.2025."""
    if not reference_date:
        return ""
    year = reference_date.year
    month = reference_date.month - 1
    if month == 0:
        month = 12
        year -= 1
    return f"{_RU_MONTHS_NAMES[month - 1]} {year}"


def _format_month_label(d) -> str:
    if not d:
        return ""
    return f"{_RU_MONTHS_NAMES[d.month - 1]} {d.year}"


def _is_already_dn_record(record: dict, company_name: str) -> bool:
    """
    Проверяет, является ли запись уже DN-employer-ом.
    Используется для идемпотентности sync.
    """
    if not isinstance(record, dict):
        return False
    rec_company = (record.get("company") or "").strip().lower()
    target = (company_name or "").strip().lower()
    rec_end = (record.get("period_end") or "").strip().lower()
    return rec_company == target and rec_end in _PRESENT_LABELS


def sync_dn_work_record(
    applicant,
    application,
    session: Session,
    *,
    company=None,
    position=None,
) -> bool:
    """
    Синхронизирует applicant.work_history с текущим DN-работодателем.

    Логика:
    1. Если нет всех данных (applicant/application/company/position/contract_sign_date) —
       возвращает False (no-op, не падает).
    2. Если первая запись уже = DN-employer + period_end='по настоящее время' —
       возвращает False (уже синхронизировано).
    3. Иначе:
       a. Если первая запись имеет period_end='по настоящее время' и компания
          ДРУГАЯ — меняет period_end на месяц перед contract_sign_date.
       b. Вставляет новую запись в начало с DN-работодателем.
       c. Сохраняет в БД.

    Args:
        applicant: Applicant ORM объект
        application: Application ORM объект
        session: активная сессия (commit делается этой функцией)
        company: опционально, иначе подтянется из application.company_id
        position: опционально, иначе подтянется из application.position_id

    Returns:
        True если БД обновлена, False если no-op.
    """
    if not applicant or not application:
        return False

    if company is None:
        if not application.company_id:
            return False
        from app.models import Company
        company = session.get(Company, application.company_id)
        if not company:
            return False

    if position is None:
        if not application.position_id:
            return False
        from app.models import Position
        position = session.get(Position, application.position_id)
        if not position:
            return False

    if not application.contract_sign_date:
        log.info(
            "[wh_sync] applicant=%s no contract_sign_date — skip",
            applicant.id,
        )
        return False

    company_name = (company.full_name_ru or "").strip()
    if not company_name:
        log.info(
            "[wh_sync] applicant=%s company.full_name_ru is empty — skip",
            applicant.id,
        )
        return False

    base = list(applicant.work_history or [])

    # Проверка идемпотентности: первая запись уже = DN-employer
    if base and _is_already_dn_record(base[0], company_name):
        log.info(
            "[wh_sync] applicant=%s already synced with %s — no-op",
            applicant.id, company_name,
        )
        return False

    # Фиксим предыдущую первую запись если у неё period_end='по настоящее время'
    # и компания НЕ совпадает с DN-employer-ом (то есть это реальная прошлая работа).
    fixed_base = []
    for i, item in enumerate(base):
        if not isinstance(item, dict):
            fixed_base.append(item)
            continue
        new_item = dict(item)
        if i == 0:
            pe = (new_item.get("period_end") or "").strip().lower()
            if pe in _PRESENT_LABELS:
                # Это была "текущая работа" — закрываем её предыдущим месяцем
                new_item["period_end"] = _previous_month_label(
                    application.contract_sign_date
                )
        fixed_base.append(new_item)

    # Создаём DN-запись
    dn_record = {
        "period_start": _format_month_label(application.contract_sign_date),
        "period_end": "по настоящее время",
        "company": company_name,
        "position": position.title_ru or "",
        "duties": list(position.duties or []),
    }

    # Новый список: DN первой + остальные
    new_history = [dn_record] + fixed_base

    # Сохраняем. work_history — JSON-поле, нужен явный flag_modified
    # на случай SQLAlchemy кэширования.
    applicant.work_history = new_history
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(applicant, "work_history")
    except Exception:
        pass

    session.add(applicant)
    session.commit()

    log.info(
        "[wh_sync] applicant=%s synced: DN-employer=%s, position=%s, "
        "period_start=%s, records=%d",
        applicant.id, company_name, position.title_ru,
        dn_record["period_start"], len(new_history),
    )
    return True


def sync_dn_work_record_safe(application, session: Session) -> bool:
    """
    Безопасная обёртка для вызова из endpoint hooks. Подтягивает applicant
    сама, логирует ошибки, никогда не падает (только возвращает False).

    Используется в PATCH/assign endpoints где мы не хотим что бы ошибка
    sync уронила весь запрос менеджера.
    """
    if not application or not application.applicant_id:
        return False

    try:
        from app.models import Applicant
        applicant = session.get(Applicant, application.applicant_id)
        if not applicant:
            return False
        return sync_dn_work_record(applicant, application, session)
    except Exception as e:
        log.exception("[wh_sync] sync failed for application=%s: %s", application.id, e)
        return False
