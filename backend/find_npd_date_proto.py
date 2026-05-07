"""
Прототип Pack 28.5 — бинпоиск даты регистрации НПД через FNS API.

Запуск:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:PYTHONIOENCODING = "utf-8"
    python find_npd_date_proto.py 542907257032

ИЛИ можно передать несколько ИНН через запятую:
    python find_npd_date_proto.py 542907257032,540550702852,542050234310

Алгоритм:
  left = max(2019-01-01, rmsp_support_date - 1 год)  — safe lower bound
  right = today
  while right - left > 1 day:
      mid = left + (right - left) // 2
      status_on_mid = api(inn, mid)
      if status_on_mid == True:   right = mid     # был НПД, регистрация раньше
      else:                       left = mid      # не был, регистрация позже
  return right                                    # точная дата регистрации

Сложность: O(log₂(7.5 лет × 365)) ≈ 11-12 запросов на ИНН × 31 сек/запрос = ~6 мин/ИНН.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, timedelta
from typing import Optional

# Подключаем существующий NpdStatusChecker из проекта
sys.path.insert(0, ".")
from app.services.inn_generator.npd_status import NpdStatusChecker, NpdStatusError


# Жёсткий нижний предел — самозанятые появились по 422-ФЗ только с 01.01.2019
NPD_LAW_START = date(2019, 1, 1)


async def find_registration_date(
    checker: NpdStatusChecker,
    inn: str,
    *,
    upper_bound: Optional[date] = None,
    lower_bound: Optional[date] = None,
    verbose: bool = True,
) -> Optional[date]:
    """
    Бинпоиск даты регистрации НПД для ИНН.

    Args:
        checker: уже открытый NpdStatusChecker (через async with)
        inn: 12-значный ИНН
        upper_bound: гарантированно ПОСЛЕ регистрации (обычно today)
        lower_bound: гарантированно ДО регистрации (обычно 2019-01-01)
        verbose: печатать каждый шаг

    Returns:
        Точная дата регистрации, или None если ИНН не НПД на upper_bound.
    """
    if upper_bound is None:
        upper_bound = date.today()
    if lower_bound is None:
        lower_bound = NPD_LAW_START

    # Sanity: проверяем что upper действительно НПД
    if verbose:
        print(f"\n=== {inn} ===")
        print(f"  диапазон: {lower_bound} … {upper_bound}")
        print(f"  Проверка upper={upper_bound}:")

    upper_check = await checker.check(inn, request_date=upper_bound)
    if not upper_check.is_active:
        if verbose:
            print(f"    is_active=False → ИНН не НПД на {upper_bound}, бинпоиск невозможен")
        return None
    if verbose:
        full_name = upper_check.full_name or "(имя не возвращено)"
        print(f"    is_active=True, имя: {full_name}")

    # Sanity: проверяем что на lower кандидат ещё НЕ был НПД
    if verbose:
        print(f"  Проверка lower={lower_bound}:")
    lower_check = await checker.check(inn, request_date=lower_bound)
    if lower_check.is_active:
        # Уже был НПД на 2019-01-01? Маловероятно (закон только начал действовать),
        # но возможно если эксперимент в 4 регионах. Возвращаем lower как лучший ответ.
        if verbose:
            print(f"    is_active=True уже на {lower_bound} → возвращаем lower")
        return lower_bound
    if verbose:
        print(f"    is_active=False (как ожидалось)")

    # Бинпоиск
    left = lower_bound
    right = upper_bound
    step = 0
    if verbose:
        print(f"\n  --- Бинпоиск ---")

    while (right - left).days > 1:
        step += 1
        mid = left + (right - left) // 2

        if verbose:
            range_days = (right - left).days
            print(f"  Шаг {step:2d}: [{left} … {right}] = {range_days} дн., mid={mid}", end="", flush=True)

        try:
            result = await checker.check(inn, request_date=mid)
        except NpdStatusError as e:
            if verbose:
                print(f"  ERROR: {e}")
            # Вероятнее всего mid слишком стар (422). Сдвигаем left вверх.
            left = mid
            continue

        if result.is_active:
            right = mid
            if verbose:
                print(f"  → True  (right := mid)")
        else:
            left = mid
            if verbose:
                print(f"  → False (left  := mid)")

    if verbose:
        print(f"\n  Сошлось: регистрация = {right} (за {step} запросов)")

    return right


async def main():
    if len(sys.argv) < 2:
        print("Использование: python find_npd_date_proto.py <inn>[,<inn>...]")
        sys.exit(1)

    inns = sys.argv[1].split(",")
    inns = [i.strip() for i in inns if i.strip()]

    print(f"Будет проверено {len(inns)} ИНН.")
    print(f"Ожидаемое время: ~6 минут на ИНН (log₂(7.5лет×365) × 31 сек)")
    print(f"Итого: ~{len(inns) * 6} минут\n")

    logging.basicConfig(
        level=logging.WARNING,  # WARNING чтобы не засорять info-логами от npd_status
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    async with NpdStatusChecker() as checker:
        results = []
        for inn in inns:
            try:
                reg_date = await find_registration_date(checker, inn)
                results.append((inn, reg_date))
            except Exception as e:
                print(f"\n  FAIL для {inn}: {type(e).__name__}: {e}")
                results.append((inn, None))

    print("\n" + "=" * 60)
    print("ИТОГИ:")
    print("=" * 60)
    for inn, reg_date in results:
        if reg_date:
            print(f"  {inn}: {reg_date}")
        else:
            print(f"  {inn}: НЕ НАЙДЕНА")


if __name__ == "__main__":
    asyncio.run(main())
