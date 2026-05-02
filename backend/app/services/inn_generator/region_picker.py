"""
Pack 17.2 — выбор региона для генерации ИНН/адреса самозанятого.

Логика выбора региона по приоритетам (от высокого к низкому):

  1. applicant.home_address — если есть, парсим из него регион (НЕ генерируем адрес)
  2. application.contract_sign_city — город подписания договора
  3. company.legal_address — регион Заказчика (часто там же где работает клиент)
  4. applicant.education_city — регион места обучения
  5. Случайный из «диаспоры» по applicant.nationality (Region.diaspora_for_countries)
  6. Fallback — Москва (универсальный регион где работают все диаспоры)

Реализация поиска по строке: ищем подстроки названий регионов из таблицы Region
(name, name_full) внутри строки адреса/города.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import List, Optional

from sqlmodel import Session, select

from app.models import Region, Applicant, Application, Company

log = logging.getLogger(__name__)


@dataclass
class RegionPickResult:
    """Результат выбора региона."""
    region: Region                    # выбранный Region из БД
    source: str                       # откуда взяли: 'home_address', 'sign_city', 'company', 'education', 'diaspora', 'fallback'
    explanation: str                  # человекочитаемое объяснение для UI
    use_existing_address: bool = False  # если True — используем applicant.home_address как есть, не генерируем


# Fallback на Москву (универсальный регион)
FALLBACK_KLADR = "7700000000000"


def pick_region(
    session: Session,
    applicant: Applicant,
    application: Optional[Application] = None,
    company: Optional[Company] = None,
    rng: Optional[random.Random] = None,
) -> RegionPickResult:
    """
    Выбирает Region для генерации ИНН + адреса.

    Args:
        session: открытая Session SQLModel
        applicant: заявитель (обязательно)
        application: заявка (опционально, для contract_sign_city)
        company: компания-Заказчик (опционально, для legal_address)
        rng: для воспроизводимости в тестах

    Returns:
        RegionPickResult с выбранным регионом и причиной.
    """
    if rng is None:
        rng = random.Random()

    # === 1. applicant.home_address — высший приоритет ===
    # Если адрес уже есть, используем его + парсим регион оттуда
    if applicant.home_address and applicant.home_address.strip():
        region = _find_region_in_text(session, applicant.home_address)
        if region:
            return RegionPickResult(
                region=region,
                source="home_address",
                explanation=(
                    f"Использую адрес заявителя ({region.name}). "
                    f"ИНН подберу для этого региона, адрес НЕ генерирую."
                ),
                use_existing_address=True,
            )
        # Адрес есть, но регион не распознан — используем адрес как есть,
        # ИНН берём из любого региона (наш фильтр всё равно гибкий)
        log.warning(
            f"[region_picker] applicant.home_address={applicant.home_address!r} "
            f"но регион не распознан — fallback к sign_city"
        )

    # === 2. application.contract_sign_city ===
    if application and application.contract_sign_city:
        sign_city = application.contract_sign_city.strip()
        region = _find_region_by_city_name(session, sign_city)
        if region:
            return RegionPickResult(
                region=region,
                source="sign_city",
                explanation=(
                    f"По городу подписания договора «{sign_city}» → {region.name_full}"
                ),
                use_existing_address=False,
            )

    # === 3. company.legal_address ===
    if company and company.legal_address:
        region = _find_region_in_text(session, company.legal_address)
        if region:
            return RegionPickResult(
                region=region,
                source="company",
                explanation=(
                    f"По юр.адресу Заказчика → {region.name_full}"
                ),
                use_existing_address=False,
            )

    # === 4. applicant.education_city — пока не используется ===
    # На этом этапе у Applicant нет отдельного поля education_city,
    # education это JSON список с institution+specialty.
    # Можно расширить позже — сейчас пропускаем.

    # === 5. Диаспора по nationality ===
    if applicant.nationality:
        nationality = applicant.nationality.upper()
        diaspora_regions = _find_diaspora_regions(session, nationality)
        if diaspora_regions:
            region = rng.choice(diaspora_regions)
            return RegionPickResult(
                region=region,
                source="diaspora",
                explanation=(
                    f"Случайный регион диаспоры для {nationality}: {region.name_full}"
                ),
                use_existing_address=False,
            )

    # === 6. Fallback Москва ===
    fallback = session.exec(
        select(Region).where(Region.kladr_code == FALLBACK_KLADR)
    ).first()

    if fallback:
        return RegionPickResult(
            region=fallback,
            source="fallback",
            explanation=(
                f"Не удалось определить регион — используем Москву (универсальный)"
            ),
            use_existing_address=False,
        )

    # Совсем плохо — нет даже Москвы в БД
    raise RuntimeError(
        "В таблице Region нет регионов! Сначала примените миграцию Pack 17.0 "
        "или запустите seed."
    )


def _find_region_by_city_name(
    session: Session,
    city_name: str,
) -> Optional[Region]:
    """
    Ищет Region по названию города (точное совпадение по `name`, регистронезависимо).

    Примеры:
        "Сочи" → kladr_code 2300000700000
        "Москва" → kladr_code 7700000000000
        "Ростов-на-Дону" → kladr_code 6100000100000
    """
    if not city_name:
        return None

    city_normalized = city_name.strip().lower()

    # Получаем все активные регионы и ищем по name (регистронезависимо)
    regions = session.exec(
        select(Region).where(Region.is_active == True)  # noqa: E712
    ).all()

    for r in regions:
        if r.name.lower() == city_normalized:
            return r

    # Не нашли точное — пробуем contains
    for r in regions:
        if city_normalized in r.name.lower() or r.name.lower() in city_normalized:
            return r

    return None


def _find_region_in_text(
    session: Session,
    text: str,
) -> Optional[Region]:
    """
    Ищет упоминание любого известного региона в тексте (например в адресе).

    Примеры:
        "Краснодарский край, г.Сочи, ул...." → Сочи
        "г. Москва, ул...." → Москва
        "г. Ростов-на-Дону, ..." → Ростов-на-Дону
    """
    if not text:
        return None

    text_lower = text.lower()
    regions = session.exec(
        select(Region).where(Region.is_active == True)  # noqa: E712
    ).all()

    # Сначала ищем по name_full (более специфичный паттерн — "городской округ Сочи")
    # Берём region у которого name_full даёт самое длинное совпадение
    best_match: Optional[Region] = None
    best_match_len = 0

    for r in regions:
        name_full_lower = r.name_full.lower()
        # Разделяем name_full на части по запятым и проверяем включение каждой
        for part in name_full_lower.split(","):
            part = part.strip()
            if len(part) >= 4 and part in text_lower:
                if len(part) > best_match_len:
                    best_match = r
                    best_match_len = len(part)

    if best_match:
        return best_match

    # Fallback — простой поиск по name
    for r in regions:
        if r.name.lower() in text_lower:
            return r

    return None


def _find_diaspora_regions(
    session: Session,
    nationality_iso3: str,
) -> List[Region]:
    """
    Возвращает все активные регионы где `nationality_iso3` есть в diaspora_for_countries.

    Поскольку diaspora_for_countries это JSON массив, фильтруем на стороне Python
    (для совместимости SQLite + Postgres).
    """
    nationality = nationality_iso3.upper()

    regions = session.exec(
        select(Region).where(Region.is_active == True)  # noqa: E712
    ).all()

    return [
        r for r in regions
        if r.diaspora_for_countries and nationality in r.diaspora_for_countries
    ]
