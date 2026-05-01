"""
Сборка контекста (данных) для DOCX/PDF шаблонов.

Берёт Application + связанные сущности, превращает в плоский dict,
который docxtpl подставит в переменные {{ ... }}.

Pack 14 finishing: расширены справочники стран (TUR, POL, DEU и т.д.) +
fallback на latin если у иностранца нет русского имени.
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
    """04.05.2025 → '«04» мая 2025 г.'"""
    if not d:
        return ""
    months = {1: "января", 2: "февраля", 3: "марта", 4: "апреля",
              5: "мая", 6: "июня", 7: "июля", 8: "августа",
              9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}
    return f"«{d.day:02d}» {months[d.month]} {d.year} г."


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
    return f'«{d.day:02d}» {_MONTHS_GENITIVE_RU[d.month - 1]} {d.year} г.'


def fmt_date_human_ru(d: date | None) -> str:
    if d is None:
        return ""
    return f"{d.day} {_MONTHS_GENITIVE_RU[d.month - 1]} {d.year} года"


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


def _initials_native(applicant: Applicant) -> str:
    """
    Сокращённая форма (Иванов И.И.).
    Pack 14 fix: fallback на latin (Yuksel V.).
    """
    if applicant.last_name_native and applicant.first_name_native:
        result = f"{applicant.last_name_native} {applicant.first_name_native[0]}."
        if applicant.middle_name_native:
            result += f"{applicant.middle_name_native[0]}."
        return result

    # Fallback на latin
    if applicant.last_name_latin and applicant.first_name_latin:
        return f"{applicant.last_name_latin} {applicant.first_name_latin[0]}."

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

    last_year = submission.year if submission.month > 1 else submission.year - 1
    last_month = submission.month - 1 if submission.month > 1 else 12

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

    return collected


# ============================================================================
# EUR conversion
# ============================================================================

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
    }


# ============================================================================
# Bank statement
# ============================================================================

def _build_bank_context(application: Application, company: Company | None) -> dict:
    if application.bank_transactions_override:
        try:
            data = deserialize_from_storage(application.bank_transactions_override)
            transactions = data["transactions"]
            opening_balance = data["opening_balance"]
            period_start = data["period_start"]
            period_end = data["period_end"]
        except (KeyError, ValueError):
            return _generate_fresh_bank_context(application, company)

        total_income = sum(
            (t["amount"] for t in transactions if t["amount"] > 0),
            Decimal("0"),
        )
        total_expense = sum(
            (-t["amount"] for t in transactions if t["amount"] < 0),
            Decimal("0"),
        )
        closing_balance = opening_balance + total_income - total_expense

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

    return _generate_fresh_bank_context(application, company)


def _generate_fresh_bank_context(application: Application, company: Company | None) -> dict:
    if not application.submission_date or not company or not application.salary_rub:
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

    result = generate_default_transactions(
        submission_date=application.submission_date,
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
    )

    if application.bank_period_start:
        result["period_start"] = application.bank_period_start
    if application.bank_period_end:
        result["period_end"] = application.bank_period_end
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
    bank_data = _build_bank_context(application, company)

    # Парсим паспорт по гражданству
    passport_data = _parse_passport(applicant.passport_number, applicant.nationality)

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
            "passport_number": applicant.passport_number,
            "passport_series": passport_data["series"],
            "passport_number_only": passport_data["number_only"],
            "passport_formatted": passport_data["formatted"],
            "passport_issue_date": applicant.passport_issue_date,
            "passport_issue_date_str": fmt_date_ru(applicant.passport_issue_date),
            "passport_issuer": applicant.passport_issuer or "",
            "inn": applicant.inn or "",
            "home_address": applicant.home_address,
            "home_address_line1": applicant.home_address_line1 or applicant.home_address,
            "home_address_line2": applicant.home_address_line2 or "",
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
            "work_history": applicant.work_history or [],
            "languages": applicant.languages or [],
        },

        "company": {
            "short_name": company.short_name,
            "full_name_ru": company.full_name_ru,
            "full_name_es": company.full_name_es,
            "tax_id_primary": company.tax_id_primary,
            "tax_id_secondary": company.tax_id_secondary or "",
            "legal_address": company.legal_address,
            "legal_address_line1": company.legal_address_line1 or company.legal_address,
            "legal_address_line2": company.legal_address_line2 or "",
            "postal_address": company.postal_address or company.legal_address,
            "postal_address_line1": company.postal_address_line1 or company.postal_address or "",
            "postal_address_line2": company.postal_address_line2 or "",
            "director_full_name_ru": company.director_full_name_ru,
            "director_full_name_genitive_ru": company.director_full_name_genitive_ru,
            "director_short_ru": company.director_short_ru,
            "director_position_ru": company.director_position_ru,
            "bank_name": company.bank_name,
            "bank_account": company.bank_account,
            "bank_bic": company.bank_bic,
            "bank_correspondent_account": company.bank_correspondent_account or "",
        },

        "position": {
            "title_ru": position.title_ru,
            "title_ru_genitive": position.title_ru_genitive or position.title_ru,
            "title_es": position.title_es,
            "duties": position.duties,
        },

        "contract": {
            "number": application.contract_number or "",
            "sign_date": application.contract_sign_date,
            "sign_city": application.contract_sign_city or "",
            "end_date": application.contract_end_date,
            "salary_rub": application.salary_rub,
            "salary_rub_words": _money_to_words_ru(application.salary_rub),
            "sign_date_str": _format_date_ru(application.contract_sign_date),
        },

        "monthly_documents": monthly_docs,

        "eur": eur_data or {
            "rate": Decimal("0"),
            "rate_date": date.today(),
            "amount": Decimal("0"),
            "amount_int": 0,
            "amount_words_es": "cero",
        },

        "letter": {
            "number": application.employer_letter_number or "",
            "date": application.employer_letter_date,
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
        "fmt_date_human_ru": fmt_date_human_ru,
        "fmt_money": fmt_money,
        "fmt_money_kop": fmt_money_kop,
        "fmt_amount_signed": fmt_amount_signed,
    }
