"""
Pack 58 — реалистичный отток в банковской выписке.
Проблема: доход приходил и почти вся сумма сразу уходила ОДНИМ переводом
(KWIKPAY у самозанятого / крупные СБП у найма) — выглядит как транзит и вызывает
вопросы. Теперь расходы «как в жизни»: много мелких трат по категориям (продукты,
кафе, доставка, маркетплейсы, транспорт, АЗС, аптеки, ЖКХ), размазанных по всему
периоду, на суммарно ~50-70% прихода. Остаток копится — это нормально.
Применяется и к найму, и к самозанятым. Ставится ПОСЛЕ apply_bank_proration.py.
Идемпотентно, .bak, py_compile. В корень репо: python apply_bank_realistic_spend.py
"""
import os, py_compile

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(ROOT, "backend", "app", "services", "bank_statement_generator.py")
MARKER = "Pack 58"

EVERYDAY_CONST = '''

# Pack 58 — бытовые траты (карта/СБП): много мелких операций для реалистичной
# выписки, чтобы деньги не «сливались» одним переводом. (label, [мерчанты], min, max).
EVERYDAY_SPEND = [
    ("Продукты", ["Магнит", "Пятёрочка", "Перекрёсток", "ВкусВилл", "Лента", "Ашан", "Дикси"], 700, 6500),
    ("Кафе и рестораны", ["Кофейня", "Ресторан", "Шоколадница", "Додо Пицца", "Кафе"], 500, 4500),
    ("Доставка еды", ["Яндекс.Еда", "Самокат", "Купер", "Кухня на районе"], 600, 3800),
    ("Маркетплейсы", ["OZON", "Wildberries", "Яндекс Маркет", "Мегамаркет"], 900, 16000),
    ("Транспорт", ["Яндекс.Такси", "Метрополитен", "Ситидрайв", "Транспортная карта"], 250, 1800),
    ("АЗС", ["АЗС Лукойл", "АЗС Газпромнефть", "АЗС Роснефть"], 1500, 4500),
    ("Аптеки", ["Аптека Ригла", "Аптека 36,6", "Здравсити"], 350, 2800),
    ("ЖКХ и связь", ["ЖКУ", "МТС", "Билайн", "Ростелеком", "МегаФон"], 600, 9000),
]

'''

EVERYDAY_GEN = '''    self_phone = _resolve_self_phone_for_sbp(applicant_phone)
    self_phone_masked = _format_ru_phone_masked(self_phone)
    self_short_name = _short_name_for_sbp(applicant_full_name_ru)

    # Pack 58: расходы «как в жизни» — крупные регулярные статьи (аренда, переводы
    # на накопительный счёт) + мелкие бытовые траты по категориям, размазанные по
    # всему периоду. Цель — суммарный отток ~45-60% прихода: деньги не «сливаются»
    # одним переводом сразу после поступления, но и не копятся нереалистично.
    _ev_income = sum((t["amount"] for t in transactions if t["amount"] > 0), Decimal("0.00"))
    _ev_spent = sum((-t["amount"] for t in transactions if t["amount"] < 0), Decimal("0.00"))
    _ev_ratio = Decimal(str(round(random.uniform(0.45, 0.60), 4)))
    _ev_budget = (_ev_income * _ev_ratio).quantize(Decimal("0.01")) - _ev_spent
    _ev_days = max(1, (period_end - period_start).days)
    _ev_cap = max(0, round(6 * _ev_days / 30.0))
    _ev_n = 0

    # (1) Аренда жилья — ежемесячно (крупная регулярная статья, ~3-10 числа).
    _rm_y, _rm_m = period_start.year, period_start.month
    while date(_rm_y, _rm_m, 1) <= period_end and _ev_budget > Decimal("2000") and _ev_n < _ev_cap:
        try:
            _rent_date = _adjust_to_business_day(date(_rm_y, _rm_m, random.randint(3, 10)))
        except ValueError:
            _rent_date = None
        if _rent_date and period_start <= _rent_date <= period_end:
            _rent = Decimal(f"{random.randint(45000, 92000)}.{random.randint(0, 99):02d}")
            if _rent > _ev_budget:
                _rent = _ev_budget.quantize(Decimal("0.01"))
            if _rent >= Decimal("2000"):
                transactions.append({
                    "transaction_date": _rent_date, "code": _gen_payment_code(),
                    "description": "Оплата аренды жилья по договору найма.",
                    "amount": -_rent, "currency": "RUR", "category": "Прочие операции"})
                _ev_budget -= _rent
                _ev_n += 1
        if _rm_m == 12:
            _rm_y, _rm_m = _rm_y + 1, 1
        else:
            _rm_m += 1

    # (2) Переводы на накопительный/СБП себе + бытовые траты, размазаны по периоду.
    _ev_tries = 0
    while _ev_budget > Decimal("1500") and _ev_n < _ev_cap and _ev_tries < _ev_cap * 6 + 10:
        _ev_tries += 1
        _ev_date = _adjust_to_business_day(
            period_start + timedelta(days=random.randint(0, _ev_days)))
        if _ev_date > period_end:
            continue
        if _ev_budget > Decimal("50000") and random.random() < 0.5:
            _ev_hi = int(min(Decimal("90000"), _ev_budget))
            _ev_amt = Decimal(f"{random.randint(40000, max(40001, _ev_hi))}.{random.randint(0, 99):02d}")
            if random.random() < 0.5:
                _ev_desc = "Перевод между своими счетами. Пополнение накопительного счёта."
                _ev_code = _gen_payment_code()
                _ev_cat = "Перевод СБП"
            else:
                _ev_desc = (f"Перевод по СБП. Получатель: {self_short_name}\\n"
                            f"Тинькофф Банк, {self_phone_masked}")
                _ev_code = _gen_sbp_code()
                _ev_cat = "Перевод СБП"
        else:
            _ev_label, _ev_merchants, _ev_lo, _ev_hi2 = random.choice(EVERYDAY_SPEND)
            _ev_amt = Decimal(f"{random.randint(_ev_lo, _ev_hi2)}.{random.randint(0, 99):02d}")
            _ev_desc = f"Оплата товаров и услуг. {random.choice(_ev_merchants)}"
            _ev_code = _gen_payment_code()
            _ev_cat = "Прочие операции"
        if _ev_amt > _ev_budget:
            _ev_amt = _ev_budget.quantize(Decimal("0.01"))
            if _ev_amt < Decimal("300"):
                break
        transactions.append({
            "transaction_date": _ev_date, "code": _ev_code, "description": _ev_desc,
            "amount": -_ev_amt, "currency": "RUR", "category": _ev_cat})
        _ev_budget -= _ev_amt
        _ev_n += 1
'''

