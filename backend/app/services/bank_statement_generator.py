"""
Генератор транзакций для банковской выписки.

Pack 25.8 / 25.9 (06.05.2026):
- Дата формирования = today() - random(7..10) дней (раньше считалась как period_end+1)
- Pack 25.9: период = [statement_date - 3 мес, statement_date]
  (period_end теперь равен дате формирования, не -1 день)
- Pack 25.9: ручной override через application.bank_statement_date (опционально)
- Hard-фильтр: ни одна транзакция не выходит за [period_start, period_end]
- Копейки во всех суммах кроме поступлений по договору (там целые рубли)
- Новый тип: СБП-переводы себе (телефон РФ, генерится если applicant.phone не +7)
- Новый тип: онлайн-подписки на сервисы без географической привязки
  (Яндекс Плюс, Кинопоиск, Литрес, VK Музыка, IVI, Okko, Букмейт, Storytel,
   MyBook, Reg.ru, Timeweb, Boosty)

Логика месяцев (Pack 25.8):
- Зарплата от Заказчика приходит ~6 числа следующего месяца. Если эта дата
  выходит за period_end — поступление за этот месяц НЕ показываем.
- НПД списывается ~20 числа следующего месяца. Если > period_end — не показываем.
- Комиссия за пакет списывается ~1 числа следующего месяца. Если > period_end — не показываем.
- Это не подозрительно: реальная выписка за 12.02–11.05 покажет налоги/комиссии
  только за февраль и март (списание в марте и апреле), а за апрель — нет
  (списание в мае ещё не наступило к 11.05).

Менеджер в админке может изменить любую транзакцию или весь список целиком.
"""
import logging
import random
import re
import string
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from dateutil.relativedelta import relativedelta

log = logging.getLogger(__name__)


# === Дефолтные параметры ===

DEFAULT_NPD_RATE = Decimal("0.06")
DEFAULT_BANK_FEE_PER_MONTH = Decimal("399.00")
DEFAULT_KWIKPAY_RESERVE = Decimal("800")
DEFAULT_BANK_PERIOD_OFFSET_DAYS = 9   # legacy, оставлен для совместимости сигнатуры
DEFAULT_BANK_PERIOD_MONTHS = 3
DEFAULT_OPENING_BALANCE = Decimal("301018.66")

# Pack 25.8: дата формирования = today() - random(STATEMENT_AGE_DAYS_MIN..MAX)
STATEMENT_AGE_DAYS_MIN = 7
STATEMENT_AGE_DAYS_MAX = 10


# === Генераторы кодов операций ===

def _gen_credit_code() -> str:
    return "C16" + "".join(random.choices(string.digits, k=13))


def _gen_payment_code() -> str:
    # Кириллическая С — как в реальных выписках Альфы
    return "С011" + "".join(random.choices(string.digits, k=13))


def _gen_fee_code() -> str:
    return "MOSH 19" + "".join(random.choices(string.digits, k=8))


def _gen_sbp_code() -> str:
    """Код для СБП-перевода. Альфа использует префикс SBP."""
    return "SBP " + "".join(random.choices(string.digits, k=12))


def _gen_subscription_code() -> str:
    """Код для оплаты онлайн-сервиса (рекуррент). Альфа: RECUR <digits>."""
    return "RECUR " + "".join(random.choices(string.digits, k=10))


# === Хелперы ===

_MONTHS_GENITIVE_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

_MONTHS_NOMINATIVE_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

# Pack 25.8: префиксы мобильных РФ-операторов (план нумерации Россвязи 2026)
RU_MOBILE_PREFIXES = [
    # МТС
    "910", "911", "912", "913", "914", "915", "916", "917", "918", "919",
    # Билайн
    "903", "905", "906", "909", "960", "961", "962", "963", "964", "965", "966", "967", "968",
    # Мегафон
    "920", "921", "922", "923", "924", "925", "926", "927", "928", "929",
    "930", "931", "932", "933", "934", "936", "937", "938",
    # Т2 (Tele2)
    "900", "901", "902", "904", "908", "950", "951", "952", "953",
    "980", "981", "982", "983", "984", "985", "986", "987", "988", "989",
    # Тинькофф Мобайл / Yota
    "977", "978", "999",
]

