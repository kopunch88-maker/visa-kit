"""
Названия стран по-испански (для подстановки в DEX_NACION, DEX_PAIS, Texto4 и др).

Маппим ISO-3 → испанское название в Title Case с акцентами
(как на образцах официальных форм Минюста Испании: Rusia, Turquía, Azerbaiyán).

Исправлено vs исходной версии:
- Расширен список с 14 до 80+ стран
- Сменён регистр UPPERCASE → Title Case с диакритикой
  (RUSIA → Rusia, AZERBAIYAN → Azerbaiyán и т.д.)
- KIRGUIZISTAN → Kirguistán (современная норма)
- Добавлен fallback с ISO-2 (TR → TUR → Turquía) для случаев если
  в БД сохранится 2-буквенный код вместо 3-буквенного.
"""

# Карта ISO-3 → испанское название (Title Case с правильной диакритикой)
COUNTRY_NAMES_ES = {
    # Постсоветское пространство
    "RUS": "Rusia",
    "AZE": "Azerbaiyán",
    "ARM": "Armenia",
    "KAZ": "Kazajistán",
    "BLR": "Bielorrusia",
    "UKR": "Ucrania",
    "GEO": "Georgia",
    "UZB": "Uzbekistán",
    "TJK": "Tayikistán",
    "KGZ": "Kirguistán",
    "MDA": "Moldavia",
    "TKM": "Turkmenistán",
    "EST": "Estonia",
    "LVA": "Letonia",
    "LTU": "Lituania",

    # Балканы / Восточная Европа
    "MKD": "Macedonia del Norte",
    "ALB": "Albania",
    "SRB": "Serbia",
    "BIH": "Bosnia y Herzegovina",
    "MNE": "Montenegro",
    "HRV": "Croacia",
    "SVN": "Eslovenia",
    "BGR": "Bulgaria",
    "ROU": "Rumanía",
    "HUN": "Hungría",
    "POL": "Polonia",
    "CZE": "República Checa",
    "SVK": "Eslovaquia",

    # Ближний Восток / Турция
    "TUR": "Turquía",
    "ISR": "Israel",
    "IRN": "Irán",
    "IRQ": "Irak",
    "SYR": "Siria",
    "JOR": "Jordania",
    "LBN": "Líbano",
    "ARE": "Emiratos Árabes Unidos",
    "SAU": "Arabia Saudí",
    "QAT": "Catar",

    # Азия
    "CHN": "China",
    "IND": "India",
    "PAK": "Pakistán",
    "BGD": "Bangladés",
    "JPN": "Japón",
    "KOR": "Corea del Sur",
    "PRK": "Corea del Norte",
    "VNM": "Vietnam",
    "THA": "Tailandia",
    "IDN": "Indonesia",
    "PHL": "Filipinas",
    "MYS": "Malasia",
    "SGP": "Singapur",

    # Западная Европа
    "ESP": "España",
    "FRA": "Francia",
    "DEU": "Alemania",
    "ITA": "Italia",
    "PRT": "Portugal",
    "GBR": "Reino Unido",
    "IRL": "Irlanda",
    "NLD": "Países Bajos",
    "BEL": "Bélgica",
    "CHE": "Suiza",
    "AUT": "Austria",
    "SWE": "Suecia",
    "NOR": "Noruega",
    "FIN": "Finlandia",
    "DNK": "Dinamarca",
    "GRC": "Grecia",

    # Америка
    "USA": "Estados Unidos",
    "CAN": "Canadá",
    "MEX": "México",
    "ARG": "Argentina",
    "BRA": "Brasil",
    "CHL": "Chile",
    "COL": "Colombia",
    "PER": "Perú",
    "URY": "Uruguay",
    "VEN": "Venezuela",
    "ECU": "Ecuador",
    "BOL": "Bolivia",
    "PRY": "Paraguay",
    "CUB": "Cuba",
    "DOM": "República Dominicana",

    # Другие
    "AUS": "Australia",
    "NZL": "Nueva Zelanda",
    "ZAF": "Sudáfrica",
    "EGY": "Egipto",
    "MAR": "Marruecos",
    "TUN": "Túnez",
    "DZA": "Argelia",
    # Pack 36.2 — недостающие страны (фикс сырого ISO-кода на формах, напр. XKX->Kosovo)
    "AFG": "Afganistán",
    "AGO": "Angola",
    "AND": "Andorra",
    "ATG": "Antigua y Barbuda",
    "BDI": "Burundi",
    "BEN": "Benín",
    "BFA": "Burkina Faso",
    "BHR": "Baréin",
    "BHS": "Bahamas",
    "BLZ": "Belice",
    "BRB": "Barbados",
    "BRN": "Brunéi",
    "BTN": "Bután",
    "BWA": "Botsuana",
    "CAF": "República Centroafricana",
    "CIV": "Costa de Marfil",
    "CMR": "Camerún",
    "COD": "República Democrática del Congo",
    "COG": "República del Congo",
    "COM": "Comoras",
    "CPV": "Cabo Verde",
    "CRI": "Costa Rica",
    "CYP": "Chipre",
    "DJI": "Yibuti",
    "DMA": "Dominica",
    "ERI": "Eritrea",
    "ETH": "Etiopía",
    "FJI": "Fiyi",
    "FSM": "Micronesia",
    "GAB": "Gabón",
    "GHA": "Ghana",
    "GIN": "Guinea",
    "GMB": "Gambia",
    "GNB": "Guinea-Bisáu",
    "GNQ": "Guinea Ecuatorial",
    "GRD": "Granada",
    "GTM": "Guatemala",
    "GUY": "Guyana",
    "HND": "Honduras",
    "HTI": "Haití",
    "JAM": "Jamaica",
    "KEN": "Kenia",
    "KHM": "Camboya",
    "KIR": "Kiribati",
    "KNA": "San Cristóbal y Nieves",
    "KWT": "Kuwait",
    "LAO": "Laos",
    "LBR": "Liberia",
    "LBY": "Libia",
    "LCA": "Santa Lucía",
    "LIE": "Liechtenstein",
    "LKA": "Sri Lanka",
    "LSO": "Lesoto",
    "LUX": "Luxemburgo",
    "MCO": "Mónaco",
    "MDG": "Madagascar",
    "MDV": "Maldivas",
    "MHL": "Islas Marshall",
    "MLI": "Malí",
    "MLT": "Malta",
    "MMR": "Myanmar",
    "MNG": "Mongolia",
    "MOZ": "Mozambique",
    "MRT": "Mauritania",
    "MUS": "Mauricio",
    "MWI": "Malaui",
    "NAM": "Namibia",
    "NER": "Níger",
    "NGA": "Nigeria",
    "NIC": "Nicaragua",
    "NPL": "Nepal",
    "NRU": "Nauru",
    "OMN": "Omán",
    "PAN": "Panamá",
    "PLW": "Palaos",
    "PNG": "Papúa Nueva Guinea",
    "PSE": "Palestina",
    "RWA": "Ruanda",
    "SDN": "Sudán",
    "SEN": "Senegal",
    "SLB": "Islas Salomón",
    "SLE": "Sierra Leona",
    "SLV": "El Salvador",
    "SMR": "San Marino",
    "SOM": "Somalia",
    "SSD": "Sudán del Sur",
    "STP": "Santo Tomé y Príncipe",
    "SUR": "Surinam",
    "SWZ": "Esuatini",
    "SYC": "Seychelles",
    "TCD": "Chad",
    "TGO": "Togo",
    "TLS": "Timor Oriental",
    "TON": "Tonga",
    "TTO": "Trinidad y Tobago",
    "TUV": "Tuvalu",
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "VAT": "Ciudad del Vaticano",
    "VCT": "San Vicente y las Granadinas",
    "VUT": "Vanuatu",
    "WSM": "Samoa",
    "XKX": "Kosovo",
    "YEM": "Yemen",
    "ZMB": "Zambia",
    "ZWE": "Zimbabue",
}


