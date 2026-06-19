"""
Pack 57.5 — пропорция неполного месяца договора в банковской выписке.
Найм: месяц приёма -> одна выплата зарплатой (без аванса), на руки = гросс*0.87
      с пропорцией по рабочим дням. Полные месяцы — как раньше (аванс+зарплата).
Самозанятый: первый/последний месяц договора -> доход по календарным дням,
      период в акте = [дата_договора..конец], НПД и KWIKPAY от факт. дохода месяца.
Дополняет backend/app/services/prod_calendar.py функцией prorate_calendar.
Идемпотентно, .bak, py_compile. Кладётся в КОРЕНЬ репо: python apply_bank_proration.py
"""
import os
import py_compile

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVICES = os.path.join(ROOT, "backend", "app", "services")
CAL_PATH = os.path.join(SERVICES, "prod_calendar.py")
BANK = os.path.join(SERVICES, "bank_statement_generator.py")

PRORATE_CAL_FUNC = '''

def prorate_calendar(amount, year, month, start_date=None, end_date=None):
    """Pack 57.5: пропорция суммы по КАЛЕНДАРНЫМ дням месяца (услуги самозанятого).
    Полный месяц -> полная сумма; неполный первый/последний -> сумма * дни / дни_мес."""
    if amount is None:
        return Decimal("0.00")
    amount = Decimal(str(amount))
    last = calendar.monthrange(year, month)[1]
    m_start, m_end = date(year, month, 1), date(year, month, last)
    s = max(m_start, start_date) if start_date else m_start
    e = min(m_end, end_date) if end_date else m_end
    if e < s:
        return Decimal("0.00")
    days = (e - s).days + 1
    if days >= last:
        return amount.quantize(Decimal("0.01"))
    return (amount * Decimal(days) / Decimal(last)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
'''

# Полный модуль на случай, если Pack 57 не запускали (создаём с нуля)
FULL_MODULE = '''\
"""Производственный календарь РФ + пропорция неполного месяца (Pack 57 / 57.5)."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import calendar

_HOLIDAY_WEEKDAYS = {
    2026: {
        date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6),
        date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9),
        date(2026, 2, 23), date(2026, 3, 9), date(2026, 5, 1), date(2026, 5, 11),
        date(2026, 6, 12), date(2026, 11, 4), date(2026, 12, 31),
    },
}
_STATUTORY = [(1, d) for d in range(1, 9)] + [(2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4)]


def _auto_holidays(year):
    hs = set()
    for mth, day in _STATUTORY:
        d = date(year, mth, day)
        if mth == 1 and 1 <= day <= 8:
            if d.weekday() < 5:
                hs.add(d)
            continue
        if d.weekday() >= 5:
            d2 = d
            while d2.weekday() >= 5:
                d2 += timedelta(days=1)
            hs.add(d2)
        else:
            hs.add(d)
    return hs


def _holidays(year):
    return _HOLIDAY_WEEKDAYS.get(year) or _auto_holidays(year)


def is_working_day(d):
    if d.weekday() >= 5:
        return False
    return d not in _holidays(d.year)


def working_days_in_range(d1, d2):
    if not d1 or not d2 or d2 < d1:
        return 0
    n, cur = 0, d1
    while cur <= d2:
        if is_working_day(cur):
            n += 1
        cur += timedelta(days=1)
    return n


def working_days_in_month(year, month):
    last = calendar.monthrange(year, month)[1]
    return working_days_in_range(date(year, month, 1), date(year, month, last))


def monthly_gross(salary, year, month, hire_date=None, termination_date=None):
    if salary is None:
        return Decimal("0.00")
    salary = Decimal(str(salary))
    last = calendar.monthrange(year, month)[1]
    m_start, m_end = date(year, month, 1), date(year, month, last)
    work_start = max(m_start, hire_date) if hire_date else m_start
    work_end = min(m_end, termination_date) if termination_date else m_end
    if work_end < work_start:
        return Decimal("0.00")
    total = working_days_in_month(year, month)
    if total == 0:
        return Decimal("0.00")
    worked = working_days_in_range(work_start, work_end)
    if worked >= total:
        return salary.quantize(Decimal("0.01"))
    return (salary * Decimal(worked) / Decimal(total)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
''' + PRORATE_CAL_FUNC


