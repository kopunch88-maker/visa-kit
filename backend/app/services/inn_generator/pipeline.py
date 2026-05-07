"""
Pack 17 / Pack 18.1 / Pack 18.3.4 / Pack 28 Часть 2 — пайплайн подбора ИНН.

ПЕРЕПИСАНО Pack 28 Часть 2 (08.05.2026):
- ИСТОЧНИК ИНН: npd_candidate (ВМЕСТО self_employed_registry).
  SNRIP-дамп больше не используется — все его записи это ИП, не самозанятые.
  Pack 28 Часть 1 ввёл новую таблицу npd_candidate с реальными чистыми
  самозанятыми из rmsp-pp.nalog.ru, прошедшими EGRUL+NPD верификацию.

- ВНИМАНИЕ: tier-fallback УБРАН. В новой архитектуре если в регионе пул
  пуст — endpoint inn-suggest возвращает 202 Accepted с task_id, фронт
  показывает спиннер "Идёт поиск...", в фоне идёт refill_pool_for_region.
  Это решение принято потому что:
  1. По разведке — 23-59% rmsp-pp кандидатов чистые → быстро добиваем 5
  2. Менеджеру лучше подождать 5-10 мин и получить чистого САМОЗАНЯТОГО
     именно из его региона, чем сразу получить чистого москвича (адрес
     придётся подменять — лишняя работа).

- НОВАЯ функция: pick_verified_candidate_for_region() — забирает один
  verified кандидат из npd_candidate, ставит ему status='allocated' с
  броней на 30 минут. inn-accept потом переведёт в 'used'.

- НОВЫЙ exception: NeedsRefillError — бросается когда verified=0 в регионе.
  endpoint его ловит и стартует BackgroundTask + возвращает 202.

- registration_date теперь берётся ИЗ candidate.registration_date (реальная
  дата постановки на учёт по НПД из ФНС API). Если её нет (Pack 28.5
  ещё не сделан, ФНС API урезали — см. Инцидент 19) — fallback на
  синтетическую как в Pack 18.3.4.

УБРАНО Pack 28 Часть 2:
- pick_candidate_with_fallback (tier-fallback больше не нужен)
- _pick_random_free_in_region (заменён на _pick_one_verified)
- list_diaspora_regions_for_nationality (диаспоры не используются —
  если у клиента указано гражданство Турция, но регион РФ, refill идёт
  по фактическому региону)
- Импорт SelfEmployedRegistry полностью

Pack 18.3.4 ОСТАЛОСЬ: _synthetic_npd_registration_date(). Используется как
fallback если candidate.registration_date is None.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Applicant, Application, Company, NpdCandidate, Region

from .kladr_address_gen import KNOWN_REGIONS, generate_address
from .region_picker import (
    RegionPickResult,
    get_moscow,
    get_region_by_code,
    pick_region,
)

log = logging.getLogger(__name__)


# ===========================================================================
# Бронь allocated на 30 минут
# ===========================================================================
ALLOCATION_TTL_MINUTES = 30


# ===========================================================================
# Exceptions
# ===========================================================================


class NeedsRefillError(Exception):
    """
    Бросается когда в пуле verified=0 для региона. endpoint ловит и стартует
    lazy refill через BackgroundTask + возвращает 202 Accepted с task_id.

    В отличие от RuntimeError из старого кода — это НЕ ошибка, это сигнал
    "пожалуйста подожди пока мы найдём".
    """

    def __init__(self, region_code: str, region_name: str):
        self.region_code = region_code
        self.region_name = region_name
        super().__init__(
            f"Pool empty for region {region_code} ({region_name}). "
            "Trigger lazy refill via BackgroundTask."
        )


# ===========================================================================
# Result dataclass
# ===========================================================================


@dataclass
class InnSuggestion:
    """Результат подбора ИНН для applicant'а."""
    inn: str
    full_name: str
    home_address: str
    kladr_code: str
    region_name: str
    region_code: str
    inn_registration_date: Optional[date] = None

    # Источник определения целевого региона (home_address / contract_city / ...)
    source: str = "unknown"

    # Pack 28 Часть 2: больше нет fallback (если регион пуст — refill, не fallback).
    # Поля оставлены для совместимости со старым фронтом.
    fallback_used: bool = False
    requested_region_name: Optional[str] = None
    requested_region_code: Optional[str] = None
    fallback_reason: Optional[str] = None


# ===========================================================================
# Подбор verified-кандидата с allocated-броней
# ===========================================================================


