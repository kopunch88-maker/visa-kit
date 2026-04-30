"""
Названия стран по-испански (для подстановки в DEX_NACION, Texto4 и др).

Маппим ISO-3 → испанское название в верхнем регистре.
"""

COUNTRY_NAMES_ES = {
    "RUS": "RUSIA",
    "AZE": "AZERBAIYAN",
    "ARM": "ARMENIA",
    "KAZ": "KAZAJSTAN",
    "BLR": "BIELORRUSIA",
    "UKR": "UCRANIA",
    "GEO": "GEORGIA",
    "UZB": "UZBEKISTAN",
    "TJK": "TAYIKISTAN",
    "KGZ": "KIRGUIZISTAN",
    "MDA": "MOLDAVIA",
    "TKM": "TURKMENISTAN",
    "MKD": "MACEDONIA DEL NORTE",
    "ALB": "ALBANIA",
}


def country_es(iso3: str | None) -> str:
    """ISO-3 → испанское название. Если не знаем — возвращаем ISO как есть."""
    if not iso3:
        return ""
    return COUNTRY_NAMES_ES.get(iso3.upper(), iso3.upper())


# Названия месяцев по-испански (для подстановки в DESIGNACION Texto38 и др.)
MONTHS_ES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]


def month_es(month: int) -> str:
    """1-12 → название месяца по-испански (UPPERCASE)."""
    if not month or month < 1 or month > 12:
        return ""
    return MONTHS_ES[month - 1]


# Месяцы по-испански lowercase (для текстовых документов типа COMPROMISO)
MONTHS_ES_LOWER = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def month_es_lower(month: int) -> str:
    if not month or month < 1 or month > 12:
        return ""
    return MONTHS_ES_LOWER[month - 1]
