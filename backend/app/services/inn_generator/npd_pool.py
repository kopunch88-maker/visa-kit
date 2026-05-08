"""
Pack 28 (07.05.2026) + Pack 28.2 (08.05.2026): сервис управления пулом
чистых самозанятых.

ENTRY POINTS:
    refill_pool_for_region(session, region_code, target=30)
        — низкоуровневый refill (без task) для CLI и smoke-тестов
    refill_pool_for_region_with_progress(session, task_id, region_code, target=5)
        — refill с обновлением прогресса в NpdRefillTask
    revalidate_verified_candidates(session, task_id=None, max_age_days=7)
        — перепроверяет все verified, помечает как rejected_* если статус ушёл
    run_global_refill(session, task_id, regions, target_per_region, revalidate_first)
        — комбо: ревалидация + добивка по списку регионов

ЛОГИКА REFILL ОДНОГО РЕГИОНА:
    1. RmspClient.search_multiple_pages(kladr_for_region, max=fetch_count)
    2. Дедуп vs БД: если ИНН уже есть в npd_candidate — пропуск
    3. Создаём pending-записи в БД
    4. Для каждого pending: EgrulChecker.is_in_egrul(inn)
       True  → status='rejected_ip'
       False → дальше
    5. NpdStatusChecker.check(inn)
       is_active=False → status='rejected_inactive'
       is_active=True  → status='verified',
                          registration_date = result.registration_date

ОГРАНИЧЕНИЯ ПО СКОРОСТИ:
    - rmsp-pp: throttle 0.5 сек, max 100 на страницу
    - egrul.nalog.ru: 200+ запросов без бана, throttle 0.3
    - npd.nalog.ru: жёсткий rate limit 2 req/min — 31 сек между запросами

KEY_REGIONS:
    Список ключевых регионов для глобального refill (cron + кнопка "Обновить
    весь пул"). Москва, СПб, краснодарский край, Ростов, Свердловск, Татарстан,
    Новосибирск — где самые большие диаспоры и подача документов.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import (
    NpdCandidate,
    NpdPoolRefillResult,
    NpdPoolStats,
    NpdRefillTask,
)
from app.services.inn_generator.egrul_check import (
    EgrulCaptchaRequired,
    EgrulChecker,
    EgrulError,
)
from app.services.inn_generator.npd_status import (
    NpdStatusChecker,
    NpdStatusError,
)
from app.services.inn_generator.rmsp_client import RmspClient, RmspError

log = logging.getLogger(__name__)


# ===========================================================================
# Ключевые регионы для глобального refill
# ===========================================================================
# Порядок важен — ставим Москву первой т.к. там самый большой пул и там
# больше всего клиентов. Если cron упадёт на середине — Москва уже обновлена.
KEY_REGIONS: tuple[str, ...] = (
    "77",  # Москва
    "78",  # Санкт-Петербург
    "23",  # Краснодарский край
    "61",  # Ростовская область
    "66",  # Свердловская область
    "16",  # Татарстан
    "54",  # Новосибирская область
    "50",  # Московская область
)

# Pack 28.5: лимит refine-задач за один cron (защита от бесконечного бинпоиска).
# 20 × ~7 мин = ~2.5 часа max на этап refine_pending_dates.
# Остальные verified без даты доуточнятся в следующий cron.
REFINE_DATE_PER_CRON_LIMIT = 20


# ===========================================================================
# Утилиты
# ===========================================================================


def _region_code_to_subject_kladr(region_code: str) -> str:
    """'23' → '2300000000000' (Краснодарский край в целом)."""
    code = (region_code or "").strip().zfill(2)[:2]
    return code + "0" * 11


def _update_task_progress(
    session: Session,
    task_id: Optional[int],
    *,
    progress_text: Optional[str] = None,
    progress_current: Optional[int] = None,
    progress_total: Optional[int] = None,
) -> None:
    """
    Обновляет прогресс задачи. Не падает если task_id=None или task не найден.
    Делает session.commit() — поэтому фронт сразу видит обновление при поллинге.
    """
    if task_id is None:
        return
    try:
        task = session.get(NpdRefillTask, task_id)
        if not task:
            return
        if progress_text is not None:
            task.progress_text = progress_text[:255]
        if progress_current is not None:
            task.progress_current = progress_current
        if progress_total is not None:
            task.progress_total = progress_total
        session.add(task)
        session.commit()
    except Exception:
        # Не валим refill из-за ошибки обновления прогресса
        log.exception("[npd_pool] failed to update task progress (task_id=%s)", task_id)
        try:
            session.rollback()
        except Exception:
            pass


# ===========================================================================
# Низкоуровневые helper'ы
# ===========================================================================


async def _fetch_rmsp_candidates(kladr_code: str, target: int) -> list[dict]:
    """Достаёт кандидатов из rmsp-pp.nalog.ru через RmspClient."""
    log.info("[npd_pool] fetching %d candidates from rmsp-pp for kladr=%s",
             target, kladr_code)
    async with RmspClient() as client:
        candidates = await client.search_multiple_pages(
            kladr_code=kladr_code,
            max_candidates=target,
            page_size=100,
            max_pages=10,
            delay_between_pages=0.5,
            strict_region_filter=True,
        )

    out = []
    for c in candidates:
        out.append({
            "inn": c.inn,
            "full_name": c.full_name,
            "region_code": c.region_code,
            "dt_support_begin": c.dt_support_begin,
            "rmsp_pp_id": c.raw.get("id") if c.raw else None,
        })
    log.info("[npd_pool] rmsp-pp returned %d candidates", len(out))
    return out


def _filter_already_in_db(
    session: Session, candidates: list[dict],
) -> tuple[list[dict], int]:
    """Отсекает ИНН которые уже есть в npd_candidate."""
    inns = [c["inn"] for c in candidates]
    if not inns:
        return [], 0

    existing = session.exec(
        select(NpdCandidate.inn).where(NpdCandidate.inn.in_(inns))  # type: ignore[attr-defined]
    ).all()
    existing_set = set(existing)

    new = [c for c in candidates if c["inn"] not in existing_set]
    return new, len(existing_set)


def _insert_pending(session: Session, new_candidates: list[dict]) -> list[NpdCandidate]:
    """Вставляет новых кандидатов со статусом 'pending'."""
    from datetime import date as _date

    inserted: list[NpdCandidate] = []
    for c in new_candidates:
        support_date = None
        raw_date = c.get("dt_support_begin")
        if raw_date:
            try:
                date_str = raw_date.split(" ")[0]
                day, month, year = date_str.split(".")
                support_date = _date(int(year), int(month), int(day))
            except (ValueError, AttributeError):
                pass

        cand = NpdCandidate(
            inn=c["inn"],
            full_name=(c.get("full_name") or "").strip() or None,
            region_code=c["region_code"],
            rmsp_pp_id=c.get("rmsp_pp_id"),
            rmsp_pp_support_date=support_date,
            status="pending",
            fetched_at=datetime.utcnow(),
        )
        session.add(cand)
        inserted.append(cand)

    session.commit()
    log.info("[npd_pool] inserted %d pending candidates", len(inserted))
    return inserted


async def _verify_candidate(
    inn: str,
    egrul: EgrulChecker,
    npd: NpdStatusChecker,
) -> dict:
    """Верифицирует один ИНН через EGRUL+NPD. Возвращает dict с обновлениями."""
    out = {
        "egrul_found": None,
        "egrul_checked_at": None,
        "npd_active": None,
        "npd_checked_at": None,
        "registration_date": None,
        "verified_at": None,
        "rejection_reason": None,
    }

    # Шаг 1: EGRUL
    try:
        in_egrul = await egrul.is_in_egrul(inn)
        out["egrul_found"] = in_egrul
        out["egrul_checked_at"] = datetime.utcnow()
    except EgrulCaptchaRequired:
        raise
    except EgrulError as e:
        log.warning("[npd_pool] EGRUL error for %s: %s", inn, e)
        out["status"] = "rejected_other"
        out["rejection_reason"] = f"EGRUL error: {e}"
        return out

    if in_egrul:
        log.info("[npd_pool] %s found in EGRUL (open IP) — reject", inn)
        out["status"] = "rejected_ip"
        out["rejection_reason"] = "Found in EGRUL/EGRIP"
        return out

    # Шаг 2: NPD
    try:
        result = await npd.check(inn=inn)
        out["npd_active"] = result.is_active
        out["npd_checked_at"] = datetime.utcnow()
    except NpdStatusError as e:
        log.warning("[npd_pool] NPD error for %s: %s", inn, e)
        out["status"] = "rejected_other"
        out["rejection_reason"] = f"NPD error: {e}"
        return out

    if not result.is_active:
        log.info("[npd_pool] %s not active in NPD — reject", inn)
        out["status"] = "rejected_inactive"
        out["rejection_reason"] = result.message or "NPD reports not active"
        return out

    # Успех
    out["status"] = "verified"
    out["registration_date"] = result.registration_date
    out["verified_at"] = datetime.utcnow()
    log.info(
        "[npd_pool] %s VERIFIED, registration_date=%s",
        inn, result.registration_date,
    )
    return out


def _apply_verification_to_candidate(cand: NpdCandidate, updates: dict) -> None:
    """Применяет результат верификации к модели (без commit)."""
    for key, value in updates.items():
        if hasattr(cand, key) and value is not None:
            setattr(cand, key, value)
    if "status" in updates:
        cand.status = updates["status"]


# ===========================================================================
# Основной refill одного региона (LOW-LEVEL, без task)
# ===========================================================================


async def refill_pool_for_region(
    session: Session,
    region_code: str,
    target: int = 30,
    *,
    fetch_multiplier: float = 2.5,
) -> NpdPoolRefillResult:
    """
    Низкоуровневый refill — для CLI и smoke-тестов. Без отслеживания прогресса.

    Args:
        session: активная Session к БД
        region_code: 2-значный код субъекта ('77', '23', ...)
        target: сколько verified кандидатов хотим получить
        fetch_multiplier: сколько ИНН тянуть из rmsp-pp на 1 ожидаемого
            verified (по разведке: 2.5x безопасный default).

    Returns:
        NpdPoolRefillResult со статистикой.
    """
    return await _refill_one_region_inner(
        session=session,
        task_id=None,
        region_code=region_code,
        target=target,
        fetch_multiplier=fetch_multiplier,
        progress_offset=0,
        progress_total=target,
    )


# ===========================================================================
# Refill одного региона С ПРОГРЕССОМ (для inn-suggest lazy task)
# ===========================================================================


async def refill_pool_for_region_with_progress(
    session: Session,
    task_id: int,
    region_code: str,
    target: int = 5,
    *,
    fetch_multiplier: float = 2.5,
) -> NpdPoolRefillResult:
    """
    Refill одного региона с обновлением NpdRefillTask.

    Используется когда менеджер жмёт "Подобрать ИНН" в регионе где пул пуст.
    Фронт показывает спиннер + прогресс из task'а.
    """
    # Помечаем task как running
    _update_task_progress(
        session,
        task_id,
        progress_text=f"Запрос rmsp-pp.nalog.ru (регион {region_code})...",
        progress_current=0,
        progress_total=target,
    )

    result = await _refill_one_region_inner(
        session=session,
        task_id=task_id,
        region_code=region_code,
        target=target,
        fetch_multiplier=fetch_multiplier,
        progress_offset=0,
        progress_total=target,
    )

    # Успех / частичный успех — task обновится в _refill_one_region_inner
    return result


# ===========================================================================
# Внутренняя реализация refill
# ===========================================================================


async def _refill_one_region_inner(
    *,
    session: Session,
    task_id: Optional[int],
    region_code: str,
    target: int,
    fetch_multiplier: float,
    progress_offset: int,
    progress_total: int,
) -> NpdPoolRefillResult:
    """
    Реальная реализация refill — общая для CLI и для task.

    progress_offset / progress_total — для глобального refill, чтобы прогресс
    показывал X из Y где Y > target_per_region (всего регионов × target).
    """
    t_start = time.time()
    result = NpdPoolRefillResult(region_code=region_code)

    # Pack 28.6 fix2: компенсируем кандидатов которые уже в БД (любого статуса).
    # Иначе search_multiple_pages вернёт первые fetch_count уникальных и они окажутся
    # все уже виденными, после _filter_already_in_db останется 0 новых.
    already_in_db_count = len(session.exec(
        select(NpdCandidate).where(NpdCandidate.region_code == region_code)
    ).all())
    fetch_count = max(int(target * fetch_multiplier) + already_in_db_count, 10)
    kladr = _region_code_to_subject_kladr(region_code)

    log.info(
        "[npd_pool] refill region=%s target=%d (fetch=%d, kladr=%s)",
        region_code, target, fetch_count, kladr,
    )

    # ----- Шаг 1: rmsp-pp -----
    _update_task_progress(
        session, task_id,
        progress_text=f"Поиск кандидатов в rmsp-pp (регион {region_code})...",
    )
    try:
        rmsp_candidates = await _fetch_rmsp_candidates(kladr, fetch_count)
    except RmspError as e:
        log.error("[npd_pool] RmspError: %s", e)
        result.errors += 1
        result.elapsed_seconds = time.time() - t_start
        return result

    result.rmsp_fetched = len(rmsp_candidates)

    # ----- Шаг 2: дедуп -----
    new_candidates, dup_count = _filter_already_in_db(session, rmsp_candidates)
    result.duplicates_skipped = dup_count
    log.info("[npd_pool] %d new, %d dups", len(new_candidates), dup_count)

    if not new_candidates:
        result.elapsed_seconds = time.time() - t_start
        _update_task_progress(
            session, task_id,
            progress_text=f"Все кандидаты уже в пуле (регион {region_code})",
        )
        return result

    # ----- Шаг 3: вставка как pending -----
    pending = _insert_pending(session, new_candidates)

    # ----- Шаг 4: верификация -----
    async with EgrulChecker() as egrul, NpdStatusChecker() as npd:
        for idx, cand in enumerate(pending):
            if result.verified_added >= target:
                log.info(
                    "[npd_pool] target=%d reached, leaving %d candidates pending",
                    target, len(pending) - idx,
                )
                break

            _update_task_progress(
                session, task_id,
                progress_text=(
                    f"Проверка {cand.inn} в ЕГРЮЛ + ФНС НПД "
                    f"(регион {region_code}, найдено {result.verified_added}/{target})..."
                ),
                progress_current=progress_offset + result.verified_added,
            )

            try:
                updates = await _verify_candidate(cand.inn, egrul, npd)
            except EgrulCaptchaRequired:
                log.warning("[npd_pool] CAPTCHA — pause 60s and retry once")
                await asyncio.sleep(60)
                try:
                    updates = await _verify_candidate(cand.inn, egrul, npd)
                except EgrulCaptchaRequired:
                    log.error("[npd_pool] CAPTCHA again — abort refill")
                    result.errors += 1
                    break
            except Exception as e:
                log.exception("[npd_pool] unexpected error verifying %s: %s",
                              cand.inn, e)
                result.errors += 1
                continue

            _apply_verification_to_candidate(cand, updates)
            session.add(cand)
            session.commit()

            status_v = updates.get("status", "rejected_other")
            if status_v == "verified":
                result.verified_added += 1
            elif status_v == "rejected_ip":
                result.egrul_rejected += 1
            elif status_v == "rejected_inactive":
                result.npd_rejected += 1
            else:
                result.errors += 1

    result.elapsed_seconds = time.time() - t_start
    log.info(
        "[npd_pool] refill DONE region=%s verified=%d ip=%d inactive=%d "
        "errors=%d in %.1f sec",
        region_code,
        result.verified_added,
        result.egrul_rejected,
        result.npd_rejected,
        result.errors,
        result.elapsed_seconds,
    )

    _update_task_progress(
        session, task_id,
        progress_text=(
            f"Регион {region_code} готов: добавлено {result.verified_added} verified"
        ),
        progress_current=progress_offset + result.verified_added,
    )

    return result


# ===========================================================================
# Ревалидация существующих verified
# ===========================================================================


async def revalidate_verified_candidates(
    session: Session,
    task_id: Optional[int] = None,
    *,
    max_age_days: int = 7,
    limit: Optional[int] = None,
) -> dict:
    """
    Перепроверяет всех verified-кандидатов которые не проверялись `max_age_days`.
    Если кто-то из них:
      - открыл ИП → status='rejected_ip'
      - снялся с НПД → status='rejected_inactive'
      - всё ещё чист → обновляем npd_checked_at, остаётся 'verified'

    Returns:
        {'total': X, 'invalidated': Y, 'still_valid': Z}
    """
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    stmt = (
        select(NpdCandidate)
        .where(NpdCandidate.status == "verified")
        .where(
            (NpdCandidate.npd_checked_at == None)  # noqa: E711
            | (NpdCandidate.npd_checked_at < cutoff)
        )
        .order_by(NpdCandidate.npd_checked_at)  # type: ignore[arg-type]
    )
    if limit:
        stmt = stmt.limit(limit)

    candidates = session.exec(stmt).all()
    total = len(candidates)
    invalidated = 0
    still_valid = 0

    log.info("[npd_pool] revalidating %d verified candidates (cutoff=%s)",
             total, cutoff.isoformat())

    if total == 0:
        return {"total": 0, "invalidated": 0, "still_valid": 0}

    _update_task_progress(
        session, task_id,
        progress_text=f"Ревалидация {total} verified кандидатов...",
    )

    async with EgrulChecker() as egrul, NpdStatusChecker() as npd:
        for idx, cand in enumerate(candidates):
            _update_task_progress(
                session, task_id,
                progress_text=(
                    f"Ревалидация {idx + 1}/{total}: {cand.inn} "
                    f"(invalidated: {invalidated})"
                ),
            )

            try:
                updates = await _verify_candidate(cand.inn, egrul, npd)
            except EgrulCaptchaRequired:
                log.warning("[npd_pool] CAPTCHA during revalidate — pause 60s")
                await asyncio.sleep(60)
                try:
                    updates = await _verify_candidate(cand.inn, egrul, npd)
                except EgrulCaptchaRequired:
                    log.error("[npd_pool] CAPTCHA persists — abort revalidate")
                    break
            except Exception as e:
                log.exception("[npd_pool] revalidate error for %s: %s",
                              cand.inn, e)
                continue

            new_status = updates.get("status", "rejected_other")
            if new_status == "verified":
                # Всё ещё чист — обновляем только timestamp
                cand.npd_checked_at = datetime.utcnow()
                if updates.get("egrul_checked_at"):
                    cand.egrul_checked_at = updates["egrul_checked_at"]
                session.add(cand)
                still_valid += 1
            else:
                # Стал нечист — переводим в rejected_*
                _apply_verification_to_candidate(cand, updates)
                session.add(cand)
                invalidated += 1
                log.warning(
                    "[npd_pool] revalidate: %s → %s (was verified)",
                    cand.inn, new_status,
                )

            session.commit()

    log.info(
        "[npd_pool] revalidate DONE total=%d invalidated=%d still_valid=%d",
        total, invalidated, still_valid,
    )
    return {
        "total": total,
        "invalidated": invalidated,
        "still_valid": still_valid,
    }


# ===========================================================================
# Глобальный refill (cron + кнопка "Обновить весь пул")
# ===========================================================================


async def _refine_pending_dates(
    session,
    task,
    *,
    limit: int = REFINE_DATE_PER_CRON_LIMIT,
) -> int:
    """
    Pack 28.5: для до `limit` verified-кандидатов без registration_date
    запускает бинпоиск и сохраняет реальную дату.

    Используется в run_global_refill после revalidate + refill.

    Возвращает: сколько дат было успешно найдено и сохранено.
    """
    from datetime import date as _date
    from .npd_date_finder import binary_search_registration_date
    from .npd_status import NpdStatusChecker, NpdStatusError
    from sqlmodel import select
    from app.models import NpdCandidate

    candidates = session.exec(
        select(NpdCandidate)
        .where(NpdCandidate.status == "verified")
        .where(NpdCandidate.registration_date.is_(None))
        .order_by(NpdCandidate.fetched_at.asc())
        .limit(limit)
    ).all()

    if not candidates:
        log.info("[refine_dates] no candidates need refinement")
        return 0

    log.info(
        f"[refine_dates] starting binary search for {len(candidates)} "
        f"candidates (limit={limit})"
    )

    refined = 0
    async with NpdStatusChecker() as checker:
        for i, cand in enumerate(candidates, 1):
            task.progress_text = (
                f"Уточняю даты НПД: {i}/{len(candidates)} ({cand.inn})"
            )
            session.add(task)
            session.commit()

            try:
                reg_date = await binary_search_registration_date(
                    checker,
                    cand.inn,
                    upper_bound=cand.rmsp_pp_support_date or _date.today(),
                )
                if reg_date:
                    fresh = session.get(NpdCandidate, cand.inn)
                    if fresh:
                        fresh.registration_date = reg_date
                        session.add(fresh)
                        session.commit()
                        refined += 1
                        log.info(f"[refine_dates] {cand.inn}: registration_date = {reg_date}")
                else:
                    log.warning(f"[refine_dates] {cand.inn} returned None")
            except NpdStatusError as e:
                log.warning(f"[refine_dates] {cand.inn}: {e}")
            except Exception:
                log.exception(f"[refine_dates] {cand.inn}: unexpected error")

    log.info(f"[refine_dates] done: {refined}/{len(candidates)} dates refined")
    return refined


async def run_global_refill(
    session: Session,
    task_id: int,
    *,
    regions: Optional[list[str]] = None,
    target_per_region: int = 5,
    revalidate_first: bool = True,
) -> None:
    """
    Полный цикл: ревалидация + добивка пула по списку регионов.

    Обновляет NpdRefillTask на каждом шаге. По окончании ставит status='done'
    или 'failed'. Все ошибки логируются но не прерывают весь refill — каждый
    регион независим.
    """
    regions = regions or list(KEY_REGIONS)
    t_start = time.time()

    task = session.get(NpdRefillTask, task_id)
    if not task:
        log.error("[npd_pool] task_id=%s not found", task_id)
        return

    task.status = "running"
    task.started_at = datetime.utcnow()
    task.progress_text = "Старт глобального refill..."
    task.progress_total = len(regions) * target_per_region
    task.progress_current = 0
    session.add(task)
    session.commit()

    try:
        # ----- Шаг 0: ревалидация -----
        if revalidate_first:
            reval_result = await revalidate_verified_candidates(
                session, task_id=task_id, max_age_days=7,
            )
            task.revalidated_total = reval_result["total"]
            task.revalidated_invalidated = reval_result["invalidated"]
            session.add(task)
            session.commit()

        # ----- Шаг 1: добивка по регионам -----
        cumulative_verified = 0
        for region_idx, region_code in enumerate(regions):
            # Сколько уже verified в этом регионе?
            current_verified = session.exec(
                select(NpdCandidate)
                .where(NpdCandidate.region_code == region_code)
                .where(NpdCandidate.status == "verified")
            ).all()
            current_count = len(current_verified)

            need = max(0, target_per_region - current_count)

            _update_task_progress(
                session, task_id,
                progress_text=(
                    f"Регион {region_code} ({region_idx + 1}/{len(regions)}): "
                    f"{current_count} verified, нужно ещё {need}"
                ),
                progress_current=cumulative_verified,
            )

            if need == 0:
                log.info(
                    "[npd_pool] region=%s already has %d verified, skip",
                    region_code, current_count,
                )
                cumulative_verified += target_per_region  # уже укомплектован
                continue

            try:
                region_result = await _refill_one_region_inner(
                    session=session,
                    task_id=task_id,
                    region_code=region_code,
                    target=need,
                    fetch_multiplier=2.5,
                    progress_offset=cumulative_verified,
                    progress_total=task.progress_total,
                )
                task.verified_added += region_result.verified_added
                task.egrul_rejected += region_result.egrul_rejected
                task.npd_rejected += region_result.npd_rejected
                cumulative_verified += region_result.verified_added
                session.add(task)
                session.commit()
            except Exception as e:
                log.exception(
                    "[npd_pool] region=%s refill failed: %s", region_code, e,
                )
                # Продолжаем со следующим регионом
                continue

        # ----- Финал -----
        # Pack 28.5: уточняем даты регистрации НПД у verified без даты
        task.progress_text = "Уточняю даты регистрации НПД..."
        session.add(task)
        session.commit()
        try:
            refined = await _refine_pending_dates(session, task)
            log.info(f"[run_global_refill] refined {refined} dates")
        except Exception:
            log.exception("[run_global_refill] refine_pending_dates failed")
            # не валим весь cron из-за refine — это опциональный шаг

        task.status = "done"
        task.finished_at = datetime.utcnow()
        elapsed = time.time() - t_start
        task.progress_text = (
            f"Готово за {elapsed:.0f} сек. "
            f"Добавлено verified: {task.verified_added}. "
            f"Ревалидация: {task.revalidated_total} проверено, "
            f"{task.revalidated_invalidated} переведено в rejected."
        )
        task.progress_current = task.progress_total
        session.add(task)
        session.commit()
        log.info(
            "[npd_pool] global refill DONE task_id=%s elapsed=%.1fs",
            task_id, elapsed,
        )
    except Exception as e:
        log.exception("[npd_pool] global refill task_id=%s FAILED", task_id)
        task.status = "failed"
        task.error = f"{type(e).__name__}: {e}"[:1024]
        task.finished_at = datetime.utcnow()
        session.add(task)
        session.commit()
        raise


# ===========================================================================
# Lazy refill для inn-suggest (одиночный регион, target=5)
# ===========================================================================


async def run_lazy_region_refill(
    session: Session,
    task_id: int,
    region_code: str,
    target: int = 5,
) -> None:
    """
    Ленивый refill одного региона — стартует когда менеджер жмёт "Подобрать
    ИНН" в регионе где verified=0. По окончании в task.result_inn попадает
    ИНН первого verified кандидата (фронт может его сразу взять).
    """
    task = session.get(NpdRefillTask, task_id)
    if not task:
        log.error("[npd_pool] task_id=%s not found (lazy)", task_id)
        return

    task.status = "running"
    task.started_at = datetime.utcnow()
    task.progress_text = f"Поиск чистого самозанятого (регион {region_code})..."
    task.progress_total = target
    session.add(task)
    session.commit()

    try:
        result = await refill_pool_for_region_with_progress(
            session=session,
            task_id=task_id,
            region_code=region_code,
            target=target,
        )

        task.verified_added = result.verified_added
        task.egrul_rejected = result.egrul_rejected
        task.npd_rejected = result.npd_rejected

        if result.verified_added > 0:
            # Берём первый verified из этого региона как hint
            first_verified = session.exec(
                select(NpdCandidate)
                .where(NpdCandidate.region_code == region_code)
                .where(NpdCandidate.status == "verified")
                .order_by(NpdCandidate.verified_at.desc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            if first_verified:
                task.result_inn = first_verified.inn
                task.result_region_code = first_verified.region_code

            task.status = "done"
            task.progress_text = (
                f"Готово. Найдено {result.verified_added} чистых "
                f"самозанятых в регионе {region_code}."
            )
            task.progress_current = result.verified_added
        else:
            task.status = "failed"
            task.error = (
                f"Не удалось найти чистого самозанятого в регионе "
                f"{region_code}. Проверено: rmsp_fetched={result.rmsp_fetched}, "
                f"egrul_rejected={result.egrul_rejected}, "
                f"npd_rejected={result.npd_rejected}."
            )

        task.finished_at = datetime.utcnow()
        session.add(task)
        session.commit()
        log.info(
            "[npd_pool] lazy refill DONE task_id=%s region=%s verified=%d",
            task_id, region_code, result.verified_added,
        )
    except Exception as e:
        log.exception("[npd_pool] lazy refill task_id=%s FAILED", task_id)
        task.status = "failed"
        task.error = f"{type(e).__name__}: {e}"[:1024]
        task.finished_at = datetime.utcnow()
        session.add(task)
        session.commit()
        raise


# ===========================================================================
# Статистика пула
# ===========================================================================


def get_pool_stats(session: Session) -> NpdPoolStats:
    """Сводная статистика по npd_candidate для admin UI и CLI."""
    from sqlalchemy import func

    total = session.exec(
        select(func.count()).select_from(NpdCandidate)  # type: ignore[arg-type]
    ).one()
    if isinstance(total, tuple):
        total = total[0]

    by_status_rows = session.exec(
        select(NpdCandidate.status, func.count())  # type: ignore[arg-type]
        .group_by(NpdCandidate.status)
    ).all()
    by_status: dict[str, int] = {}
    for row in by_status_rows:
        if isinstance(row, tuple):
            status, count = row
        else:
            status, count = row.status, row.count
        by_status[status or "unknown"] = int(count)

    by_region_rows = session.exec(
        select(NpdCandidate.region_code, func.count())  # type: ignore[arg-type]
        .where(NpdCandidate.status == "verified")
        .group_by(NpdCandidate.region_code)
    ).all()
    by_region: dict[str, int] = {}
    for row in by_region_rows:
        if isinstance(row, tuple):
            rcode, count = row
        else:
            rcode, count = row.region_code, row.count
        by_region[rcode or "??"] = int(count)

    last_row = session.exec(
        select(NpdCandidate.fetched_at, NpdCandidate.region_code)  # type: ignore[arg-type]
        .order_by(NpdCandidate.fetched_at.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()
    last_fetched_at: Optional[datetime] = None
    last_region: Optional[str] = None
    if last_row:
        if isinstance(last_row, tuple):
            last_fetched_at, last_region = last_row
        else:
            last_fetched_at = getattr(last_row, "fetched_at", None)
            last_region = getattr(last_row, "region_code", None)

    return NpdPoolStats(
        total=int(total),
        by_status=by_status,
        by_region_verified=by_region,
        last_refill_at=last_fetched_at,
        last_refill_region=last_region,
    )