def _expire_stale_allocations(session: Session) -> int:
    """
    Освобождает кандидатов которые были allocated больше ALLOCATION_TTL_MINUTES
    назад (менеджер открыл модал и закрыл не приняв).

    Returns: сколько кандидатов разаллоцировано.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=ALLOCATION_TTL_MINUTES)
    stale = session.exec(
        select(NpdCandidate)
        .where(NpdCandidate.status == "allocated")
        .where(NpdCandidate.allocated_until < cutoff)
    ).all()
    if not stale:
        return 0
    for cand in stale:
        cand.status = "verified"
        cand.allocated_until = None
        session.add(cand)
    session.commit()
    log.info("[pipeline] expired %d stale allocations", len(stale))
    return len(stale)


def pick_verified_candidate_for_region(
    session: Session,
    region_code: str,
    *,
    seed: Optional[int] = None,
) -> Optional[NpdCandidate]:
    """
    Забирает один verified-кандидат из региона и помечает allocated.

    Возвращает None если в регионе 0 verified — endpoint должен бросить
    NeedsRefillError и стартануть refill.
    """
    # Сначала освобождаем зависшие allocated
    _expire_stale_allocations(session)

    # Берём случайного verified — sample через ORDER BY RANDOM()
    rng = random.Random(seed)

    verified = session.exec(
        select(NpdCandidate)
        .where(NpdCandidate.region_code == region_code)
        .where(NpdCandidate.status == "verified")
    ).all()

    if not verified:
        log.warning(
            "[pipeline] pool empty for region=%s (verified=0)", region_code,
        )
        return None

    cand = rng.choice(list(verified))

    # Помечаем allocated
    cand.status = "allocated"
    cand.allocated_until = datetime.utcnow() + timedelta(
        minutes=ALLOCATION_TTL_MINUTES
    )
    session.add(cand)
    session.commit()
    log.info(
        "[pipeline] allocated inn=%s region=%s until=%s",
        cand.inn, region_code, cand.allocated_until.isoformat() if cand.allocated_until else None,
    )
    return cand


# ===========================================================================
# Синтетическая дата НПД (Pack 18.3.4) — fallback
# ===========================================================================


def _synthetic_npd_registration_date(
    submission_date: Optional[date],
    contract_sign_date: Optional[date],
    rng: random.Random,
) -> date:
    """
    Pack 18.3.4: синтетическая дата постановки на НПД.

    База — submission_date (дата подачи в консул). Если её нет — fallback на
    contract_sign_date + 90 дней. Если оба нет — today() + 30.

    Диапазон: 120-210 дней до базы (4-7 месяцев = "≥3 месяца НПД с запасом
    30 дней на возможный перенос подачи").

    Pack 28 Часть 2: используется ТОЛЬКО как fallback когда у NpdCandidate
    нет реальной registration_date (ФНС API урезали в апреле 2026 — см.
    Инцидент 19). Pack 28.5 в roadmap заменит этот fallback на реальную
    дату через бинпоиск или dt_support_begin.
    """
    if submission_date:
        base = submission_date
    elif contract_sign_date:
        base = contract_sign_date + timedelta(days=90)
    else:
        base = date.today() + timedelta(days=30)

    days_before = rng.randint(120, 210)
    return base - timedelta(days=days_before)


# ===========================================================================
# Главный entry point
# ===========================================================================


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

    Pack 28 Часть 2: НОВАЯ архитектура.
    - Источник: npd_candidate (а не self_employed_registry)
    - Если verified=0 в регионе → бросаем NeedsRefillError
    - Tier-fallback УБРАН — endpoint решает что делать (lazy refill task)
    - Адрес генерируется под фактический регион (как раньше)
    - registration_date берётся из candidate если есть, иначе синтетическая

    Raises:
        NeedsRefillError: если в пуле verified=0 для региона
    """
    rng = random.Random(seed)

    # ----- 1. Выбираем целевой регион -----
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
        "suggest_inn_for_applicant: target region=%s (code=%s, source=%s)",
        requested_region.name,
        requested_code,
        requested_pick.source,
    )

    # ----- 2. Подбор verified-кандидата (БЕЗ tier-fallback) -----
    candidate = pick_verified_candidate_for_region(
        session, requested_code, seed=seed,
    )
    if candidate is None:
        # Пул пуст — endpoint должен стартануть refill task
        raise NeedsRefillError(
            region_code=requested_code,
            region_name=requested_region.name,
        )

    # ----- 3. Адрес генерируется под актуальный регион кандидата -----
    actual_region_code = candidate.region_code or requested_code
    if actual_region_code != requested_code:
        # Это НЕ должно случаться в Pack 28 Часть 2 (мы строго фильтруем),
        # но на всякий случай логируем
        log.warning(
            "[pipeline] candidate region_code=%s != requested=%s",
            actual_region_code, requested_code,
        )

    actual_region = get_region_by_code(session, actual_region_code)
    if actual_region is None:
        actual_region = requested_region  # fallback на запрошенный

    # Если у applicant'а уже есть home_address в том же регионе — оставляем
    keep_existing_address = (
        bool(applicant.home_address)
        and actual_region_code == requested_code
        and requested_pick.source == "home_address"
    )
    if keep_existing_address:
        home_address = applicant.home_address
        kladr_code = applicant.inn_kladr_code or _make_subject_kladr(actual_region_code)
        log.info("[pipeline] keeping existing applicant.home_address")
    else:
        target_kladr = _resolve_known_kladr(
            actual_region.kladr_code, actual_region_code,
        )
        addr = generate_address(target_kladr, rng)
        home_address = addr.full
        kladr_code = addr.kladr_code
        log.info(
            "[pipeline] generated new address for region=%s kladr=%s",
            actual_region.name, target_kladr,
        )

    # ----- 4. Дата НПД — РЕАЛЬНАЯ из candidate, fallback на синтетическую -----
    if candidate.registration_date:
        inn_reg_date = candidate.registration_date
        log.info("[pipeline] using REAL registration_date=%s from npd_candidate",
                 inn_reg_date)
    else:
        # Защитный getattr на случай если в Application нет submission_date
        # (по PROJECT_STATE поле есть с Pack 18.3.4, но fail-safe не помешает)
        submission_date = (
            getattr(application, "submission_date", None) if application else None
        )
        contract_sign_date = (
            getattr(application, "contract_sign_date", None) if application else None
        )
        inn_reg_date = _synthetic_npd_registration_date(
            submission_date=submission_date,
            contract_sign_date=contract_sign_date,
            rng=rng,
        )
        log.info(
            "[pipeline] using SYNTHETIC registration_date=%s "
            "(candidate.registration_date is None — Pack 28.5 will fix)",
            inn_reg_date,
        )

    # ----- 5. Сборка результата -----
    suggestion = InnSuggestion(
        inn=candidate.inn,
        full_name=(candidate.full_name or "").strip() or "—",
        home_address=home_address,
        kladr_code=kladr_code,
        region_name=actual_region.name,
        region_code=actual_region_code,
        inn_registration_date=inn_reg_date,
        source=requested_pick.source,
        # Pack 28 Часть 2: fallback больше не нужен
        fallback_used=False,
        requested_region_name=None,
        requested_region_code=None,
        fallback_reason=None,
    )

    log.info(
        "suggest_inn_for_applicant: SUCCESS inn=%s region=%s npd_date=%s",
        suggestion.inn, suggestion.region_name, suggestion.inn_registration_date,
    )
    return suggestion


