"""
Pack 16 — генератор номера расчётного счёта по правилам ЦБ РФ.

Алгоритм:
- Структура счёта физлица РФ (20 цифр):
  408 + XXX + ВВВ + Б + ККККККК
  где:
    408   — балансовый счёт первого порядка для физлиц
    XXX   — 0X8: 018=резидент РФ, 028=нерезидент
    ВВВ   — валюта по ОКВ: 810=RUB, 840=USD, 978=EUR
    Б     — позиция 9 (0-индекс), контрольный разряд (рассчитывается)
    КККК  — 11 цифр: 3 номер подразделения банка + 8 номер лицевого счёта

- Контрольный разряд считается по алгоритму ЦБ РФ:
  Берём последние 3 цифры БИК + 20 цифр счёта = 23 цифры.
  Умножаем поразрядно на коэффициенты [7,1,3,7,1,3,7,1,3,7,1,3,7,1,3,7,1,3,7,1,3,7,1].
  Берём последний разряд каждого произведения, суммируем.
  Сумма должна делиться на 10 (mod 10 == 0). Иначе счёт невалидный.

  Чтобы СГЕНЕРИРОВАТЬ валидный — рассчитываем контрольный разряд под уже
  подобранные другие цифры.

Уникальность счёта в Pack 16 обеспечивается циклом:
  generate → check Applicant.bank_account != x → если занят → retry.
"""

import logging
import random
from typing import Optional

from sqlmodel import Session, select

log = logging.getLogger(__name__)

# Коэффициенты алгоритма (положение Банка России № 579-П приложение 9)
COEFFICIENTS = [7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1]

# Префиксы счёта 408
PREFIX_RESIDENT = "40817"      # физлица-резиденты РФ (4 + 0 + 8 + 1 + 7)
PREFIX_NON_RESIDENT = "40820"  # физлица-нерезиденты

# Валюта
CURRENCY_RUB = "810"


def calculate_check_digit(bik: str, account_without_check: str) -> int:
    """
    Рассчитывает контрольный разряд счёта.

    Args:
        bik: БИК банка (9 цифр)
        account_without_check: Счёт где на месте контрольной цифры стоит '0',
                                длина 20 цифр (включая placeholder).

    Returns:
        int 0-9 — корректное значение контрольного разряда.
    """
    if len(bik) != 9 or not bik.isdigit():
        raise ValueError(f"Invalid BIK: {bik!r} (need 9 digits)")
    if len(account_without_check) != 20 or not account_without_check.isdigit():
        raise ValueError(f"Invalid account length: {account_without_check!r} (need 20 digits)")

    # 23 цифры = последние 3 БИК + 20 счёта
    digits_str = bik[-3:] + account_without_check
    digits = [int(c) for c in digits_str]

    # Сумма последних разрядов произведений
    s = sum((d * c) % 10 for d, c in zip(digits, COEFFICIENTS))

    # Корректный счёт: s mod 10 == 0
    # Текущая контрольная позиция в общей строке = 11 (3 + 8) — это позиция 9 в счёте,
    # её коэффициент = COEFFICIENTS[11] = 3
    # Если поставить вместо 0 цифру k, изменение суммы = (k * 3) mod 10
    # Нужно: (s + k*3) mod 10 == 0  ⇒  (k * 3) mod 10 == (10 - s mod 10) mod 10
    # Перебираем k от 0 до 9, найдём подходящий.
    target = (10 - (s % 10)) % 10
    for k in range(10):
        if (k * 3) % 10 == target:
            return k
    raise RuntimeError(f"Cannot find check digit (s={s}, target={target})")


def generate_account(bik: str, is_resident: bool = True, currency: str = CURRENCY_RUB) -> str:
    """
    Генерирует одноразовый валидный номер счёта (без проверки уникальности).

    Args:
        bik: БИК банка (9 цифр)
        is_resident: True для резидентов РФ, False для нерезидентов
        currency: Код валюты (810=RUB, 840=USD, 978=EUR)

    Returns:
        20-значный номер счёта.
    """
    prefix = PREFIX_RESIDENT if is_resident else PREFIX_NON_RESIDENT

    # 5 (префикс) + 3 (валюта) + 1 (контрольная) + 11 (тело) = 20 ✓
    body = "".join(str(random.randint(0, 9)) for _ in range(11))
    # Сначала ставим 0 на место контрольной — потом заменим
    account_with_zero = prefix + currency + "0" + body

    check = calculate_check_digit(bik, account_with_zero)

    return prefix + currency + str(check) + body


def is_account_unique(session: Session, account: str) -> bool:
    """Проверяет что счёт ещё нигде не используется."""
    # Импорт здесь чтобы избежать циклического импорта
    from app.models import Applicant

    existing = session.exec(
        select(Applicant).where(Applicant.bank_account == account)
    ).first()
    return existing is None


def generate_unique_account(
    session: Session,
    bik: str,
    is_resident: bool = True,
    max_attempts: int = 100,
) -> str:
    """
    Генерирует уникальный валидный счёт, проверяя по БД что не занят.

    Args:
        session: SQLModel session
        bik: БИК банка
        is_resident: резидент или нет
        max_attempts: максимум попыток (для безопасности)

    Returns:
        Уникальный 20-значный номер счёта.

    Raises:
        RuntimeError: если за max_attempts не нашли уникальный счёт
                      (практически невозможно — пространство 10^11 счетов).
    """
    for attempt in range(1, max_attempts + 1):
        account = generate_account(bik, is_resident=is_resident)
        if is_account_unique(session, account):
            log.info(
                f"[account_gen] Generated unique account on attempt {attempt}: "
                f"{account[:6]}...{account[-4:]} (bik={bik})"
            )
            return account
        log.warning(f"[account_gen] Account collision on attempt {attempt}, retrying")

    raise RuntimeError(
        f"Failed to generate unique account after {max_attempts} attempts "
        f"(bik={bik}). Statistically impossible — check DB integrity."
    )


def validate_account(bik: str, account: str) -> bool:
    """Проверяет валидность счёта по контрольному разряду."""
    if len(account) != 20 or not account.isdigit():
        return False
    if len(bik) != 9 or not bik.isdigit():
        return False

    digits_str = bik[-3:] + account
    digits = [int(c) for c in digits_str]
    s = sum((d * c) % 10 for d, c in zip(digits, COEFFICIENTS))
    return s % 10 == 0