# Pack 25.8: онлайн-сервисы без географической привязки
# (только цифровой контент / подписки / хостинг — пользоваться можно из любой страны)
ONLINE_SERVICES = [
    ("Яндекс Плюс",    [Decimal("199.00"), Decimal("299.00"), Decimal("399.00")]),
    ("Кинопоиск HD",   [Decimal("299.00"), Decimal("399.00")]),
    ("Литрес",         [Decimal("399.00"), Decimal("499.00"), Decimal("749.00"), Decimal("1990.00")]),
    ("VK Музыка",      [Decimal("169.00"), Decimal("199.00")]),
    ("VK Combo",       [Decimal("299.00")]),
    ("IVI",            [Decimal("399.00"), Decimal("599.00")]),
    ("Okko",           [Decimal("399.00"), Decimal("499.00"), Decimal("799.00")]),
    ("Букмейт",        [Decimal("299.00"), Decimal("399.00")]),
    ("Storytel",       [Decimal("549.00"), Decimal("749.00")]),
    ("MyBook",         [Decimal("279.00"), Decimal("379.00")]),
    ("Reg.ru",         [Decimal("450.00"), Decimal("1290.00"), Decimal("2900.00")]),
    ("Timeweb",        [Decimal("199.00"), Decimal("590.00"), Decimal("1490.00")]),
    ("Boosty",         [Decimal("149.00"), Decimal("299.00"), Decimal("499.00"), Decimal("990.00")]),
]


