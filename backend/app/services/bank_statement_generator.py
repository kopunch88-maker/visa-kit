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

# ============================================================================
# Pack 34.4 — сокращение ОПФ для поля "Плательщик" в выписке
# ============================================================================
# Реальные банки (в т.ч. Альфа-Банк по официальным правилам Form Rule)
# принимают как полное, так и сокращённое наименование юр.лица в платёжках,
# и сокращённое — стандартная практика. Эталон выписки Алиева использует
# «ООО "Строительная компания СК10"», а не «Общество с ограниченной...».
# Для новых компаний с длинным брендовым именем (РЕНКОНС ХЭВИ ИНДАСТРИС)
# полная форма не влезает в одну строку ячейки и Word ломает выравнивание.
# Решение — детерминированное сокращение ОПФ только для поля «Плательщик»
# в банковской выписке. В договоре/актах/счетах используется по-прежнему
# полное юридическое название (там оно обязательно).

_OPF_SHORTEN_MAP = [
    # Порядок важен: более длинные паттерны раньше, чтобы «Непубличное АО»
    # не схватилось правилом для «Акционерное общество».
    (r"^\s*Непубличное\s+акционерное\s+общество\s+", "НАО "),
    (r"^\s*Публичное\s+акционерное\s+общество\s+", "ПАО "),
    (r"^\s*Закрытое\s+акционерное\s+общество\s+", "ЗАО "),
    (r"^\s*Открытое\s+акционерное\s+общество\s+", "ОАО "),
    (r"^\s*Общество\s+с\s+ограниченной\s+ответственностью\s+", "ООО "),
    (r"^\s*Акционерное\s+общество\s+", "АО "),
    (r"^\s*Индивидуальный\s+предприниматель\s+", "ИП "),
]


def _shorten_opf(full_name: str) -> str:
    """
    Сокращает организационно-правовую форму в начале названия компании.

    >>> _shorten_opf('Общество с ограниченной ответственностью "РЕНКОНС ХЭВИ ИНДАСТРИС"')
    'ООО "РЕНКОНС ХЭВИ ИНДАСТРИС"'
    >>> _shorten_opf('Публичное акционерное общество "Газпром"')
    'ПАО "Газпром"'
    >>> _shorten_opf('ИП Иванов И.И.')
    'ИП Иванов И.И.'
    >>> _shorten_opf('Sociedad de Responsabilidad Limitada "X"')
    'Sociedad de Responsabilidad Limitada "X"'
    >>> _shorten_opf('')
    ''
    """
    if not full_name:
        return full_name
    for pattern, replacement in _OPF_SHORTEN_MAP:
        new_name, count = re.subn(pattern, replacement, full_name, count=1, flags=re.IGNORECASE)
        if count:
            return new_name
    return full_name



def _gen_credit_code() -> str:
    return "C16" + "".join(random.choices(string.digits, k=13))


def _gen_payment_code() -> str:
    # Кириллическая С — как в реальных выписках Альфы.
    # Pack 59.3: 16 символов (12 цифр), иначе 17-символьный код переносится
    # на 2-ю строку в узкой колонке ЧБ-шаблона.
    return "С011" + "".join(random.choices(string.digits, k=12))


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


