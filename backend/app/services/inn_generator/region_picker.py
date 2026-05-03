"""
Pack 17 / Pack 18.1: выбор региона для генерации ИНН самозанятого.

Логика приоритетов (без изменений с Pack 17):
1. applicant.home_address — если адрес явно указан и регион парсится
2. application.contract_sign_city — город подписания договора
3. company.legal_address — регион заказчика
4. random_diaspora_for_nationality — диаспоры по гражданству клиента
5. fallback — Москва (region_code='77')

Pack 18.1 изменения:
- RegionPickResult получает property `region_code: str` (берётся напрямую из
  region.region_code, который уже есть в модели Region — отдельное поле, не
  derive из kladr_code).
- Добавлены helpers get_region_by_code() и list_diaspora_regions_for_nationality().
- Используется реальное имя поля диаспор: Region.diaspora_for_countries (НЕ
  diaspora_for_nationalities — это была моя ошибка в первой итерации Pack 18.1).
- Для матчинга по тексту используются ТОЛЬКО реально существующие поля
  Region.name и Region.name_full (не aliases/city_name — этих полей нет
  в текущей модели).
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, select

from app.models import Region

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------


@dataclass
class RegionPickResult:
    """
    Результат выбора региона.

    Pack 18.1: добавлена property region_code (берётся напрямую из
    region.region_code, который уже есть в модели Region).
    """

    region: Region
    source: str  # 'home_address' | 'contract_city' | 'company_legal' | 'diaspora' | 'fallback_moscow'
    matched_text: Optional[str] = None  # что распарсили из адреса/города

    @property
    def region_code(self) -> str:
        """Двухзначный код субъекта РФ как строка ('77', '02', '20', ...)."""
        rc = (self.region.region_code or "").strip()
        if not rc:
            # На случай битых данных в БД — fallback на kladr_code[:2]
            kladr = (self.region.kladr_code or "").strip()
            if len(kladr) >= 2:
                return kladr[:2]
            log.warning(
                "RegionPickResult.region_code: empty region_code AND kladr_code for region id=%s name=%r",
                self.region.id,
                self.region.name,
            )
            return "77"
        return rc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Нижний регистр, убираем пунктуацию и лишние пробелы."""
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r"[.,;:\"\'«»()]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _all_aliases(region: Region) -> list[str]:
    """
    Все варианты названия региона/города по которым можно его «узнать» в тексте.

    Pack 18.1: используем только реально существующие поля модели — name и
    name_full. Поля aliases / city_name в модели Region НЕТ (см.
    backend/app/models/region.py).
    """
    out: list[str] = []
    for raw in (region.name, region.name_full):
        if not raw:
            continue
        norm = _normalize(raw)
        if norm and norm not in out:
            out.append(norm)
    return out


def _match_region_in_text(text: str, regions: list[Region]) -> Optional[Region]:
    """
    Ищем какой регион упоминается в свободном тексте.

    Стратегия: сначала пытаемся «длинные» матчи (name_full), потом короткие (name).
    Это защищает от ложного срабатывания например «Краснодар» когда в тексте
    реально упомянут «Краснодарский край» — оба совпадут, но мы хотим чтобы
    прошёл первый совпавший в порядке списка regions.

    Возвращает первый найденный (в порядке regions, как пришло из get_active_regions).
    """
    if not text:
        return None
    norm_text = _normalize(text)
    if not norm_text:
        return None

    # Сначала проверяем по name_full (более длинному и однозначному)
    for r in regions:
        full = _normalize(r.name_full or "")
        if full and full in norm_text:
            return r

    # Потом по name (короткому, может быть неоднозначным — Сочи это и city, и часть Краснодарского края)
    for r in regions:
        nm = _normalize(r.name or "")
        if nm and nm in norm_text:
            return r

    return None


