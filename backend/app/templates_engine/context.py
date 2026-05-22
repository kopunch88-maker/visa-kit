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
from datetime import date
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
    """"John Robert Smith" → "J. Smith". "Smith" → "Smith"."""
    if not full_latin:
        return ""
    parts = full_latin.strip().split()
    if len(parts) == 0:
        return ""
    if len(parts) == 1:
        return parts[0]
    # Берём первую букву от первого слова + последнее слово
    return f"{parts[0][0]}. {parts[-1]}"


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

    # Парсим паспорт по гражданству
    # Pack 41.0-E — паспорт для русских документов через passport_id_for_ru_docs
    _ru_passport = get_passport_dict_for_ru_docs(applicant)
    passport_data = _parse_passport(_ru_passport["number"], applicant.nationality)

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
            "passport_number": _ru_passport["number"] or "",  # Pack 41.0-E
            "passport_series": passport_data["series"],
            "passport_number_only": passport_data["number_only"],
            "passport_formatted": passport_data["formatted"],
            "passport_issue_date": _ru_passport["issue_date"],  # Pack 41.0-E
            "passport_issue_date_str": fmt_date_ru(_ru_passport["issue_date"]),  # Pack 41.0-E
            "passport_issuer": _resolve_passport_issuer_for_template_from_dict(_ru_passport, applicant.nationality),  # Pack 41.0-E
            "inn": applicant.inn or "",
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
            "bank_name": applicant.bank_name or "",
            "bank_bic": applicant.bank_bic or "",
            "bank_correspondent_account": applicant.bank_correspondent_account or "",
            "education": applicant.education or [],
            "work_history": _build_cv_work_history(applicant, application, company, position),
            "languages": applicant.languages or [],
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

