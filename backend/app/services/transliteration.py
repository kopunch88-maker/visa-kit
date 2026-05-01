"""
Транслитерация русского текста в латиницу по ГОСТ 52535.1-2006.

И — Pack 14 finishing — обратная операция: латиница → русский с учётом языка.

ГОСТ-направление (рус → латиница) используется для:
- ФИО в анкетах
- Загранпаспортов
- Виз
- Международных документов

Особенности ГОСТ 52535.1-2006:
- Е → E (не YE)
- Ё → E (не YO)
- Й → I (не Y/J)
- Ю → IU (не YU)
- Я → IA (не YA)
- Ц → TS
- Ч → CH
- Ш → SH
- Щ → SHCH
- Ъ → IE
- Ы → Y
- Ь → "" (опускается)

Это отличается от привычных схем (ALA-LC, BGN/PCGN, и т.д.) — но именно
этот стандарт совпадает с тем, как пишут имена в современных загранпаспортах.

Если у клиента есть загранпаспорт — там уже есть авторитетная транслитерация,
её и нужно использовать. Эта функция — fallback когда загранпаспорта нет.
"""

# Таблица соответствий ГОСТ 52535.1-2006 (заглавные)
GOST_R_52535_1_2006: dict[str, str] = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D",
    "Е": "E", "Ё": "E", "Ж": "ZH", "З": "Z", "И": "I",
    "Й": "I", "К": "K", "Л": "L", "М": "M", "Н": "N",
    "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T",
    "У": "U", "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH",
    "Ш": "SH", "Щ": "SHCH", "Ъ": "IE", "Ы": "Y", "Ь": "",
    "Э": "E", "Ю": "IU", "Я": "IA",
}


def transliterate_ru_to_lat(text: str) -> str:
    """
    Транслитерирует русский текст в латиницу по ГОСТ 52535.1-2006.

    Сохраняет регистр:
    - "Иванов" → "Ivanov"
    - "ИВАНОВ" → "IVANOV"
    - "иванов" → "ivanov"
    """
    if not text:
        return ""

    result_parts = []
    for char in text:
        upper = char.upper()
        if upper in GOST_R_52535_1_2006:
            translit = GOST_R_52535_1_2006[upper]
            if char.isupper():
                result_parts.append(translit)
            else:
                result_parts.append(translit.lower())
        else:
            result_parts.append(char)

    return "".join(result_parts)


def transliterate_name(name: str) -> str:
    """
    Удобный wrapper для имени/фамилии.

    Применяет транслитерацию и приводит результат к Title Case
    (первая буква каждого слова — заглавная), как принято в паспортах.
    """
    if not name:
        return ""

    lower_translit = transliterate_ru_to_lat(name.lower().strip())

    result = []
    current_word = []
    for char in lower_translit:
        if char in (" ", "-"):
            if current_word:
                word = "".join(current_word)
                result.append(word.capitalize())
                current_word = []
            result.append(char)
        else:
            current_word.append(char)
    if current_word:
        word = "".join(current_word)
        result.append(word.capitalize())

    return "".join(result)


# ============================================================================
# Pack 14 finishing — обратная транслитерация (Latin → русский)
# ============================================================================

# Базовая таблица символов (общая для всех языков). Двух- и трёх-символьные
# последовательности обрабатываются отдельно (см. _MULTI_CHAR_RULES).
# Применяется ПОСЛЕ multi-char замен.
_BASE_LAT_TO_RU = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "х", "i": "и", "j": "й", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
    "y": "и", "z": "з",
    # Диакритика — общая
    "ä": "э", "ö": "ё", "ü": "ю", "ß": "сс",
    "à": "а", "á": "а", "â": "а", "ã": "а", "å": "а",
    "è": "е", "é": "е", "ê": "е", "ë": "е",
    "ì": "и", "í": "и", "î": "и", "ï": "и",
    "ò": "о", "ó": "о", "ô": "о", "õ": "о",
    "ù": "у", "ú": "у", "û": "у",
    "ý": "и", "ÿ": "и",
    "ñ": "нь", "ç": "с",
    "ş": "ш", "ç": "ч",  # тур.
    "ğ": "г",  # тур.
    "ı": "ы", "İ": "И",  # тур.
    "ł": "л",  # пол.
    "ń": "нь", "ó": "у", "ś": "сь", "ź": "зь", "ż": "ж",  # пол.
    "č": "ч", "š": "ш", "ž": "ж",  # чех/хорв.
    "ř": "рж", "ě": "е",  # чех.
}

