"""
Pack 28.5 — бинпоиск даты регистрации НПД через FNS API.

Использует существующий NpdStatusChecker (rate-limit 31 сек/запрос).

Алгоритм:
  left  = 2019-01-01 (старт 422-ФЗ, более ранние даты ФНС возвращает 422)
  right = today
  while right - left > 1 day:
      mid = left + (right - left) // 2
      status_on_mid = api(inn, mid)
      if status_on_mid: right = mid    # был НПД, регистрация раньше
      else:             left = mid     # не был, регистрация позже
  return right                         # точная дата

Сложность: log₂(7.5лет × 365) ≈ 11-12 запросов на ИНН × 31 сек = ~6 мин/ИНН.

Прогресс-callback вызывается перед КАЖДЫМ запросом — это позволяет UI
показывать актуальный статус «Шаг 5/12 — проверяю 2024-01-15».

Тестировано прототипом 08.05.2026 на ИНН 542907257032 — нашло точную дату
2024-03-29 (rmsp_pp_support_date был 2024-04-16, отставание 18 дней).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Awaitable, Callable, Optional

from .npd_status import NpdStatusChecker, NpdStatusError

log = logging.getLogger(__name__)


# Жёсткий нижний предел — 422-ФЗ от 27.11.2018, действует с 01.01.2019.
# Более ранние даты ФНС возвращает HTTP 422 Unprocessable Entity.
NPD_LAW_START = date(2019, 1, 1)


# Тип callback для прогресса. Может быть синхронным или асинхронным.
# (step, total_estimated, current_left, current_right, mid_being_checked)
ProgressCallback = Callable[[int, int, date, date, date], Awaitable[None]]


# Оценка количества шагов для UI.
# log2(7.5 лет × 365) ≈ 11.4. Но добавляем 2 sanity-проверки (upper и lower).
ESTIMATED_TOTAL_STEPS = 14


async def binary_search_registration_date(
    checker: NpdStatusChecker,
    inn: str,
    *,
    upper_bound: Optional[date] = None,
    lower_bound: Optional[date] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[date]:
    """
    Бинпоиск точной даты регистрации НПД для ИНН.

    Args:
        checker: уже открытый NpdStatusChecker (через async with).
            Класс-уровневый rate-limiter гарантирует 31 сек между запросами.
        inn: 12-значный ИНН физлица.
        upper_bound: гарантированно ПОСЛЕ регистрации (по умолчанию today).
            Можно сузить если знаем верхнюю оценку (например rmsp_support_date).
        lower_bound: гарантированно ДО регистрации (по умолчанию 2019-01-01).
        on_progress: optional async callback с (step, total, left, right, mid).
            Позволяет в UI показывать «Шаг N/14 — проверяю дату X».

    Returns:
        Точная дата регистрации НПД, или None если ИНН не НПД на upper_bound
        (значит человек снялся с учёта или вообще не был самозанятым).

    Raises:
        NpdStatusError: при HTTP-ошибках (кроме 422 на середине бинпоиска,
            где 422 трактуется как «слишком ранняя дата» и left := mid).
    """
    if upper_bound is None:
        upper_bound = date.today()
    if lower_bound is None:
        lower_bound = NPD_LAW_START

    # Защита от очевидных ошибок
    if lower_bound >= upper_bound:
        raise ValueError(
            f"lower_bound ({lower_bound}) must be strictly before "
            f"upper_bound ({upper_bound})"
        )

    log.info(
        f"[binary_search] inn={inn} range=[{lower_bound} … {upper_bound}]"
    )

    step = 0

    # === Sanity 1: ИНН действительно НПД на upper_bound?
    step += 1
    if on_progress:
        await on_progress(step, ESTIMATED_TOTAL_STEPS, lower_bound, upper_bound, upper_bound)
    upper_check = await checker.check(inn, request_date=upper_bound)
    if not upper_check.is_active:
        log.warning(
            f"[binary_search] inn={inn} not active on {upper_bound} — "
            f"binary search impossible"
        )
        return None
    log.info(
        f"[binary_search] inn={inn} active on {upper_bound}, "
        f"имя: {upper_check.full_name or '(не возвращено)'}"
    )

    # === Sanity 2: на lower_bound кандидат ещё НЕ был НПД?
    step += 1
    if on_progress:
        await on_progress(step, ESTIMATED_TOTAL_STEPS, lower_bound, upper_bound, lower_bound)
    try:
        lower_check = await checker.check(inn, request_date=lower_bound)
        if lower_check.is_active:
            # Уже был НПД на lower (маловероятно). Возвращаем lower.
            log.info(
                f"[binary_search] inn={inn} already active on {lower_bound} — "
                f"returning lower_bound"
            )
            return lower_bound
    except NpdStatusError as e:
        # Если на lower сразу 422 — двигаем lower на 30 дней позже и повторяем
        log.warning(
            f"[binary_search] inn={inn} 422 on lower={lower_bound}: {e}. "
            f"This shouldn't happen for {NPD_LAW_START}+, проверка алгоритма."
        )
        # Не падаем — продолжаем бинпоиск, может на середине пройдёт

    # === Бинпоиск
    left = lower_bound
    right = upper_bound

    while (right - left).days > 1:
        step += 1
        mid = left + (right - left) // 2

        if on_progress:
            await on_progress(step, ESTIMATED_TOTAL_STEPS, left, right, mid)

        log.info(
            f"[binary_search] inn={inn} step={step} "
            f"[{left} … {right}] = {(right - left).days} days, mid={mid}"
        )

        try:
            result = await checker.check(inn, request_date=mid)
        except NpdStatusError as e:
            err_str = str(e)
            if "422" in err_str:
                # mid слишком стар → регистрация позже
                log.info(f"[binary_search] inn={inn} 422 on {mid} → left := mid")
                left = mid
                continue
            else:
                # Другая ошибка (timeout, 500) — пробрасываем
                raise

        if result.is_active:
            right = mid
            log.info(f"[binary_search] inn={inn} active on {mid} → right := mid")
        else:
            left = mid
            log.info(f"[binary_search] inn={inn} not active on {mid} → left := mid")

    log.info(
        f"[binary_search] inn={inn} converged to {right} "
        f"(after {step} requests)"
    )
    return right