# KWIKPAY-блок целиком (как в файле после Pack 57.5) — удаляем.
KWIKPAY_OLD = (
    '        # 2. KWIKPAY (~10-15 числа того же месяца, в котором пришла зарплата)\n'
    '        kwikpay_day = random.randint(10, 15)\n'
    '        try:\n'
    '            kwikpay_date = _adjust_to_business_day(date(next_y, next_m, kwikpay_day))\n'
    '        except ValueError:\n'
    '            kwikpay_date = None\n'
    '        if kwikpay_date and period_start <= kwikpay_date <= period_end:\n'
    '            # \u00b110% \u0432\u0430\u0440\u0438\u0430\u0446\u0438\u044f\n'
    '            kwikpay_variation = Decimal(random.randint(-10000, 10000))\n'
    '            kwikpay_amount = (_m_kwikpay + kwikpay_variation).quantize(\n'
    '                Decimal("0.01"), rounding=ROUND_HALF_UP\n'
    '            )\n'
    '            transactions.append({\n'
    '                "transaction_date": kwikpay_date,\n'
    '                "code": _gen_payment_code(),\n'
    '                "description": "\u041f\u0435\u0440\u0435\u0432\u043e\u0434   JSC*KWIKPAY online.",\n'
    '                "amount": -kwikpay_amount,\n'
    '                "currency": "RUR",\n'
    '                "category": "\u041f\u0440\u043e\u0447\u0438\u0435 \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u0438",\n'
    '            })\n\n'
)
KWIKPAY_NEW = (
    '        # Pack 58: KWIKPAY-«слив» убран — отток теперь размазан бытовыми тратами ниже.\n\n'
)

