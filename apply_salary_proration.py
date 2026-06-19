"""
Pack 57 — пропорция неполного месяца приёма для зарплатных документов.
1) создаёт backend/app/services/prod_calendar.py (движок рабочих дней РФ);
2) патчит build_ndfl_2_context и build_payslip_context в context.py
   так, чтобы доход считался помесячно с пропорцией по рабочим дням.
Идемпотентно, с .bak бэкапом и py_compile-проверкой.
Кладётся в КОРЕНЬ репо, запуск:  python apply_salary_proration.py
"""
import os
import py_compile

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVICES = os.path.join(ROOT, "backend", "app", "services")
CONTEXT = os.path.join(ROOT, "backend", "app", "templates_engine", "context.py")
CAL_PATH = os.path.join(SERVICES, "prod_calendar.py")

PROD_CALENDAR_SRC = '''\
"""Производственный календарь РФ + пропорция неполного месяца (Pack 57).

Считает рабочие дни из набора нерабочих ДАТ (выходные вычисляются, праздники/
переносы — из набора). Годы без выверенного набора -> авто по статутным датам.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import calendar

# Нерабочие БУДНИ (сб/вс считаются отдельно). Выверено по календарю РФ.
_HOLIDAY_WEEKDAYS = {
    2026: {
        date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6),
        date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9),
        date(2026, 2, 23),
        date(2026, 3, 9),
        date(2026, 5, 1), date(2026, 5, 11),
        date(2026, 6, 12),
        date(2026, 11, 4),
        date(2026, 12, 31),
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
    """Гросс за месяц. Полный месяц -> полный оклад; неполный (приём/увольнение
    в середине) -> оклад * отработанные_раб_дни / раб_дни_месяца; вне найма -> 0."""
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
    return (salary * Decimal(worked) / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
'''

# ---- патчи context.py (OLD -> NEW), LF-форма ----
PATCHES = [
    # A: база + помесячный доход + итог в build_ndfl_2_context
    (
        '    # Сумма зарплаты в месяц\n'
        '    monthly_income = application.salary_rub or _D("0")\n'
        '    total_income = (monthly_income * _D(months_count)).quantize(_D("0.01"))\n'
        '    tax_base = total_income\n',
        '    # Сумма зарплаты в месяц (база — полный оклад)\n'
        '    monthly_income = application.salary_rub or _D("0")\n'
        '    # Pack 57: помесячный доход с пропорцией неполного месяца приёма/увольнения.\n'
        '    from app.services.prod_calendar import monthly_gross as _monthly_gross\n'
        '    _hire = application.contract_sign_date\n'
        '    _term = application.contract_end_date\n'
        '    _ndfl_per_month = []\n'
        '    for _m in range(period_from, period_to + 1):\n'
        '        _g = _monthly_gross(monthly_income, year, _m, _hire, _term) if monthly_income else _D("0")\n'
        '        if _g > 0:\n'
        '            _ndfl_per_month.append((_m, _g))\n'
        '    total_income = sum((g for _, g in _ndfl_per_month), _D("0")).quantize(_D("0.01"))\n'
        '    tax_base = total_income\n',
    ),
    # B: строки месяцев в build_ndfl_2_context
    (
        '    rows = []\n'
        '    for m in range(period_from, period_to + 1):\n'
        '        rows.append({\n'
        '            "month": f"{m:02d}",\n'
        '            "income_code": "2000",\n'
        '            "income_amount": _ndfl_2_fmt_money(monthly_income),\n'
        '            "deduction_code": "",\n'
        '            "deduction_amount": "",\n'
        '        })\n',
        '    rows = []\n'
        '    for _m, _g in _ndfl_per_month:\n'
        '        rows.append({\n'
        '            "month": f"{_m:02d}",\n'
        '            "income_code": "2000",\n'
        '            "income_amount": _ndfl_2_fmt_money(_g),\n'
        '            "deduction_code": "",\n'
        '            "deduction_amount": "",\n'
        '        })\n',
    ),
    # C: оклад в build_payslip_context -> пропорция
    (
        '    # 2. Оклад\n'
        '    salary = application.salary_rub if application.salary_rub else position.salary_rub_default\n'
        '    if salary is None:\n'
        '        salary = _Decimal("0")\n'
        '    salary_f = float(salary)\n',
        '    # 2. Оклад (база) + пропорция неполного месяца приёма (Pack 57)\n'
        '    _base = application.salary_rub if application.salary_rub else position.salary_rub_default\n'
        '    if _base is None:\n'
        '        _base = _Decimal("0")\n'
        '    from app.services.prod_calendar import monthly_gross as _monthly_gross\n'
        '    _hire = application.contract_sign_date\n'
        '    _term = application.contract_end_date\n'
        '    salary = _monthly_gross(_base, year, month, _hire, _term) if _base else _Decimal("0")\n'
        '    salary_f = float(salary)\n',
    ),
    # D: рабочие дни/часы в build_payslip_context -> фактические за месяц/приём
    (
        '    # 4. Рабочие дни/часы\n'
        '    working_days = _payslip_working_days(year, month)\n'
        '    working_hours = working_days * 8\n',
        '    # 4. Рабочие дни/часы (для месяца приёма — фактически отработанные). Pack 57.\n'
        '    from app.services.prod_calendar import working_days_in_range as _wdir\n'
        '    import calendar as _cal2\n'
        '    from datetime import date as _date2\n'
        '    _last = _cal2.monthrange(year, month)[1]\n'
        '    _ws = max(_date2(year, month, 1), _hire) if _hire else _date2(year, month, 1)\n'
        '    _we = min(_date2(year, month, _last), _term) if _term else _date2(year, month, _last)\n'
        '    working_days = _wdir(_ws, _we)\n'
        '    working_hours = working_days * 8\n',
    ),
    # E: нарастающий итог в build_payslip_context -> сумма помесячного гросса
    (
        '    # 5. Нарастающий итог — salary × месяц_в_году\n'
        '    # Дек 2025 → за 2025 год: salary × 12.\n'
        '    # Янв 2026 → за 2026 год: salary × 1.\n'
        '    # Фев 2026 → за 2026 год: salary × 2.\n'
        '    yearly_total = salary_f * month\n',
        '    # 5. Нарастающий итог — сумма помесячного гросса с начала года (Pack 57)\n'
        '    yearly_total = 0.0\n'
        '    for _ym in range(1, month + 1):\n'
        '        yearly_total += (float(_monthly_gross(_base, year, _ym, _hire, _term)) if _base else 0.0)\n',
    ),
]