def ensure_calendar():
    os.makedirs(SERVICES, exist_ok=True)
    if not os.path.exists(CAL_PATH):
        open(CAL_PATH, "w", encoding="utf-8").write(FULL_MODULE)
        py_compile.compile(CAL_PATH, doraise=True)
        print("Создан prod_calendar.py (с prorate_calendar).")
        return
    cur = open(CAL_PATH, "r", encoding="utf-8").read()
    if "def prorate_calendar" in cur:
        print("prod_calendar.py уже содержит prorate_calendar — пропускаю.")
        return
    open(CAL_PATH + ".bak", "w", encoding="utf-8").write(cur)
    open(CAL_PATH, "a", encoding="utf-8").write(PRORATE_CAL_FUNC)
    py_compile.compile(CAL_PATH, doraise=True)
    print("Дополнен prod_calendar.py: prorate_calendar.")


PATCHES = [
    # --- сигнатура: добавляем опциональный contract_end_date (keyword-only, без слома вызовов) ---
    (
        "    contract_sign_date: date,\n"
        "    company_full_name: str,\n",
        "    contract_sign_date: date,\n"
        "    contract_end_date: Optional[date] = None,  # Pack 57.5\n"
        "    company_full_name: str,\n",
    ),
    # --- НАЙМ: вставляем пропорцию перед _split_salary_employment ---
    (
        '            _csd = contract_sign_date.strftime("%d.%m.%Y") if contract_sign_date else ""\n'
        '            _avans, _zarplata = _split_salary_employment(salary_rub)\n',
        '            _csd = contract_sign_date.strftime("%d.%m.%Y") if contract_sign_date else ""\n'
        '            # Pack 57.5: гросс месяца с пропорцией неполного месяца приёма/увольнения.\n'
        '            from app.services.prod_calendar import monthly_gross as _monthly_gross\n'
        '            _m_gross = _monthly_gross(salary_rub, year, month, contract_sign_date, contract_end_date)\n'
        '            if _m_gross <= 0:\n'
        '                continue  # месяц вне срока трудоустройства — выплат нет\n'
        '            _full_gross = _monthly_gross(salary_rub, year, month, None, None)\n'
        '            if _m_gross < _full_gross:\n'
        '                # Неполный месяц приёма/увольнения: одна выплата зарплатой (без аванса),\n'
        '                # на руки = гросс * 0.87 (минус 13% НДФЛ).\n'
        '                _net_partial = (_m_gross * Decimal("0.87")).quantize(\n'
        '                    Decimal("0.01"), rounding=ROUND_HALF_UP)\n'
        '                _zp_day = random.randint(5, 9)\n'
        '                try:\n'
        '                    _zp_date = _adjust_to_business_day(date(next_y, next_m, _zp_day))\n'
        '                except ValueError:\n'
        '                    _zp_date = None\n'
        '                if _zp_date and period_start <= _zp_date <= period_end:\n'
        '                    transactions.append({\n'
        '                        "transaction_date": _zp_date,\n'
        '                        "code": _gen_credit_code(),\n'
        '                        "description": (\n'
        '                            f"{_company_display}, ИНН {company_inn}  Заработная плата за "\n'
        '                            f"{month_name_nominative} {year}г. по Трудовому договору "\n'
        '                            f"№{_cn} от {_csd}"\n'
        '                        ),\n'
        '                        "amount": _net_partial,\n'
        '                        "currency": "RUR",\n'
        '                        "category": "Прочие операции",\n'
        '                    })\n'
        '                continue\n'
        '            _avans, _zarplata = _split_salary_employment(salary_rub)\n',
    ),
    # --- Самозанятый: пропорция дохода + период акта + НПД/KWIKPAY от факт. дохода ---
    (
        '        # 1. Поступление от Заказчика (~6 числа следующего месяца)\n'
        '        income_day = random.randint(5, 8)\n',
        '        # Pack 57.5 — самозанятый: доход месяца с пропорцией неполного первого/\n'
        '        # последнего месяца договора по КАЛЕНДАРНЫМ дням; НПД и KWIKPAY за месяц\n'
        '        # считаются от фактического дохода месяца.\n'
        '        from app.services.prod_calendar import prorate_calendar as _prorate_cal\n'
        '        _m_income = _prorate_cal(salary_rub, year, month, contract_sign_date, contract_end_date)\n'
        '        if _m_income <= 0:\n'
        '            continue  # месяц вне срока договора\n'
        '        _per_from = 1\n'
        '        if (contract_sign_date and contract_sign_date.year == year\n'
        '                and contract_sign_date.month == month and contract_sign_date.day > 1):\n'
        '            _per_from = contract_sign_date.day\n'
        '        _per_to = last_day\n'
        '        if (contract_end_date and contract_end_date.year == year\n'
        '                and contract_end_date.month == month and contract_end_date.day < last_day):\n'
        '            _per_to = contract_end_date.day\n'
        '        _m_tax = (_m_income * npd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)\n'
        '        _m_kwikpay = (_m_income - _m_tax - DEFAULT_KWIKPAY_RESERVE).quantize(\n'
        '            Decimal("0.01"), rounding=ROUND_HALF_UP)\n'
        '        # 1. Поступление от Заказчика (~6 числа следующего месяца)\n'
        '        income_day = random.randint(5, 8)\n',
    ),
    # период акта: 01.MM -> _per_from..._per_to
    (
        '                f"01.{month:02d}.{year}-{last_day:02d}.{month:02d}.{year}г., "\n',
        '                f"{_per_from:02d}.{month:02d}.{year}-{_per_to:02d}.{month:02d}.{year}г., "\n',
    ),
    # сумма дохода: salary_rub -> _m_income
    (
        '                "description": income_desc,\n'
        '                "amount": Decimal(salary_rub).quantize(Decimal("0.01")),\n',
        '                "description": income_desc,\n'
        '                "amount": _m_income.quantize(Decimal("0.01")),\n',
    ),
    # KWIKPAY от факт. дохода
    (
        'kwikpay_amount = (kwikpay_default + kwikpay_variation).quantize(',
        'kwikpay_amount = (_m_kwikpay + kwikpay_variation).quantize(',
    ),
    # НПД от факт. дохода
    (
        '                "amount": -tax_amount,\n',
        '                "amount": -_m_tax,\n',
    ),
]

MARKER = "Pack 57.5"


def patch_bank():
    if not os.path.exists(BANK):
        raise SystemExit("Не найден bank_statement_generator.py: " + BANK)
    raw = open(BANK, "rb").read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    norm = raw.replace("\r\n", "\n").replace("\r", "")
    if MARKER in norm:
        print("bank_statement_generator.py уже пропатчен — пропускаю.")
        return
    for i, (old, new) in enumerate(PATCHES, 1):
        cnt = norm.count(old)
        if cnt != 1:
            raise SystemExit("BANK PATCH %d: блок найден %d раз (ожидалось 1). Прерываю." % (i, cnt))
    open(BANK + ".bak", "wb").write(raw.encode("utf-8"))
    for old, new in PATCHES:
        norm = norm.replace(old, new, 1)
    open(BANK, "wb").write(norm.replace("\n", eol).encode("utf-8"))
    py_compile.compile(BANK, doraise=True)
    print("Пропатчен bank_statement_generator.py | бэкап .bak")


if __name__ == "__main__":
    ensure_calendar()
    patch_bank()
    print("py_compile: OK. Готово.")
