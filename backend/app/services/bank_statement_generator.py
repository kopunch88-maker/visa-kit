"""
Генератор транзакций для банковской выписки.

Создаёт реалистичный черновик из ~15 транзакций за 3 месяца, имитирующий
реальную выписку Альфа-банка по счёту самозанятого, который:
- получает зарплату от компании раз в месяц (обычно ~6 числа)
- платит налог НПД (6% от дохода) ~20 числа следующего месяца
- выводит почти всё через KWIKPAY ~10-15 числа
- платит комиссию за пакет услуг 399 ₽ ~1 числа

Логика автогенерации:
1. Период определяется от submission_date - 9 дней назад на 90 дней
2. Внутри периода — 3 полных месяца с зарплатой
3. На каждый месяц генерируется 4 транзакции:
   - Поступление от компании (salary_rub)
   - Перевод KWIKPAY (salary - tax - 800)  ← дефолт, менеджер может править
   - НПД (salary * 0.06)
   - Комиссия 399 ₽

Все коды операций — случайные, в правильном формате Альфа-банка.

Менеджер в админке может изменить любую транзакцию или весь список целиком.
"""
import random
import string
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional


# === Дефолтные параметры (можно изменить через override в Application) ===

DEFAULT_NPD_RATE = Decimal("0.06")          # НПД для самозанятого с юрлицами
DEFAULT_BANK_FEE_PER_MONTH = Decimal("399") # Альфа пакет «Премиум» или похожий
DEFAULT_KWIKPAY_RESERVE = Decimal("800")    # сколько оставляем на счёте для комиссии
DEFAULT_BANK_PERIOD_OFFSET_DAYS = 9          # выписка обычно за период до X дней до подачи
DEFAULT_BANK_PERIOD_MONTHS = 3                # период выписки в месяцах


# === Генераторы кодов операций (правдоподобный формат Альфа-банка) ===

def _gen_credit_code() -> str:
    """Код для поступления / зарплаты. Формат: C16<13 цифр>"""
    return "C16" + "".join(random.choices(string.digits, k=13))


def _gen_payment_code() -> str:
    """Код для оплаты налога / KWIKPAY-перевода. Формат: С011<13 цифр>"""
    # Использует кириллическую С — как в реальных выписках Альфа-банка
    return "С011" + "".join(random.choices(string.digits, k=13))


def _gen_fee_code() -> str:
    """Код для комиссии за пакет. Формат: MOSH 19<8 цифр>"""
    return "MOSH 19" + "".join(random.choices(string.digits, k=8))


# === Хелперы ===

_MONTHS_GENITIVE_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

_MONTHS_NOMINATIVE_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def _adjust_to_business_day(d: date) -> date:
    """Если дата выпала на выходной, сдвигаем на ближайший рабочий день вперёд."""
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