# Многосимвольные паттерны (применяются ПЕРВЫМИ)
# Структура: (язык-приоритет, паттерн lat → русский)
# Применяются case-insensitive, регистр восстанавливается потом.
_MULTI_CHAR_RULES: dict[str, list[tuple[str, str]]] = {
    "TUR": [
        # Турецкие особые сочетания
        ("yü", "ю"), ("yu", "ю"),
        ("yo", "ё"), ("yö", "ё"),
        ("ya", "я"),
        ("ye", "е"),
        ("ş", "ш"), ("ç", "ч"), ("ğ", "г"),
        ("ı", "ы"), ("ü", "ю"), ("ö", "ё"),
    ],
    "POL": [
        ("sz", "ш"), ("cz", "ч"), ("rz", "ж"), ("dz", "дз"),
        ("ch", "х"), ("dż", "дж"), ("dź", "дзь"),
        ("ie", "е"), ("ia", "я"), ("io", "ё"), ("iu", "ю"),
        ("ł", "л"), ("ż", "ж"), ("ź", "зь"), ("ś", "сь"), ("ć", "ць"), ("ń", "нь"),
        ("ó", "у"),
    ],
    "DEU": [
        ("sch", "ш"), ("tsch", "ч"), ("ch", "х"),
        ("ei", "ай"), ("ie", "и"), ("eu", "ой"), ("au", "ау"),
        ("ä", "э"), ("ö", "ё"), ("ü", "ю"), ("ß", "сс"),
        ("ts", "ц"), ("th", "т"),
    ],
    "CZE": [
        ("ch", "х"), ("š", "ш"), ("č", "ч"), ("ž", "ж"),
        ("ř", "рж"), ("ě", "е"),
    ],
    "ITA": [
        ("gli", "льи"), ("gn", "нь"),
        ("sci", "ши"), ("sce", "ше"),
        ("ci", "чи"), ("ce", "че"),
        ("gi", "джи"), ("ge", "дже"),
        ("chi", "ки"), ("che", "ке"),
        ("ghi", "ги"), ("ghe", "ге"),
    ],
    "ESP": [
        ("ch", "ч"), ("ll", "ль"),
        ("ñ", "нь"), ("qu", "к"),
    ],
    "FRA": [
        ("ch", "ш"), ("eau", "о"), ("au", "о"), ("ou", "у"),
        ("oi", "уа"), ("ai", "е"), ("ei", "е"),
        ("ç", "с"),
    ],
    # СНГ — латинская версия имён довольно близка к русской
    "AZE": [
        ("ş", "ш"), ("ç", "ч"), ("ğ", "г"),
        ("ı", "ы"), ("ü", "ю"), ("ö", "ё"), ("ə", "э"),
    ],
    "UZB": [
        ("o'", "о"), ("g'", "г"),
        ("ch", "ч"), ("sh", "ш"),
    ],
    "KAZ": [
        ("ch", "ч"), ("sh", "ш"),
        ("ä", "а"), ("ö", "ё"), ("ü", "ю"), ("ı", "ы"),
        ("ñ", "нь"),
    ],
    "GEO": [
        ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
        ("dz", "дз"), ("zh", "ж"),
    ],
    # Универсальные паттерны (если язык не известен или не покрыт)
    "DEFAULT": [
        ("sh", "ш"), ("ch", "ч"), ("zh", "ж"),
        ("kh", "х"), ("ts", "ц"),
        ("ya", "я"), ("yu", "ю"), ("yo", "ё"), ("ye", "е"),
        ("th", "т"), ("ph", "ф"),
    ],
}


