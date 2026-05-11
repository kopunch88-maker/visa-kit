"""
Pack 35.2 — Резолвер русифицированного названия органа, выдавшего паспорт.

Используется в:
  1. _auto_apply_ocr_to_applicant (import_package.py) — после OCR паспорта
     резолвит и сохраняет в applicant.passport_issuer_ru.
  2. context.py при рендере DOCX — если passport_issuer_ru пустое, резолвит
     на лету (не сохраняя в БД).
  3. UI ApplicantDrawer — кнопка «Пересобрать» вызывает /api endpoint.

Поведение:
  - Если входной passport_issuer уже на кириллице → возвращаем как есть
    (это RUS-паспорт или менеджер уже исправил).
  - Если EMBASSY / CONSULATE → «посольством <страны> в России»
    (страну определяем из текста issuer, fallback на nationality).
  - Если MINISTRY OF INTERNAL AFFAIRS / MIA / M.I.A. → «МВД <страны>».
  - Если MINISTRY OF FOREIGN AFFAIRS / MFA → «МИД <страны>».
  - Иначе → возвращаем как есть (менеджер увидит и поправит).
"""

from __future__ import annotations

import re
from typing import Optional


# === Словари ===

# Страна в родительном падеже для «МВД ЧЕГО?»
COUNTRY_GENITIVE_RU: dict[str, str] = {
    "RUS": "Российской Федерации",
    "AZE": "Азербайджана",
    "ARM": "Армении",
    "BLR": "Беларуси",
    "GEO": "Грузии",
    "KAZ": "Казахстана",
    "KGZ": "Киргизии",
    "TJK": "Таджикистана",
    "TKM": "Туркменистана",
    "UKR": "Украины",
    "UZB": "Узбекистана",
    "MDA": "Молдовы",
    "TUR": "Турции",
    "CHN": "Китая",
    "IRN": "Ирана",
    "IND": "Индии",
    "ISR": "Израиля",
    "SRB": "Сербии",
    "POL": "Польши",
    "DEU": "Германии",
    "FRA": "Франции",
    "GBR": "Великобритании",
    "USA": "США",
    "VNM": "Вьетнама",
    "EGY": "Египта",
    "MKD": "Северной Македонии",
    "ITA": "Италии",
    "ESP": "Испании",
    "PRT": "Португалии",
    "CZE": "Чехии",
    "SVK": "Словакии",
    "HUN": "Венгрии",
    "ROU": "Румынии",
    "BGR": "Болгарии",
    "GRC": "Греции",
    "AUT": "Австрии",
    "CHE": "Швейцарии",
    "NLD": "Нидерландов",
    "BEL": "Бельгии",
    "SWE": "Швеции",
    "NOR": "Норвегии",
    "FIN": "Финляндии",
    "DNK": "Дании",
    "EST": "Эстонии",
    "LVA": "Латвии",
    "LTU": "Литвы",
    "KOR": "Республики Корея",
    "JPN": "Японии",
    "MNG": "Монголии",
    "PAK": "Пакистана",
    "AFG": "Афганистана",
    "SYR": "Сирии",
    "IRQ": "Ирака",
    "LBN": "Ливана",
    "ARE": "ОАЭ",
    "SAU": "Саудовской Аравии",
    "MAR": "Марокко",
    "TUN": "Туниса",
    "DZA": "Алжира",
    "NGA": "Нигерии",
    "ETH": "Эфиопии",
    "ZAF": "ЮАР",
}

# Дипломатическая форма (для посольств) — где обычно используют сокращения
COUNTRY_DIPLOMATIC_RU: dict[str, str] = {
    "CHN": "КНР",
    "PRK": "КНДР",
    "KOR": "Республики Корея",
    "USA": "США",
    "ARE": "ОАЭ",
    "GBR": "Великобритании",
    # для остальных стран используется COUNTRY_GENITIVE_RU
}

# Ключевые слова стран в issuer-тексте → ISO-3.
# ПОРЯДОК ВАЖЕН: длинные / специфичные сначала. Иначе «P.R.CHINA»
# распознается как «CHINA», а «RUSSIAN FEDERATION» проиграет «RUSSIA».
# RUSSIA в самом конце — иначе посольство ЛЮБОЙ страны «in Russia»
# будет принято за российский орган.
COUNTRY_KEYWORDS: list[tuple[str, str]] = [
    ("P.R.CHINA", "CHN"), ("PR CHINA", "CHN"), ("PRC", "CHN"), ("CHINA", "CHN"),
    ("TURKIYE", "TUR"), ("TURKEY", "TUR"),
    ("AZERBAIJAN", "AZE"), ("ARMENIA", "ARM"), ("BELARUS", "BLR"),
    ("GEORGIA", "GEO"), ("KAZAKHSTAN", "KAZ"), ("UKRAINE", "UKR"),
    ("UZBEKISTAN", "UZB"), ("TAJIKISTAN", "TJK"), ("KYRGYZSTAN", "KGZ"),
    ("TURKMENISTAN", "TKM"), ("MOLDOVA", "MDA"),
    ("ISRAEL", "ISR"), ("SERBIA", "SRB"), ("POLAND", "POL"),
    ("GERMANY", "DEU"), ("FRANCE", "FRA"), ("VIETNAM", "VNM"),
    ("EGYPT", "EGY"), ("ITALY", "ITA"), ("SPAIN", "ESP"),
    ("CZECH", "CZE"), ("SLOVAKIA", "SVK"), ("HUNGARY", "HUN"),
    ("ROMANIA", "ROU"), ("BULGARIA", "BGR"), ("GREECE", "GRC"),
    ("AUSTRIA", "AUT"), ("SWITZERLAND", "CHE"), ("NETHERLANDS", "NLD"),
    ("BELGIUM", "BEL"), ("SWEDEN", "SWE"), ("NORWAY", "NOR"),
    ("FINLAND", "FIN"), ("DENMARK", "DNK"), ("ESTONIA", "EST"),
    ("LATVIA", "LVA"), ("LITHUANIA", "LTU"), ("KOREA", "KOR"),
    ("JAPAN", "JPN"), ("MONGOLIA", "MNG"), ("PAKISTAN", "PAK"),
    ("AFGHANISTAN", "AFG"), ("SYRIA", "SYR"), ("IRAQ", "IRQ"),
    ("LEBANON", "LBN"), ("EMIRATES", "ARE"), ("U.A.E.", "ARE"),
    ("SAUDI ARABIA", "SAU"), ("MOROCCO", "MAR"), ("TUNISIA", "TUN"),
    ("ALGERIA", "DZA"), ("NIGERIA", "NGA"), ("ETHIOPIA", "ETH"),
    ("INDIA", "IND"), ("IRAN", "IRN"),
    # RUSSIA — самым последним
    ("RUSSIAN FEDERATION", "RUS"),
    ("RUSSIA", "RUS"),
]