def _format_amount_for_description(amount: Decimal) -> str:
    """300000 → '300 000,00'"""
    return f"{int(amount):,}".replace(",", " ") + ",00"


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
    period_offset_days: int = DEFAULT_BANK_PERIOD_OFFSET_DAYS,
    bank_fee: Decimal = DEFAULT_BANK_FEE_PER_MONTH,
    seed: Optional[int] = None,
) -> dict:
    """
    Генерирует черновик списка транзакций для выписки.

    Returns:
        {
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

    # Период выписки — заканчивается за period_offset_days до подачи
    period_end = submission_date - timedelta(days=period_offset_days)
    period_start = period_end - timedelta(days=90)

    # Налог и сумма перевода KWIKPAY
    tax_amount = (salary_rub * npd_rate).quantize(Decimal("1"))
    # KWIKPAY = зарплата - налог - запас 800 на комиссию (приблизительный остаток)
    kwikpay_default = salary_rub - tax_amount - DEFAULT_KWIKPAY_RESERVE
    kwikpay_default = kwikpay_default.quantize(Decimal("1"))

    # Определяем месяцы для выписки.
    # Идём от period_end назад: текущий месяц + 2 предыдущих
    # Например, если period_end = 19.04.2026, то месяцы: январь, февраль, март
    # (потому что апрель ещё не закрыт — оплата за март приходит в апреле)
    months = []
    cur = date(period_end.year, period_end.month, 1) - timedelta(days=1)  # последний день предыдущего
    for _ in range(period_months):
        months.append((cur.year, cur.month))
        cur = date(cur.year, cur.month, 1) - timedelta(days=1)
    months.reverse()  # самый старый первым: [январь, февраль, март]

    transactions = []
    opening_balance = Decimal("301018.66")  # реалистичный остаток на начало (примерно как у Алиева)

    for idx, (year, month) in enumerate(months):
        month_name_genitive = _MONTHS_GENITIVE_RU[month - 1]
        month_name_nominative = _MONTHS_NOMINATIVE_RU[month - 1]

        # === 1. Поступление от компании (~6 числа) ===
        income_day = random.randint(5, 8)
        income_date = _adjust_to_business_day(date(year, month, income_day))
        income_desc = (
            f'Плательщик: {company_full_name}\n'
            f'ИНН плательщика: {company_inn}\n'
            f'Счет плательщика: {company_bank_account}, БИК {company_bank_bic}\n'
            f'Назначение платежа: Оплата за оказание услуг по Договору №{contract_number} '
            f'от {contract_sign_date.strftime("%d.%m.%y")}г. за период '
            f'01.{month:02d}-{_last_day_of_month(year, month):02d}.{month:02d}.{year}г., '
            f'Акт №{idx + 1}/{year % 100:02d} от {_last_day_of_month(year, month):02d}.{month:02d}.{year}г., без НДС.'
        )
        transactions.append({
            "transaction_date": income_date,
            "code": _gen_credit_code(),
            "description": income_desc,
            "amount": salary_rub,
            "currency": "RUR",
        })

        # === 2. Перевод KWIKPAY (~10-15 числа) ===
        kwikpay_day = random.randint(10, 15)
        kwikpay_date = _adjust_to_business_day(date(year, month, kwikpay_day))
        # Сумма колеблется ±10% для реалистичности
        kwikpay_variation = Decimal(random.randint(-10000, 10000))
        kwikpay_amount = kwikpay_default + kwikpay_variation
        transactions.append({
            "transaction_date": kwikpay_date,
            "code": _gen_payment_code(),
            "description": "Перевод   JSC*KWIKPAY online.",
            "amount": -kwikpay_amount,
            "currency": "RUR",
        })

        # === 3. НПД (~20 числа следующего месяца) ===
        # Например за январь налог платится в феврале
        npd_year, npd_month = (year, month + 1) if month < 12 else (year + 1, 1)
        npd_day = random.randint(18, 22)
        npd_date = _adjust_to_business_day(date(npd_year, npd_month, npd_day))
        npd_desc = f"Единый налоговый платеж. Оплата НПД за {month_name_nominative} {year}г."
        transactions.append({
            "transaction_date": npd_date,
            "code": _gen_payment_code(),
            "description": npd_desc,
            "amount": -tax_amount,
            "currency": "RUR",
        })

        # === 4. Комиссия за пакет (~1 числа следующего месяца) ===
        fee_year, fee_month = (year, month + 1) if month < 12 else (year + 1, 1)
        fee_date = _adjust_to_business_day(date(fee_year, fee_month, 1))
        fee_desc = f"Комиссия за пакет услуг за {month_name_nominative} {year} г. Согласно тарифам банка."
        transactions.append({
            "transaction_date": fee_date,
            "code": _gen_fee_code(),
            "description": fee_desc,
            "amount": -bank_fee,
            "currency": "RUR",
        })

    # Сортируем от новой к старой (как в реальной выписке Альфы — последняя сверху)
    transactions.sort(key=lambda t: t["transaction_date"], reverse=True)

    # Считаем балансы
    total_income = sum((t["amount"] for t in transactions if t["amount"] > 0), Decimal("0"))
    total_expense = sum((-t["amount"] for t in transactions if t["amount"] < 0), Decimal("0"))
    closing_balance = opening_balance + total_income - total_expense

    return {
        "period_start": period_start,
        "period_end": period_end,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "total_income": total_income,
        "total_expense": total_expense,
        "transactions": transactions,
    }


def _last_day_of_month(year: int, month: int) -> int:
    """Последнее число месяца."""
    from calendar import monthrange
    return monthrange(year, month)[1]


def serialize_for_storage(generated: dict) -> dict:
    """
    Конвертирует результат генерации в JSON-сериализуемый вид.
    Используется когда нужно сохранить в Application.bank_transactions_override.
    """
    return {
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


def deserialize_from_storage(stored: dict) -> dict:
    """Обратное преобразование — из JSON в Python-объекты."""
    return {
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
