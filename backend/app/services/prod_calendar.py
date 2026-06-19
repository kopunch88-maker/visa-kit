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