# === Паттерны типа органа ===

MIA_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bMINISTRY OF INTERNAL AFFAIRS\b", re.IGNORECASE),
    re.compile(r"\bMIA\b", re.IGNORECASE),
    re.compile(r"\bM\.I\.A\.?", re.IGNORECASE),
    re.compile(r"\bMVD\b", re.IGNORECASE),
]

EMBASSY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bEMBASSY\b", re.IGNORECASE),
    re.compile(r"\bEMB\.\s*OF\b", re.IGNORECASE),
]

CONSULATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bCONSULATE\b", re.IGNORECASE),
    re.compile(r"\bCONSUL", re.IGNORECASE),
]

MFA_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bMINISTRY OF FOREIGN AFFAIRS\b", re.IGNORECASE),
    re.compile(r"\bMFA\b", re.IGNORECASE),
]


# === Хелперы ===

def _is_cyrillic(text: str) -> bool:
    """True если в строке есть кириллические буквы."""
    return bool(re.search(r"[А-Яа-яЁё]", text))


def _detect_country(issuer_text: str, nationality: Optional[str]) -> Optional[str]:
    """
    Ищет упоминание страны в тексте issuer.

    Стратегия:
      - Сканируем по COUNTRY_KEYWORDS (упорядоченно).
      - Если найдены и RUS и не-RUS — приоритет не-RUS (т.к. «...IN RUSSIA»
        обычно означает что российская локация, а страна паспорта другая).
      - Иначе — первое найденное.
      - Если ничего не найдено — fallback на nationality.
    """
    upper = issuer_text.upper()
    found: list[tuple[int, str]] = []
    for kw, code in COUNTRY_KEYWORDS:
        idx = upper.find(kw)
        if idx != -1:
            found.append((idx, code))

    if not found:
        return nationality

    # Приоритет non-RUS
    non_rus = [c for _, c in found if c != "RUS"]
    if non_rus:
        return non_rus[0]
    return found[0][1]


def _country_name_for_embassy(country_code: Optional[str]) -> str:
    """Название страны для конструкции «посольством <X> в России»."""
    if not country_code:
        return "?"
    return COUNTRY_DIPLOMATIC_RU.get(
        country_code, COUNTRY_GENITIVE_RU.get(country_code, country_code)
    )


def _country_name_for_ministry(country_code: Optional[str]) -> str:
    """Название страны для конструкции «МВД <X>» / «МИД <X>»."""
    if not country_code:
        return "?"
    return COUNTRY_GENITIVE_RU.get(country_code, country_code)


# === Главная функция ===

def resolve_passport_issuer_ru(
    issuer_raw: Optional[str],
    nationality: Optional[str],
) -> Optional[str]:
    """
    Возвращает русифицированное название органа, выдавшего паспорт.

    Args:
        issuer_raw: то что лежит в applicant.passport_issuer (как есть).
        nationality: ISO-3 код гражданства (для МВД/МИД, и fallback для посольств).

    Returns:
        Русская строка для подстановки в шаблон, либо None если входной был пустой.
    """
    if not issuer_raw or not issuer_raw.strip():
        return None

    issuer = issuer_raw.strip()

    # 1. Уже на кириллице — возвращаем как есть
    if _is_cyrillic(issuer):
        return issuer

    upper = issuer.upper()

    # 2. Посольство / консульство
    is_embassy = any(p.search(upper) for p in EMBASSY_PATTERNS)
    is_consul = any(p.search(upper) for p in CONSULATE_PATTERNS)
    if is_embassy or is_consul:
        country = _detect_country(issuer, nationality)
        country_name = _country_name_for_embassy(country)
        if is_consul:
            return f"консульством {country_name} в России"
        return f"посольством {country_name} в России"

    # 3. МВД
    if any(p.search(upper) for p in MIA_PATTERNS):
        return f"МВД {_country_name_for_ministry(nationality)}"

    # 4. МИД
    if any(p.search(upper) for p in MFA_PATTERNS):
        return f"МИД {_country_name_for_ministry(nationality)}"

    # 5. Не распознали — возвращаем как есть, менеджер увидит и поправит
    return issuer