# ===========================================================================
# Helpers — оставлены без изменений (использовались в старом коде)
# ===========================================================================


def _make_subject_kladr(region_code: str) -> str:
    """Заглушка KLADR уровня субъекта: '77' + 11 нулей."""
    code = (region_code or "00").zfill(2)[:2]
    return code + "0" * 11


def _resolve_known_kladr(region_kladr: Optional[str], region_code: str) -> str:
    """
    KNOWN_REGIONS в kladr_address_gen.py содержит точные KLADR'ы городов.
    Region.kladr_code в БД может быть любым из этих, либо общим для субъекта.

    Логика:
    1. Если region.kladr_code напрямую в KNOWN_REGIONS — используем его.
    2. Иначе ищем в KNOWN_REGIONS любой kladr с тем же 2-значным префиксом.
    3. Иначе — заглушка _make_subject_kladr.
    """
    if region_kladr and region_kladr in KNOWN_REGIONS:
        return region_kladr

    prefix = (region_code or "").strip().zfill(2)[:2]
    for kladr in KNOWN_REGIONS.keys():
        if kladr.startswith(prefix):
            return kladr

    return _make_subject_kladr(region_code)


# === Pack 28.2 backward compatibility ===
# Алиас для обратной совместимости с inn_generator/__init__.py и любым
# внешним кодом который ловит "except InnPipelineError". В Pack 28.2
# исключение переименовано в NeedsRefillError (более точное имя — это
# не ошибка, а сигнал endpoint'у что надо стартовать lazy refill task).
InnPipelineError = NeedsRefillError


# === Pack 17.x backward compat ===
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