def _apply_rules(text: str, rules: list[tuple[str, str]]) -> str:
    """Применяет multi-char правила case-insensitive с сохранением регистра."""
    result = text
    for lat_pattern, ru_replacement in rules:
        # Проходим разными вариантами регистра
        for variant in (lat_pattern, lat_pattern.upper(), lat_pattern.capitalize()):
            if variant in result:
                # Восстанавливаем регистр в замене
                if variant == lat_pattern:
                    repl = ru_replacement
                elif variant == lat_pattern.upper():
                    repl = ru_replacement.upper()
                else:
                    repl = ru_replacement.capitalize()
                result = result.replace(variant, repl)
    return result


def transliterate_lat_to_ru(text: str, nationality: str | None = None) -> str:
    """
    Pack 14 finishing — обратная транслитерация: латиница → русский.

    Используется для иностранных клиентов, у которых в паспорте только латинское имя:
    - YUKSEL VEDAT (TUR) → Юксель Ведат
    - KOWALSKI JAN (POL) → Ковальский Ян
    - MÜLLER HANS (DEU) → Мюллер Ханс

    Применяет правила в зависимости от nationality:
    - Сначала специфичные для языка многосимвольные правила
    - Потом универсальные DEFAULT правила
    - Потом базовая посимвольная замена

    Результат всегда в Title Case (первая буква каждого слова — заглавная,
    остальные — строчные).

    Args:
        text: латинский текст для транслитерации
        nationality: ISO-3 код страны (TUR, POL, DEU, ...). Опционально.

    Examples:
        >>> transliterate_lat_to_ru("YUKSEL VEDAT", "TUR")
        'Юксель Ведат'
        >>> transliterate_lat_to_ru("KOWALSKI JAN", "POL")
        'Ковальский Ян'
        >>> transliterate_lat_to_ru("MÜLLER HANS", "DEU")
        'Мюллер Ханс'
    """
    if not text:
        return ""

    # 1. Приводим к нижнему регистру для применения правил (потом приведём к Title Case)
    work = text.strip().lower()

    # 2. Применяем правила выбранного языка
    if nationality and nationality.upper() in _MULTI_CHAR_RULES:
        rules = _MULTI_CHAR_RULES[nationality.upper()]
        for lat, ru in rules:
            work = work.replace(lat.lower(), ru.lower())

    # 3. Применяем универсальные правила DEFAULT
    for lat, ru in _MULTI_CHAR_RULES["DEFAULT"]:
        work = work.replace(lat.lower(), ru.lower())

    # 4. Посимвольная замена
    result_parts = []
    for char in work:
        if char in _BASE_LAT_TO_RU:
            result_parts.append(_BASE_LAT_TO_RU[char])
        else:
            # Уже кириллица или разделитель — оставляем
            result_parts.append(char)
    transliterated = "".join(result_parts)

    # 5. Title Case
    return _to_title_case(transliterated)


def _to_title_case(text: str) -> str:
    """Title Case с разделителями пробел/дефис."""
    if not text:
        return ""

    result = []
    current_word = []
    for char in text:
        if char in (" ", "-", "'"):
            if current_word:
                word = "".join(current_word)
                result.append(word.capitalize())
                current_word = []
            result.append(char)
        else:
            current_word.append(char)
    if current_word:
        word = "".join(current_word)
        result.append(word.capitalize())

    return "".join(result)


def normalize_russian_case(text: str) -> str:
    """
    Pack 14 finishing — нормализует регистр русского имени к Title Case.

    Используется в PATCH endpoint Applicant'а — менеджер мог ввести что угодно,
    приводим к стандартному виду для документов:

    - "ИВАНОВ" → "Иванов"
    - "иванов" → "Иванов"
    - "Иванов-Петров" → "Иванов-Петров"
    - "анна мария" → "Анна Мария"
    - "ЮКСЕЛЬ" → "Юксель"

    Латиница и не-русские символы тоже обрабатываются (Title Case применяется
    ко всему тексту), на случай если поле _native заполнено латиницей.
    """
    if not text:
        return ""
    return _to_title_case(text.strip().lower())