def _adjust_to_business_day(d: date) -> date:
    """Если дата выпала на выходной, сдвигаем вперёд на ближайший будний."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _last_day_of_month(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _format_amount_for_description(amount: Decimal) -> str:
    """3000.50 → '3 000,50'. Без копеек если они нулевые? — нет, всегда с копейками для расходов."""
    q = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    int_part = int(q)
    frac = (q - Decimal(int_part)).copy_abs()
    frac_str = f"{frac:.2f}".split(".")[1]
    return f"{int_part:,}".replace(",", " ") + "," + frac_str


def _is_valid_ru_mobile(phone: Optional[str]) -> bool:
    """Проверяет, является ли номер валидным российским мобильным.
    +7 9XX XXX-XX-XX или 89XXXXXXXXX. Префикс 9XX должен быть в RU_MOBILE_PREFIXES."""
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = digits[1:]
    elif len(digits) == 10:
        pass
    else:
        return False
    return digits[:3] in RU_MOBILE_PREFIXES


def _format_ru_phone_masked(phone_digits10: str) -> str:
    """'9165557788' → '+7 916 ***-**-88' (как в банковских выписках для приватности)."""
    if len(phone_digits10) != 10:
        return phone_digits10
    return f"+7 {phone_digits10[:3]} ***-**-{phone_digits10[8:]}"


def _gen_random_ru_mobile() -> str:
    """Генерит случайный валидный российский мобильный, 10 цифр без +7."""
    prefix = random.choice(RU_MOBILE_PREFIXES)
    rest = "".join(random.choices(string.digits, k=7))
    return prefix + rest


def _resolve_self_phone_for_sbp(applicant_phone: Optional[str]) -> str:
    """Возвращает 10-значный российский мобильный.
    Если applicant.phone валидный РФ — берём его. Иначе генерим случайный."""
    if applicant_phone:
        digits = re.sub(r"\D", "", applicant_phone)
        if len(digits) == 11 and digits[0] in ("7", "8"):
            digits = digits[1:]
        if len(digits) == 10 and digits[:3] in RU_MOBILE_PREFIXES:
            return digits
    return _gen_random_ru_mobile()


def _short_name_for_sbp(full_name_ru: Optional[str]) -> str:
    """'Веда́т Карагёзов Бухарийич' → 'Ведат К.'
    Берём имя + первая буква фамилии."""
    if not full_name_ru:
        return "Получатель"
    parts = [p for p in full_name_ru.strip().split() if p]
    if not parts:
        return "Получатель"
    first = parts[0]
    if len(parts) >= 2:
        return f"{first} {parts[1][0]}."
    return first


# === Главная функция ===

def generate_default_transactions(
    *,
    submission_date: date,
    salary_rub: Decimal,
    contract_number: str,
    contract_sign_date: date,
    company_full_name: str,
    company_inn: str,
    company_bank_account: str,
    company_bank_bic: str,
    npd_rate: Decimal = DEFAULT_NPD_RATE,
    period_months: int = DEFAULT_BANK_PERIOD_MONTHS,
    period_offset_days: int = DEFAULT_BANK_PERIOD_OFFSET_DAYS,  # legacy, не используется
    bank_fee: Decimal = DEFAULT_BANK_FEE_PER_MONTH,
    seed: Optional[int] = None,
    # Pack 25.8: новые опциональные параметры
    applicant_full_name_ru: Optional[str] = None,
    applicant_phone: Optional[str] = None,
    statement_date_override: Optional[date] = None,
) -> dict:
    """
    Генерирует черновик списка транзакций для выписки.

    Pack 25.8: добавлены statement_date, СБП-переводы, онлайн-подписки.

    Returns:
        {
            "statement_date": date,           # Pack 25.8: новое поле
            "period_start": date,
            "period_end": date,
            "opening_balance": Decimal,
            "closing_balance": Decimal,
            "total_income": Decimal,
            "total_expense": Decimal,
            "transactions": [
                {
                    "transaction_date": date,
                    "code": str,
                    "description": str,
                    "amount": Decimal,  # отрицательная = списание
                    "currency": "RUR",
                },
                ...
            ]
        }
    """
    if seed is not None:
        random.seed(seed)

    # === Pack 25.8: дата формирования и период ===
    if statement_date_override is not None:
        statement_date = statement_date_override
    else:
        today = date.today()
        statement_date = today - timedelta(
            days=random.randint(STATEMENT_AGE_DAYS_MIN, STATEMENT_AGE_DAYS_MAX)
        )

    # Pack 25.9: period_end = statement_date (включая день формирования).
    # Реальные банки: «выписка с 27.01 по 27.04, дата формирования 27.04».
    period_end = statement_date
    period_start = (statement_date - relativedelta(months=period_months))

    # Налог и сумма перевода KWIKPAY (с копейками)
    tax_amount = (Decimal(salary_rub) * npd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    kwikpay_default = (Decimal(salary_rub) - tax_amount - DEFAULT_KWIKPAY_RESERVE)
    kwikpay_default = kwikpay_default.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Определяем месяцы внутри периода (для генерации зарплат / налогов / комиссий).
    # Берём ВСЕ месяцы, которые хотя бы частично попадают в [period_start, period_end].
    months = []
    cur = date(period_start.year, period_start.month, 1)
    while cur <= period_end:
        months.append((cur.year, cur.month))
        # шагаем на следующий месяц
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    transactions = []

    # === Поступления, налоги, комиссии — по месяцам ===
    for idx, (year, month) in enumerate(months):
        month_name_nominative = _MONTHS_NOMINATIVE_RU[month - 1]
        last_day = _last_day_of_month(year, month)

        # 1. Поступление от Заказчика (~6 числа следующего месяца)
        next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)
        income_day = random.randint(5, 8)
        try:
            income_date = _adjust_to_business_day(date(next_y, next_m, income_day))
        except ValueError:
            continue
        if period_start <= income_date <= period_end:
            income_desc = (
                f"Плательщик: {company_full_name}\n"
                f"ИНН плательщика: {company_inn}\n"
                f"Счет плательщика: {company_bank_account}, БИК {company_bank_bic}\n"
                f"Назначение платежа: Оплата за оказание услуг по Договору №{contract_number} "
                f"от {contract_sign_date.strftime('%d.%m.%y')}г. за период "
                f"01.{month:02d}.{year}-{last_day:02d}.{month:02d}.{year}г., "
                f"Акт №{idx + 1}/{year % 100:02d} от {last_day:02d}.{month:02d}.{year}г., без НДС."
            )
            transactions.append({
                "transaction_date": income_date,
                "code": _gen_credit_code(),
                "description": income_desc,
                "amount": Decimal(salary_rub).quantize(Decimal("0.01")),
                "currency": "RUR",
            })

        # 2. KWIKPAY (~10-15 числа того же месяца, в котором пришла зарплата)
        kwikpay_day = random.randint(10, 15)
        try:
            kwikpay_date = _adjust_to_business_day(date(next_y, next_m, kwikpay_day))
        except ValueError:
            kwikpay_date = None
        if kwikpay_date and period_start <= kwikpay_date <= period_end:
            # ±10% вариация
            kwikpay_variation = Decimal(random.randint(-10000, 10000))
            kwikpay_amount = (kwikpay_default + kwikpay_variation).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            transactions.append({
                "transaction_date": kwikpay_date,
                "code": _gen_payment_code(),
                "description": "Перевод   JSC*KWIKPAY online.",
                "amount": -kwikpay_amount,
                "currency": "RUR",
            })

        # 3. НПД (~18-22 числа месяца, следующего за месяцем дохода)
        # т.е. за январь налог в феврале, но нам надо из месяца "получения" дохода (next)
        # Точнее: доход за месяц X пришёл в (X+1), налог за X платится тоже в (X+1) ~20 числа
        npd_day = random.randint(18, 25)
        try:
            npd_date = _adjust_to_business_day(date(next_y, next_m, npd_day))
        except ValueError:
            npd_date = None
        if npd_date and period_start <= npd_date <= period_end:
            npd_desc = (
                f"Единый налоговый платеж. Уплата НПД за {month_name_nominative} {year} г."
            )
            transactions.append({
                "transaction_date": npd_date,
                "code": _gen_payment_code(),
                "description": npd_desc,
                "amount": -tax_amount,
                "currency": "RUR",
            })

        # 4. Комиссия за пакет (~1 числа месяца, следующего за месяцем дохода = next+1)
        fee_y, fee_m = (next_y, next_m + 1) if next_m < 12 else (next_y + 1, 1)
        fee_day = random.randint(1, 3)
        try:
            fee_date = _adjust_to_business_day(date(fee_y, fee_m, fee_day))
        except ValueError:
            fee_date = None
        if fee_date and period_start <= fee_date <= period_end:
            fee_desc = (
                f"Комиссия за пакет услуг за {_MONTHS_NOMINATIVE_RU[next_m - 1]} {next_y} г. "
                f"Согласно тарифам банка."
            )
            transactions.append({
                "transaction_date": fee_date,
                "code": _gen_fee_code(),
                "description": fee_desc,
                "amount": -bank_fee,
                "currency": "RUR",
            })

    # === Pack 25.8: СБП-переводы себе ===
    self_phone = _resolve_self_phone_for_sbp(applicant_phone)
    self_phone_masked = _format_ru_phone_masked(self_phone)
    self_short_name = _short_name_for_sbp(applicant_full_name_ru)

    sbp_count_total = random.randint(3, 8)  # 3-8 за весь период (~1-3 в месяц)
    for _ in range(sbp_count_total):
        # Случайная дата внутри периода
        delta_days = random.randint(0, (period_end - period_start).days)
        sbp_date = _adjust_to_business_day(period_start + timedelta(days=delta_days))
        if sbp_date > period_end:
            continue
        # Сумма 5000.00 - 60000.00 с копейками
        rub = random.randint(5000, 60000)
        kop = random.randint(0, 99)
        sbp_amount = Decimal(f"{rub}.{kop:02d}")
        sbp_desc = (
            f"Перевод по СБП. Получатель: {self_short_name}\n"
            f"Тинькофф Банк, {self_phone_masked}"
        )
        transactions.append({
            "transaction_date": sbp_date,
            "code": _gen_sbp_code(),
            "description": sbp_desc,
            "amount": -sbp_amount,
            "currency": "RUR",
        })

    # === Pack 25.8: онлайн-подписки и оплаты сервисов ===
    subs_count_total = random.randint(10, 20)  # за весь период
    for _ in range(subs_count_total):
        delta_days = random.randint(0, (period_end - period_start).days)
        sub_date = period_start + timedelta(days=delta_days)
        if sub_date > period_end:
            continue
        service_name, price_options = random.choice(ONLINE_SERVICES)
        sub_amount = random.choice(price_options)
        sub_desc = f"Оплата услуг. {service_name}"
        transactions.append({
            "transaction_date": sub_date,
            "code": _gen_subscription_code(),
            "description": sub_desc,
            "amount": -sub_amount,
            "currency": "RUR",
        })

    # === Pack 25.8: hard-фильтр + sanity check ===
    before = len(transactions)
    transactions = [
        t for t in transactions
        if period_start <= t["transaction_date"] <= period_end
    ]
    dropped = before - len(transactions)
    if dropped > 0:
        log.warning(
            "[Pack 25.8] dropped %d tx outside period %s..%s",
            dropped, period_start, period_end,
        )
    # Жёсткая проверка
    for t in transactions:
        assert period_start <= t["transaction_date"] <= period_end, (
            f"[Pack 25.8] tx {t['transaction_date']} outside period "
            f"{period_start}..{period_end} — generator bug"
        )

    # Сортируем от новой к старой (как в реальной выписке Альфы — последняя сверху)
    transactions.sort(key=lambda t: t["transaction_date"], reverse=True)

    # Балансы
    total_income = sum(
        (t["amount"] for t in transactions if t["amount"] > 0), Decimal("0.00")
    )
    total_expense = sum(
        (-t["amount"] for t in transactions if t["amount"] < 0), Decimal("0.00")
    )
    opening_balance = DEFAULT_OPENING_BALANCE
    closing_balance = (opening_balance + total_income - total_expense).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return {
        "statement_date": statement_date,   # Pack 25.8
        "period_start": period_start,
        "period_end": period_end,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "total_income": total_income,
        "total_expense": total_expense,
        "transactions": transactions,
    }


def serialize_for_storage(generated: dict) -> dict:
    """JSON-сериализация результата генерации."""
    out = {
        "period_start": generated["period_start"].isoformat(),
        "period_end": generated["period_end"].isoformat(),
        "opening_balance": str(generated["opening_balance"]),
        "transactions": [
            {
                "transaction_date": t["transaction_date"].isoformat(),
                "code": t["code"],
                "description": t["description"],
                "amount": str(t["amount"]),
                "currency": t["currency"],
            }
            for t in generated["transactions"]
        ],
    }
    # Pack 25.8: сохраняем statement_date если он есть
    if generated.get("statement_date"):
        out["statement_date"] = generated["statement_date"].isoformat()
    return out


def deserialize_from_storage(stored: dict) -> dict:
    """Обратная сериализация."""
    out = {
        "period_start": date.fromisoformat(stored["period_start"]),
        "period_end": date.fromisoformat(stored["period_end"]),
        "opening_balance": Decimal(stored["opening_balance"]),
        "transactions": [
            {
                "transaction_date": date.fromisoformat(t["transaction_date"]),
                "code": t["code"],
                "description": t["description"],
                "amount": Decimal(t["amount"]),
                "currency": t["currency"],
            }
            for t in stored["transactions"]
        ],
    }
    # Pack 25.8: восстанавливаем statement_date если был сохранён
    if stored.get("statement_date"):
        out["statement_date"] = date.fromisoformat(stored["statement_date"])
    return out
