"""
Сборка контекста (данных) для DOCX/PDF шаблонов.

Берёт Application + связанные сущности, превращает в плоский dict,
который docxtpl подставит в переменные {{ ... }}.

Pack 14 finishing: расширены справочники стран (TUR, POL, DEU и т.д.) +
fallback на latin если у иностранца нет русского имени.

Pack 33.1 (10.05.2026): добавлен алиас fmt_date_quoted_ru = fmt_date_long_ru.
Шаблоны avtodom/hayat использовали имя fmt_date_quoted_ru, которого не было
в контексте — Jinja падал с UndefinedError. Формат идентичен fmt_date_long_ru:
«05» сентября 2025 г. Алиас, не дубликат — единая точка правды для формата.

Pack 33.2 (10.05.2026): NBSP (\u00A0) внутри длинных русских дат вместо обычных
пробелов. Word при выравнивании по ширине (justify) разрывал строку между
"2026" и "г.", из-за чего "г." уезжало на следующую строку. NBSP — стандартный
типографский неразрывный пробел — Word гарантированно не разорвёт по нему.
Затронуто 3 функции: _format_date_ru, fmt_date_long_ru, fmt_date_human_ru.
fmt_date_quoted_ru — это алиас на fmt_date_long_ru, поэтому правка тоже
автоматически применяется и к нему.
"""

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from calendar import monthrange

from sqlmodel import Session

from app.models import (
    Application, Applicant, Company, Position,
    Representative, SpainAddress,
)
from app.services.cbr_client import convert_rub_to_eur, get_eur_rub_rate
from app.services.bank_statement_generator import (
    generate_default_transactions, deserialize_from_storage,
    DEFAULT_NPD_RATE, DEFAULT_BANK_FEE_PER_MONTH,
)
from app.services.applicant_passports import get_passport_dict_for_ru_docs  # Pack 41.0-E


def _format_date_ru(d):
    """04.05.2025 → '«04»\u00a0мая\u00a02025\u00a0г.'  (Pack 33.2: NBSP внутри даты)"""
    if not d:
        return ""
    months = {1: "января", 2: "февраля", 3: "марта", 4: "апреля",
              5: "мая", 6: "июня", 7: "июля", 8: "августа",
              9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}
    # Pack 33.2: NBSP (\u00a0) между всеми частями даты — Word не разорвёт по ним
    return f"«{d.day:02d}»\u00a0{months[d.month]}\u00a0{d.year}\u00a0г."


# ============================================================================
# Hardcoded dictionaries
# ============================================================================

_MONTHS_GENITIVE_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

_MONTHS_NOMINATIVE_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

# Юридически правильные названия стран в родительном падеже
# (используется в фразе «Гражданин <ROD>», «Гражданка <ROD>»)
_NATIONALITY_GENITIVE_RU = {
    # СНГ + ближнее зарубежье
    "RUS": "Российской Федерации",
    "AZE": "Азербайджанской Республики",
    "ARM": "Республики Армения",
    "KAZ": "Республики Казахстан",
    "BLR": "Республики Беларусь",
    "UKR": "Украины",
    "GEO": "Грузии",
    "UZB": "Республики Узбекистан",
    "TJK": "Республики Таджикистан",
    "KGZ": "Кыргызской Республики",
    "MDA": "Республики Молдова",
    "TKM": "Туркменистана",
    "MKD": "Республики Северная Македония",
    "ALB": "Республики Албания",
    # Pack 14 — расширение для иностранных клиентов
    "TUR": "Турецкой Республики",
    "POL": "Республики Польша",
    "DEU": "Федеративной Республики Германия",
    "CZE": "Чешской Республики",
    "SVK": "Словацкой Республики",
    "SVN": "Республики Словения",
    "HUN": "Венгрии",
    "ROU": "Румынии",
    "BGR": "Республики Болгария",
    "EST": "Эстонской Республики",
    "LVA": "Латвийской Республики",
    "LTU": "Литовской Республики",
    "ESP": "Королевства Испания",
    "ITA": "Итальянской Республики",
    "PRT": "Португальской Республики",
    "GRC": "Греческой Республики",
    "FRA": "Французской Республики",
    "BEL": "Королевства Бельгия",
    "NLD": "Королевства Нидерландов",
    "AUT": "Австрийской Республики",
    "CHE": "Швейцарской Конфедерации",
    "GBR": "Соединённого Королевства Великобритании и Северной Ирландии",
    "IRL": "Ирландии",
    "NOR": "Королевства Норвегия",
    "SWE": "Королевства Швеция",
    "DNK": "Королевства Дания",
    "FIN": "Финляндской Республики",
    "ISL": "Республики Исландия",
    "ISR": "Государства Израиль",
    "USA": "Соединённых Штатов Америки",
    "CAN": "Канады",
    "MEX": "Мексиканских Соединённых Штатов",
    "BRA": "Федеративной Республики Бразилия",
    "ARG": "Аргентинской Республики",
    "CHN": "Китайской Народной Республики",
    "JPN": "Японии",
    "KOR": "Республики Корея",
    "IND": "Республики Индия",
    "THA": "Королевства Таиланд",
    "VNM": "Социалистической Республики Вьетнам",
    "PHL": "Республики Филиппины",
    "IDN": "Республики Индонезия",
    "MYS": "Малайзии",
    "SGP": "Республики Сингапур",
    "ARE": "Объединённых Арабских Эмиратов",
    "SAU": "Королевства Саудовская Аравия",
    "EGY": "Арабской Республики Египет",
    "MAR": "Королевства Марокко",
    "ZAF": "Южно-Африканской Республики",
    "AUS": "Австралии",
    "NZL": "Новой Зеландии",
    "SRB": "Республики Сербия",
    "MNE": "Черногории",
    "BIH": "Боснии и Герцеговины",
    "HRV": "Республики Хорватия",
}

_NATIONALITY_NOMINATIVE_RU = {
    "RUS": "Российская Федерация",
    "AZE": "Азербайджан",
    "KAZ": "Казахстан",
    "BLR": "Беларусь",
    "UKR": "Украина",
    "ARM": "Армения",
    "GEO": "Грузия",
    "UZB": "Узбекистан",
    "TJK": "Таджикистан",
    "KGZ": "Кыргызстан",
    "MKD": "Северная Македония",
    "ALB": "Албания",
    "MDA": "Молдова",
    "TKM": "Туркменистан",
    "TUR": "Турция",
    "POL": "Польша",
    "DEU": "Германия",
    "CZE": "Чехия",
    "SVK": "Словакия",
    "SVN": "Словения",
    "HUN": "Венгрия",
    "ROU": "Румыния",
    "BGR": "Болгария",
    "EST": "Эстония",
    "LVA": "Латвия",
    "LTU": "Литва",
    "ESP": "Испания",
    "ITA": "Италия",
    "PRT": "Португалия",
    "GRC": "Греция",
    "FRA": "Франция",
    "BEL": "Бельгия",
    "NLD": "Нидерланды",
    "AUT": "Австрия",
    "CHE": "Швейцария",
    "GBR": "Великобритания",
    "IRL": "Ирландия",
    "NOR": "Норвегия",
    "SWE": "Швеция",
    "DNK": "Дания",
    "FIN": "Финляндия",
    "ISL": "Исландия",
    "ISR": "Израиль",
    "USA": "США",
    "CAN": "Канада",
    "MEX": "Мексика",
    "BRA": "Бразилия",
    "ARG": "Аргентина",
    "CHN": "Китай",
    "JPN": "Япония",
    "KOR": "Республика Корея",
    "IND": "Индия",
    "THA": "Таиланд",
    "VNM": "Вьетнам",
    "PHL": "Филиппины",
    "IDN": "Индонезия",
    "MYS": "Малайзия",
    "SGP": "Сингапур",
    "ARE": "ОАЭ",
    "SAU": "Саудовская Аравия",
    "EGY": "Египет",
    "MAR": "Марокко",
    "ZAF": "ЮАР",
    "AUS": "Австралия",
    "NZL": "Новая Зеландия",
    "SRB": "Сербия",
    "MNE": "Черногория",
    "BIH": "Босния и Герцеговина",
    "HRV": "Хорватия",
}

_SALARY_WORDS_RU = {
    280000: "двести восемьдесят тысяч",
    290000: "двести девяносто тысяч",
    296000: "двести девяносто шесть тысяч",
    300000: "триста тысяч",
    310000: "триста десять тысяч",
    320000: "триста двадцать тысяч",
    330000: "триста тридцать тысяч",
    340000: "триста сорок тысяч",
    350000: "триста пятьдесят тысяч",
    370000: "триста семьдесят тысяч",
    380000: "триста восемьдесят тысяч",
}

_HUNDREDS_ES = {
    1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos",
    5: "quinientos", 6: "seiscientos", 7: "setecientos", 8: "ochocientos",
    9: "novecientos",
}
_TENS_ES = {
    20: "veinte", 30: "treinta", 40: "cuarenta", 50: "cincuenta",
    60: "sesenta", 70: "setenta", 80: "ochenta", 90: "noventa",
}
_UNITS_ES = {
    0: "cero", 1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco",
    6: "seis", 7: "siete", 8: "ocho", 9: "nueve", 10: "diez",
    11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
    16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
    21: "veintiuno", 22: "veintidós", 23: "veintitrés", 24: "veinticuatro",
    25: "veinticinco", 26: "veintiséis", 27: "veintisiete", 28: "veintiocho",
    29: "veintinueve",
}


# ============================================================================
# Forming helpers
# ============================================================================

def fmt_date_ru(d: date | None) -> str:
    if d is None:
        return ""
    return d.strftime("%d.%m.%Y")


def fmt_date_long_ru(d: date | None) -> str:
    if d is None:
        return ""
    # Pack 33.2: NBSP (\u00a0) между всеми частями даты вместо обычных пробелов.
    # Word при выравнивании по ширине разрывал по обычному пробелу — например,
    # "2026 г." могло превратиться в "2026" в конце строки и "г." в начале
    # следующей. NBSP запрещает разрыв.
    # Алиас fmt_date_quoted_ru = fmt_date_long_ru унаследует этот фикс автоматически.
    return f'«{d.day:02d}»\u00a0{_MONTHS_GENITIVE_RU[d.month - 1]}\u00a0{d.year}\u00a0г.'


# Pack 33.1: алиас для шаблонов avtodom/hayat где автор использовал имя
# fmt_date_quoted_ru. Формат идентичен fmt_date_long_ru: «05» сентября 2025 г.
# Алиас (не дубликат логики) — единая точка правды для формата.
fmt_date_quoted_ru = fmt_date_long_ru


def fmt_date_human_ru(d: date | None) -> str:
    if d is None:
        return ""
    # Pack 33.2: NBSP (\u00a0) между частями даты — см. fmt_date_long_ru.
    return f"{d.day}\u00a0{_MONTHS_GENITIVE_RU[d.month - 1]}\u00a0{d.year}\u00a0года"


def fmt_money(amount: Decimal | int | float | None) -> str:
    if amount is None:
        return ""
    return f"{int(amount):,}".replace(",", " ")


def fmt_money_kop(amount: Decimal | int | float | None) -> str:
    if amount is None:
        return ""
    n = int(amount)
    sign = "-" if n < 0 else ""
    abs_n = abs(n)
    formatted = f"{abs_n:,}".replace(",", " ")
    return f"{sign}{formatted},00"


def fmt_amount_signed(amount: Decimal | int | float | None) -> str:
    if amount is None:
        return ""
    return fmt_money_kop(amount) + " RUR"


# === Pack 47.2: форматтеры для мульти-банк системы ===

def _fmt_bank_account_groups(account: str | None) -> str:
    """
    Pack 47.7: формат 20-значного российского расчётного счёта с разделителями.

    Формат Сбера: 5-3-1-4-7 (как в реальной выписке).
    Пример: "40817810130850859826" -> "40817 810 1 3085 0859826"

    Если account != 20 цифр — возвращаем как есть (back-compat для тестовых /
    неполных значений).
    """
    if not account:
        return ""
    digits = "".join(c for c in account if c.isdigit())
    if len(digits) != 20:
        return account
    return f"{digits[0:5]} {digits[5:8]} {digits[8:9]} {digits[9:13]} {digits[13:20]}"


def fmt_amount_sber(amount: Decimal | int | float | None) -> str:
    """
    Pack 47.2: формат суммы как в эталоне Сбера.
    - Без " RUR" в конце (в шапке выписки уже указано "Российский рубль").
    - Положительные с префиксом "+" (поступления).
    - Отрицательные БЕЗ минуса (списания) — в выписке Сбера все расходы
      отображаются как абсолютное значение без знака, направление операции
      понятно из контекста (категория, описание).

    Примеры:
      Decimal("2500.00")  -> "+2 500,00"
      Decimal("-2243.64") -> "2 243,64"
      Decimal("0")        -> "0,00"
    """
    if amount is None:
        return ""
    n_decimal = Decimal(amount).quantize(Decimal("0.01"))
    sign = ""
    if n_decimal > 0:
        sign = "+"
    abs_amount = n_decimal.copy_abs()
    int_part = int(abs_amount)
    frac = (abs_amount - Decimal(int_part)).copy_abs()
    frac_str = f"{frac:.2f}".split(".")[1]
    formatted = f"{int_part:,}".replace(",", " ") + "," + frac_str
    return f"{sign}{formatted}"


def fmt_amount_sber_unsigned(amount: Decimal | int | float | None) -> str:
    """
    Pack 47.2: формат суммы как в эталоне Сбера БЕЗ знака
    (для блока "Итого по операциям": Пополнение / Списание / Остаток).
    """
    if amount is None:
        return ""
    n_decimal = Decimal(amount).quantize(Decimal("0.01"))
    abs_amount = n_decimal.copy_abs()
    int_part = int(abs_amount)
    frac = (abs_amount - Decimal(int_part)).copy_abs()
    frac_str = f"{frac:.2f}".split(".")[1]
    return f"{int_part:,}".replace(",", " ") + "," + frac_str


# === Pack 47.2: эвристика category из description (backfill для старых tx) ===

# Sber-категории по началу description. Применяется ТОЛЬКО если category
# отсутствует в tx (старые сохранённые выписки). После backfill значение
# не записывается обратно в БД — следующий ребилд выписки менеджером запишет
# его автоматически через generate_default_transactions.
_SBER_CATEGORY_BY_PREFIX = (
    ("Перевод по СБП", "Перевод СБП"),
    ("Перевод СБП", "Перевод СБП"),
    # все остальные распознанные паттерны — категория "Прочие операции"
    # (как делает реальный Сбер для зарплат/налогов/комиссий/подписок)
)


def _sber_category_from_description(description: str) -> str:
    """
    Pack 47.2: backfill категории для tx без поля "category".

    Используется в _apply_sber_postprocess для старых выписок которые
    были сохранены до Pack 47.2. По умолчанию возвращает "Прочие операции"
    (стандартная категория Сбера для платежей без MCC-маппинга).
    """
    if not description:
        return "Прочие операции"
    desc_stripped = description.lstrip()
    for prefix, category in _SBER_CATEGORY_BY_PREFIX:
        if desc_stripped.startswith(prefix):
            return category
    return "Прочие операции"


# === Pack 47.2: резолв "это Сбер-выписка?" по applicant.bank_id ===

# БИК Сбера в нашей БД. Один источник правды — этот константный список.
# Когда подключим ВТБ/ТБанк/Открытие — добавятся новые pack-функции с
# их БИК, не трогая Sber-функцию.
_SBER_BIK = "044525225"


