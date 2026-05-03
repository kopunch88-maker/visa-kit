"""
Pack 17 / Pack 18.1 — пайплайн подбора ИНН самозанятого для заявителя.

Pack 18.1 изменения:
- Новая функция pick_candidate_with_fallback(): tier-fallback по region_code.
  Tier 1 (строго): WHERE region_code = target_region_code AND is_used=FALSE
  Tier 2 (диаспоры): пробуем регионы где есть диаспора национальности клиента
  Tier 3 (safety net): Москва (region_code='77') — там 34k+ свободных, не пустеет

- При fallback регион в результате — это РЕАЛЬНЫЙ регион из которого взяли кандидата
  (actual_region), а не исходный (requested_region). Адрес перегенерируется
  под actual_region чтобы ИНН и адрес были из одного субъекта.

- InnSuggestion расширен полями:
    fallback_used: bool
    requested_region_name: Optional[str]
    fallback_reason: Optional[str]
    region_code: str (всегда есть)
    requested_region_code: Optional[str] (только если был fallback)

Эти поля прокидываются в endpoint -> фронт показывает warning менеджеру.

Замечание про SelfEmployedRegistry: ФИО хранится одной строкой в поле full_name
(см. backend/app/models/self_employed_registry.py). Поля last_name/first_name/
middle_name отдельно НЕ существуют.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Applicant, Application, Company, Region, SelfEmployedRegistry
from app.models.self_employed_registry import (
    RegistryImportLog,
    SelfEmployedRegistryStats,
)

from .kladr_address_gen import KNOWN_REGIONS, generate_address
from .region_picker import (
    RegionPickResult,
    get_moscow,
    get_region_by_code,
    list_diaspora_regions_for_nationality,
    pick_region,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions (Pack 17 compat)
# ---------------------------------------------------------------------------


class InnPipelineError(RuntimeError):
    """
    Базовое исключение пайплайна. Re-экспортируется из __init__.py для
    обратной совместимости с Pack 17. Endpoint'ы ловят его как RuntimeError
    (InnPipelineError -> RuntimeError) и возвращают 409.
    """


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------


@dataclass
class InnSuggestion:
    """
    Предложение ИНН самозанятого, готовое к показу менеджеру в InnSuggestionModal.
    """

    inn: str
    full_name: str  # ФИО реального самозанятого из реестра (для дашборда менеджера, не идёт в документы)
    home_address: str
    kladr_code: str  # 13-значный КЛАДР сгенерированного адреса
    region_name: str  # Имя ФАКТИЧЕСКОГО региона (из которого взят ИНН)
    region_code: str  # 2-значный код субъекта (например '77', '02')
    inn_registration_date: date
    source: str  # 'home_address' | 'contract_city' | ... (откуда выбрали изначальный регион)

    # Pack 18.1: tier-fallback диагностика
    fallback_used: bool = False
    requested_region_name: Optional[str] = None  # имя ИЗНАЧАЛЬНО желаемого региона
    requested_region_code: Optional[str] = None  # его 2-значный код
    fallback_reason: Optional[str] = None
    # 'no_free_in_target_region' | 'no_free_in_target_or_diaspora'

    # Метаданные кандидата (не отображаются клиенту, нужны для accept)
    candidate_inn: str = ""  # дублирует inn для accept-флоу

    def __post_init__(self):
        if not self.candidate_inn:
            self.candidate_inn = self.inn


# ---------------------------------------------------------------------------
# Tier-fallback подбор кандидата
# ---------------------------------------------------------------------------


@dataclass
class CandidatePickResult:
    candidate: SelfEmployedRegistry
    actual_region: Region
    actual_region_code: str
    fallback_used: bool
    fallback_reason: Optional[str] = None
    tried_region_codes: list[str] = field(default_factory=list)


def _pick_random_free_in_region(
    session: Session, region_code: str
) -> Optional[SelfEmployedRegistry]:
    """
    Достаём случайного свободного кандидата из реестра в указанном регионе.

    Используем ORM-запрос с фильтром по частичному индексу
    idx_self_employed_region_available (region_code, WHERE is_used=FALSE) — Pack 17.6.

    ORDER BY RANDOM() LIMIT 1 — стандартный подход для случайной выборки.
    На частичном индексе при ~10-30k свободных записей в регионе — быстро (10-50ms).
    """
    stmt = (
        select(SelfEmployedRegistry)
        .where(SelfEmployedRegistry.region_code == region_code)
        .where(SelfEmployedRegistry.is_used == False)  # noqa: E712
        .order_by(func.random())
        .limit(1)
    )
    return session.exec(stmt).first()


def pick_candidate_with_fallback(
    session: Session,
    *,
    target_region_code: str,
    nationality: Optional[str] = None,
    seed: Optional[int] = None,
) -> CandidatePickResult:
    """
    Pack 18.1: подбор кандидата с tier-fallback.

    Tier 1 — target_region_code (строго).
    Tier 2 — диаспорные регионы по nationality (по очереди, перетасованы).
    Tier 3 — Москва (region_code='77').

    На каждом уровне:
    - если найден свободный кандидат -> возвращаем
    - если 0 свободных -> переходим на следующий уровень

    Возвращаем CandidatePickResult c флагом fallback_used и причиной.
    Если даже в Москве 0 (фактически невозможно при здоровой БД) —
    бросаем RuntimeError, endpoint его обработает в 409.
    """
    rng = random.Random(seed)
    tried: list[str] = []

    # ----- Tier 1: target -----
    tried.append(target_region_code)
    cand = _pick_random_free_in_region(session, target_region_code)
    if cand is not None:
        actual_region = get_region_by_code(session, target_region_code)
        if actual_region is None:
            raise RuntimeError(
                f"Pack 18.1: candidate found for region_code={target_region_code} "
                f"but no Region row matches it. Inconsistency between registry and Region table."
            )
        log.info(
            "pick_candidate_with_fallback: Tier 1 hit, region_code=%s candidate inn=%s",
            target_region_code,
            cand.inn,
        )
        return CandidatePickResult(
            candidate=cand,
            actual_region=actual_region,
            actual_region_code=target_region_code,
            fallback_used=False,
            tried_region_codes=tried,
        )

    log.warning(
        "pick_candidate_with_fallback: Tier 1 EMPTY for region_code=%s, trying diaspora",
        target_region_code,
    )

    # ----- Tier 2: диаспоры по гражданству -----
    diaspora_regions = list_diaspora_regions_for_nationality(session, nationality)
    # Исключим target из диаспор (мы его уже пробовали)
    diaspora_regions = [
        r for r in diaspora_regions if (r.region_code or "") != target_region_code
    ]
    rng.shuffle(diaspora_regions)

    for r in diaspora_regions:
        rc = (r.region_code or "").strip()
        if not rc or rc in tried:
            continue
        tried.append(rc)
        cand = _pick_random_free_in_region(session, rc)
        if cand is not None:
            log.info(
                "pick_candidate_with_fallback: Tier 2 (diaspora) hit, region_code=%s region=%s",
                rc,
                r.name,
            )
            return CandidatePickResult(
                candidate=cand,
                actual_region=r,
                actual_region_code=rc,
                fallback_used=True,
                fallback_reason="no_free_in_target_region",
                tried_region_codes=tried,
            )

    log.warning(
        "pick_candidate_with_fallback: Tier 2 EMPTY (tried diaspora for nationality=%s), falling back to Moscow",
        nationality,
    )

    # ----- Tier 3: Москва -----
    moscow_code = "77"
    if moscow_code not in tried:
        tried.append(moscow_code)
        cand = _pick_random_free_in_region(session, moscow_code)
        if cand is not None:
            moscow = get_moscow(session)
            if moscow is None:
                raise RuntimeError(
                    "Pack 18.1: candidate in registry with region_code='77' but Region(Moscow) row missing"
                )
            log.info(
                "pick_candidate_with_fallback: Tier 3 (Moscow safety net) hit, candidate inn=%s",
                cand.inn,
            )
            if target_region_code == moscow_code:
                # Москва была изначальным таргетом, но Tier 1 показал пусто, а сейчас не пусто?
                # Race condition между запросами или кеш — но Tier 3 нашёл, значит просто продолжаем.
                # Технически fallback_used=False (мы не сменили регион).
                return CandidatePickResult(
                    candidate=cand,
                    actual_region=moscow,
                    actual_region_code=moscow_code,
                    fallback_used=False,
                    tried_region_codes=tried,
                )
            reason = (
                "no_free_in_target_or_diaspora"
                if diaspora_regions
                else "no_free_in_target_region"
            )
            return CandidatePickResult(
                candidate=cand,
                actual_region=moscow,
                actual_region_code=moscow_code,
                fallback_used=True,
                fallback_reason=reason,
                tried_region_codes=tried,
            )

    # Если мы здесь — даже Москва пуста. Это означает что вся БД исчерпана.
    raise RuntimeError(
        "Pack 18.1: ни в target-регионе, ни в диаспорах, ни в Москве нет свободных "
        f"кандидатов. tried={tried}. Срочно обновите дамп ФНС "
        "(см. docs/ежемесячное_обновление_базы_ИНН.md)."
    )


# ---------------------------------------------------------------------------
# Дата НПД (без изменений с Pack 17.5)
# ---------------------------------------------------------------------------


def _synthetic_npd_registration_date(
    contract_sign_date: Optional[date], rng: random.Random
) -> date:
    """
    Pack 17.5: синтетическая дата регистрации НПД.
    contract_sign_date - 30..90 дней (рандом).
    Если contract_sign_date не задан — берём сегодня.
    """
    base = contract_sign_date or date.today()
    days_before = rng.randint(30, 90)
    return base - timedelta(days=days_before)


# ---------------------------------------------------------------------------
# Главный entry point
# ---------------------------------------------------------------------------


def suggest_inn_for_applicant(
    session: Session,
    *,
    applicant: Applicant,
    application: Optional[Application] = None,
    company: Optional[Company] = None,
    seed: Optional[int] = None,
) -> InnSuggestion:
    """
    Главная функция: подбираем кандидата под applicant'а.

    Pack 18.1 изменения по сравнению с Pack 17:
    - больше нет параметра filter_by_region (всегда фильтруем — это правильное поведение)
    - используем pick_candidate_with_fallback вместо «или строго, или любой»
    - адрес генерируется под ФАКТИЧЕСКИЙ регион (после fallback)
    - возвращаем расширенный InnSuggestion с warning-полями
    """
    rng = random.Random(seed)

    # ----- 1. Выбираем желаемый регион -----
    nationality = (applicant.nationality or "").strip() or None
    requested_pick: RegionPickResult = pick_region(
        session,
        home_address=applicant.home_address,
        contract_sign_city=(application.contract_sign_city if application else None),
        company_legal_address=(company.legal_address if company else None),
        nationality=nationality,
        seed=seed,
    )
    requested_region = requested_pick.region
    requested_code = requested_pick.region_code

    log.info(
        "suggest_inn_for_applicant: requested region=%s (code=%s, source=%s)",
        requested_region.name,
        requested_code,
        requested_pick.source,
    )

    # ----- 2. Подбор кандидата с tier-fallback -----
    pick = pick_candidate_with_fallback(
        session,
        target_region_code=requested_code,
        nationality=nationality,
        seed=seed,
    )
    candidate = pick.candidate
    actual_region = pick.actual_region
    actual_code = pick.actual_region_code

    # ----- 3. Адрес под ФАКТИЧЕСКИЙ регион -----
    # Если у applicant'а уже есть home_address и регион не сменился — оставляем его.
    # Если регион сменился (fallback) — генерируем новый адрес под actual_region.
    keep_existing_address = (
        bool(applicant.home_address)
        and not pick.fallback_used
        and requested_pick.source == "home_address"
    )
    if keep_existing_address:
        home_address = applicant.home_address
        # kladr_code берём из реального адреса, если в applicant'е есть; иначе генерим
        # короткий 2-значный код субъекта, дополним до 13 нулями справа (заглушка KLADR)
        kladr_code = applicant.inn_kladr_code or _make_subject_kladr(actual_code)
        log.info(
            "suggest_inn_for_applicant: keeping existing applicant.home_address (source=home_address, no fallback)"
        )
    else:
        # Pack 18.1: реальная функция называется generate_address(kladr_code, rng).
        # Принимает kladr_code из KNOWN_REGIONS (см. kladr_address_gen.py).
        # Если region.kladr_code не в KNOWN_REGIONS — пробуем найти любой подходящий
        # KLADR из KNOWN_REGIONS с тем же 2-значным префиксом (region_code).
        target_kladr = _resolve_known_kladr(actual_region.kladr_code, actual_code)
        addr = generate_address(target_kladr, rng)
        home_address = addr.full
        kladr_code = addr.kladr_code
        log.info(
            "suggest_inn_for_applicant: generated new address for actual_region=%s kladr=%s (fallback_used=%s)",
            actual_region.name,
            target_kladr,
            pick.fallback_used,
        )

    # ----- 4. Дата НПД -----
    inn_reg_date = _synthetic_npd_registration_date(
        application.contract_sign_date if application else None, rng
    )

    # ----- 5. Сборка результата -----
    suggestion = InnSuggestion(
        inn=candidate.inn,
        full_name=(candidate.full_name or "").strip() or "—",
        home_address=home_address,
        kladr_code=kladr_code,
        region_name=actual_region.name,
        region_code=actual_code,
        inn_registration_date=inn_reg_date,
        source=requested_pick.source,
        fallback_used=pick.fallback_used,
        requested_region_name=(
            requested_region.name if pick.fallback_used else None
        ),
        requested_region_code=(requested_code if pick.fallback_used else None),
        fallback_reason=pick.fallback_reason,
    )

    log.info(
        "suggest_inn_for_applicant: SUCCESS inn=%s region=%s (code=%s) fallback=%s",
        suggestion.inn,
        suggestion.region_name,
        suggestion.region_code,
        suggestion.fallback_used,
    )
    return suggestion


def _make_subject_kladr(region_code: str) -> str:
    """
    Заглушка KLADR-кода уровня субъекта: '77' + 11 нулей = 13 цифр.
    Используется когда у applicant'а уже есть home_address но нет inn_kladr_code.
    Лучше чем None — пайплайн дальше может писать в БД.
    """
    code = (region_code or "00").zfill(2)[:2]
    return code + "0" * 11


def _resolve_known_kladr(region_kladr: Optional[str], region_code: str) -> str:
    """
    Pack 18.1: KNOWN_REGIONS в kladr_address_gen.py содержит точные KLADR'ы
    городов (например '2300000700000' для Сочи и '2300000100000' для
    Краснодара). Region.kladr_code в БД может быть любым из этих, либо
    общим '2300000000000' для субъекта.

    Логика:
    1. Если region.kladr_code напрямую в KNOWN_REGIONS — используем его.
    2. Иначе ищем в KNOWN_REGIONS любой kladr с тем же 2-значным префиксом
       (region_code). Если их несколько (например '23xxx' = Сочи И Краснодар) —
       берём первый по сортировке (детерминистично).
    3. Если ничего не нашли — это критическая ошибка конфигурации
       (KNOWN_REGIONS не покрывает регион из таблицы Region). Бросаем ясную
       ошибку.
    """
    if region_kladr and region_kladr in KNOWN_REGIONS:
        return region_kladr

    code = (region_code or "").strip()[:2]
    if code:
        matches = sorted(k for k in KNOWN_REGIONS.keys() if k.startswith(code))
        if matches:
            chosen = matches[0]
            log.info(
                "_resolve_known_kladr: region_kladr=%r not in KNOWN_REGIONS, "
                "matched by region_code=%s -> %s",
                region_kladr,
                code,
                chosen,
            )
            return chosen

    raise InnPipelineError(
        f"Pack 18.1: KNOWN_REGIONS does not contain kladr matching region_kladr={region_kladr!r} "
        f"or region_code={region_code!r}. Update kladr_address_gen.KNOWN_REGIONS to cover this region."
    )

# ---------------------------------------------------------------------------
# Pack 17.2.4 compat: статистика реестра (используется в registry_admin endpoint)
# ---------------------------------------------------------------------------


def get_registry_stats(session: Session) -> SelfEmployedRegistryStats:
    """
    Сводная статистика по реестру self_employed_registry для админ-эндпоинта
    GET /admin/registry/import-status.

    Pack 18.1: восстановлена из старого pipeline (импортируется в
    backend/app/api/registry_admin.py).

    Возвращает:
        - total_records: всего записей в реестре
        - available_records: с is_used=False (доступны для выдачи)
        - used_records: с is_used=True (уже выданы applicant'ам)
        - last_import_date: started_at последнего импорта (если есть)
        - last_import_status: 'success' | 'failed' | 'running' | 'queued' | None
        - last_import_dump_date: dump_date последнего импорта (если есть)
    """
    total = session.exec(
        select(func.count()).select_from(SelfEmployedRegistry)  # type: ignore[arg-type]
    ).one()
    used = session.exec(
        select(func.count())
        .select_from(SelfEmployedRegistry)
        .where(SelfEmployedRegistry.is_used == True)  # noqa: E712
    ).one()

    # session.exec(scalar_select).one() в SQLModel возвращает int (не Row).
    # Подстраховка для разных версий SQLModel:
    if isinstance(total, tuple):
        total = total[0]
    if isinstance(used, tuple):
        used = used[0]

    available = int(total) - int(used)

    # Последний импорт по started_at DESC
    last_log = session.exec(
        select(RegistryImportLog).order_by(RegistryImportLog.started_at.desc()).limit(1)  # type: ignore[union-attr]
    ).first()

    return SelfEmployedRegistryStats(
        total_records=int(total),
        available_records=int(available),
        used_records=int(used),
        last_import_date=(last_log.started_at if last_log else None),
        last_import_status=(last_log.status if last_log else None),
        last_import_dump_date=(last_log.dump_date if last_log else None),
    )
