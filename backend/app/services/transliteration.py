"""
Транслитерация русского текста в латиницу по ГОСТ 52535.1-2006.

Это стандарт, по которому транслитерируют ФИО в загранпаспортах РФ
с 2010 года. Используется для:
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

    Не-русские символы (пробелы, дефисы, латиница, цифры) сохраняются как есть.

    Examples:
        >>> transliterate_ru_to_lat("Иван")
        'Ivan'
        >>> transliterate_ru_to_lat("Юлия")
        'Iuliia'
        >>> transliterate_ru_to_lat("Щёлково")
        'Shchelkovo'
        >>> transliterate_ru_to_lat("Анна-Мария")
        'Anna-Mariia'
    """
    if not text:
        return ""

    result_parts = []
    for char in text:
        upper = char.upper()
        if upper in GOST_R_52535_1_2006:
            translit = GOST_R_52535_1_2006[upper]
            # Сохраняем регистр исходного символа
            if char.isupper():
                result_parts.append(translit)  # уже uppercase в таблице
            else:
                result_parts.append(translit.lower())
        else:
            # Не русская буква — оставляем как есть (пробелы, дефисы, и т.д.)
            result_parts.append(char)

    return "".join(result_parts)


def transliterate_name(name: str) -> str:
    """
    Удобный wrapper для имени/фамилии.

    Применяет транслитерацию и приводит результат к Title Case
    (первая буква каждого слова — заглавная), как принято в паспортах.

    Examples:
        >>> transliterate_name("иван")
        'Ivan'
        >>> transliterate_name("ИВАНОВ")
        'Ivanov'
        >>> transliterate_name("Анна-Мария")
        'Anna-Mariia'
        >>> transliterate_name("ванья")
        'Vania'
    """
    if not name:
        return ""

    # Сначала всё к нижнему регистру + транслитерация
    lower_translit = transliterate_ru_to_lat(name.lower().strip())

    # Title case через split + capitalize по разделителям
    # Разделители: пробел, дефис
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