# Старый СБП-блок (вместе с шапкой self_phone) → бытовой генератор
SBP_OLD = (
    '    self_phone = _resolve_self_phone_for_sbp(applicant_phone)\n'
    '    self_phone_masked = _format_ru_phone_masked(self_phone)\n'
    '    self_short_name = _short_name_for_sbp(applicant_full_name_ru)\n'
    '\n\n'
    '    # Pack 51: scale \u043d\u0430 \u0434\u043b\u0438\u043d\u0443 \u043f\u0435\u0440\u0438\u043e\u0434\u0430 (baseline 90 \u0434\u043d\u0435\u0439 = 3-8). \u0414\u043b\u044f \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0445\n'
    '    # append-\u043f\u0435\u0440\u0438\u043e\u0434\u043e\u0432 \u044d\u0442\u043e \u0434\u0430\u0451\u0442 \u043f\u0440\u043e\u043f\u043e\u0440\u0446\u0438\u043e\u043d\u0430\u043b\u044c\u043d\u043e \u043c\u0435\u043d\u044c\u0448\u0435 \u0421\u0411\u041f-\u043f\u0435\u0440\u0435\u0432\u043e\u0434\u043e\u0432.\n'
    '    _sbp_scale = max(1, (period_end - period_start).days + 1) / 90.0\n'
    '    _sbp_min = max(0, round(3 * _sbp_scale))\n'
    '    _sbp_max = max(_sbp_min, round(8 * _sbp_scale))\n'
    '    sbp_count_total = random.randint(_sbp_min, _sbp_max) if _sbp_max > 0 else 0\n'
    '    for _ in range(sbp_count_total):\n'
    '        # \u0421\u043b\u0443\u0447\u0430\u0439\u043d\u0430\u044f \u0434\u0430\u0442\u0430 \u0432\u043d\u0443\u0442\u0440\u0438 \u043f\u0435\u0440\u0438\u043e\u0434\u0430\n'
    '        delta_days = random.randint(0, (period_end - period_start).days)\n'
    '        sbp_date = _adjust_to_business_day(period_start + timedelta(days=delta_days))\n'
    '        if sbp_date > period_end:\n'
    '            continue\n'
    '        # \u0421\u0443\u043c\u043c\u0430 5000.00 - 60000.00 \u0441 \u043a\u043e\u043f\u0435\u0439\u043a\u0430\u043c\u0438\n'
    '        rub = random.randint(5000, 60000)\n'
    '        kop = random.randint(0, 99)\n'
    '        sbp_amount = Decimal(f"{rub}.{kop:02d}")\n'
    '        sbp_desc = (\n'
    '            f"\u041f\u0435\u0440\u0435\u0432\u043e\u0434 \u043f\u043e \u0421\u0411\u041f. \u041f\u043e\u043b\u0443\u0447\u0430\u0442\u0435\u043b\u044c: {self_short_name}\\n"\n'
    '            f"\u0422\u0438\u043d\u044c\u043a\u043e\u0444\u0444 \u0411\u0430\u043d\u043a, {self_phone_masked}"\n'
    '        )\n'
    '        transactions.append({\n'
    '            "transaction_date": sbp_date,\n'
    '            "code": _gen_sbp_code(),\n'
    '            "description": sbp_desc,\n'
    '            "amount": -sbp_amount,\n'
    '            "currency": "RUR",\n'
    '            "category": "\u041f\u0435\u0440\u0435\u0432\u043e\u0434 \u0421\u0411\u041f",\n'
    '        })\n'
)

PATCHES = [
    # P1 — константа EVERYDAY_SPEND после ONLINE_SERVICES
    (
        'Decimal("990.00")]),\n]\n',
        'Decimal("990.00")]),\n]\n' + EVERYDAY_CONST,
    ),
    # P2 — удаляем KWIKPAY
    (KWIKPAY_OLD, KWIKPAY_NEW),
    # P3 — СБП-блок → бытовой генератор
    (SBP_OLD, EVERYDAY_GEN),
    # P4 — меньше подписок (баланс «жизни» теперь дают бытовые траты)
    ('_subs_min = max(0, round(10 * _subs_scale))', '_subs_min = max(0, round(6 * _subs_scale))'),
    ('_subs_max = max(_subs_min, round(20 * _subs_scale))', '_subs_max = max(_subs_min, round(12 * _subs_scale))'),
]


def main():
    if not os.path.exists(BANK):
        raise SystemExit("Не найден bank_statement_generator.py: " + BANK)
    raw = open(BANK, "rb").read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    norm = raw.replace("\r\n", "\n").replace("\r", "")
    if MARKER in norm:
        print("Pack 58 уже применён — пропускаю.")
        return
    for i, (old, new) in enumerate(PATCHES, 1):
        c = norm.count(old)
        if c != 1:
            raise SystemExit("PATCH %d: блок найден %d раз (ожидалось 1). Прерываю." % (i, c))
    open(BANK + ".bak58", "wb").write(raw.encode("utf-8"))
    for old, new in PATCHES:
        norm = norm.replace(old, new, 1)
    open(BANK, "wb").write(norm.replace("\n", eol).encode("utf-8"))
    py_compile.compile(BANK, doraise=True)
    print("Pack 58 применён | бэкап .bak58 | py_compile OK")


if __name__ == "__main__":
    main()