MARKER = "Pack 57: помесячный доход"


def write_module():
    os.makedirs(SERVICES, exist_ok=True)
    if os.path.exists(CAL_PATH):
        cur = open(CAL_PATH, "r", encoding="utf-8").read()
        if "def monthly_gross" in cur:
            print("prod_calendar.py уже есть — пропускаю запись модуля.")
            return
    with open(CAL_PATH, "w", encoding="utf-8") as f:
        f.write(PROD_CALENDAR_SRC)
    py_compile.compile(CAL_PATH, doraise=True)
    print("Создан:", os.path.relpath(CAL_PATH, ROOT))


def patch_context():
    if not os.path.exists(CONTEXT):
        raise SystemExit("Не найден context.py: " + CONTEXT)
    raw = open(CONTEXT, "rb").read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    norm = raw.replace("\r\n", "\n").replace("\r", "")
    if MARKER in norm:
        print("context.py уже пропатчен — пропускаю.")
        return
    for i, (old, new) in enumerate(PATCHES, 1):
        cnt = norm.count(old)
        if cnt != 1:
            raise SystemExit("PATCH %d: старый блок найден %d раз (ожидалось 1). Прерываю, ничего не изменено." % (i, cnt))
    open(CONTEXT + ".bak", "wb").write(raw.encode("utf-8"))
    for old, new in PATCHES:
        norm = norm.replace(old, new, 1)
    out = norm.replace("\n", eol)
    open(CONTEXT, "wb").write(out.encode("utf-8"))
    py_compile.compile(CONTEXT, doraise=True)
    print("Пропатчен:", os.path.relpath(CONTEXT, ROOT), "| бэкап:", os.path.relpath(CONTEXT + ".bak", ROOT))


if __name__ == "__main__":
    write_module()
    patch_context()
    print("py_compile: OK. Готово.")