def _is_sber_applicant(applicant, session) -> bool:
    """Pack 47.2: True если у applicant.bank указан Сбер."""
    if applicant is None or not getattr(applicant, "bank_id", None):
        return False
    if session is None:
        return False
    from app.models import Bank
    bank = session.get(Bank, applicant.bank_id)
    if bank is None:
        return False
    return getattr(bank, "bik", None) == _SBER_BIK


# === Pack 47.2: пост-процессинг bank_data для Сбер-выписки ===

def _apply_sber_postprocess(bank_data: dict, applicant, session) -> dict:
    """
    Pack 47.2: если applicant — Сбер-клиент, применяем:
      1. backfill category в каждом tx (если поле отсутствует или пустое).
      2. running_balance: сортируем tx по дате asc, накапливаем баланс,
         сортируем обратно по дате desc для вывода (как в эталоне Сбера).
         Каждой tx добавляется ключ running_balance + running_balance_formatted.
      3. amount_formatted переформатируем через fmt_amount_sber.
      4. opening/closing/total_*_formatted переформатируем через
         fmt_amount_sber_unsigned (без знака — в блоке "Итого").

    Если applicant НЕ Сбер — возвращаем bank_data без изменений.
    Это сохраняет поведение Альфы.
    """
    if not _is_sber_applicant(applicant, session):
        return bank_data

    transactions = bank_data.get("transactions") or []

    # === 1. Backfill category ===
    for tx in transactions:
        if not tx.get("category"):
            tx["category"] = _sber_category_from_description(tx.get("description", ""))

    # === 2. Running balance ===
    # Берём opening_balance уже из bank_data (он мог быть скорректирован
    # MIN_CLOSING в _build_bank_context — нам нужен финальный)
    opening = bank_data.get("opening_balance") or Decimal("0")
    txs_sorted_asc = sorted(
        transactions,
        key=lambda t: t.get("transaction_date") or date.min,
    )
    running = opening
    for tx in txs_sorted_asc:
        amount = tx.get("amount") or Decimal("0")
        running = Decimal(running) + Decimal(amount)
        tx["running_balance"] = running
        tx["running_balance_formatted"] = fmt_amount_sber_unsigned(running)

    # Сортируем выводимые транзакции по дате desc (новые сверху, как в эталоне)
    transactions_desc = sorted(
        transactions,
        key=lambda t: t.get("transaction_date") or date.min,
        reverse=True,
    )
    bank_data["transactions"] = transactions_desc

    # === 3. amount_formatted через Sber-форматтер ===
    for tx in transactions_desc:
        tx["amount_formatted"] = fmt_amount_sber(tx.get("amount"))

    # === 4. Итоги через Sber-форматтер без знака ===
    for key in ("opening_balance_formatted", "closing_balance_formatted",
                "total_income_formatted", "total_expense_formatted"):
        raw_key = key[: -len("_formatted")]
        if raw_key in bank_data:
            bank_data[key] = fmt_amount_sber_unsigned(bank_data[raw_key])

    return bank_data


# === Pack 48.0: ТБанк (АО «ТБанк») — резолв, форматтеры, постпроцессинг ===
# Документ-эталон: PDF "Справка о движении средств" от ТБанка.
# BIK 044525974 (АО «ТБанк», к/с 30101810145250000974).
#
# Особенности ТБанка относительно Сбера:
#   - формат суммы tx: "+574.00 ₽" / "-964.00 ₽" (точка как десятичный разделитель,
#     знак ВСЕГДА присутствует, символ ₽ в конце).
#   - формат итогов внизу: "799 033,00 ₽" (запятая как разделитель, без знака).
#     Это намеренная несовместимость стилей внутри одного банка — повторяем 1-в-1
#     как в эталоне.
#   - в tx-таблице 6 колонок: дата+время операции / дата+время списания / сумма
#     в валюте операции / сумма в валюте карты / описание / номер карты.
#   - дата+время в первой/второй колонке хранятся в одной ячейке как
#     "DD.MM.YYYY\nHH:MM" (две строки) — multiline-механика в docx_renderer
#     обработает это автоматически.
#   - "номер карты" — 4 последние цифры, у нас в БД не хранится; генерируем
#     детерминированно по applicant.bank_account.
#   - категории и running_balance НЕ нужны (в эталоне ТБанка таких колонок нет).
_TBANK_BIK = "044525974"


def fmt_amount_tbank(amount: Decimal | int | float | None) -> str:
    """
    Pack 48.0: формат суммы tx в эталоне ТБанка.

    Особенности (см. эталон PDF "Справка о движении средств"):
      - Знак ВСЕГДА присутствует: "+" для пополнений, "-" для списаний.
      - Точка как десятичный разделитель (НЕ запятая как у Сбера в tx).
      - Пробел-разделитель тысяч.
      - Символ ₽ в конце через неразрывный пробел.

    Примеры:
      Decimal("574.00")    -> "+574.00 ₽"
      Decimal("-964.00")   -> "-964.00 ₽"
      Decimal("10000.00")  -> "+10 000.00 ₽"
      Decimal("-1399.00")  -> "-1 399.00 ₽"
      None                 -> ""
    """
    if amount is None:
        return ""
    n_decimal = Decimal(amount).quantize(Decimal("0.01"))
    sign = "+" if n_decimal >= 0 else "-"
    abs_amount = n_decimal.copy_abs()
    int_part = int(abs_amount)
    frac = (abs_amount - Decimal(int_part)).copy_abs()
    frac_str = f"{frac:.2f}".split(".")[1]
    formatted = f"{int_part:,}".replace(",", " ") + "." + frac_str
    return f"{sign}{formatted}\u00a0₽"


def fmt_amount_tbank_totals(amount: Decimal | int | float | None) -> str:
    """
    Pack 48.0: формат итогов внизу выписки ТБанка ("Пополнения / Расходы").

    Отличается от fmt_amount_tbank:
      - БЕЗ знака (показываем абсолютное значение, направление понятно из лейбла).
      - Запятая как десятичный разделитель (а не точка как в tx-строках).

    Примеры:
      Decimal("799033.00")  -> "799 033,00 ₽"
      Decimal("804577.21")  -> "804 577,21 ₽"
    """
    if amount is None:
        return ""
    n_decimal = Decimal(amount).quantize(Decimal("0.01"))
    abs_amount = n_decimal.copy_abs()
    int_part = int(abs_amount)
    frac = (abs_amount - Decimal(int_part)).copy_abs()
    frac_str = f"{frac:.2f}".split(".")[1]
    formatted = f"{int_part:,}".replace(",", " ") + "," + frac_str
    return f"{formatted}\u00a0₽"


def _is_tbank_applicant(applicant, session) -> bool:
    """Pack 48.0: True если у applicant.bank указан ТБанк (BIK 044525974)."""
    if applicant is None or not getattr(applicant, "bank_id", None):
        return False
    if session is None:
        return False
    from app.models import Bank
    bank = session.get(Bank, applicant.bank_id)
    if bank is None:
        return False
    return getattr(bank, "bik", None) == _TBANK_BIK


def _generate_tbank_card_number(bank_account: str | None) -> str:
    """
    Pack 48.0: генерирует 4 цифры "номера карты" детерминированно из bank_account.

    Эталон ТБанка показывает 4 последние цифры карты (напр. "9655"). У нас в БД
    номера карт нет, есть только номер счёта (20 цифр). Решение: hash(bank_account)
    → 4 цифры. Это даёт:
      - одинаковые 4 цифры для ВСЕХ транзакций одного клиента (как в реальной
        выписке — клиент ходит с одной картой);
      - стабильность между разными рендерами выписки одного и того же клиента
        (хеш детерминированный);
      - визуальную правдоподобность (не "0000", не "1234", не похоже на заглушку);
      - независимость от последних 4 цифр счёта (счёт ≠ карта, не путаем).

    Если bank_account пустой — возвращаем "—" (как в эталоне ТБанка для операций
    не привязанных к карте, например "Плата за обслуживание").
    """
    if not bank_account:
        return "—"
    # SHA1 для детерминированности (hash() в Python3 рандомизирован через PYTHONHASHSEED)
    import hashlib
    digest = hashlib.sha1(bank_account.encode("utf-8")).hexdigest()
    # Берём первые 8 hex-символов (32 бита) → mod 10000 → 4 цифры
    num = int(digest[:8], 16) % 10000
    return f"{num:04d}"


def _generate_tbank_contract(applicant_id: int | None, statement_date: date | None) -> tuple[str, str]:
    """
    Pack 48.3.1: генерирует пару (contract_date_formatted, contract_number)
    детерминированно по applicant.id.

    Логика:
      - contract_date = statement_date - (540..720 дней) — договор заключён
        18-24 месяца назад относительно даты справки (как у реальных клиентов
        с подросшей историей операций).
      - contract_number = 10 цифр (формат как в эталоне ТБанка: "5707847458").

    Оба значения детерминированно вычисляются по applicant.id, поэтому между
    повторными рендерами одной выписки не меняются.

    Возвращает ("", "") если входы пустые.
    """
    if not applicant_id or not statement_date:
        return ("", "")
    import hashlib
    # Seed: applicant.id (стабильный, не зависит от даты вызова).
    seed_bytes = f"tbank_contract:{applicant_id}".encode("utf-8")
    digest = hashlib.sha1(seed_bytes).hexdigest()

    # Offset 540..720 дней
    offset_days = 540 + (int(digest[:6], 16) % 181)
    contract_date = statement_date - timedelta(days=offset_days)
    contract_date_str = contract_date.strftime("%d.%m.%Y")

    # Номер договора: 10 цифр через mod 10^10
    contract_num_int = int(digest[8:18], 16) % 10_000_000_000
    contract_number = f"{contract_num_int:010d}"

    return (contract_date_str, contract_number)


def _generate_tbank_tx_times(tx_date: date, amount, tx_index: int) -> tuple[str, str]:
    """
    Pack 48.3.1: генерирует пару (time_op, time_settle) для транзакции
    детерминированно по (tx_date, amount, tx_index).

    Логика (по анализу эталона ТБанка):
      - time_op:   06:00..23:30 — реалистичное распределение в течение дня.
      - time_settle = time_op + задержка:
          * мелкие операции (|amount| < 1000): +1..15 минут
          * средние (1000..10000):              +15..60 минут
          * крупные (>10000):                   +1..6 часов, иногда +1 день

    Возвращает кортеж форматированных HH:MM строк (settle date = tx_date,
    т.к. для большинства операций settle в тот же день; для крупных может
    быть на следующий день — это пометим переносом, но MVP — same day).
    """
    import hashlib
    try:
        amt_abs = abs(float(amount))
    except (TypeError, ValueError):
        amt_abs = 0.0

    # Seed по (tx_date, amount, tx_index) — стабильный между рендерами
    seed = f"tbank_time:{tx_date.isoformat()}:{amount}:{tx_index}".encode("utf-8")
    digest = hashlib.sha1(seed).hexdigest()

    # time_op: минута в [06:00 = 360, 23:30 = 1410] (1050 минут диапазон)
    op_minute = 360 + (int(digest[:5], 16) % 1051)
    op_h, op_m = divmod(op_minute, 60)
    time_op = f"{op_h:02d}:{op_m:02d}"

    # Задержка settle по размеру операции
    if amt_abs < 1000:
        # 1..15 минут
        delay = 1 + (int(digest[5:9], 16) % 15)
    elif amt_abs < 10000:
        # 15..60 минут
        delay = 15 + (int(digest[5:9], 16) % 46)
    else:
        # 60..360 минут (1-6 часов)
        delay = 60 + (int(digest[5:9], 16) % 301)

    settle_minute = op_minute + delay
    # Если перевалили за 24:00 — обрежем на 23:59 (в MVP не переносим на след. день)
    if settle_minute >= 1440:
        settle_minute = 1439
    set_h, set_m = divmod(settle_minute, 60)
    time_settle = f"{set_h:02d}:{set_m:02d}"

    return (time_op, time_settle)


def _apply_tbank_postprocess(bank_data: dict, applicant, session) -> dict:
    """
    Pack 48.0 + 48.3.1: если applicant — ТБанк-клиент, обогащаем bank_data
    под формат эталона ТБанка.

    Шаги:
      1. amount_formatted переформатируем через fmt_amount_tbank
         (+/- знак + точка + " ₽").
      2. Каждой tx добавляем card_number — 4 цифры, одинаковые для всех tx
         клиента, детерминированные по bank_account.
      3. Сортируем tx по дате desc (новые сверху, как в эталоне ТБанка).
      4. opening/closing/total_*_formatted переформатируем через
         fmt_amount_tbank_totals (без знака + запятая + " ₽") — для блока
         "Пополнения / Расходы" на последней странице.
      5. (Pack 48.3.1) bank.contract_date_formatted + bank.contract_number —
         генерируем детерминированно по applicant.id (18-24 мес. назад от
         statement_date, 10-значный номер).
      6. (Pack 48.3.1) tx.date_formatted превращаем в multiline "DD.MM.YYYY\nHH:MM"
         (multiline-механика в docx_renderer._replace_marker_with_multiline
         разобьёт это на 2 параграфа в ячейке таблицы).
         Также заполняем tx.settle_date_formatted (для маркера __TX_DATE_SETTLE__).

    Если applicant НЕ ТБанк — возвращаем bank_data без изменений.
    No-op для Альфы и Сбера.
    """
    if not _is_tbank_applicant(applicant, session):
        return bank_data

    transactions = bank_data.get("transactions") or []

    # === 1. amount_formatted через ТБанк-форматтер ===
    for tx in transactions:
        tx["amount_formatted"] = fmt_amount_tbank(tx.get("amount"))

    # === 2. card_number — 4 цифры, детерминированно из bank_account ===
    bank_account = getattr(applicant, "bank_account", None) if applicant else None
    card_number = _generate_tbank_card_number(bank_account)
    for tx in transactions:
        tx["card_number"] = card_number

    # === 3. Сортируем по дате desc (новые сверху) ===
    transactions_desc = sorted(
        transactions,
        key=lambda t: t.get("transaction_date") or date.min,
        reverse=True,
    )
    bank_data["transactions"] = transactions_desc

    # === 4. Итоги через ТБанк-форматтер без знака ===
    for key in ("opening_balance_formatted", "closing_balance_formatted",
                "total_income_formatted", "total_expense_formatted"):
        raw_key = key[: -len("_formatted")]
        if raw_key in bank_data:
            bank_data[key] = fmt_amount_tbank_totals(bank_data[raw_key])

    # === 5. (Pack 48.3.1) Договор: дата заключения + номер ===
    applicant_id = getattr(applicant, "id", None) if applicant else None
    statement_date = bank_data.get("statement_date")
    if statement_date is None:
        # Fallback: period_end или сегодня
        statement_date = bank_data.get("period_end") or date.today()
    contract_date_str, contract_number = _generate_tbank_contract(applicant_id, statement_date)
    bank_data["contract_date_formatted"] = contract_date_str
    bank_data["contract_number"] = contract_number

    # === 6. (Pack 48.3.1) Времена операций + дата+время списания (multiline) ===
    for idx, tx in enumerate(transactions_desc):
        tx_date = tx.get("transaction_date")
        if not tx_date:
            # Без даты — нечего генерировать
            continue
        time_op, time_settle = _generate_tbank_tx_times(tx_date, tx.get("amount"), idx)
        # tx_date в виде "DD.MM.YYYY" — у Альфы/Сбера уже строится в _build_bank_context
        # как fmt_date_ru, но fmt_date_ru даёт "DD.MM.YYYY". Проверяем что date_formatted
        # имеет формат — если да, добавляем \n+время; если нет — собираем сами.
        date_str = tx.get("date_formatted") or tx_date.strftime("%d.%m.%Y")
        # Очищаем от уже добавленного \n (на случай повторного вызова)
        date_str_clean = date_str.split("\n")[0]
        tx["date_formatted"] = f"{date_str_clean}\n{time_op}"
        tx["settle_date_formatted"] = f"{date_str_clean}\n{time_settle}"

    return bank_data



