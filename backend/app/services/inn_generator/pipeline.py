
"""
Pack 17.2.4 — pipeline автогенерации ИНН на основе ЛОКАЛЬНОЙ БД самозанятых.

ИЗМЕНЕНИЯ vs 17.2.3:
- НЕ ходим в rmsp-pp.nalog.ru (он постоянно режет соединения с Railway)
- Источник ИНН: таблица self_employed_registry (импортируется из дампа ФНС
  раз в месяц через services/inn_generator/dump_importer.py)
- Поиск SQL-запросом, мгновенно
- Опциональный фильтр по region_code (по умолчанию ВЫКЛЮЧЕН — берём любого
  активного, потому что в реестре всё равно ~27k+ записей; адрес генерируем
  под регион клиента отдельно)

Логика выбора региона (для адреса) прежняя:
  home_address > contract_sign_city > company > диаспоры > Москва
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import text
from sqlmodel import Session, select

from app.models import Applicant, Application, Company
from app.models.self_employed_registry import SelfEmployedRegistry

from .kladr_address_gen import generate_address, GeneratedAddress, is_known_region
from .region_picker import pick_region, RegionPickResult


log = logging.getLogger(__name__)


@dataclass
class InnSuggestion:
    inn: str
    full_name_rmsp: Optional[str]
    region_code: Optional[str]

    home_address: str
    address_was_generated: bool

    estimated_npd_start: Optional[date]
    estimated_npd_start_raw: Optional[str]

    target_kladr_code: str
    target_region_name: str

    region_pick_source: str
    region_pick_explanation: str

    rmsp_raw: dict  # для совместимости со старым API; теперь содержит данные из БД


class InnPipelineError(Exception):
    pass


def suggest_inn_for_applicant(
    session: Session,
    applicant: Applicant,
    application: Optional[Application] = None,
    company: Optional[Company] = None,
    *,
    filter_by_region: bool = False,
    rng: Optional[random.Random] = None,
) -> InnSuggestion:
    """
    Главная функция: подбирает ИНН + адрес + дату для заявителя.

    Pack 17.2.4: ИНН берётся из локальной БД (self_employed_registry),
    которая раз в месяц обновляется из дампа ФНС.

    Args:
        filter_by_region: если True, ищет ИНН только из выбранного региона
                         (region_code = первые 2 цифры KLADR). По умолчанию
                         False — берём любого, и в этом нет рисков
                         (адрес всё равно генерируем под регион клиента).
    """
    if rng is None:
        rng = random.Random()

    # === Шаг 1: Выбор региона ===
    region_result: RegionPickResult = pick_region(
        session=session,
        applicant=applicant,
        application=application,
        company=company,
        rng=rng,
    )

    log.info(
        f"[pipeline] Region picked: {region_result.region.name} "
        f"(source={region_result.source}, kladr={region_result.region.kladr_code})"
    )

    # === Шаг 2: Выбор кандидата из локальной БД ===
    candidate = _pick_candidate_from_db(
        session=session,
        target_region_code=region_result.region.kladr_code[:2] if filter_by_region else None,
        rng=rng,
    )

    if candidate is None:
        if filter_by_region:
            raise InnPipelineError(
                f"В локальной БД нет свободных самозанятых из региона "
                f"{region_result.region.kladr_code[:2]} ({region_result.region.name}). "
                f"Попробуй без фильтра по региону или обнови реестр."
            )
        else:
            raise InnPipelineError(
                "В локальной БД нет свободных самозанятых. "
                "Возможно нужно импортировать дамп ФНС: "
                "POST /api/admin/registry/import-self-employed"
            )

    log.info(
        f"[pipeline] Chosen: {candidate.inn} {candidate.full_name} "
        f"(region {candidate.region_code}, support_begin={candidate.support_begin_date})"
    )

    # === Шаг 3: Адрес ===
    home_address: str
    address_was_generated: bool

    if region_result.use_existing_address and applicant.home_address:
        home_address = applicant.home_address.strip()
        address_was_generated = False
        log.info(f"[pipeline] Using existing address")
    else:
        if not is_known_region(region_result.region.kladr_code):
            raise InnPipelineError(
                f"Регион {region_result.region.kladr_code} ({region_result.region.name}) "
                f"не поддерживается address-generator'ом."
            )

        generated: GeneratedAddress = generate_address(
            kladr_code=region_result.region.kladr_code,
            rng=rng,
        )
        home_address = generated.full
        address_was_generated = True
        log.info(f"[pipeline] Generated address: {home_address}")

    # === Шаг 4: Дата начала НПД ===
    # Pack 17.5: генерируем синтетическую дату регистрации НПД, которая:
    # - всегда РАНЬШЕ даты подписания договора (минимум 30 дней)
    # - не сильно раньше (максимум 90 дней) — реалистичная история:
    #   "недавно стал самозанятым → начал работу → подписал договор"
    #
    # Почему 30-90 дней:
    # - Реестр SNRIP не содержит реальной даты регистрации НПД, только дату дампа
    # - Слишком давний срок (год+) рискован: на эту дату ИНН мог ещё не быть активным,
    #   что палится проверкой через npd.nalog.ru/check-status
    # - 30-90 дней — естественная история, минимум разрыва между регистрацией и
    #   договором но без подозрительной близости (1-2 дня = "только сегодня стал?")
    # - Каждый запрос suggest даёт новую дату (rng.randint)
    if application and application.contract_sign_date:
        days_before = rng.randint(30, 90)
        estimated_npd_start = application.contract_sign_date - timedelta(days=days_before)
        log.info(
            f"[pipeline] Synthetic NPD start date: {estimated_npd_start} "
            f"({days_before} days before contract_sign_date={application.contract_sign_date})"
        )
    else:
        # Fallback на дату из реестра если нет даты договора
        estimated_npd_start = candidate.support_begin_date
        log.warning(
            f"[pipeline] No contract_sign_date — falling back to registry date: "
            f"{estimated_npd_start}"
        )

    estimated_npd_raw = (
        estimated_npd_start.isoformat() if estimated_npd_start else None
    )

    return InnSuggestion(
        inn=candidate.inn,
        full_name_rmsp=candidate.full_name,
        region_code=candidate.region_code,
        home_address=home_address,
        address_was_generated=address_was_generated,
        estimated_npd_start=estimated_npd_start,
        estimated_npd_start_raw=estimated_npd_raw,
        target_kladr_code=region_result.region.kladr_code,
        target_region_name=region_result.region.name,
        region_pick_source=region_result.source,
        region_pick_explanation=region_result.explanation,
        rmsp_raw={
            "source": "local_db",
            "registry_create_date": (
                candidate.registry_create_date.isoformat()
                if candidate.registry_create_date
                else None
            ),
            "imported_at": (
                candidate.imported_at.isoformat()
                if candidate.imported_at
                else None
            ),
        },
    )


def mark_inn_as_used(
    session: Session,
    inn: str,
    applicant_id: int,
) -> None:
    """
    Помечает ИНН в self_employed_registry как использованный.
    Вызывается из endpoint /inn-accept после того, как менеджер принял ИНН.
    """
    now = datetime.utcnow()
    result = session.execute(
        text("""
            UPDATE self_employed_registry
            SET is_used = TRUE, used_by_applicant_id = :aid, used_at = :now
            WHERE inn = :inn AND is_used = FALSE
        """),
        {"inn": inn, "aid": applicant_id, "now": now},
    )
    if (result.rowcount or 0) == 0:
        log.warning(
            f"[pipeline] mark_inn_as_used: INN {inn} not found "
            f"in self_employed_registry or already used"
        )
    session.commit()


# ---------------------------------------------------------------------------
# Внутренние функции
# ---------------------------------------------------------------------------

def _pick_candidate_from_db(
    session: Session,
    target_region_code: Optional[str],
    rng: random.Random,
) -> Optional[SelfEmployedRegistry]:
    """
    Выбирает случайного неиспользованного самозанятого из БД.

    Стратегия: SQL ORDER BY RANDOM() LIMIT 1.
    Это медленно на больших таблицах, но у нас ~27k строк — не проблема.

    Если задан target_region_code — фильтр по нему.
    Если кандидатов нет — возвращает None.
    """
    stmt = select(SelfEmployedRegistry).where(
        SelfEmployedRegistry.is_used == False  # noqa: E712
    )
    if target_region_code:
        stmt = stmt.where(SelfEmployedRegistry.region_code == target_region_code)

    # Postgres-специфичный ORDER BY RANDOM() — для SQLite тот же синтаксис работает
    stmt = stmt.order_by(text("RANDOM()")).limit(1)

    return session.exec(stmt).first()


def get_registry_stats(session: Session) -> dict:
    """Статистика для админ-эндпоинта."""
    total_q = session.execute(
        text("SELECT COUNT(*) FROM self_employed_registry")
    ).scalar() or 0
    used_q = session.execute(
        text("SELECT COUNT(*) FROM self_employed_registry WHERE is_used = TRUE")
    ).scalar() or 0
    available = total_q - used_q
    return {
        "total_records": total_q,
        "available_records": available,
        "used_records": used_q,
    }