def _pick_diaspora_region(
    nationality: Optional[str], regions: list[Region], rng: random.Random
) -> Optional[tuple[Region, str]]:
    """
    Подбираем регион из диаспор по гражданству клиента.

    Pack 18.1: реальное имя поля — Region.diaspora_for_countries (НЕ
    diaspora_for_nationalities как я ошибочно писал в первой версии).
    Хранит ISO-3 коды (TUR, AZE, RUS, ...).
    """
    if not nationality:
        return None
    nat = nationality.strip().upper()
    candidates = [
        r for r in regions if nat in (r.diaspora_for_countries or [])
    ]
    if not candidates:
        return None
    chosen = rng.choice(candidates)
    return chosen, nat


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_active_regions(session: Session) -> list[Region]:
    """Все активные регионы из БД, отсортированы по id."""
    stmt = select(Region).where(Region.is_active == True).order_by(Region.id)  # noqa: E712
    return list(session.exec(stmt).all())


def get_moscow(session: Session) -> Optional[Region]:
    """Москва как safety-net регион. Берём по region_code='77'."""
    stmt = select(Region).where(Region.region_code == "77")
    return session.exec(stmt).first()


def get_region_by_code(session: Session, region_code: str) -> Optional[Region]:
    """
    Найти активный регион по двухзначному коду субъекта (например '77', '05', '23').
    """
    if not region_code:
        return None
    code = region_code.strip()
    if len(code) != 2:
        return None
    stmt = (
        select(Region)
        .where(Region.is_active == True)  # noqa: E712
        .where(Region.region_code == code)
    )
    return session.exec(stmt).first()


def pick_region(
    session: Session,
    *,
    home_address: Optional[str] = None,
    contract_sign_city: Optional[str] = None,
    company_legal_address: Optional[str] = None,
    nationality: Optional[str] = None,
    seed: Optional[int] = None,
) -> RegionPickResult:
    """
    Главная функция выбора региона.

    Pack 18.1: возвращает RegionPickResult с property region_code (str, 2 цифры).
    Сама логика приоритетов идентична Pack 17.
    """
    rng = random.Random(seed)
    regions = get_active_regions(session)
    if not regions:
        raise RuntimeError(
            "Нет ни одного активного региона в таблице region. "
            "Проверьте миграцию Pack 17.0 / seed."
        )

    # Tier 1: home_address
    if home_address:
        r = _match_region_in_text(home_address, regions)
        if r:
            log.info(
                "pick_region: matched home_address -> region=%s (code=%s)",
                r.name,
                r.region_code,
            )
            return RegionPickResult(region=r, source="home_address", matched_text=home_address)

    # Tier 2: contract_sign_city
    if contract_sign_city:
        r = _match_region_in_text(contract_sign_city, regions)
        if r:
            log.info(
                "pick_region: matched contract_sign_city=%r -> region=%s",
                contract_sign_city,
                r.name,
            )
            return RegionPickResult(
                region=r, source="contract_city", matched_text=contract_sign_city
            )

    # Tier 3: company_legal_address
    if company_legal_address:
        r = _match_region_in_text(company_legal_address, regions)
        if r:
            log.info(
                "pick_region: matched company_legal_address -> region=%s",
                r.name,
            )
            return RegionPickResult(
                region=r, source="company_legal", matched_text=company_legal_address
            )

    # Tier 4: диаспора по гражданству
    diaspora = _pick_diaspora_region(nationality, regions, rng)
    if diaspora:
        r, nat = diaspora
        log.info(
            "pick_region: diaspora-pick for nationality=%s -> region=%s",
            nat,
            r.name,
        )
        return RegionPickResult(region=r, source="diaspora", matched_text=nat)

    # Tier 5: Москва
    moscow = get_moscow(session)
    if moscow:
        log.info("pick_region: fallback to Moscow")
        return RegionPickResult(region=moscow, source="fallback_moscow")

    # Если даже Москвы нет — берём первый активный регион
    log.warning("pick_region: Moscow not found in regions table, taking first active region")
    return RegionPickResult(region=regions[0], source="fallback_moscow")


def list_diaspora_regions_for_nationality(
    session: Session, nationality: Optional[str]
) -> list[Region]:
    """
    Все активные регионы где есть диаспора указанной национальности.

    Используется в Pack 18.1 tier-fallback (когда в исходном регионе кончились
    кандидаты — пробуем диаспоры).
    """
    if not nationality:
        return []
    nat = nationality.strip().upper()
    if not nat:
        return []
    regions = get_active_regions(session)
    return [r for r in regions if nat in (r.diaspora_for_countries or [])]