def _money_to_words_ru(amount) -> str:
    if amount is None:
        return ""
    n = int(amount)
    if n in _SALARY_WORDS_RU:
        return _SALARY_WORDS_RU[n]
    if n % 1000 == 0:
        thousands = n // 1000
        if thousands == 1:
            return "одна тысяча"
        return f"{thousands} тысяч"
    return str(n)


def _number_to_words_ru(n) -> str:
    """
    Pack 26.0.1: произвольное целое n >= 0 -> русские числительные.
    Для EUR-сумм (3194 -> "три тысячи сто девяносто четыре").

    В отличие от _money_to_words_ru (которая работает только для круглых
    рублёвых зарплат через словарь _SALARY_WORDS_RU), эта функция строит
    числительные для любых чисел. Не учитывает копейки/центы.
    """
    if n is None:
        return ""
    n = int(n)
    if n == 0:
        return "ноль"
    if n < 0:
        return f"минус {_number_to_words_ru(-n)}"

    _UNITS_M = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    _UNITS_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    _TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
              "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
    _TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
             "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
    _HUNDREDS = ["", "сто", "двести", "триста", "четыреста",
                 "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

    def _hundreds_to_words(num: int, feminine: bool = False) -> str:
        if num == 0:
            return ""
        out = []
        h = num // 100
        rest = num % 100
        if h:
            out.append(_HUNDREDS[h])
        if 10 <= rest <= 19:
            out.append(_TEENS[rest - 10])
        else:
            t = rest // 10
            u = rest % 10
            if t:
                out.append(_TENS[t])
            if u:
                out.append((_UNITS_F if feminine else _UNITS_M)[u])
        return " ".join(out)

    def _plural_thousand(num: int) -> str:
        n100 = num % 100
        n10 = num % 10
        if 11 <= n100 <= 14:
            return "тысяч"
        if n10 == 1:
            return "тысяча"
        if 2 <= n10 <= 4:
            return "тысячи"
        return "тысяч"

    def _plural_million(num: int) -> str:
        n100 = num % 100
        n10 = num % 10
        if 11 <= n100 <= 14:
            return "миллионов"
        if n10 == 1:
            return "миллион"
        if 2 <= n10 <= 4:
            return "миллиона"
        return "миллионов"

    parts = []
    millions = n // 1_000_000
    rest_after_m = n % 1_000_000
    thousands = rest_after_m // 1000
    rest = rest_after_m % 1000

    if millions:
        parts.append(_hundreds_to_words(millions, feminine=False))
        parts.append(_plural_million(millions))
    if thousands:
        parts.append(_hundreds_to_words(thousands, feminine=True))
        parts.append(_plural_thousand(thousands))
    if rest:
        parts.append(_hundreds_to_words(rest, feminine=False))

    return " ".join(p for p in parts if p)


def _money_to_words_es(amount: int) -> str:
    if amount is None or amount == 0:
        return "cero"
    if amount < 0:
        return f"menos {_money_to_words_es(-amount)}"
    if amount >= 1000:
        thousands = amount // 1000
        rest = amount % 1000
        if thousands == 1:
            thousands_str = "mil"
        else:
            thousands_str = f"{_money_to_words_es(thousands)} mil"
        if rest == 0:
            return thousands_str
        return f"{thousands_str} {_money_to_words_es(rest)}"
    if amount >= 100:
        hundreds = amount // 100
        rest = amount % 100
        if hundreds == 1 and rest == 0:
            return "cien"
        hundreds_str = _HUNDREDS_ES[hundreds]
        if rest == 0:
            return hundreds_str
        return f"{hundreds_str} {_money_to_words_es(rest)}"
    if amount in _UNITS_ES:
        return _UNITS_ES[amount]
    if amount in _TENS_ES:
        return _TENS_ES[amount]
    tens = (amount // 10) * 10
    units = amount % 10
    return f"{_TENS_ES[tens]} y {_UNITS_ES[units]}"


# ============================================================================
# Helpers for applicant
# ============================================================================

def _bank_statement_address_line1(applicant: Applicant) -> str:
    """
    Pack 16.5: первая строка адреса для шапки выписки.

    Применяет сокращения адресных объектов согласно Приказу Минфина 171н
    (область → обл., край → кр., городской округ → г.о., улица → ул., и т.д.).
    Это позволяет даже длинным адресам помещаться в фиксированную рамку textbox.

    Если applicant.home_address_line1 задан явно — сокращаем и возвращаем его.
    Иначе — сокращаем home_address и разбиваем на 2 строки по запятой.
    """
    if applicant.home_address_line1:
        return abbreviate_address(applicant.home_address_line1)
    addr = abbreviate_address(applicant.home_address or "")
    if not addr:
        return ""
    line1, _ = _split_address_at_comma(addr)
    return line1


def _bank_statement_address_line2(applicant: Applicant) -> str:
    """
    Pack 16.5: вторая строка адреса для шапки выписки. См. _bank_statement_address_line1.
    """
    if applicant.home_address_line2:
        return abbreviate_address(applicant.home_address_line2)
    addr = abbreviate_address(applicant.home_address or "")
    if not addr:
        return ""
    # Если есть line1 явно, а line2 нет — line2 пустая
    if applicant.home_address_line1:
        return ""
    _, line2 = _split_address_at_comma(addr)
    return line2


def _split_address_at_comma(addr: str) -> tuple[str, str]:
    """
    Разбивает адрес на 2 строки по запятой ближайшей к середине.

    После применения сокращений адрес становится короче, и разбивка
    на 2 строки по запятой даёт хорошо отформатированную пару.
    """
    if len(addr) <= 50:
        # Короткий — целиком в line1
        return addr, ""

    # Ищем запятую ближе к середине
    target = len(addr) // 2
    commas = [i for i, ch in enumerate(addr) if ch == ',']
    if not commas:
        return addr, ""

    # Ближайшая к target
    best_comma = min(commas, key=lambda i: abs(i - target))
    line1 = addr[: best_comma + 1].strip()
    line2 = addr[best_comma + 1 :].strip()
    return line1, line2


# Pack 16.5: словарь сокращений адресных объектов по Приказу Минфина 171н
# от 05.11.2015. Применяется ко всем адресам в шапке банковской выписки чтобы
# длинные адреса помещались в фиксированную рамку textbox.
_ADDRESS_ABBREVIATIONS = [
    # Субъекты РФ
    (r'\bАвтономный округ\b', 'АО'),
    (r'\bАвтономная область\b', 'Аобл'),
    (r'\bРеспублика\b', 'Респ.'),
    (r'\bкрая\b', 'кр.'),
    (r'\bкрай\b', 'кр.'),
    (r'\bобласти\b', 'обл.'),
    (r'\bобласть\b', 'обл.'),
    # Районы / округа / поселения (длинные первыми чтобы не перепутать с короткими)
    (r'\bмуниципальный район\b', 'м.р-н'),
    (r'\bмуниципальное образование\b', 'м.о.'),
    (r'\bгородской округ\b', 'г.о.'),
    (r'\bсельское поселение\b', 'с.п.'),
    (r'\bгородское поселение\b', 'г.п.'),
    (r'\bсельская администрация\b', 'с/а'),
    (r'\bсельский округ\b', 'с/о'),
    (r'\bсельсовет\b', 'с/с'),
    (r'\bрайон\b', 'р-н'),
    # Населённые пункты
    (r'\bпоселок городского типа\b', 'пгт'),
    (r'\bдачный поселок\b', 'дп'),
    (r'\bкурортный поселок\b', 'кп'),
    (r'\bрабочий поселок\b', 'рп'),
    (r'\bпромышленная зона\b', 'промзона'),
    (r'\bжелезнодорожная станция\b', 'ж/д ст.'),
    (r'\bнаселенный пункт\b', 'нп'),
    (r'\bстаница\b', 'ст-ца'),
    (r'\bдеревня\b', 'д.'),
    (r'\bсело\b', 'с.'),
    (r'\bпосёлок\b', 'пос.'),
    (r'\bпоселок\b', 'пос.'),
    (r'\bгород\b', 'г.'),
    (r'\bхутор\b', 'х.'),
    (r'\bслобода\b', 'сл.'),
    # Улицы / переулки / проспекты
    (r'\bпроспект\b', 'пр-кт'),
    (r'\bпереулок\b', 'пер.'),
    (r'\bбульвар\b', 'б-р'),
    (r'\bнабережная\b', 'наб.'),
    (r'\bплощадь\b', 'пл.'),
    (r'\bмикрорайон\b', 'мкр'),
    (r'\bквартал\b', 'кв-л'),
    (r'\bтупик\b', 'туп.'),
    (r'\bшоссе\b', 'ш.'),
    (r'\bтерритория\b', 'тер.'),
    (r'\bдорога\b', 'дор.'),
    (r'\bулица\b', 'ул.'),
    # Дом / квартира / помещение
    (r'\bкорпус\b', 'к.'),
    (r'\bстроение\b', 'стр.'),
    (r'\bпомещение\b', 'пом.'),
    (r'\bквартира\b', 'кв.'),
    (r'\bкомната\b', 'комн.'),
    (r'\bоффис\b', 'оф.'),
    (r'\bофис\b', 'оф.'),
    (r'\bдом\b', 'д.'),
]


# ============================================================================
# Pack 34.5 — NBSP-связки в адресах для устойчивого word wrap.
# ============================================================================
# Чтобы Word не разрывал «ул. Ивана Франко» в середине названия улицы
# или «д. 8» между префиксом и номером — везде где обычный пробел может
# превратиться в перенос, ставим неразрывный пробел (U+00A0).

_NBSP = chr(0xa0)  # U+00A0 NO-BREAK SPACE

# Префиксы после которых ровно один обычный пробел становится NBSP.
_NEVER_BREAK_AFTER = [
    # Регионы / населённые пункты
    "г.", "обл.", "кр.", "Респ.", "р-н", "м.р-н", "г.о.", "с.п.", "г.п.",
    "пос.", "с.", "д.", "х.", "ст-ца", "пгт", "дп", "кп", "рп", "нп",
    # Улицы и аналоги
    "ул.", "пер.", "пр-кт", "б-р", "наб.", "пл.", "ш.", "тер.", "дор.",
    "мкр", "кв-л", "туп.", "сл.", "Аобл",
    # Дом / помещение
    "к.", "стр.", "пом.", "кв.", "комн.", "оф.",
    # Дополнительно — встречается в реальных адресах
    "эт.",  # этаж (РЕНКОНС: «эт. 15, пом. I»)
    "зд.",  # здание
]

# Сортируем убывающе по длине, чтобы «м.р-н» матчился раньше «р-н»,
# а «г.о.» раньше «г.»
_NEVER_BREAK_AFTER_SORTED = sorted(set(_NEVER_BREAK_AFTER), key=len, reverse=True)

# Префиксы названий улиц — после них всё до запятой считается «именем улицы»
# и все пробелы внутри → NBSP. Чтобы «Ивана Франко» / «Большая Ордынка» /
# «Маршала Тухачевского» не разрывались.
_STREET_PREFIXES = ["ул.", "пер.", "пр-кт", "б-р", "наб.", "пл.", "ш.",
                    "тер.", "дор.", "мкр", "кв-л", "туп."]


def _glue_inside_street_name(addr: str) -> str:
    """
    Pack 34.5: в названии улицы (после ул./пер./пр-кт/... до запятой)
    меняем обычные пробелы на NBSP. Word рассматривает многословные
    названия улиц как единое слово.

    Примеры:
      «ул. Ивана Франко, д. 8»   → «ул.<NBSP>Ивана<NBSP>Франко, д. 8»
      «пр-кт Маршала Жукова»     → «пр-кт<NBSP>Маршала<NBSP>Жукова»
    """
    pattern = (
        r"(" + "|".join(re.escape(p) for p in _STREET_PREFIXES) + r")"
        + "([ " + _NBSP + "]+)"
        + r"([^,]+)"
    )

    def repl(match):
        prefix = match.group(1)
        # Внутри названия улицы — все обычные пробелы становятся NBSP
        street_part = match.group(3).replace(" ", _NBSP)
        return prefix + _NBSP + street_part

    return re.sub(pattern, repl, addr)


def _glue_after_prefix(addr: str) -> str:
    """
    Pack 34.5: после адресных префиксов (г./д./эт./пом./кв./...) ровно
    один обычный пробел заменяется на NBSP. Чтобы Word не оторвал
    «г.» от «Москва», «д.» от «8», «эт.» от «15».
    """
    result = addr
    for prefix in _NEVER_BREAK_AFTER_SORTED:
        escaped = re.escape(prefix)
        # Перед префиксом — не словесный символ и не NBSP (на случай
        # повторного запуска или составных «м.р-н» внутри слова).
        # После префикса — РОВНО один обычный пробел и затем не-пробел.
        pattern = r"(?<![\w" + _NBSP + r"])" + escaped + r" (?=\S)"
        result = re.sub(pattern, prefix + _NBSP, result)
    return result

def abbreviate_address(addr: str | None) -> str:
    """
    Pack 16.5: применяет официальные сокращения адресных объектов к строке адреса.

    Использует словарь _ADDRESS_ABBREVIATIONS, основанный на Приказе Минфина РФ
    №171н от 05.11.2015 «Об утверждении Перечня элементов планировочной структуры…
    и Правил сокращенного наименования адресообразующих элементов».

    Сокращения регистронезависимы и сохраняют пробелы между элементами.
    Слова без явного типа (например, названия улиц «Линия», «Аллея») не трогаются.

    Примеры:
        "Краснодарский край, городской округ Сочи, село Раздольное, улица Тепличная"
        → "Краснодарский кр., г.о. Сочи, с. Раздольное, ул. Тепличная"

        "Республика Татарстан, муниципальный район Высокогорский"
        → "Респ. Татарстан, м.р-н Высокогорский"
    """
    if not addr:
        return ""

    import re
    result = addr
    for pattern, replacement in _ADDRESS_ABBREVIATIONS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # Чистим пробелы — двойные пробелы могли появиться после сокращений
    result = re.sub(r'  +', ' ', result)
    result = result.strip()
    # Pack 34.5: NBSP-связки чтобы Word не разрывал «ул. Ивана Франко»
    # и «д. 8» внутри. Сначала внутри названия улицы (все пробелы),
    # потом после всех адресных префиксов (только один пробел после).
    result = _glue_inside_street_name(result)
    result = _glue_after_prefix(result)
    return result


def _full_name_native(applicant: Applicant) -> str:
    """
    Полное имя на русском (Им. падеж).
    Pack 14 fix: если native пустые — fallback на latin (для иностранцев которым менеджер
    ещё не вписал русское имя).
    """
    if applicant.last_name_native and applicant.first_name_native:
        parts = [applicant.last_name_native, applicant.first_name_native]
        if applicant.middle_name_native:
            parts.append(applicant.middle_name_native)
        return " ".join(p for p in parts if p)

    # Fallback на latin
    if applicant.last_name_latin and applicant.first_name_latin:
        return f"{applicant.last_name_latin} {applicant.first_name_latin}"

    return ""


def _nbsp_initials(value: str | None) -> str:
    """Pack 35.11: заменить обычный пробел перед инициалами на NBSP.

    Применяется к строкам вида «Иванов И.А.», «Василевская А.В.» —
    Word не должен разрывать строку между фамилией и инициалом.

    Логика: ищем последний пробел перед `<буква>.` паттерном и меняем на NBSP.
    Если паттерн не найден — возвращаем значение как есть.
    """
    if not value:
        return value or ""
    import re
    # Паттерн: пробел перед заглавной буквой с точкой (один или несколько инициалов)
    # Примеры match: " И.", " И.А.", " А.В."
    return re.sub(r" (?=[А-ЯA-ZЁ]\.(?:[А-ЯA-ZЁ]\.)*$)", chr(0xa0), value)


def _initials_native(applicant: Applicant) -> str:
    """
    Сокращённая форма (Иванов И.И.).
    Pack 14 fix: fallback на latin (Yuksel V.).
    """
    if applicant.last_name_native and applicant.first_name_native:
        # Pack 35.11: NBSP между фамилией и инициалом (Word не разрывает строку)
        result = f"{applicant.last_name_native} {applicant.first_name_native[0]}."
        if applicant.middle_name_native:
            result += f"{applicant.middle_name_native[0]}."
        return result

    # Fallback на latin
    if applicant.last_name_latin and applicant.first_name_latin:
        # Pack 35.11: NBSP между фамилией и инициалом (latin fallback)
        return f"{applicant.last_name_latin} {applicant.first_name_latin[0]}."

    return ""


def _build_citizen_phrase(applicant: Applicant) -> str:
    """
    Юридически правильная формулировка для договора:
    "Гражданин Российской Федерации"
    "Гражданка Турецкой Республики"
    "Гражданин Республики Польша"

    Pack 14 fix: расширен список стран до 60+. Если страна не в словаре —
    fallback на ISO код (например "Гражданин XYZ"), чтобы было видно непокрытый кейс.
    """
    is_female = applicant.sex == "M"  # M = Mujer
    citizen_word = "Гражданка" if is_female else "Гражданин"

    nationality = applicant.nationality
    if not nationality:
        # Если nationality не задано — оставляем как было (RUS по умолчанию)
        country = "Российской Федерации"
    else:
        country = _NATIONALITY_GENITIVE_RU.get(nationality)
        if not country:
            # Страна не в словаре — используем ISO код (видимый «дефект» который заметит менеджер)
            country = nationality

    return f"{citizen_word} {country}"


def _build_named_suffix(applicant: Applicant) -> str:
    """'ый' для мужчин и 'ая' для женщин."""
    is_female = applicant.sex == "M"
    return "ая" if is_female else "ый"


def _parse_passport(passport_number: str | None, nationality: str | None) -> dict:
    """Разбирает номер паспорта на серию и номер с учётом гражданства."""
    if not passport_number:
        return {"series": "", "number_only": "", "formatted": ""}

    clean = passport_number.replace(" ", "").replace("-", "")

    if nationality == "RUS":
        digits = re.sub(r"\D", "", clean)
        if len(digits) >= 10:
            series = digits[:4]
            number_only = digits[4:10]
            return {
                "series": series,
                "number_only": number_only,
                "formatted": f"серии {series} № {number_only}",
            }
        return {
            "series": "",
            "number_only": passport_number,
            "formatted": f"№ {passport_number}",
        }

    return {
        "series": "",
        "number_only": passport_number,
        "formatted": f"№ {passport_number}",
    }


# ============================================================================
# Monthly documents (acts + invoices)
# ============================================================================

def _generate_monthly_documents(application: Application) -> list[dict]:
    if application.monthly_documents_override:
        result = []
        for item in application.monthly_documents_override:
            row = dict(item)
            for key in ("period_start", "period_end", "document_date"):
                if isinstance(row.get(key), str):
                    row[key] = date.fromisoformat(row[key])
            row["month_name_ru"] = _MONTHS_NOMINATIVE_RU[row["period_end"].month - 1]
            row["month_name_genitive_ru"] = _MONTHS_GENITIVE_RU[row["period_end"].month - 1]
            row["year_suffix"] = f"{row['period_end'].year % 100:02d}"
            row["salary_rub_words"] = _money_to_words_ru(row.get("salary_rub", 0))
            result.append(row)
        return result

    submission = application.submission_date or date.today()
    months_count = application.payments_period_months or 3
    salary = application.salary_rub or Decimal("0")

    # Pack 30.0 — правило 5-го числа.
    # До 5-го (1-4) последний учтённый месяц = позапрошлый (submission - 2).
    # С 5-го (включительно) — предыдущий (submission - 1).
    # Это стандартная буферная дата: к 5-му числу следующего месяца предыдущий
    # считается полностью закрытым (зарплата выплачена, налоги учтены, чек НПД
    # сформирован в "Моём налоге").
    months_back = 1 if submission.day >= 5 else 2

    # Вычисляем (year, month) последнего «закрытого» месяца, отступая months_back назад.
    last_year = submission.year
    last_month = submission.month - months_back
    while last_month <= 0:
        last_month += 12
        last_year -= 1

    cur_year, cur_month = last_year, last_month
    collected = []
    for i in range(months_count):
        period_start = date(cur_year, cur_month, 1)
        last_day = monthrange(cur_year, cur_month)[1]
        period_end = date(cur_year, cur_month, last_day)
        collected.append({
            "period_start": period_start,
            "period_end": period_end,
            "document_date": period_end,
            "month_name_ru": _MONTHS_NOMINATIVE_RU[cur_month - 1],
            "month_name_genitive_ru": _MONTHS_GENITIVE_RU[cur_month - 1],
            "year_suffix": f"{cur_year % 100:02d}",
            "salary_rub": salary,
            "salary_rub_words": _money_to_words_ru(salary),
        })
        cur_month -= 1
        if cur_month == 0:
            cur_month = 12
            cur_year -= 1

    collected.sort(key=lambda x: x["period_start"])
    for idx, item in enumerate(collected, start=1):
        item["sequence_number"] = idx
        # Pack 25.6 v2: display_number = "MM/YY" для шаблонов (АКТ № 04/26)
        # sequence_number оставляем idx для lookup в docx_renderer
        _month_str = f"{item['period_start'].month:02d}"
        item["display_number"] = f"{_month_str}/{item['year_suffix']}"

    return collected


# ============================================================================
# EUR conversion
# ============================================================================

def _company_legal_line1(company) -> str:
    """
    Pack 26.1: первая строка юр. адреса компании.
    Если задан ручной legal_address_line1 — сокращаем и используем его.
    Иначе — сокращаем legal_address и берём первую половину сплита по запятой.
    """
    if company.legal_address_line1:
        return abbreviate_address(company.legal_address_line1)
    addr = abbreviate_address(company.legal_address or "")
    if not addr:
        return ""
    line1, _ = _split_address_at_comma(addr)
    return line1


def _company_legal_line2(company) -> str:
    """Pack 26.1: вторая строка юр. адреса компании."""
    if company.legal_address_line2:
        return abbreviate_address(company.legal_address_line2)
    if company.legal_address_line1:
        # line1 задан вручную, line2 нет — оставляем пустым (предполагается полностью в line1)
        return ""
    addr = abbreviate_address(company.legal_address or "")
    if not addr:
        return ""
    _, line2 = _split_address_at_comma(addr)
    return line2


def _company_postal_line1(company) -> str:
    """Pack 26.1: первая строка почт. адреса компании."""
    if company.postal_address_line1:
        return abbreviate_address(company.postal_address_line1)
    addr = abbreviate_address(company.postal_address or company.legal_address or "")
    if not addr:
        return ""
    line1, _ = _split_address_at_comma(addr)
    return line1


def _company_postal_line2(company) -> str:
    """Pack 26.1: вторая строка почт. адреса компании."""
    if company.postal_address_line2:
        return abbreviate_address(company.postal_address_line2)
    if company.postal_address_line1:
        return ""
    addr = abbreviate_address(company.postal_address or company.legal_address or "")
    if not addr:
        return ""
    _, line2 = _split_address_at_comma(addr)
    return line2


def _build_eur_data(application: Application) -> dict:
    salary = application.salary_rub or Decimal("0")

    rate_date = (
        application.employer_letter_date
        or application.contract_sign_date
        or date.today()
    )

    if application.eur_rate_override is not None:
        rate = application.eur_rate_override
    else:
        rate = get_eur_rub_rate(rate_date)

    eur_amount = (Decimal(str(salary)) / rate).quantize(Decimal("1"))

    return {
        "rate": rate,
        "rate_date": rate_date,
        "amount": eur_amount,
        "amount_int": int(eur_amount),
        "amount_words_es": _money_to_words_es(int(eur_amount)),
        "amount_words_ru": _number_to_words_ru(int(eur_amount)),
    }


# ============================================================================
# Bank statement
# ============================================================================

def _enrich_bank_with_statement_fields(
    bank_data: dict,
    application: Application,
) -> dict:
    """
    Pack 16.2: добавляет в bank_data дополнительные поля для шапки выписки:
    - account_open_date / account_open_date_formatted: дата открытия счёта
      (предполагаем contract_sign_date - 6 месяцев, если другое не задано)
    - statement_date / statement_date_formatted: дата формирования выписки
      (период_end + 1 день, либо submission_date)

    Эти поля нужны новому шаблону bank_statement_template.docx.
    """
    from datetime import timedelta

    # Дата открытия счёта: contract_sign_date минус ~6 месяцев (≈183 дня).
    # Не используем relativedelta чтобы не тащить dateutil как зависимость.
    account_open_date = None
    if application.contract_sign_date:
        account_open_date = application.contract_sign_date - timedelta(days=183)

    # Pack 25.8: дата формирования берётся из генератора (today - random(7..10)).
    # Fallback на старую логику period_end+1, в крайнем случае - submission_date.
    statement_date = bank_data.get("statement_date")
    if not statement_date:
        period_end = bank_data.get("period_end")
        if period_end:
            statement_date = period_end + timedelta(days=1)
        elif application.submission_date:
            statement_date = application.submission_date

    bank_data["account_open_date"] = account_open_date
    bank_data["account_open_date_formatted"] = fmt_date_ru(account_open_date) if account_open_date else ""
    bank_data["statement_date"] = statement_date
    bank_data["statement_date_formatted"] = fmt_date_ru(statement_date) if statement_date else ""

    return bank_data


def _build_bank_context(application: Application, company: Company | None, applicant: Applicant | None = None) -> dict:
    if application.bank_transactions_override:
        try:
            data = deserialize_from_storage(application.bank_transactions_override)
            transactions = data["transactions"]
            opening_balance = data["opening_balance"]
            period_start = data["period_start"]
            period_end = data["period_end"]
        except (KeyError, ValueError):
            return _generate_fresh_bank_context(application, company, applicant)

        total_income = sum(
            (t["amount"] for t in transactions if t["amount"] > 0),
            Decimal("0"),
        )
        total_expense = sum(
            (-t["amount"] for t in transactions if t["amount"] < 0),
            Decimal("0"),
        )
        # Pack 36.1: гарантируем closing_balance >= 5000
        MIN_CLOSING = Decimal("5000.00")
        net = total_income - total_expense
        if opening_balance + net < MIN_CLOSING:
            opening_balance = MIN_CLOSING - net
        closing_balance = opening_balance + net

        for t in transactions:
            t["amount_formatted"] = fmt_amount_signed(t["amount"])
            t["date_formatted"] = fmt_date_ru(t["transaction_date"])

        return {
            "period_start": period_start,
            "period_end": period_end,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "total_income": total_income,
            "total_expense": total_expense,
            "transactions": transactions,
            "period_start_formatted": fmt_date_ru(period_start),
            "period_end_formatted": fmt_date_ru(period_end),
            "opening_balance_formatted": fmt_amount_signed(opening_balance),
            "closing_balance_formatted": fmt_amount_signed(closing_balance),
            "total_income_formatted": fmt_amount_signed(total_income),
            "total_expense_formatted": fmt_amount_signed(total_expense),
        }

    return _generate_fresh_bank_context(application, company, applicant)


def _generate_fresh_bank_context(application: Application, company: Company | None, applicant: Applicant | None = None) -> dict:
    # Pack 16.2: используем contract_sign_date как fallback если submission_date None.
    # Это позволяет генерировать выписку до того как менеджер выставит дату подачи.
    base_date = application.submission_date or application.contract_sign_date

    if not base_date or not company or not application.salary_rub:
        return {
            "period_start": None, "period_end": None,
            "opening_balance": Decimal("0"), "closing_balance": Decimal("0"),
            "total_income": Decimal("0"), "total_expense": Decimal("0"),
            "transactions": [],
            "period_start_formatted": "", "period_end_formatted": "",
            "opening_balance_formatted": "", "closing_balance_formatted": "",
            "total_income_formatted": "", "total_expense_formatted": "",
        }

    npd_rate = application.bank_npd_rate or DEFAULT_NPD_RATE
    monthly_fee = application.bank_monthly_fee or DEFAULT_BANK_FEE_PER_MONTH

    # Pack 35.4: applicant теперь передаётся параметром (не через ленивый relationship).
    # Это критично т.к. application.applicant иногда не подгружен в сессии
    # (зависит от того как application пришёл в build_context).
    # Pack 25.9.1: реальные поля: first_name_native + last_name_native.
    # Pack 35.4 fallback: если русские поля пустые — пробуем латинские
    # (для иностранцев, у которых менеджер ещё не вписал русские).
    _applicant_full_name_ru = None
    _applicant_phone = None
    if applicant is not None:
        _first = (applicant.first_name_native or "").strip()
        _last = (applicant.last_name_native or "").strip()
        _full = f"{_first} {_last}".strip()
        if not _full:
            # Fallback на латинские поля (имя + фамилия)
            _first_l = (applicant.first_name_latin or "").strip()
            _last_l = (applicant.last_name_latin or "").strip()
            _full = f"{_first_l} {_last_l}".strip()
        _applicant_full_name_ru = _full or None
        
        _applicant_phone = applicant.phone

    result = generate_default_transactions(
        submission_date=base_date,
        salary_rub=application.salary_rub,
        contract_number=application.contract_number or "",
        contract_sign_date=application.contract_sign_date,
        company_full_name=company.full_name_ru,
        company_inn=company.tax_id_primary,
        company_bank_account=company.bank_account,
        company_bank_bic=company.bank_bic,
        npd_rate=npd_rate,
        bank_fee=monthly_fee,
        seed=application.id or 0,
        applicant_full_name_ru=_applicant_full_name_ru,
        applicant_phone=_applicant_phone,
        
        # Pack 25.9: ручной override даты формирования (если задан в админке)
        statement_date_override=getattr(application, "bank_statement_date", None),
    )

    # Pack 25.9: legacy bank_period_start/end больше не override-ят период.
    # Период теперь определяется через application.bank_statement_date (см. вызов выше).
    # if application.bank_period_start:
    #     result["period_start"] = application.bank_period_start
    # if application.bank_period_end:
    #     result["period_end"] = application.bank_period_end
    if application.bank_opening_balance is not None:
        result["opening_balance"] = application.bank_opening_balance
        result["closing_balance"] = (
            result["opening_balance"] + result["total_income"] - result["total_expense"]
        )

    for t in result["transactions"]:
        t["amount_formatted"] = fmt_amount_signed(t["amount"])
        t["date_formatted"] = fmt_date_ru(t["transaction_date"])

    result["period_start_formatted"] = fmt_date_ru(result["period_start"])
    result["period_end_formatted"] = fmt_date_ru(result["period_end"])
    result["opening_balance_formatted"] = fmt_amount_signed(result["opening_balance"])
    result["closing_balance_formatted"] = fmt_amount_signed(result["closing_balance"])
    result["total_income_formatted"] = fmt_amount_signed(result["total_income"])
    result["total_expense_formatted"] = fmt_amount_signed(result["total_expense"])

    return result


# ============================================================================
# Main: build context dict for templates
# ============================================================================

# ============================================================================
# Pack 25.7: DN-наниматель первой записью в CV work_history.
# ============================================================================

_RU_MONTHS_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def _previous_month_label(reference_date) -> str:
    """Возвращает 'Сентябрь 2025' если reference_date = 14.10.2025."""
    if not reference_date:
        return ""
    year = reference_date.year
    month = reference_date.month - 1
    if month == 0:
        month = 12
        year -= 1
    return f"{_RU_MONTHS_NAMES[month - 1]} {year}"


def _format_month_label(d) -> str:
    if not d:
        return ""
    return f"{_RU_MONTHS_NAMES[d.month - 1]} {d.year}"


def _build_cv_work_history(applicant, application, company, position) -> list:
    """
    Pack 25.7: вставляет DN-нанимателя (текущего работодателя по визе) ПЕРВОЙ
    записью в work_history. Чинит предыдущую запись чтобы не было двух работ
    с period_end='по настоящее время'.

    Возвращает новый список — applicant.work_history НЕ модифицируется.

    Pack 37.6: после Pack 37.2 (sync work_history в БД) функция стала защитным
    слоем. Если БД уже содержит DN-employer первой записью — no-op, возвращаем
    base как есть. Иначе подмешиваем как раньше.
    """
    base = list(applicant.work_history or [])

    # Если нет всех данных для DN-работы — возвращаем сырой work_history
    if not application or not company or not position:
        return base
    if not application.contract_sign_date:
        return base

    # Pack 37.6: проверка идемпотентности. Если первая запись уже = DN-employer
    # с period_end='по настоящее время' — БД синхронизирована (Pack 37.2),
    # ничего не подмешиваем. Без этой проверки CV получал бы дубликат
    # работодателя с битыми датами 'Февраль 2026 — Январь 2026'.
    if base and isinstance(base[0], dict):
        first_company = (base[0].get("company") or "").strip()
        first_period_end = (base[0].get("period_end") or "").strip().lower()
        target_company = (company.full_name_ru or "").strip()
        # Сравниваем без учёта тонких различий в кавычках/пробелах
        def _normalize(s: str) -> str:
            return " ".join(s.replace("«", '"').replace("»", '"').split())
        if (
            _normalize(first_company) == _normalize(target_company)
            and first_period_end in ("по настоящее время", "настоящее время", "н.в.", "по н.в.")
        ):
            # БД уже синхронизирована — ничего не делаем
            return base

    # 1. Чиним предыдущую запись (первую в списке — самую свежую)
    fixed_base = []
    for i, item in enumerate(base):
        if not isinstance(item, dict):
            fixed_base.append(item)
            continue
        new_item = dict(item)  # копия чтобы не мутировать оригинал
        if i == 0:  # самая свежая запись
            pe = (new_item.get("period_end") or "").strip().lower()
            if pe in ("по настоящее время", "настоящее время", "н.в.", "по н.в."):
                new_item["period_end"] = _previous_month_label(application.contract_sign_date)
        fixed_base.append(new_item)

    # 2. Создаём DN-запись
    dn_record = {
        "period_start": _format_month_label(application.contract_sign_date),
        "period_end": "по настоящее время",
        "company": company.full_name_ru or "",
        "position": position.title_ru or "",
        "duties": list(position.duties or []),
    }

    # 3. Возвращаем DN первой + остальные
    return [dn_record] + fixed_base




# ============================================================
# Pack 40.0: Helper'ы для Tech Opinion (Техническое заключение)
# ============================================================

_DIRECTOR_POSITION_NOMINATIVE_RU = {
    "Генерального директора": "Генеральный директор",
    "генерального директора": "Генеральный директор",
    "Директора": "Директор",
    "директора": "Директор",
    "Исполнительного директора": "Исполнительный директор",
    "исполнительного директора": "Исполнительный директор",
    "Управляющего": "Управляющий",
    "управляющего": "Управляющий",
    "Президента": "Президент",
    "президента": "Президент",
}


_DIRECTOR_POSITION_ES = {
    "Генерального директора": "Director General",
    "генерального директора": "Director General",
    "Генеральный директор": "Director General",
    "генеральный директор": "Director General",
    "Директора": "Director",
    "директора": "Director",
    "Директор": "Director",
    "директор": "Director",
    "Исполнительного директора": "Director Ejecutivo",
    "Исполнительный директор": "Director Ejecutivo",
    "Управляющего": "Gerente",
    "Управляющий": "Gerente",
    "Президента": "Presidente",
    "Президент": "Presidente",
}


_RU_CITY_TO_ES = {
    "Москва": "Moscú",
    "москва": "Moscú",
    "г. Москва": "Moscú",
    "Санкт-Петербург": "San Petersburgo",
    "Санкт-петербург": "San Petersburgo",
    "г. Санкт-Петербург": "San Petersburgo",
    "Новосибирск": "Novosibirsk",
    "Екатеринбург": "Ekaterimburgo",
    "Казань": "Kazán",
    "Нижний Новгород": "Nizhni Nóvgorod",
    "Челябинск": "Cheliábinsk",
    "Самара": "Samara",
    "Омск": "Omsk",
    "Ростов-на-Дону": "Rostov del Don",
    "Уфа": "Ufá",
    "Красноярск": "Krasnoyarsk",
    "Воронеж": "Vorónezh",
    "Пермь": "Perm",
    "Волгоград": "Volgogrado",
    "Краснодар": "Krasnodar",
    "Саратов": "Sarátov",
    "Тюмень": "Tiumén",
    "Тольятти": "Tolyatti",
    "Ижевск": "Izhevsk",
    "Барнаул": "Barnaúl",
    "Ульяновск": "Uliánovsk",
    "Иркутск": "Irkutsk",
    "Хабаровск": "Jabárovsk",
    "Ярославль": "Yaroslavl",
    "Владивосток": "Vladivostok",
    "Махачкала": "Majachkalá",
    "Томск": "Tomsk",
    "Оренбург": "Orenburgo",
    "Кемерово": "Kémerovo",
    "Новокузнецк": "Novokuznetsk",
    "Рязань": "Riazán",
    "Астрахань": "Astracán",
    "Набережные Челны": "Náberezhnye Chelny",
    "Пенза": "Penza",
    "Липецк": "Lipetsk",
    "Тула": "Tula",
    "Киров": "Kírov",
    "Чебоксары": "Cheboksary",
    "Калининград": "Kaliningrado",
    "Брянск": "Briansk",
    "Курск": "Kursk",
    "Иваново": "Ivánovo",
    "Магнитогорск": "Magnitogorsk",
    "Тверь": "Tver",
    "Ставрополь": "Stávropol",
    "Симферополь": "Simferópol",
    "Белгород": "Bélgorod",
    "Архангельск": "Arjángelsk",
    "Владимир": "Vladímir",
    "Сочи": "Sochi",
    "Курган": "Kurgán",
    "Смоленск": "Smolensko",
    "Калуга": "Kaluga",
    "Чита": "Chita",
    "Орёл": "Oriol",
    "Волжский": "Volzhski",
    "Череповец": "Cherepovets",
    "Владикавказ": "Vladikavkaz",
    "Мурманск": "Múrmansk",
    "Сургут": "Surgut",
    "Вологда": "Vólogda",
    "Тамбов": "Tambov",
    "Стерлитамак": "Sterlitamak",
    "Грозный": "Grozni",
    "Якутск": "Yakutsk",
    "Кострома": "Kostromá",
    "Комсомольск-на-Амуре": "Komsomolsk del Amur",
    "Петрозаводск": "Petrozavodsk",
    "Таганрог": "Taganrog",
    "Нижневартовск": "Nizhnevartovsk",
    "Йошкар-Ола": "Yoshkar-Olá",
    "Братск": "Bratsk",
    "Новороссийск": "Novorossiisk",
    "Дзержинск": "Dzerzhinsk",
    "Шахты": "Shajty",
    "Нальчик": "Nálchik",
    "Орск": "Orsk",
    "Сыктывкар": "Syktyvkar",
    "Нижнекамск": "Nizhnekamsk",
    "Ангарск": "Angarsk",
    "Балашиха": "Balashija",
    "Благовещенск": "Blagovéshchensk",
    "Прокопьевск": "Prokópievsk",
    "Химки": "Jimki",
    "Псков": "Pskov",
    "Бийск": "Biisk",
    "Энгельс": "Engels",
    "Рыбинск": "Rybinsk",
    "Балаково": "Balakovo",
    "Северодвинск": "Severodvinsk",
    "Армавир": "Armavir",
    "Подольск": "Podolsk",
    "Королёв": "Koroliov",
    "Сызрань": "Syzran",
    "Норильск": "Norilsk",
    "Златоуст": "Zlatoust",
    "Каменск-Уральский": "Kámensk-Uralski",
    "Мытищи": "Mytíshchi",
    "Люберцы": "Liubertsy",
    "Волгодонск": "Volgodonsk",
    "Новочеркасск": "Novocherkassk",
    "Абакан": "Abakán",
    "Находка": "Najodka",
    "Уссурийск": "Ussuriisk",
    "Березники": "Berezniki",
    "Салават": "Salavat",
    "Электросталь": "Elektrostal",
    "Миасс": "Miass",
    "Рубцовск": "Rubtsovsk",
    "Альметьевск": "Almétievsk",
    "Ковров": "Kovrov",
    "Коломна": "Kolomna",
    "Майкоп": "Maikop",
    "Пятигорск": "Piatigorsk",
    "Одинцово": "Odintsovo",
    "Копейск": "Kopeisk",
    "Хасавюрт": "Jasaviurt",
    "Новомосковск": "Novomoskovsk",
    "Кисловодск": "Kislovodsk",
    "Серпухов": "Serpújov",
    "Первоуральск": "Pervouralsk",
    "Нефтеюганск": "Neftéyugansk",
    "Черкесск": "Cherkessk",
    "Орехово-Зуево": "Orejovo-Zuyevo",
    "Дербент": "Derbent",
    "Камышин": "Kamyshin",
    "Невинномысск": "Nevinnomyssk",
    "Красногорск": "Krasnogorsk",
    "Муром": "Murom",
    "Батайск": "Bataisk",
    "Новочебоксарск": "Novocheboksarsk",
    "Тобольск": "Tobolsk",
    "Бердск": "Berdsk",
    "Каспийск": "Kaspiisk",
    "Назрань": "Nazran",
    "Артём": "Artiom",
    "Ачинск": "Achinsk",
    "Ноябрьск": "Noyabrsk",
    "Северск": "Seversk",
    "Дербент": "Derbent",
}


_RU_MONTH_TO_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _to_director_position_nominative_ru(pos_ru: str) -> str:
    """"Генерального директора" → "Генеральный директор". Если нет в словаре — вернёт как есть."""
    if not pos_ru:
        return ""
    return _DIRECTOR_POSITION_NOMINATIVE_RU.get(pos_ru.strip(), pos_ru)


def _to_director_position_es(pos_ru: str) -> str:
    """"Генерального директора" → "Director General". Если нет — fallback на "Director General"."""
    if not pos_ru:
        return "Director General"
    return _DIRECTOR_POSITION_ES.get(pos_ru.strip(), "Director General")


def _ru_city_to_es(ru_city: str) -> str:
    """"Москва" → "Moscú". Если нет в словаре — вернёт исходное (транслит сделает руками либо латиницей)."""
    if not ru_city:
        return ""
    s = ru_city.strip()
    # Снимаем префикс "г. "
    if s.startswith("г. "):
        s = s[3:]
    return _RU_CITY_TO_ES.get(s, s)


def _fmt_date_es(d) -> str:
    """"15.01.2025" → "15 de enero de 2025". Принимает date|None, возвращает str."""
    if d is None:
        return ""
    try:
        return f"{d.day} de {_RU_MONTH_TO_ES[d.month]} de {d.year}"
    except Exception:
        return str(d)


def _short_latin_from_full(full_latin: str) -> str:
    """Pack 44.0: русский порядок ФИО (Фамилия Имя Отчество) → испанский стиль подписи.

    "KAYTUKTI KONSTANTIN PETROVICH" → "K.P. KAYTUKTI"
    "Vasilevskaia Anna Vadimovna"   → "A.V. VASILEVSKAIA"
    "Smith"                          → "SMITH"
    ""                               → ""

    Логика:
        - parts[0]  = фамилия (первая в русском ФИО)
        - parts[1:] = имя + отчество → становятся инициалами
        - Результат: "{INITIALS}. {LASTNAME_UPPER}"
        - Фамилия в UPPERCASE — испанский визовый стиль (как MRZ).
    """
    if not full_latin:
        return ""
    parts = full_latin.strip().split()
    if len(parts) == 0:
        return ""
    if len(parts) == 1:
        return parts[0].upper()
    last_name = parts[0]
    given_names = parts[1:]
    initials = ".".join(p[0] for p in given_names if p) + "."
    return f"{initials} {last_name.upper()}"


def _build_applicant_honorifics(applicant) -> dict:
    """
    Возвращает dict с honorific-формами по полу applicant.gender ('M'/'F'/None).
    Если поля gender нет в модели — пробуем определить по middle_name_native (отчество на -ич/-ыч → мужской).
    """
    gender = getattr(applicant, "gender", None)
    if not gender:
        # Эвристика по отчеству
        mn = (getattr(applicant, "middle_name_native", "") or "").strip().lower()
        if mn.endswith(("вич", "ьич", "ыч", "ич")):
            gender = "M"
        elif mn.endswith(("вна", "ична", "инична")):
            gender = "F"
        else:
            gender = "M"  # fallback

    if gender == "F":
        return {
            "honorific_ru": "Гражданка",
            "honorific_ru_genitive": "гражданки",
            "honorific_ru_dative": "гражданке",
            "honorific_ru_instrumental": "гражданкой",
            "honorific_es": "la Sra.",
        }
    # M (default)
    return {
        "honorific_ru": "Гражданин",
        "honorific_ru_genitive": "гражданина",
        "honorific_ru_dative": "гражданину",
        "honorific_ru_instrumental": "гражданином",
        "honorific_es": "el Sr.",
    }


def _full_name_latin_combined(applicant) -> str:
    """"first_name_latin + ' ' + last_name_latin" с защитой от None."""
    fn = (getattr(applicant, "first_name_latin", "") or "").strip()
    ln = (getattr(applicant, "last_name_latin", "") or "").strip()
    return (fn + " " + ln).strip()



# =============================================================================
# Pack 50.7-C — Приказ Т-9 о командировке: helpers
# =============================================================================

# Русские месяцы в родительном падеже (для дат вида «25 января 2026»)
_RU_MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _ru_int_to_words(n: int) -> str:
    """Целое число прописью на русском (нужно для срока 'три года', 'Сорок шесть месяцев')."""
    if n == 0:
        return "ноль"
    if n < 0:
        return "минус " + _ru_int_to_words(-n)

    units = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
             "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
    tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
            "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
    hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
                "шестьсот", "семьсот", "восемьсот", "девятьсот"]

    def _three_digits(n: int) -> str:
        parts = []
        h, rem = divmod(n, 100)
        if h:
            parts.append(hundreds[h])
        if 10 <= rem < 20:
            parts.append(teens[rem - 10])
        else:
            t, u = divmod(rem, 10)
            if t:
                parts.append(tens[t])
            if u:
                parts.append(units[u])
        return " ".join(parts)

    parts = []
    if n >= 1000:
        thousands, n = divmod(n, 1000)
        if thousands == 1:
            parts.append("одна тысяча")
        elif thousands == 2:
            parts.append("две тысячи")
        elif 3 <= thousands <= 4:
            parts.append(_three_digits(thousands) + " тысячи")
        else:
            parts.append(_three_digits(thousands) + " тысяч")
    if n:
        parts.append(_three_digits(n))
    return " ".join(parts).strip()


def _ru_capitalize_first(text: str) -> str:
    """'три года' → 'Три года' (только первую букву капитализируем, остальное не трогаем)."""
    if not text:
        return text
    return text[0].upper() + text[1:]


def _bt_duration_unit_full(unit: str, count: int) -> str:
    """Полная фраза единицы со склонением: 'календарных дней/месяцев/года/лет/годов'.

    Правила:
    - 1 → 'календарных <day/month/года>' (унифицированная форма Т-9 — всегда мн. число)
    - 2-4 → 'календарных <дня/месяца/года>'
    - 5+ → 'календарных <дней/месяцев/лет>'

    ОДНАКО в эталонах Т-9 (АО ПроТехнологии, ООО ФАКТОР СТРОЙ) ВСЕГДА
    используется множественное «календарных»:
      'три календарных года' (хотя по русскому было бы 'три календарных года')
      'Сорок шесть календарных месяцев'
      '1127 календарных дней'
    Поэтому возвращаем фиксированно мн. форму.
    """
    if unit == "days":
        return "календарных дней"
    if unit == "months":
        return "календарных месяцев"
    if unit == "years":
        # В эталонах: 'три календарных года' (даже если строго грамматически было бы иначе)
        if count in (1,):
            return "календарный год"
        if 2 <= count % 10 <= 4 and not (12 <= count % 100 <= 14):
            return "календарных года"
        return "календарных лет"
    return f"календарных {unit}"


def _bt_auto_duration(start_date, end_date) -> tuple[str, str]:
    """Авто-вычисление срока словами + единицы из дат начала/конца.

    Возвращает (duration_words, duration_unit), где unit ∈ {'days','months','years'}.

    Логика выбора:
    - Если разница ровно ≥730 дней и кратна полному году (±3 дня) → 'годы'
    - Иначе если ≥60 дней → 'месяцы'
    - Иначе → 'дни'
    """
    if not start_date or not end_date:
        return ("", "days")
    days = (end_date - start_date).days + 1  # включительно
    if days <= 0:
        return ("", "days")

    # Проверим — кратно ли полному году (с допуском)
    years_exact = days / 365.25
    if years_exact >= 1.0:
        years_round = round(years_exact)
        # допуск ±5 дней
        if abs(days - years_round * 365.25) <= 5:
            return (_ru_int_to_words(years_round), "years")

    # Проверим месяцы (≈30.44 дня)
    months_exact = days / 30.44
    if months_exact >= 2.0:
        months_round = round(months_exact)
        if abs(days - months_round * 30.44) <= 5:
            return (_ru_int_to_words(months_round), "months")

    # По умолчанию — дни
    return (_ru_int_to_words(days), "days")


def _bt_auto_order_number(application, session) -> str:
    """Авто-номерация номера приказа Т-9 по компании + текущему году.

    Логика — как outgoing_number в Pack 40.0-G (см. ниже в build_context):
    ищем MAX(N) среди application.business_trip_order_number у других заявок
    той же компании в текущем году, возвращаем (N+1)/к.

    Если для компании ещё ни одной заявки нет — '1/к'.
    """
    import re as _re
    from sqlmodel import select as _select

    if not application.company_id:
        return "1/к"

    stmt = _select(Application.business_trip_order_number).where(
        Application.company_id == application.company_id,
        Application.business_trip_order_number.is_not(None),
    )
    max_n = 0
    for raw in session.exec(stmt).all():
        if raw is None:
            continue
        m = _re.search(r"(\d+)", str(raw))
        if m:
            try:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return f"{max_n + 1}/к"


def _bt_format_place(spain_address, short_mode: bool) -> str:
    """Формат адреса командировки.

    short_mode=True → 'Испания, г. Барселона'
    short_mode=False → '08014, Королевство Испания, г. Барселона, ул. Каррер де Сантс, 95, 2-4'

    Если spain_address отсутствует — возвращаем хоть что-то ('Королевство Испания').
    """
    if spain_address is None:
        return "Королевство Испания"

    city = (spain_address.city or "").strip()
    if short_mode:
        if city:
            return f"Испания, г. {city}"
        return "Испания"

    # Полный формат
    parts = []
    if spain_address.zip:
        parts.append(spain_address.zip)
    parts.append("Королевство Испания")
    if city:
        parts.append(f"г. {city}")
    street = (spain_address.street or "").strip()
    number = (spain_address.number or "").strip()
    floor = (spain_address.floor or "").strip()
    if street:
        addr_tail = street
        if number:
            addr_tail += f", {number}"
        if floor:
            addr_tail += f"-{floor}"
        parts.append(addr_tail)
    return ", ".join(parts)


def _bt_resolve_purpose(application, position) -> str:
    """Резолв цели командировки.

    Приоритет: application.business_trip_purpose_override → position.business_trip_purpose → '' .
    """
    if application.business_trip_purpose_override:
        return application.business_trip_purpose_override.strip()
    if position and position.business_trip_purpose:
        return position.business_trip_purpose.strip()
    return ""


def build_business_trip_context(application, applicant, company, position, spain_address, session) -> dict:
    """Pack 50.7-C — собирает блок 'business_trip' для шаблона Т-9.

    Возвращает dict с 17 ключами, ВСЕ строки (для безопасной подстановки в DOCX).

    Если каких-то дат нет — авто-вычисляем дефолты:
    - order_date = contract_sign_date (или сегодня если нет)
    - start_date = submission_date или contract_sign_date + 30 дней (если нет — сегодня)
    - end_date = start_date + 3 года

    Авто-номерация order_number если NULL (по компании, как outgoing_number).
    Авто-вычисление duration_words + duration_unit если NULL (из дат).
    """
    from datetime import date as _date, timedelta

    # ---- Daты ----
    order_date = application.business_trip_order_date or application.contract_sign_date or _date.today()
    start_date = application.business_trip_start_date or application.submission_date
    if start_date is None and application.contract_sign_date:
        start_date = application.contract_sign_date + timedelta(days=30)
    if start_date is None:
        start_date = _date.today() + timedelta(days=30)

    end_date = application.business_trip_end_date
    if end_date is None:
        # +3 года от start
        try:
            end_date = start_date.replace(year=start_date.year + 3)
        except ValueError:
            # 29 февраля високосного → 28 февраля
            end_date = start_date.replace(year=start_date.year + 3, day=28)

    acknowledged_date = order_date  # дата ознакомления = дата приказа

    # ---- Срок словами + единица ----
    if application.business_trip_duration_words and application.business_trip_duration_unit:
        # menedger override
        duration_words = _ru_capitalize_first(application.business_trip_duration_words)
        duration_unit = application.business_trip_duration_unit
        # для unit_full нужен count, попробуем извлечь из слов или дат
        if duration_unit == "days":
            count = (end_date - start_date).days + 1
        elif duration_unit == "months":
            count = max(1, round(((end_date - start_date).days + 1) / 30.44))
        else:
            count = max(1, round(((end_date - start_date).days + 1) / 365.25))
    else:
        auto_words, auto_unit = _bt_auto_duration(start_date, end_date)
        duration_words = _ru_capitalize_first(auto_words) if auto_words else ""
        duration_unit = auto_unit
        if duration_unit == "days":
            count = (end_date - start_date).days + 1
        elif duration_unit == "months":
            count = max(1, round(((end_date - start_date).days + 1) / 30.44))
        else:
            count = max(1, round(((end_date - start_date).days + 1) / 365.25))

    # ---- Номер приказа ----
    order_number = application.business_trip_order_number
    if not order_number:
        # Авто-номерация по компании
        order_number = _bt_auto_order_number(application, session)
        # Пишем в БД (как outgoing_number в Pack 40.0)
        application.business_trip_order_number = order_number
        session.add(application)
        session.commit()
        session.refresh(application)

    # ---- Цель ----
    purpose = _bt_resolve_purpose(application, position)

    # ---- Место ----
    place = _bt_format_place(spain_address, application.business_trip_place_short or False)

    # ---- Финальный словарь ----
    return {
        "order_number": order_number,
        "order_date_str": order_date.strftime("%d.%m.%Y"),
        "employee_tab_number": application.employee_tab_number or "",
        "purpose": purpose,
        "place": place,
        "duration_words": duration_words,
        "duration_unit_full": _bt_duration_unit_full(duration_unit, count),
        # Даты разложенные на компоненты для ячеек Т-9
        "start_day": f"{start_date.day:02d}",
        "start_month_name_genitive": _RU_MONTHS_GENITIVE[start_date.month - 1],
        "start_year_short": f"{start_date.year % 100:02d}",
        "end_day": f"{end_date.day:02d}",
        "end_month_name_genitive": _RU_MONTHS_GENITIVE[end_date.month - 1],
        "end_year_short": f"{end_date.year % 100:02d}",
        "acknowledged_day": f"{acknowledged_date.day:02d}",
        "acknowledged_month_name_genitive": _RU_MONTHS_GENITIVE[acknowledged_date.month - 1],
        "acknowledged_year_short": f"{acknowledged_date.year % 100:02d}",
    }


def build_context(application: Application, session: Session) -> dict[str, Any]:
    applicant = session.get(Applicant, application.applicant_id) if application.applicant_id else None
    company = session.get(Company, application.company_id) if application.company_id else None
    position = session.get(Position, application.position_id) if application.position_id else None
    representative = session.get(Representative, application.representative_id) if application.representative_id else None
    spain_address = session.get(SpainAddress, application.spain_address_id) if application.spain_address_id else None

    if not applicant:
        raise ValueError("Application has no applicant data")
    if not company or not position:
        raise ValueError("Application not yet assigned to company/position")

    monthly_docs = _generate_monthly_documents(application)
    eur_data = _build_eur_data(application) if application.salary_rub else None
    bank_data = _build_bank_context(application, company, applicant)
    # Pack 16.2: добавляем поля для шапки выписки
    bank_data = _enrich_bank_with_statement_fields(bank_data, application)
    # Pack 47.2: Sber-постпроцессинг (категории, running_balance, формат сумм).
    # No-op для не-Сбер клиентов. Резолв через applicant.bank.bik.
    bank_data = _apply_sber_postprocess(bank_data, applicant, session)
    # Pack 48.0: ТБанк-постпроцессинг (формат сумм tx + итогов, генерация card_number).
    # No-op для не-ТБанк клиентов. Резолв через applicant.bank.bik (044525974).
    bank_data = _apply_tbank_postprocess(bank_data, applicant, session)

    # Парсим паспорт по гражданству.
    # Pack 41.0-K — для русских клиентов с выбранным внутренним паспортом
    # (nationality=RUS + passport_id_for_ru_docs указан + его тип RU_INTERNAL)
    # override на выбранный паспорт. Применяется ко ВСЕМ документам которые
    # идут через build_context: договор, акты, счета, ER-letter, CV,
    # tech_opinion, business_trip, employment_contract, bank statement.
    #
    # Для иностранцев и для русских без выбора внутреннего — стандартное
    # поведение Pack 41.0-G (primary через скаляр-зеркало applicant.passport_*).
    #
    # render_contract в docx_renderer.py (Pack 41.0-G) переопределяет
    # ещё раз для договора, разрешая ЛЮБОЙ тип выбранного паспорта.
    from app.services.applicant_passports import (
        get_passport_dict_for_ru_docs as _get_ru_passport,
    )
    from datetime import date as _date_pack41k
    _pass_number_pack41k = applicant.passport_number
    _pass_issue_date_pack41k = applicant.passport_issue_date
    _pass_issuer_pack41k = _resolve_passport_issuer_for_template(applicant)
    if (applicant.nationality or "").upper() == "RUS":
        _ru_dict_pack41k = _get_ru_passport(applicant)
        if (
            _ru_dict_pack41k.get("passport_type") == "RU_INTERNAL"
            and _ru_dict_pack41k.get("number")
        ):
            _pass_number_pack41k = _ru_dict_pack41k["number"]
            _raw_issue_pack41k = _ru_dict_pack41k.get("issue_date")
            if isinstance(_raw_issue_pack41k, str) and _raw_issue_pack41k:
                try:
                    _pass_issue_date_pack41k = _date_pack41k.fromisoformat(_raw_issue_pack41k)
                except ValueError:
                    pass
            elif _raw_issue_pack41k is not None:
                _pass_issue_date_pack41k = _raw_issue_pack41k
            _pass_issuer_pack41k = _resolve_passport_issuer_for_template_from_dict(
                _ru_dict_pack41k, applicant.nationality
            )
    passport_data = _parse_passport(_pass_number_pack41k, applicant.nationality)

    # === Pack 40.0-G: outgoing autogen (раньше был в API endpoint) ===
    if not application.outgoing_number or not application.outgoing_date:
        import re as _re
        from datetime import date as _date
        from sqlmodel import select as _select
        if not application.outgoing_number:
            _stmt = _select(Application.employer_letter_number).where(
                Application.company_id == application.company_id,
                Application.employer_letter_number.is_not(None),
            )
            _max_n = 0
            for _raw in session.exec(_stmt).all():
                if _raw is None:
                    continue
                _m = _re.search(r"(\d+)", str(_raw))
                if _m:
                    try:
                        _n = int(_m.group(1))
                        if _n > _max_n:
                            _max_n = _n
                    except ValueError:
                        pass
            application.outgoing_number = f"{_max_n + 1}/{_date.today().year}"
        if not application.outgoing_date:
            application.outgoing_date = _date.today()
        session.add(application)
        session.commit()
        session.refresh(application)

    return {
        "applicant": {
            "full_name_native": _full_name_native(applicant),
            "initials_native": _initials_native(applicant),
            "last_name_native": applicant.last_name_native or "",
            "first_name_native": applicant.first_name_native or "",
            "middle_name_native": applicant.middle_name_native or "",
            "last_name_latin": applicant.last_name_latin,
            "first_name_latin": applicant.first_name_latin,
            "birth_date": applicant.birth_date,
            "birth_place_latin": applicant.birth_place_latin,
            "nationality": applicant.nationality,
            # Паспорт — структурированные поля
            # Pack 41.0-K — _pass_*_pack41k = override для RUS+INT, иначе primary
            "passport_number": _pass_number_pack41k,
            "passport_series": passport_data["series"],
            "passport_number_only": passport_data["number_only"],
            "passport_formatted": passport_data["formatted"],
            "passport_issue_date": _pass_issue_date_pack41k,
            "passport_issue_date_str": fmt_date_ru(_pass_issue_date_pack41k),
            "passport_issuer": _pass_issuer_pack41k,
            "inn": applicant.inn or "",
            # Pack 50.1-F2 — СНИЛС (Трудовой договор, реквизиты работника)
            "snils": applicant.snils or "",
            "home_address": abbreviate_address(applicant.home_address or ""),
            "home_address_line1": _bank_statement_address_line1(applicant),
            "home_address_line2": _bank_statement_address_line2(applicant),
            "email": applicant.email,
            "phone": applicant.phone,
            "nationality_ru_genitive": _NATIONALITY_GENITIVE_RU.get(
                applicant.nationality, applicant.nationality or ""
            ),
            "nationality_ru": _NATIONALITY_NOMINATIVE_RU.get(
                applicant.nationality, applicant.nationality or ""
            ),
            # Юридически правильные формулировки для договора
            "citizen_phrase": _build_citizen_phrase(applicant),
            "named_suffix": _build_named_suffix(applicant),
            "passport_country_code": applicant.nationality,
            "bank_account": applicant.bank_account or "",
            # Pack 47.7: derived поле для Sber-шаблона (формат "XXXXX XXX X XXXX XXXXXXX").
            # Альфа продолжает использовать "bank_account" (без пробелов).
            "bank_account_formatted": _fmt_bank_account_groups(applicant.bank_account),
            "bank_name": applicant.bank_name or "",
            "bank_bic": applicant.bank_bic or "",
            "bank_correspondent_account": applicant.bank_correspondent_account or "",
            "education": applicant.education or [],
            "work_history": _build_cv_work_history(applicant, application, company, position),
            "languages": applicant.languages or [],
            # === Pack 50.7-C: винительный падеж ФИО для Приказа Т-9 ===
            "full_name_accusative": applicant.full_name_accusative or _full_name_native(applicant),
            # === Pack 40.0: tech_opinion ===
            "full_name_latin": _full_name_latin_combined(applicant),
            **_build_applicant_honorifics(applicant),
        },

        "company": {
            "short_name": company.short_name,
            "full_name_ru": company.full_name_ru,
            "full_name_es": company.full_name_es,
            "tax_id_primary": company.tax_id_primary,
            "tax_id_secondary": company.tax_id_secondary or "",
            # === Pack 50.7-C: ОКПО для Приказа Т-9 ===
            "okpo": company.okpo or "",
            # === Pack 50.8-B/fix3: ОКТМО + телефон для §1 справки 2-НДФЛ ===
            "oktmo": company.oktmo or "",
            "phone": company.phone or "",
            # === Pack 50.1-A/C: ОГРН + email для Трудового договора ===
            "ogrn": company.ogrn or "",
            "email": company.email or "",
            "legal_address": abbreviate_address(company.legal_address),
            "legal_address_line1": _company_legal_line1(company),
            "legal_address_line2": _company_legal_line2(company),
            "postal_address": abbreviate_address(company.postal_address or company.legal_address),
            "postal_address_line1": _company_postal_line1(company),
            "postal_address_line2": _company_postal_line2(company),
            "director_full_name_ru": company.director_full_name_ru,
            "director_full_name_genitive_ru": company.director_full_name_genitive_ru,
            "director_short_ru": _nbsp_initials(company.director_short_ru),
            "director_position_ru": company.director_position_ru,
            "bank_name": company.bank_name,
            "bank_account": company.bank_account,
            "bank_bic": company.bank_bic,
            "bank_correspondent_account": company.bank_correspondent_account or "",
            # === Pack 40.0: tech_opinion ===
            "director_position_ru_nominative": _to_director_position_nominative_ru(company.director_position_ru),
            "director_position_es": _to_director_position_es(company.director_position_ru),
            "director_full_name_latin_initials": _short_latin_from_full(company.director_full_name_latin or ""),
            "legal_address_es": company.legal_address,  # TODO: при необходимости — отдельное поле legal_address_es в модели Company
            "bank_name_es": company.bank_name,  # TODO: при необходимости — отдельное поле bank_name_es в модели Company
        },

        "position": {
            "title_ru": position.title_ru,
            "title_ru_genitive": position.title_ru_genitive or position.title_ru,
            "title_es": position.title_es,
            # === Pack 50.7-C: цель командировки (для override резолва в шаблоне) ===
            "business_trip_purpose": position.business_trip_purpose or "",
            "duties": position.duties,
            # === Pack 40.0: tech_opinion ===
            "international_analog_ru": position.international_analog_ru or "",
            "international_analog_es": position.international_analog_es or "",
            "tech_opinion_description_ru": position.tech_opinion_description_ru or "",
            "tech_opinion_description_es": position.tech_opinion_description_es or "",
            "tech_opinion_tools_ru": position.tech_opinion_tools_ru or [],
            "tech_opinion_tools_es": position.tech_opinion_tools_es or [],
            "tech_opinion_steps_ru": position.tech_opinion_steps_ru or [],
            "tech_opinion_steps_es": position.tech_opinion_steps_es or [],
            "tech_opinion_grounds_ru": position.tech_opinion_grounds_ru or [],
            "tech_opinion_grounds_es": position.tech_opinion_grounds_es or [],
            "tech_opinion_contract_clause_ru": position.tech_opinion_contract_clause_ru or "",
            "tech_opinion_contract_clause_es": position.tech_opinion_contract_clause_es or "",
        },

        "contract": {
            "number": application.contract_number or "",
            "sign_date": application.contract_sign_date,
            "sign_city": application.contract_sign_city or "",
            "end_date": application.contract_end_date,
            "salary_rub": application.salary_rub,
            "salary_rub_words": _money_to_words_ru(application.salary_rub),
            "sign_date_str": _format_date_ru(application.contract_sign_date),
            # === Pack 40.0: tech_opinion ===
            "sign_date_es": _fmt_date_es(application.contract_sign_date),
            # === Pack 41.0-J: почасовая ставка (для архетипа vozmezdnoe_hourly:
            # kns_grupp, buki_vedi). hours_per_month — стандарт ТК РФ
            # (40 ч/нед × 4 нед). hourly_rate_rub — вычисляемое поле:
            # salary_rub / 160, округлённое до 2 знаков. Если salary_rub
            # не задан — ставка 0 (шаблон покажет 0,00 ₽ как сигнал
            # менеджеру что оклад не заполнен). Шаблоны других архетипов
            # эти поля просто игнорируют (Jinja не падает на лишних
            # переменных в context). ===
            "hours_per_month": 160,
            "hourly_rate_rub": (
                (application.salary_rub / Decimal(160)).quantize(Decimal("0.01"))
                if application.salary_rub
                else Decimal("0")
            ),
        },

        "monthly_documents": monthly_docs,

        "eur": eur_data or {
            "rate": Decimal("0"),
            "rate_date": date.today(),
            "amount": Decimal("0"),
            "amount_int": 0,
            "amount_words_es": "cero",
            "amount_words_ru": "ноль",
        },

        "letter": {
            "number": application.employer_letter_number or "",
            "date": application.employer_letter_date,
        },

        # === Pack 40.0: tech_opinion — application-level поля ===
        "application": {
            "id": application.id,
            "reference": application.reference,
            "contract_number": application.contract_number or "",
            "outgoing_number": application.outgoing_number or "",
            "outgoing_date_str": _format_date_ru(application.outgoing_date) if application.outgoing_date else "",
            "outgoing_date_es": _fmt_date_es(application.outgoing_date),
            "sign_city_ru": application.contract_sign_city or "",
            "sign_city_es": _ru_city_to_es(application.contract_sign_city or ""),
            "tech_opinion_override_text": application.tech_opinion_override_text or "",
        },

        "representative": {
            "full_name": f"{representative.first_name} {representative.last_name}" if representative else "",
            "first_name": representative.first_name if representative else "",
            "last_name": representative.last_name if representative else "",
            "nie": representative.nie if representative else "",
            "email": representative.email if representative else "",
            "phone": representative.phone if representative else "",
        },

        "spain_address": {
            "street": spain_address.street if spain_address else "",
            "number": spain_address.number if spain_address else "",
            "floor": spain_address.floor if spain_address else "",
            "city": spain_address.city if spain_address else "",
            "zip": spain_address.zip if spain_address else "",
            "province": spain_address.province if spain_address else "",
        },

        "bank": bank_data,

        "fmt_date_ru": fmt_date_ru,
        "fmt_date_long_ru": fmt_date_long_ru,
        "fmt_date_quoted_ru": fmt_date_quoted_ru,
        "fmt_date_human_ru": fmt_date_human_ru,
        "fmt_money": fmt_money,
        "fmt_money_kop": fmt_money_kop,
        "fmt_amount_signed": fmt_amount_signed,

        # === Pack 50.7-C: Приказ Т-9 о командировке (найм) ===
        "business_trip": build_business_trip_context(
            application, applicant, company, position, spain_address, session,
        ),

        # === Pack 50.8-B: Справка 2-НДФЛ (найм) ===
        "ndfl_2": build_ndfl_2_context(
            application, applicant, company, session,
            passport_number_override=_pass_number_pack41k,
        ),
    }


# === Pack 35.2: passport_issuer_ru с резолвом на лету ===
def _resolve_passport_issuer_for_template(applicant) -> str:
    """
    Pack 35.2: возвращает passport_issuer для подстановки в русские шаблоны.

    Логика:
      1. Если у applicant заполнено passport_issuer_ru — используем его.
      2. Иначе — резолвим passport_issuer + nationality на лету (БД не трогаем).
      3. Если и резолв не дал ничего — fallback на passport_issuer как есть.
    """
    from app.services.passport_issuer_ru import resolve_passport_issuer_ru

    existing_ru = (getattr(applicant, "passport_issuer_ru", None) or "").strip()
    if existing_ru:
        return existing_ru

    resolved = resolve_passport_issuer_ru(
        applicant.passport_issuer, applicant.nationality
    )
    if resolved:
        return resolved

    return applicant.passport_issuer or ""


def _resolve_passport_issuer_for_template_from_dict(passport_dict: dict, nationality) -> str:
    """
    Pack 41.0-E — аналог _resolve_passport_issuer_for_template, но работает
    с произвольным passport_dict (для случая когда паспорт != primary,
    выбран через passport_id_for_ru_docs).

    Приоритет:
      1. passport_dict["issuer_ru"] если непуст.
      2. Иначе резолвим passport_dict["issuer"] + nationality.
      3. Иначе fallback на passport_dict["issuer"] как есть.
    """
    from app.services.passport_issuer_ru import resolve_passport_issuer_ru

    issuer_ru_val = passport_dict.get("issuer_ru") if passport_dict else None
    existing_ru = (issuer_ru_val or "").strip() if issuer_ru_val else ""
    if existing_ru:
        return existing_ru

    issuer = (passport_dict.get("issuer") if passport_dict else None) or ""
    if not issuer.strip():
        return ""

    resolved = resolve_passport_issuer_ru(issuer, nationality)
    if resolved:
        return resolved

    return issuer

# ============================================================================
# Pack 50.8-B — Справка 2-НДФЛ (НАЙМ)
# ============================================================================

# Код страны (ISO numeric) по nationality (ISO-3). Используется в §2 справки.
_COUNTRY_NUMERIC_CODE = {
    "RUS": "643",
    "BLR": "112",
    "UKR": "804",
    "KAZ": "398",
    "KGZ": "417",  # Кыргызстан — в одном из образцов был такой код для имени Mērim
    "UZB": "860",
    "TJK": "762",
    "ARM": "051",
    "AZE": "031",
    "GEO": "268",
    "MDA": "498",
    "TKM": "795",
}


def _ndfl_2_resolve_period(application) -> tuple[int, int, int, "_date"]:
    """Возвращает (year, period_from, period_to, issue_date) с дефолтами.

    Дефолты:
      - year = текущий год
      - period_from = 1 (январь)
      - period_to = последний полный месяц (текущий месяц - 1; если январь — то 12 предыдущего года)
      - issue_date = 1-е число месяца, следующего за period_to
    """
    from datetime import date as _date, timedelta

    today = _date.today()
    year = application.ndfl_2_year
    period_from = application.ndfl_2_period_from
    period_to = application.ndfl_2_period_to

    if not year and not period_to:
        # Полностью авто
        if today.month == 1:
            # В январе нет полных месяцев текущего года → берём декабрь предыдущего
            year = today.year - 1
            period_from = 1
            period_to = 12
        else:
            year = today.year
            period_from = 1
            period_to = today.month - 1
    else:
        # Хотя бы что-то задано — заполняем то что не задано
        if not year:
            year = today.year
        if not period_from:
            period_from = 1
        if not period_to:
            if year == today.year:
                period_to = max(1, today.month - 1)
            else:
                period_to = 12

    # Валидация
    period_from = max(1, min(12, int(period_from)))
    period_to = max(period_from, min(12, int(period_to)))

    # Дата формирования
    issue_date = application.ndfl_2_issue_date
    if not issue_date:
        # 1-е число месяца, следующего за period_to (в том же году)
        if period_to == 12:
            issue_date = _date(year + 1, 1, 1)
        else:
            issue_date = _date(year, period_to + 1, 1)

    return year, period_from, period_to, issue_date


def _ndfl_2_fmt_money(amount) -> str:
    """Форматирует Decimal/int как '300 000,00' (пробелы как разделители тысяч, запятая)."""
    from decimal import Decimal as _D
    if amount is None:
        return ""
    d = _D(str(amount)).quantize(_D("0.01"))
    int_part, dec_part = str(d).split(".")
    # Пробелы как разделители тысяч (NBSP \u00a0 не нужны — в ячейке таблицы Word не рвёт)
    negative = int_part.startswith("-")
    if negative:
        int_part = int_part[1:]
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    if int_part:
        groups.insert(0, int_part)
    # NBSP (\u00a0) вместо обычного пробела чтобы Word не переносил суммы на 2 строки в узких ячейках
    formatted = "\u00a0".join(groups) + "," + dec_part
    if negative:
        formatted = "-" + formatted
    return formatted


def _ndfl_2_resolve_passport(applicant, passport_number_override: str | None = None) -> tuple[str, str]:
    """Возвращает (id_doc_code, passport_series_number).

    id_doc_code:
      - "21" — паспорт гражданина РФ (для RUS + RU_INTERNAL)
      - "10" — паспорт иностранного гражданина (для остальных)

    passport_series_number: "XXXX YYYYYY" для РФ, либо номер как есть для иностранцев.

    Используется уже выбранный паспорт (с учётом Pack 41.0-K для русских с
    мульти-паспортом — для них передаётся passport_number_override).
    """
    import re as _re

    raw_number = passport_number_override or (applicant.passport_number or "")
    nationality = (applicant.nationality or "").upper()

    if nationality == "RUS":
        digits = _re.sub(r"\D", "", raw_number)
        if len(digits) >= 10:
            series = digits[:4]
            number_only = digits[4:10]
            return "21", f"{series} {number_only}"
        # Кривой номер — но всё равно паспорт РФ
        return "21", raw_number
    # Иностранец
    return "10", raw_number


def build_ndfl_2_context(application, applicant, company, session, passport_number_override: str | None = None) -> dict:
    """Pack 50.8-B — собирает блок 'ndfl_2' для шаблона ndfl_2_template.docx.

    Args:
        application: Application instance.
        applicant: Applicant instance.
        company: Company instance.
        session: DB session (на будущее, для авто-сохранения дефолтов).
        passport_number_override: Pack 41.0-K — выбранный паспорт для RU-документов.

    Returns:
        dict с ключами: year, period_from, period_to, issue_date_str,
        taxpayer_status, birth_date_str, country_code, id_doc_code,
        passport_series_number, total_income, tax_base, tax_calculated,
        tax_withheld, months_rows.
    """
    from decimal import Decimal as _D

    year, period_from, period_to, issue_date = _ndfl_2_resolve_period(application)
    months_count = period_to - period_from + 1

    # Сумма зарплаты в месяц
    monthly_income = application.salary_rub or _D("0")
    total_income = (monthly_income * _D(months_count)).quantize(_D("0.01"))
    tax_base = total_income
    # Налог округляется до целого рубля (стандарт ФНС)
    tax_calculated_int = int((total_income * _D("0.13")).to_integral_value(rounding="ROUND_HALF_UP"))
    tax_withheld_int = tax_calculated_int

    # Резидент / нерезидент
    nationality = (applicant.nationality or "").upper()
    taxpayer_status = "1" if nationality == "RUS" else "2"

    # Код страны
    country_code = _COUNTRY_NUMERIC_CODE.get(nationality, "")

    # Паспорт
    id_doc_code, passport_series_number = _ndfl_2_resolve_passport(
        applicant, passport_number_override
    )

    # Дата рождения
    birth_date_str = (
        applicant.birth_date.strftime("%d.%m.%Y") if applicant.birth_date else ""
    )

    # Месячные строки — фиксированный массив из 28 слотов (14 левая колонка +
    # 14 правая колонка, по эталону ФНС КНД 1175018). Первые N слотов
    # заполнены месячными доходами, остальные — пустые строки (как в бланке).
    NDFL_2_TOTAL_SLOTS = 28
    empty_row = {
        "month": "",
        "income_code": "",
        "income_amount": "",
        "deduction_code": "",
        "deduction_amount": "",
    }
    rows = []
    for m in range(period_from, period_to + 1):
        rows.append({
            "month": f"{m:02d}",
            "income_code": "2000",
            "income_amount": _ndfl_2_fmt_money(monthly_income),
            "deduction_code": "",
            "deduction_amount": "",
        })
    # Дополняем пустыми до 28
    while len(rows) < NDFL_2_TOTAL_SLOTS:
        rows.append(dict(empty_row))
    # Защита от переполнения (если кто-то задаст период > 28 месяцев)
    rows = rows[:NDFL_2_TOTAL_SLOTS]

    return {
        "year": str(year),
        "period_from": period_from,
        "period_to": period_to,
        "issue_date_str": issue_date.strftime("%d.%m.%Y"),
        "taxpayer_status": taxpayer_status,
        "birth_date_str": birth_date_str,
        "country_code": country_code,
        "id_doc_code": id_doc_code,
        "passport_series_number": passport_series_number,
        "total_income": _ndfl_2_fmt_money(total_income),
        "tax_base": _ndfl_2_fmt_money(tax_base),
        "tax_calculated": str(tax_calculated_int),
        "tax_withheld": str(tax_withheld_int),
        "rows": rows,
    }



# ============================================================
# Pack 50.9-B: Helper'ы для СТД-Р (Сведения о трудовой деятельности из СФР)
# ============================================================

_STDR_MONTHS_RU = {
    "январь": 1, "января": 1,
    "февраль": 2, "февраля": 2,
    "март": 3, "марта": 3,
    "апрель": 4, "апреля": 4,
    "май": 5, "мая": 5,
    "июнь": 6, "июня": 6,
    "июль": 7, "июля": 7,
    "август": 8, "августа": 8,
    "сентябрь": 9, "сентября": 9,
    "октябрь": 10, "октября": 10,
    "ноябрь": 11, "ноября": 11,
    "декабрь": 12, "декабря": 12,
}

_STDR_MONTHS_RU_GENITIVE = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

_STDR_CURRENT_LABELS = {
    "по настоящее время", "настоящее время", "н.в.", "по н.в.", "до настоящего времени",
}


def _stdr_parse_month_year_ru(s: str) -> "Optional[date]":
    """'Июнь 2025' → date(2025, 6, 1). None если не удалось распарсить.

    Принимает как полные ('июнь'/'июня'), так и сокращённые форматы.
    Регистр игнорируется.
    """
    from datetime import date as _date
    import re as _re
    if not s:
        return None
    s = s.strip().lower()
    if s in _STDR_CURRENT_LABELS:
        return None
    # Паттерн: МесяцНаКирилл + 4 цифры (год). Допускаем разделитель: пробел, запятая, дефис.
    m = _re.match(r"^([а-яё]+)[\s,.\-]+(\d{4})$", s)
    if not m:
        return None
    month_str = m.group(1)
    year = int(m.group(2))
    month = _STDR_MONTHS_RU.get(month_str)
    if month is None:
        return None
    return _date(year, month, 1)


def _stdr_last_day_of_month(d: "date") -> "date":
    """Последний день месяца от даты."""
    from datetime import date as _date
    import calendar as _cal
    last_day = _cal.monthrange(d.year, d.month)[1]
    return _date(d.year, d.month, last_day)


def _stdr_fmt_dd_mm_yyyy(d) -> str:
    """date → '02.06.2025'. None → ''."""
    if not d:
        return ""
    return d.strftime("%d.%m.%Y")


def _stdr_fmt_date_long_ru(d) -> str:
    """date → '"06" декабря 2025 г.' (с двойными кавычками-ёлочками не подходит для СТД-Р,
    но в эталоне СФР именно прямые двойные кавычки 0x22)."""
    if not d:
        return ""
    return f'"{d.day:02d}" {_STDR_MONTHS_RU_GENITIVE[d.month]} {d.year} г.'


def _stdr_generate_sfr_number(seed: str) -> str:
    """Детерминированный регистрационный номер СФР по hash(seed).

    Формат: XXX-XXX-XXXXXX (3+3+6 цифр).
    Один и тот же seed → один и тот же номер.
    """
    import hashlib as _hashlib
    h = _hashlib.md5(seed.encode("utf-8")).hexdigest()
    # Берём 12 hex-цифр и конвертируем в decimal (mod 10^12)
    n = int(h[:15], 16) % (10 ** 12)
    s = f"{n:012d}"
    return f"{s[:3]}-{s[3:6]}-{s[6:12]}"


def _stdr_generate_document_number(idx: int) -> str:
    """Фиктивный № приказа. Каждый последующий с разной серией для реалистичности.

    idx=0 → '12-к', idx=1 → '47 л.с.', idx=2 → '63-к', idx=3 → '84 л.с.', ...
    Чередуем суффиксы '-к' и ' л.с.'.
    """
    # Псевдо-случайное но детерминированное число от 10 до 99
    num = 12 + (idx * 31 + 7) % 88
    suffix = "-к" if idx % 2 == 0 else " л.с."
    return f"{num}{suffix}"


def _stdr_generate_dismissal_reason() -> str:
    """Стандартная формулировка увольнения по собственному."""
    return (
        "Пункт 3, Часть 1, Статья 77, Трудовой кодекс Российской Федерации "
        "по собственному желанию, пункт 3 части первой статьи 77 Трудового "
        "кодекса Российской Федерации"
    )


def _stdr_apply_override(auto_row: dict, override: dict) -> dict:
    """Мерж auto-сгенерированной записи с ручным override.

    Только не-None и не пустые строки в override переопределяют auto.
    """
    if not override:
        return auto_row
    result = dict(auto_row)
    for k, v in override.items():
        if k == "wh_index":
            continue
        if v is None or v == "":
            continue
        result[k] = v
    return result


def build_stdr_context(
    application,
    applicant,
    company,
    position,
    session,
) -> dict:
    """Pack 50.9-B — собирает блок 'stdr' для шаблона stdr_template.docx.

    Парсит applicant.work_history и разбивает на:
      - Таблица 1 (события с 01.01.2020+): приёмы/увольнения с полным набором полей
      - Таблица 2 (периоды до 31.12.2019): только периоды работы

    Для текущей DN-записи (wh[0]) использует реальные данные:
      - acceptance_date = application.contract_sign_date
      - sfr_number = company.sfr_registration_number
      - okz_code = position.okz_code
      - document_date = application.contract_sign_date

    Для прошлых работ генерирует детерминированно:
      - sfr_number = hash(company name)
      - document_number = по индексу
      - dismissal_reason = стандартная "по собственному"

    Применяет application.stdr_records_override — ручные правки.

    Заполняет фиксированное количество слотов:
      - Таблица 1: STDR_TABLE1_SLOTS (15) — пустые слоты с пустыми строками
      - Таблица 2: STDR_TABLE2_SLOTS (8)
    """
    from datetime import date as _date, datetime as _datetime

    STDR_TABLE1_SLOTS = 15
    STDR_TABLE2_SLOTS = 8
    STDR_CUTOFF = _date(2020, 1, 1)

    work_history = list(applicant.work_history or [])

    # 1. Распарсим все записи в (start_date, end_date, company_name, position_title)
    parsed_records = []
    for i, wh in enumerate(work_history):
        if not isinstance(wh, dict):
            continue
        company_name = (wh.get("company") or "").strip()
        position_title = (wh.get("position") or "").strip()
        if not company_name:
            continue
        start_date = _stdr_parse_month_year_ru(wh.get("period_start", ""))
        end_str = (wh.get("period_end") or "").strip().lower()
        if end_str in _STDR_CURRENT_LABELS:
            end_date = None  # текущая работа
        else:
            end_date_start = _stdr_parse_month_year_ru(wh.get("period_end", ""))
            end_date = _stdr_last_day_of_month(end_date_start) if end_date_start else None
        parsed_records.append({
            "wh_index": i,
            "company_name": company_name,
            "position_title": position_title,
            "start_date": start_date,
            "end_date": end_date,
        })

    # 2. Override map: wh_index → dict
    override_list = application.stdr_records_override or []
    override_map = {}
    if isinstance(override_list, list):
        for ov in override_list:
            if isinstance(ov, dict) and "wh_index" in ov:
                override_map[ov["wh_index"]] = ov

    # 3. Делим на таблицу 1 (с 2020+) и таблицу 2 (до 2020)
    table1_events = []
    table2_periods = []

    for rec in parsed_records:
        wh_idx = rec["wh_index"]
        is_dn = (wh_idx == 0)
        override = override_map.get(wh_idx, {})

        # Для wh_index == 0 (DN-работа) — реальные данные
        if is_dn and application.contract_sign_date:
            real_start = application.contract_sign_date
        else:
            real_start = rec["start_date"]

        if real_start is None:
            continue

        # Куда попадает: таблица 1 или 2?
        # В таблицу 2 — только если ВСЯ запись завершилась до 2020
        # (т.е. real_end < 2020-01-01 и real_end is not None)
        real_end = rec["end_date"]
        if real_end is not None and real_end < STDR_CUTOFF:
            # Таблица 2: только периоды
            sfr_number_auto = _stdr_generate_sfr_number(rec["company_name"])
            row = {
                "company_with_sfr": f"{rec['company_name']} {sfr_number_auto}",
                "date_from": _stdr_fmt_dd_mm_yyyy(real_start),
                "date_to": _stdr_fmt_dd_mm_yyyy(real_end),
            }
            # Применяем override
            sfr_override = override.get("sfr_number")
            if sfr_override:
                row["company_with_sfr"] = f"{rec['company_name']} {sfr_override}"
            if override.get("acceptance_date"):
                row["date_from"] = override["acceptance_date"]
            if override.get("dismissal_date"):
                row["date_to"] = override["dismissal_date"]
            table2_periods.append(row)
            continue

        # Таблица 1: события (приём + опц. увольнение)
        if is_dn:
            sfr_number_auto = company.sfr_registration_number or _stdr_generate_sfr_number(rec["company_name"])
            okz_auto = position.okz_code or ""
        else:
            sfr_number_auto = _stdr_generate_sfr_number(rec["company_name"])
            okz_auto = ""

        company_with_sfr = f"{rec['company_name']} {override.get('sfr_number') or sfr_number_auto}"

        # ПРИЁМ
        acceptance_date_str = override.get("acceptance_date") or _stdr_fmt_dd_mm_yyyy(real_start)
        doc_name = override.get("document_name") or "Приказ"
        doc_date = override.get("document_date") or acceptance_date_str
        doc_number = override.get("document_number") or _stdr_generate_document_number(wh_idx)
        okz = override.get("okz_code") or okz_auto

        table1_events.append({
            "company_with_sfr": company_with_sfr,
            "event_date": acceptance_date_str,
            "event_type": "ПРИЕМ",
            "position": rec["position_title"],
            "basis": "",
            "okz_code": okz,
            "dismissal_reason": "",
            "doc_name": doc_name,
            "doc_date": doc_date,
            "doc_number": doc_number,
            "cancellation": "",
        })

        # УВОЛЬНЕНИЕ (если есть)
        if real_end is not None:
            dismissal_date_str = override.get("dismissal_date") or _stdr_fmt_dd_mm_yyyy(real_end)
            dismissal_reason = override.get("dismissal_reason") or _stdr_generate_dismissal_reason()
            # Документ-основание увольнения — другой приказ с тем же idx, но другим суффиксом
            doc_number_dismissal = override.get("document_number_dismissal") or _stdr_generate_document_number(wh_idx + 100)
            table1_events.append({
                "company_with_sfr": company_with_sfr,
                "event_date": dismissal_date_str,
                "event_type": "УВОЛЬНЕНИЕ",
                "position": rec["position_title"],
                "basis": "",
                "okz_code": "",
                "dismissal_reason": dismissal_reason,
                "doc_name": "Приказ",
                "doc_date": dismissal_date_str,
                "doc_number": doc_number_dismissal,
                "cancellation": "",
            })

    # 4. Сортируем таблицу 1 по дате события (от ранних к поздним) — как в эталоне СФР
    def _parse_event_dt(s: str):
        if not s:
            return None
        try:
            return _datetime.strptime(s, "%d.%m.%Y").date()
        except ValueError:
            return None
    table1_events.sort(key=lambda e: _parse_event_dt(e["event_date"]) or _date(1900, 1, 1))

    # 5. Нумеруем и дополняем до фикс. количества слотов
    EMPTY_TABLE1 = {
        "index": "", "company_with_sfr": "", "event_date": "", "event_type": "",
        "position": "", "basis": "", "okz_code": "", "dismissal_reason": "",
        "doc_name": "", "doc_date": "", "doc_number": "", "cancellation": "",
    }
    EMPTY_TABLE2 = {
        "index": "", "company_with_sfr": "", "date_from": "", "date_to": "",
    }

    table1_rows = []
    for i, ev in enumerate(table1_events[:STDR_TABLE1_SLOTS]):
        ev["index"] = str(i + 1)
        table1_rows.append(ev)
    while len(table1_rows) < STDR_TABLE1_SLOTS:
        table1_rows.append(dict(EMPTY_TABLE1))

    # Таблицу 2 сортируем по date_from (по возрастанию) — старые работы сверху
    table2_periods.sort(key=lambda r: _parse_event_dt(r["date_from"]) or _date(1900, 1, 1))
    table2_rows = []
    for i, p in enumerate(table2_periods[:STDR_TABLE2_SLOTS]):
        p["index"] = str(i + 1)
        table2_rows.append(p)
    while len(table2_rows) < STDR_TABLE2_SLOTS:
        table2_rows.append(dict(EMPTY_TABLE2))

    # 6. Дата формирования
    issue_date = application.stdr_issue_date or _datetime.now().date()

    # 7. ФИО + СНИЛС + дата рождения
    last_name = (applicant.last_name_native or "").upper()
    first_name = (applicant.first_name_native or "").upper()
    middle_name = (applicant.middle_name_native or "").upper()
    snils = applicant.snils or ""
    birth_date_long = _stdr_fmt_date_long_ru(applicant.birth_date)

    return {
        "applicant": {
            "last_name_upper": last_name,
            "first_name_upper": first_name,
            "middle_name_upper": middle_name,
            "snils": snils,
            "birth_date_long": birth_date_long,
        },
        "issue_date_long": _stdr_fmt_date_long_ru(issue_date),
        "table1_rows": table1_rows,
        "table2_rows": table2_rows,
    }