def _adjust_to_previous_business_day(d: date) -> date:
    """Pack 35.0: если дата выпала на выходной, сдвигаем НАЗАД на ближайший будний.
    Используется для НПД — налоговая практика: «успеть до 22-го» означает уплатить
    в последний рабочий день до 22-го, а не позже."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
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


# ============================================================================
# Pack 73.1 — распределение зарплатной выплаты по правилу 30/50-65/5-20
# ============================================================================
#
# После каждой зарплатной выплаты (НАЙМ: аванс+зарплата; самозанятый: поступление
# от заказчика) генератор создаёт «дочерние» операции:
#   1) 30% жёстко → перевод на накопительный счёт (одна операция, +1..3 дня).
#   2) 50-65% плавающее → N карточных операций (магазины/кафе/АЗС/...) с разными
#      MCC, описаниями и суммами, распределённые равномерно от salary_date+1
#      до next_salary_date (или до конца периода если зарплата последняя).
#   3) Остаток 5-20% копится — не списывается, остаётся на счёте.
#
# Карточные операции используют формат описания Альфы:
#   "Операция по карте: 220015++++++8073, на сумму: 475.00 RUR, дата совершения
#    операции: 31.03.26, место совершения операции: 33210835\\RU\\Moscow\\
#    MAGNIT MM ASTRA MCC5411"
# Для Сбера / ТБанка bank-specific постпроцессоры переформатируют отображение,
# а category из tx используется как отдельная колонка в шаблоне Сбера.

# Категории карточных трат: (weight_pct, mcc, category_label_sber, sellers, (amt_min, amt_max))
_CARD_CATEGORIES = [
    (35, "5411", "Супермаркеты", [
        "MAGNIT MM", "MAGNIT GM", "MAGNIT KOSMETIK", "PYATEROCHKA",
        "PEREKRESTOK", "LENTA", "VKUSVILL", "DIXY", "MIRATORG", "FIX PRICE",
    ], (250, 4500)),
    (12, "5812", "Кафе и рестораны", [
        "RESTAURANT CHAYHANA", "CAFE SHOKOLADNITSA", "CAFE TRAVELERS COFFEE",
        "PIZZERIA DODO", "RESTORAN GRUZIYA", "CAFE COFFEE LIKE",
    ], (400, 3500)),
    (8, "5814", "Фастфуд", [
        "VKUSNO I TOCHKA", "KFC", "BURGER KING", "DODO PIZZA",
        "STARS COFFEE", "TEREMOK", "SUBWAY",
    ], (250, 1500)),
    (12, "5541", "Авто", [
        "AZS GAZPROMNEFT 142", "AZS LUKOIL 234", "AZS ROSNEFT 112",
        "AZS TATNEFT 089", "AZS SHELL 56", "AZS NESTE",
    ], (1500, 4500)),
    (5, "5912", "Аптеки", [
        "APTEKA 36.6", "APTEKA RIGLA", "APTEKA STOLICHKI", "APTEKA ASNA", "APTEKA APREL",
    ], (300, 2500)),
    (10, "6011", "Снятие наличных", [
        "ATM 00227620", "ATM 00115221", "ATM 00982341", "ATM 00564382",
    ], (5000, 30000)),
    (4, "4900", "Услуги связи", [
        "BEELINE", "MTS", "MEGAFON", "TELE2",
    ], (300, 1500)),
    (4, "5732", "Электроника", [
        "DNS", "M.VIDEO", "CITILINK", "ELDORADO", "RE-STORE",
    ], (1500, 25000)),
    (5, "4121", "Транспорт", [
        "YANDEX TAXI", "CITYMOBIL", "WHEELY", "METRO MOSCOW", "MOSGORTRANS",
    ], (200, 1500)),
    (3, "5499", "Магазины", [
        "OZON RU", "WILDBERRIES", "DETSKY MIR", "L ETOILE", "AROMA SOMMELYE",
    ], (500, 8000)),
    (2, "7997", "Развлечения", [
        "KINOTEATR FORMULA KINO", "OOO RAZVLECHENIYA", "MTS LIVE",
        "PARK GORKOGO", "PUSHKINSKY MUZEY",
    ], (300, 3000)),
]


def _weighted_choice_card_category(rng):
    """Возвращает одну категорию из _CARD_CATEGORIES по weight."""
    total_w = sum(c[0] for c in _CARD_CATEGORIES)
    r = rng.random() * total_w
    upto = 0.0
    for cat in _CARD_CATEGORIES:
        upto += cat[0]
        if upto >= r:
            return cat
    return _CARD_CATEGORIES[-1]


def _resolve_card_last4(
    card_number: Optional[str],
    bank_account: Optional[str],
) -> str:
    """Pack 73.1: 4 цифры карты для описаний.

    Приоритет: applicant.card_number (если задан) → fallback на hash bank_account
    (детерм., как у ТБанка сейчас). Если оба пусты — "0000".
    """
    if card_number:
        digits = re.sub(r"\D", "", card_number)
        if len(digits) >= 4:
            return digits[-4:]
    if not bank_account:
        return "0000"
    import hashlib
    digest = hashlib.sha1(bank_account.encode("utf-8")).hexdigest()
    return f"{int(digest[:8], 16) % 10000:04d}"


def _resolve_card_bin6(
    card_number: Optional[str],
    bank_bik: Optional[str],
) -> str:
    """Pack 73.1: 6 цифр BIN карты для описаний (Альфа-формат "220015++++++XXXX").

    Приоритет: первые 6 цифр applicant.card_number → дефолт по BIK банка.
    """
    if card_number:
        digits = re.sub(r"\D", "", card_number)
        if len(digits) >= 6:
            return digits[:6]
    # Дефолты по BIK
    if bank_bik == "044525225":   # Сбер
        return "427601"
    if bank_bik == "044525974":   # ТБанк
        return "220070"
    return "220015"  # Альфа / дефолт


def _generate_savings_account_last4(
    applicant_id: Optional[int],
    bank_bik: Optional[str],
) -> str:
    """Pack 73.1: 4 цифры накопительного счёта (детерм. по applicant.id + bik).

    Накопит-счёт не хранится в БД, всегда генерится на лету. Между разными
    рендерами одной и той же выписки 4 цифры стабильны.
    """
    if not applicant_id:
        return "0000"
    import hashlib
    seed = f"savings:{applicant_id}:{bank_bik or ''}".encode("utf-8")
    digest = hashlib.sha1(seed).hexdigest()
    return f"{int(digest[:8], 16) % 10000:04d}"


def _make_card_tx_description(
    bin6: str,
    card_last4: str,
    amount: Decimal,
    tx_date: date,
    mcc: str,
    seller: str,
    city: str,
    rng,
) -> str:
    """Формат описания карточной операции в стиле Альфы.

    Эталон: "Операция по карте: 220015++++++8073, на сумму: 475.00 RUR,
    дата совершения операции: 31.03.26, место совершения операции:
    33210835\\RU\\Omsk\\MAGNIT MM LAMBERT MCC5411"
    """
    amt_str = f"{amount:.2f}"
    date_str = tx_date.strftime("%d.%m.%y")
    op_code = f"{rng.randint(10000000, 99999999)}"
    return (
        f"Операция по карте: {bin6}++++++{card_last4}, "
        f"на сумму: {amt_str} RUR, "
        f"дата совершения операции: {date_str}, "
        f"место совершения операции: {op_code}\\RU\\{city}\\{seller} MCC{mcc}"
    )


def _distribute_card_budget(
    card_budget: Decimal,
    rng,
) -> list:
    """Разбивает бюджет карточных трат на N операций реалистичных сумм.

    N = 10..30 в зависимости от размера бюджета. Каждая операция — случайная
    доля от оставшегося, ограничена снизу 200 RUR. Последняя tx подгоняет
    сумму так чтобы Σ == card_budget точно (до копейки).
    """
    if card_budget <= 0:
        return []
    # Целевое количество операций — из расчёта средней суммы ~1500-2500 RUR
    avg_tx = Decimal(rng.randint(1500, 2500))
    target_n = int(card_budget / avg_tx)
    target_n = max(10, min(35, target_n))

    amounts = []
    remaining = card_budget
    for i in range(target_n - 1):
        # Случайная доля от оставшегося, с разбросом ±60%
        slots_left = target_n - i
        avg_slot = remaining / Decimal(slots_left)
        lo = float(avg_slot) * 0.4
        hi = float(avg_slot) * 1.6
        slice_val = Decimal(f"{rng.uniform(max(lo, 200.0), hi):.2f}")
        if slice_val < Decimal("200"):
            slice_val = Decimal("200.00")
        if slice_val > remaining - Decimal("200") * Decimal(slots_left - 1):
            slice_val = max(Decimal("200.00"), remaining - Decimal("200") * Decimal(slots_left - 1))
        amounts.append(slice_val)
        remaining -= slice_val
        if remaining < Decimal("200"):
            break

    if remaining > 0:
        amounts.append(remaining.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return amounts


def _distribute_salary_30_50_15(
    *,
    salary_date: date,
    salary_amount: Decimal,
    next_payout_date: Optional[date],
    period_start: date,
    period_end: date,
    applicant_id: Optional[int],
    card_number: Optional[str],
    bank_account: Optional[str],
    bank_bik: Optional[str],
    city: str,
    rng,
) -> list:
    """Pack 73.1: распределение зарплатной выплаты по правилу 30/50-65/5-20.

    Возвращает список tx-dict'ов (готовы для transactions.append):
      - 1 операция: 30% → накопительный счёт (через 1-3 дня)
      - N операций (10-30): 50-65% → карточные траты (равномерно
        salary_date+1 .. next_payout_date-1, ограничено period_end)
      - остаток 5-20% не генерится — копится на счёте.

    Все операции с amount < 0 (расход). Все даты гарантированно внутри
    [period_start, period_end] — внешние отфильтруются hard-фильтром позже.
    """
    out = []
    if salary_amount <= 0:
        return out

    # === 30% → накопительный счёт ===
    savings_amount = (salary_amount * Decimal("0.30")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    savings_offset = rng.randint(1, 3)
    try:
        savings_date = _adjust_to_business_day(
            salary_date + timedelta(days=savings_offset)
        )
    except (ValueError, OverflowError):
        savings_date = None
    if savings_date and period_start <= savings_date <= period_end:
        savings_last4 = _generate_savings_account_last4(applicant_id, bank_bik)
        out.append({
            "transaction_date": savings_date,
            "code": _gen_payment_code(),
            "description": f"Перевод между своими счетами на накопительный счёт *{savings_last4}",
            "amount": -savings_amount,
            "currency": "RUR",
            "category": "Между своими счетами",
        })

    # === 50-65% → карточные операции ===
    card_pct = Decimal(f"{rng.uniform(0.50, 0.65):.4f}")
    card_budget = (salary_amount * card_pct).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # Окно распределения дат
    window_start = max(salary_date + timedelta(days=1), period_start)
    if next_payout_date is not None:
        window_end = min(next_payout_date - timedelta(days=1), period_end)
    else:
        window_end = period_end
    # Если окно слишком узкое (< 7 дней) — расширим до period_end
    if (window_end - window_start).days < 7:
        window_end = period_end
    if window_end < window_start:
        return out  # некуда ставить
    window_days = (window_end - window_start).days + 1

    bin6 = _resolve_card_bin6(card_number, bank_bik)
    card_last4 = _resolve_card_last4(card_number, bank_account)

    amounts = _distribute_card_budget(card_budget, rng)
    for amt in amounts:
        if amt <= 0:
            continue
        tx_date = window_start + timedelta(days=rng.randint(0, window_days - 1))
        if not (period_start <= tx_date <= period_end):
            continue
        cat = _weighted_choice_card_category(rng)
        _, mcc, category_label, sellers, _amt_range = cat
        seller = rng.choice(sellers)
        out.append({
            "transaction_date": tx_date,
            "code": _gen_payment_code(),
            "description": _make_card_tx_description(
                bin6, card_last4, amt, tx_date, mcc, seller, city, rng,
            ),
            "amount": -amt,
            "currency": "RUR",
            "category": category_label,
        })

    return out


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

def _split_salary_employment(gross_salary):
    """Pack 50.30 — грязный оклад → (аванс, зарплата) на руки для НАЙМА.

    на_руки = оклад * 0.87 (минус 13% НДФЛ);
    аванс ≈ 40%, округлён вниз до 10 тыс (реалистично, как у эталона);
    зарплата = остаток. Эталон: 310000 → 269700 → 100000 + 169700.
    """
    from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
    na_ruki = (Decimal(gross_salary) * Decimal("0.87")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    avans = (na_ruki * Decimal("0.40") / 10000).quantize(
        Decimal("1"), rounding=ROUND_DOWN) * 10000
    zarplata = (na_ruki - avans).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return avans, zarplata


def generate_default_transactions(
    *,
    submission_date: date,
    salary_rub: Decimal,
    contract_number: str,
    contract_sign_date: date,
    contract_end_date: Optional[date] = None,  # Pack 57.5
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
    is_employment: bool = False,  # Pack 50.30
    # Pack 51 — append-режим: явный период перекрывает statement_date-расчёт.
    # Используется через POST /bank-transactions/append для до-генерации
    # суб-периода поверх существующего bank_transactions_override.
    period_start_override: Optional[date] = None,
    period_end_override: Optional[date] = None,
    # Pack 73.1 — новые опциональные параметры для модели 30/50/15
    applicant_id_for_savings: Optional[int] = None,
    applicant_card_number: Optional[str] = None,
    applicant_bank_account: Optional[str] = None,
    bank_bik: Optional[str] = None,
    applicant_city: Optional[str] = None,
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

    # Pack 25.11: period_end = statement_date - 1 день (как реально делают банки).
    # Пример: дата формирования 06.05 → период 06.02..05.05 (3 мес минус 1 день).
    # Pack 51: если задан явный период [start, end] — используем его вместо
    # statement_date-расчёта. Нужно для до-генерации суб-периода (append-режим).
    if period_start_override is not None and period_end_override is not None:
        period_start = period_start_override
        period_end = period_end_override
    else:
        period_end = statement_date - timedelta(days=1)
        period_start = (statement_date - relativedelta(months=period_months))

    # Налог и сумма перевода KWIKPAY (с копейками)
    tax_amount = (Decimal(salary_rub) * npd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    kwikpay_default = (Decimal(salary_rub) - tax_amount - DEFAULT_KWIKPAY_RESERVE)
    kwikpay_default = kwikpay_default.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Определяем месяцы внутри периода (для генерации зарплат / налогов / комиссий).
    # Pack 35.0: стартуем с ПРЕДЫДУЩЕГО месяца к period_start. Причина — доход за
    # месяц X приходит в (X+1), НПД за X платится в (X+1), комиссия в (X+2). Если
    # начинать перебор с месяца period_start — теряем месяц X-1, чьи производные
    # транзакции (доход/НПД) уже попадают в начало периода. Лишние месяцы хвоста
    # и головы отфильтруются по `if period_start <= date <= period_end` дальше.
    months = []
    # Pack 35.5: сдвигаем на 1 месяц назад от period_start ТОЛЬКО если
    # contract_sign_date < period_start. Логика: если договор подписан ДО
    # начала периода — производные транзакции за месяц «X-1» могут
    # попасть в начало периода (доход X-1 приходит ~6 числа period_start).
    # Если договор подписан ВНУТРИ периода — никаких актов за X-1 быть не
    # может (договора ещё не было), стартуем от месяца contract_sign_date.
    if contract_sign_date and contract_sign_date < period_start:
        # Pack 35.0 логика — для договоров подписанных ДО начала периода
        _start = period_start
        if _start.month == 1:
            cur = date(_start.year - 1, 12, 1)
        else:
            cur = date(_start.year, _start.month - 1, 1)
    else:
        # Pack 35.5: договор внутри периода — стартуем с месяца подписания
        _csd = contract_sign_date or period_start
        cur = date(_csd.year, _csd.month, 1)
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

        next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)

        # Pack 50.30 — НАЙМ: аванс (текущий месяц) + зарплата (следующий месяц),
        # без НПД/KWIKPAY/комиссии. Самозанятый идёт прежним путём ниже.
        if is_employment:
            _company_display = _shorten_opf(company_full_name)
            _cn = contract_number or ""
            _csd = contract_sign_date.strftime("%d.%m.%Y") if contract_sign_date else ""
            # Pack 57.5: гросс месяца с пропорцией неполного месяца приёма/увольнения.
            from app.services.prod_calendar import monthly_gross as _monthly_gross
            _m_gross = _monthly_gross(salary_rub, year, month, contract_sign_date, contract_end_date)
            if _m_gross <= 0:
                continue  # месяц вне срока трудоустройства — выплат нет
            _full_gross = _monthly_gross(salary_rub, year, month, None, None)
            if _m_gross < _full_gross:
                # Неполный месяц приёма/увольнения: одна выплата зарплатой (без аванса),
                # на руки = гросс * 0.87 (минус 13% НДФЛ).
                _net_partial = (_m_gross * Decimal("0.87")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP)
                _zp_day = random.randint(5, 9)
                try:
                    _zp_date = _adjust_to_business_day(date(next_y, next_m, _zp_day))
                except ValueError:
                    _zp_date = None
                if _zp_date and period_start <= _zp_date <= period_end:
                    transactions.append({
                        "transaction_date": _zp_date,
                        "code": _gen_credit_code(),
                        "description": (
                            f"{_company_display}, ИНН {company_inn}  Заработная плата за "
                            f"{month_name_nominative} {year}г. по Трудовому договору "
                            f"№{_cn} от {_csd}"
                        ),
                        "amount": _net_partial,
                        "currency": "RUR",
                        "category": "Прочие операции",
                    })
                continue
            _avans, _zarplata = _split_salary_employment(salary_rub)
            # Аванс — 20-25 число ТЕКУЩЕГО месяца (year, month)
            _av_day = random.randint(20, 25)
            try:
                _av_date = _adjust_to_business_day(date(year, month, _av_day))
            except ValueError:
                _av_date = None
            if _av_date and period_start <= _av_date <= period_end:
                transactions.append({
                    "transaction_date": _av_date,
                    "code": _gen_credit_code(),
                    "description": (
                        f"{_company_display}, ИНН {company_inn}  Аванс за "
                        f"{month_name_nominative} {year}г. по Трудовому договору "
                        f"№{_cn} от {_csd}"
                    ),
                    "amount": _avans.quantize(Decimal("0.01")),
                    "currency": "RUR",
                    "category": "Прочие операции",
                })
                # Pack 73.1 — распределение аванса 30/50-65/5-20%
                # next_payout_date = ожидаемая дата зарплаты (5-9 число next month)
                _av_next_payout = date(next_y, next_m, 7)
                transactions.extend(_distribute_salary_30_50_15(
                    salary_date=_av_date,
                    salary_amount=_avans.quantize(Decimal("0.01")),
                    next_payout_date=_av_next_payout,
                    period_start=period_start,
                    period_end=period_end,
                    applicant_id=applicant_id_for_savings,
                    card_number=applicant_card_number,
                    bank_account=applicant_bank_account,
                    bank_bik=bank_bik,
                    city=applicant_city or "Moscow",
                    rng=random,
                ))
            # Зарплата — 5-9 число СЛЕДУЮЩЕГО месяца (next_y, next_m)
            _zp_day = random.randint(5, 9)
            try:
                _zp_date = _adjust_to_business_day(date(next_y, next_m, _zp_day))
            except ValueError:
                _zp_date = None
            if _zp_date and period_start <= _zp_date <= period_end:
                transactions.append({
                    "transaction_date": _zp_date,
                    "code": _gen_credit_code(),
                    "description": (
                        f"{_company_display}, ИНН {company_inn}  Заработная плата за "
                        f"{month_name_nominative} {year}г. по Трудовому договору "
                        f"№{_cn} от {_csd}"
                    ),
                    "amount": _zarplata.quantize(Decimal("0.01")),
                    "currency": "RUR",
                    "category": "Прочие операции",
                })
                # Pack 73.1 — распределение зарплаты 30/50-65/5-20%
                # next_payout_date = ожидаемая дата следующего аванса (20 число next month)
                _next_m2_y = next_y if next_m < 12 else next_y + 1
                _next_m2_m = next_m + 1 if next_m < 12 else 1
                try:
                    _zp_next_payout = date(_next_m2_y, _next_m2_m, 22)
                except ValueError:
                    _zp_next_payout = None
                transactions.extend(_distribute_salary_30_50_15(
                    salary_date=_zp_date,
                    salary_amount=_zarplata.quantize(Decimal("0.01")),
                    next_payout_date=_zp_next_payout,
                    period_start=period_start,
                    period_end=period_end,
                    applicant_id=applicant_id_for_savings,
                    card_number=applicant_card_number,
                    bank_account=applicant_bank_account,
                    bank_bik=bank_bik,
                    city=applicant_city or "Moscow",
                    rng=random,
                ))
            continue  # найм: пропускаем KWIKPAY/НПД/комиссию

        # Pack 57.5 — самозанятый: доход месяца с пропорцией неполного первого/
        # последнего месяца договора по КАЛЕНДАРНЫМ дням; НПД и KWIKPAY за месяц
        # считаются от фактического дохода месяца.
        from app.services.prod_calendar import prorate_calendar as _prorate_cal
        _m_income = _prorate_cal(salary_rub, year, month, contract_sign_date, contract_end_date)
        if _m_income <= 0:
            continue  # месяц вне срока договора
        _per_from = 1
        if (contract_sign_date and contract_sign_date.year == year
                and contract_sign_date.month == month and contract_sign_date.day > 1):
            _per_from = contract_sign_date.day
        _per_to = last_day
        if (contract_end_date and contract_end_date.year == year
                and contract_end_date.month == month and contract_end_date.day < last_day):
            _per_to = contract_end_date.day
        _m_tax = (_m_income * npd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        _m_kwikpay = (_m_income - _m_tax - DEFAULT_KWIKPAY_RESERVE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        # 1. Поступление от Заказчика (~6 числа следующего месяца)
        income_day = random.randint(5, 8)
        try:
            income_date = _adjust_to_business_day(date(next_y, next_m, income_day))
        except ValueError:
            continue
        if period_start <= income_date <= period_end:
            # Pack 34.4: сокращаем ОПФ ('Общество с ограниченной ответственностью' → 'ООО')
            # — стандартная практика банков, эталон Алиева тоже сокращённый.
            company_display_name = _shorten_opf(company_full_name)
            income_desc = (
                f"Плательщик: {company_display_name}\n"
                f"ИНН плательщика: {company_inn}\n"
                f"Счет плательщика: {company_bank_account}, БИК {company_bank_bic}\n"
                f"Назначение платежа: Оплата за оказание услуг по Договору №{contract_number} "
                f"от {contract_sign_date.strftime('%d.%m.%y')}г. за период "
                f"{_per_from:02d}.{month:02d}.{year}-{_per_to:02d}.{month:02d}.{year}г., "
                f"Акт №{month:02d}/{year % 100:02d} от {last_day:02d}.{month:02d}.{year}г., без НДС."
            )
            transactions.append({
                "transaction_date": income_date,
                "code": _gen_credit_code(),
                "description": income_desc,
                "amount": _m_income.quantize(Decimal("0.01")),
                "currency": "RUR",
                "category": "Прочие операции",
            })
            # Pack 73.1 — распределение поступления 30/50-65/5-20%
            # (заменяет KWIKPAY: вместо одного большого расхода — много карточных)
            # next_payout_date = ~6 число месяца через 1 от next_y/next_m
            _next_inc_y = next_y if next_m < 12 else next_y + 1
            _next_inc_m = next_m + 1 if next_m < 12 else 1
            try:
                _next_inc_date = date(_next_inc_y, _next_inc_m, 6)
            except ValueError:
                _next_inc_date = None
            transactions.extend(_distribute_salary_30_50_15(
                salary_date=income_date,
                salary_amount=_m_income.quantize(Decimal("0.01")),
                next_payout_date=_next_inc_date,
                period_start=period_start,
                period_end=period_end,
                applicant_id=applicant_id_for_savings,
                card_number=applicant_card_number,
                bank_account=applicant_bank_account,
                bank_bik=bank_bik,
                city=applicant_city or "Moscow",
                rng=random,
            ))

        # Pack 73.1 — блок KWIKPAY УБРАН: заменён на _distribute_salary_30_50_15 выше.

        # 3. НПД — Pack 35.0: диапазон 17-22 (плательщики НПД успевают «до 22 числа»),
        # сдвиг на ПРЕДЫДУЩИЙ рабочий день если 22-е выходной (налоговая логика:
        # лучше уплатить заранее, чем просрочить). За месяц X налог платится в (X+1).
        npd_day = random.randint(17, 22)
        try:
            npd_date = _adjust_to_previous_business_day(date(next_y, next_m, npd_day))
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
                "amount": -_m_tax,
                "currency": "RUR",
                "category": "Прочие операции",
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
                "category": "Прочие операции",
            })

    # === Pack 25.8: СБП-переводы себе ===
    self_phone = _resolve_self_phone_for_sbp(applicant_phone)
    self_phone_masked = _format_ru_phone_masked(self_phone)
    self_short_name = _short_name_for_sbp(applicant_full_name_ru)


    # Pack 51: scale на длину периода (baseline 90 дней = 3-8). Для коротких
    # append-периодов это даёт пропорционально меньше СБП-переводов.
    _sbp_scale = max(1, (period_end - period_start).days + 1) / 90.0
    _sbp_min = max(0, round(3 * _sbp_scale))
    _sbp_max = max(_sbp_min, round(8 * _sbp_scale))
    sbp_count_total = random.randint(_sbp_min, _sbp_max) if _sbp_max > 0 else 0
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
            "category": "Перевод СБП",
        })

    # === Pack 25.8: онлайн-подписки и оплаты сервисов ===
    # Pack 51: scale на длину периода (baseline 90 дней = 10-20).
    _subs_scale = max(1, (period_end - period_start).days + 1) / 90.0
    _subs_min = max(0, round(10 * _subs_scale))
    _subs_max = max(_subs_min, round(20 * _subs_scale))
    subs_count_total = random.randint(_subs_min, _subs_max) if _subs_max > 0 else 0
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
            "category": "Прочие операции",
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

    # === Pack 32.3: лимит ≤2 страниц через бюджет «веса строк» ===
    # Вес транзакции = 1 + count('\n') в описании.
    # - single-line (KWIKPAY, НПД, комиссия, подписка) = 1.0
    # - СБП multiline (Получатель + банк/телефон) = 2.0
    # - Зарплата multiline (Плательщик + ИНН + Счёт + Назначение) = 5.0
    #
    # Эмпирически 1 страница A4 ~= 22 единицы веса (Word, Times New Roman 10,
    # шапка выписки + таблица). 2 страницы = 44, целевой бюджет 38 даёт запас
    # на orphan-control, разные размеры подписи, разрывы.
    #
    # Бюджет настраиваемый через ENV var BANK_STATEMENT_MAX_WEIGHT.
    import os as _os
    # Pack 73.1 — поднят бюджет страниц с 38 до 200, потому что новая модель
    # распределения зарплаты (30% накопит + 50-65% карточных) создаёт намного
    # больше транзакций (15-30 карточных на каждую зарплату). 2 страницы стали
    # тесными, целимся в 3-4 страницы как у реальных Сбер/Альфа-выписок.
    try:
        _max_weight = int(_os.environ.get("BANK_STATEMENT_MAX_WEIGHT", "200"))
    except (ValueError, TypeError):
        _max_weight = 200

    def _tx_weight(t: dict) -> float:
        desc = t.get("description") or ""
        return 1.0 + desc.count("\n")

    def _is_subscription(t: dict) -> bool:
        desc = t.get("description") or ""
        return desc.startswith("Оплата услуг.")

    def _is_sbp(t: dict) -> bool:
        desc = t.get("description") or ""
        return desc.startswith("Перевод по СБП.")

    total_weight = sum(_tx_weight(t) for t in transactions)
    log.info(
        "[Pack 32.3] page budget: %d transactions, total_weight=%.1f, max=%d",
        len(transactions), total_weight, _max_weight,
    )

    if total_weight > _max_weight:
        # Шаг 1 — удаляем подписки случайно по одной, пока не уложимся.
        sub_indices = [i for i, t in enumerate(transactions) if _is_subscription(t)]
        random.shuffle(sub_indices)
        removed_subs = 0
        for idx in sub_indices:
            if total_weight <= _max_weight:
                break
            total_weight -= _tx_weight(transactions[idx])
            transactions[idx] = None  # tombstone — удалим скопом ниже
            removed_subs += 1

        # Шаг 2 — если всё ещё перебор, удаляем лишние СБП, но не ниже MIN_SBP_KEEP.
        MIN_SBP_KEEP = 3
        removed_sbp = 0
        if total_weight > _max_weight:
            sbp_indices = [
                i for i, t in enumerate(transactions)
                if t is not None and _is_sbp(t)
            ]
            keep_count = MIN_SBP_KEEP
            removable = max(0, len(sbp_indices) - keep_count)
            random.shuffle(sbp_indices)
            for idx in sbp_indices[:removable]:
                if total_weight <= _max_weight:
                    break
                total_weight -= _tx_weight(transactions[idx])
                transactions[idx] = None
                removed_sbp += 1

        # Скопом удаляем tombstones
        transactions = [t for t in transactions if t is not None]

        if total_weight > _max_weight:
            log.warning(
                "[Pack 32.3] page budget exceeded after trimming: "
                "weight=%.1f > max=%d (removed %d subs + %d sbp). "
                "Likely period_months > 3 — выписка может занять >2 страниц.",
                total_weight, _max_weight, removed_subs, removed_sbp,
            )
        else:
            log.info(
                "[Pack 32.3] trimmed %d subscriptions + %d sbp, "
                "now %d transactions, weight=%.1f",
                removed_subs, removed_sbp, len(transactions), total_weight,
            )
    # === конец Pack 32.3 ===

    # Сортируем от новой к старой (как в реальной выписке Альфы — последняя сверху)
    transactions.sort(key=lambda t: t["transaction_date"], reverse=True)

    # Балансы
    total_income = sum(
        (t["amount"] for t in transactions if t["amount"] > 0), Decimal("0.00")
    )
    total_expense = sum(
        (-t["amount"] for t in transactions if t["amount"] < 0), Decimal("0.00")
    )
    # Pack 39.2: рандомный начальный остаток 50k-400k с копейками
    rng_bal = random.Random(seed)
    opening_balance = Decimal(
        f"{rng_bal.randint(50000, 400000)}.{rng_bal.randint(0, 99):02d}"
    )
    closing_balance = (opening_balance + total_income - total_expense).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    # Если закрывающий остаток отрицательный или слишком маленький —
    # поднимаем начальный чтобы closing был рандомно плюсовым (1k-50k)
    if closing_balance < Decimal("1000.00"):
        min_closing = Decimal(rng_bal.randint(1000, 50000))
        shortfall = min_closing - closing_balance
        opening_balance = (opening_balance + shortfall).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
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
                # Pack 47.2: category — опциональное поле для мульти-банк системы.
                # Старые сериализованные tx без него восстанавливаются через
                # _sber_category_from_description в _build_bank_context.
                "category": t.get("category", ""),
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
                # Pack 47.2: см. serialize_for_storage. Старые БД без поля -> "".
                "category": t.get("category", ""),
            }
            for t in stored["transactions"]
        ],
    }
    # Pack 25.8: восстанавливаем statement_date если был сохранён
    if stored.get("statement_date"):
        out["statement_date"] = date.fromisoformat(stored["statement_date"])
    return out