# Fallback с ISO-2 на ISO-3, для случая когда в БД может оказаться 2-буквенный
# код (TR вместо TUR). По стандартному маппингу ISO 3166.
ISO2_TO_ISO3 = {
    "RU": "RUS", "AZ": "AZE", "AM": "ARM", "KZ": "KAZ",
    "BY": "BLR", "UA": "UKR", "GE": "GEO", "UZ": "UZB",
    "TJ": "TJK", "KG": "KGZ", "MD": "MDA", "TM": "TKM",
    "EE": "EST", "LV": "LVA", "LT": "LTU",
    "MK": "MKD", "AL": "ALB", "RS": "SRB", "BA": "BIH",
    "ME": "MNE", "HR": "HRV", "SI": "SVN", "BG": "BGR",
    "RO": "ROU", "HU": "HUN", "PL": "POL", "CZ": "CZE",
    "SK": "SVK",
    "TR": "TUR", "IL": "ISR", "IR": "IRN", "IQ": "IRQ",
    "SY": "SYR", "JO": "JOR", "LB": "LBN", "AE": "ARE",
    "SA": "SAU", "QA": "QAT",
    "CN": "CHN", "IN": "IND", "PK": "PAK", "BD": "BGD",
    "JP": "JPN", "KR": "KOR", "KP": "PRK", "VN": "VNM",
    "TH": "THA", "ID": "IDN", "PH": "PHL", "MY": "MYS",
    "SG": "SGP",
    "ES": "ESP", "FR": "FRA", "DE": "DEU", "IT": "ITA",
    "PT": "PRT", "GB": "GBR", "IE": "IRL", "NL": "NLD",
    "BE": "BEL", "CH": "CHE", "AT": "AUT", "SE": "SWE",
    "NO": "NOR", "FI": "FIN", "DK": "DNK", "GR": "GRC",
    "US": "USA", "CA": "CAN", "MX": "MEX", "AR": "ARG",
    "BR": "BRA", "CL": "CHL", "CO": "COL", "PE": "PER",
    "UY": "URY", "VE": "VEN", "EC": "ECU", "BO": "BOL",
    "PY": "PRY", "CU": "CUB", "DO": "DOM",
    "AU": "AUS", "NZ": "NZL", "ZA": "ZAF", "EG": "EGY",
    "MA": "MAR", "TN": "TUN", "DZ": "DZA",
}


def country_es(iso_code: str | None) -> str:
    """
    ISO-3 (или ISO-2) → испанское название в Title Case (Turquía, Rusia).

    Если получен 2-буквенный код — конвертируем в 3-буквенный по карте.
    Если страна неизвестна — возвращаем код как есть. Это fallback для
    обратной совместимости; для качества вывода добавляйте страну в
    COUNTRY_NAMES_ES вместо того чтобы полагаться на fallback.
    """
    if not iso_code:
        return ""

    code = iso_code.strip().upper()

    # Если 2 буквы — конвертируем в 3
    if len(code) == 2:
        code = ISO2_TO_ISO3.get(code, code)

    return COUNTRY_NAMES_ES.get(code, code)


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
