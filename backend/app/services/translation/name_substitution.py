"""
Pack 15.1 — Pre-substitution имён до перевода через LLM.
Pack 15.2 — Расширения:
   - applicant.full_name_native (Юксел Ведат — единая строка из шаблона)
   - company.short_name (ИНЖГЕОСЕРВИС — без ООО)
   - Метки ИНН/КПП/ОГРН/БИК → NIF/KPP/OGRN/BIC (надёжная замена даже если LLM
     решит их «не трогать»)
   - "None" → "—" (фикс случаев когда Jinja подставляет None для пустых полей)

Принцип: до отправки текста в LLM, заменяем в DOCX все вхождения русских имён
(applicant, директора компании, название компании) на латинские эквиваленты.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.models import Applicant, Application, Company
from app.services.transliteration import transliterate_name

log = logging.getLogger(__name__)


# Pack 15.2: метки реквизитов всегда переводятся (а не оставляются кириллицей).
# Это надёжный backup промпта — если LLM решит «оставить как есть», pre-sub
# уже подменил их на испанскую версию.
LABEL_SUBSTITUTIONS: list[tuple[str, str]] = [
    # Налоговые ID (с пробелом после — чтобы не задеть «ИНН» внутри слов)
    ("ИНН ",  "NIF "),
    ("КПП ",  "KPP "),
    ("ОГРН ", "OGRN "),
    ("БИК ",  "BIC "),
    ("СНИЛС ", "SNILS "),
    ("ОКПО ", "OKPO "),
    # Метки в конце строки (без пробела после)
    ("ИНН\n",  "NIF\n"),
    ("КПП\n",  "KPP\n"),
    ("ОГРН\n", "OGRN\n"),
    ("БИК\n",  "BIC\n"),
    ("СНИЛС\n", "SNILS\n"),
    # Также если идут с двоеточием
    ("ИНН:",  "NIF:"),
    ("КПП:",  "KPP:"),
    ("ОГРН:", "OGRN:"),
    ("БИК:",  "BIC:"),
    # Обычно «БИК банка» в шаблонах — этот вариант уже LLM хорошо переводит,
    # но на всякий случай:
    ("БИК банка", "BIC del banco"),
    # Жёсткий фикс: None из Jinja
    (": None\n", ": —\n"),
    (" None\n", " —\n"),
    ("\nNone\n", "\n—\n"),
    ("\nNone ", "\n— "),
    ("\nNone:", "\n—:"),
]


@dataclass
class SubstitutionDict:
    """Словарь замен ru → lat для одной заявки."""
    pairs: list[tuple[str, str]]

    def apply(self, text: str) -> str:
        result = text
        for ru, lat in self.pairs:
            if ru and lat and ru in result:
                result = result.replace(ru, lat)
        return result

    def __len__(self) -> int:
        return len(self.pairs)


def _safe(value) -> str:
    """None / любой объект → '', strip whitespace."""
    if value is None:
        return ""
    return str(value).strip()


def _build_applicant_subs(applicant: Optional[Applicant]) -> list[tuple[str, str]]:
    """
    Замены для имени заявителя.

    Pack 15.2: ОБЯЗАТЕЛЬНО покрываем applicant.full_name_native — это единая
    переменная Jinja которая в шаблоне используется в реквизитной таблице
    («Юксел Ведат» одной строкой).
    """
    if not applicant:
        return []

    last_native = _safe(applicant.last_name_native)
    first_native = _safe(applicant.first_name_native)
    middle_native = _safe(getattr(applicant, "middle_name_native", None))

    last_latin = _safe(applicant.last_name_latin)
    first_latin = _safe(applicant.first_name_latin)
    middle_latin = _safe(getattr(applicant, "middle_name_latin", None))

    if not last_latin or not first_latin:
        log.info(
            f"[name_sub] Applicant {applicant.id}: latin name fields empty, "
            f"no substitution"
        )
        return []

    # Латинские формы
    full_latin_parts = [last_latin, first_latin]
    if middle_latin:
        full_latin_parts.append(middle_latin)
    full_latin = " ".join(full_latin_parts)            # "Yuksel Vedat" (Lastname Firstname order)
    short_latin = f"{last_latin} {first_latin}"

    pairs: list[tuple[str, str]] = []

    # Pack 15.2: ВАЖНО — applicant.full_name_native (если есть как computed field)
    full_native = _safe(getattr(applicant, "full_name_native", None))
    if full_native:
        pairs.append((full_native, full_latin))

    # Полные формы (длинные сначала)
    if last_native and first_native and middle_native:
        pairs.append((f"{last_native} {first_native} {middle_native}", full_latin))
    if last_native and first_native:
        pairs.append((f"{last_native} {first_native}", short_latin))
        pairs.append((f"{first_native} {last_native}", short_latin))  # обратный порядок

    # Genitive — обязательное поле через getattr
    last_genitive = _safe(getattr(applicant, "last_name_genitive_native", None))
    first_genitive = _safe(getattr(applicant, "first_name_genitive_native", None))
    if last_genitive and first_genitive:
        pairs.append((f"{last_genitive} {first_genitive}", short_latin))

    # Одиночные
    if last_native:
        pairs.append((last_native, last_latin))
    if first_native:
        pairs.append((first_native, first_latin))
    if middle_native and middle_latin:
        pairs.append((middle_native, middle_latin))

    # Pack 35.10: инициальные формы для подписи.
    # В шаблоне подпись: «{{ applicant.initials_native }}» → русский «Шахин И.»
    # Без этих пар substitution заменяет «Шахин»→«SAHIN», но «И.» остаётся
    # кириллицей → в переводе «SAHIN И.» вместо «SAHIN I.».
    # Точечный паттерн «{LASTNAME} {init}.» — не задевает другие «И.» в тексте.
    if last_native and first_native and last_latin and first_latin:
        ru_init = first_native[0]
        lat_init = first_latin[0]
        # Шахин И. → SAHIN I.
        pairs.append((f"{last_native} {ru_init}.", f"{last_latin} {lat_init}."))
        # Уже подменённый last_latin — на случай если фамилия заменилась раньше:
        # SAHIN И. → SAHIN I.
        pairs.append((f"{last_latin} {ru_init}.", f"{last_latin} {lat_init}."))
        # С middle initial если есть
        if middle_native and middle_latin:
            ru_mid = middle_native[0]
            lat_mid = middle_latin[0]
            pairs.append((
                f"{last_native} {ru_init}.{ru_mid}.",
                f"{last_latin} {lat_init}.{lat_mid}.",
            ))
            pairs.append((
                f"{last_latin} {ru_init}.{ru_mid}.",
                f"{last_latin} {lat_init}.{lat_mid}.",
            ))

    # Pack 39.3: СБП-формат "Имя Ф." → "NAME F." (имя + инициал фамилии)
    if last_native and first_native and last_latin and first_latin:
        pairs.append((f"{first_native} {last_native[0]}.", f"{first_latin} {last_latin[0]}."))
        pairs.append((f"{first_latin} {last_native[0]}.", f"{first_latin} {last_latin[0]}."))

    return pairs


def _gost_director_full(director_ru: str) -> str:
    """GOST-транслит имени директора в формате 'Фамилия Имя Отчество'."""
    if not director_ru:
        return ""
    return transliterate_name(director_ru)


def _build_director_subs(company: Optional[Company]) -> list[tuple[str, str]]:
    """Замены для имени директора компании."""
    if not company:
        return []

    full_ru = _safe(company.director_full_name_ru)
    genitive_ru = _safe(company.director_full_name_genitive_ru)
    short_ru = _safe(company.director_short_ru)

    if not full_ru:
        return []

    full_latin = _safe(getattr(company, "director_full_name_latin", None))
    if not full_latin:
        full_latin = _gost_director_full(full_ru)

    if not full_latin:
        return []

    short_latin = _short_form(full_latin)

    pairs: list[tuple[str, str]] = []
    if full_ru:
        pairs.append((full_ru, full_latin))
    if genitive_ru:
        pairs.append((genitive_ru, full_latin))
    if short_ru:
        pairs.append((short_ru, short_latin))

    return pairs


def _short_form(full_name_latin: str) -> str:
    """'Tarakin Yury Aleksandrovich' → 'Tarakin Y.A.'"""
    parts = full_name_latin.strip().split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    initials = ".".join(p[0] for p in parts[1:] if p) + "."
    return f"{parts[0]} {initials}"


def _build_company_subs(company: Optional[Company]) -> list[tuple[str, str]]:
    """
    Замены для названия компании.

    Pack 15.2: добавлены замены для company.short_name (без ООО).
    """
    if not company:
        return []

    full_ru = _safe(company.full_name_ru)
    full_es = _safe(company.full_name_es)
    short_name = _safe(company.short_name)

    pairs: list[tuple[str, str]] = []

    # Полное название (длинное сначала)
    if full_ru and full_es:
        pairs.append((full_ru, full_es))

    # Pack 15.2: short_name (например «ИНЖГЕОСЕРВИС») — ВАЖНО, в шаблоне в
    # реквизитной таблице используется именно short_name.
    # Pack 34.9: вместо голого ядра подставляем сокращённую полную форму
    # ('Sociedad Limitada "X"') — это юридически корректнее, чем просто бренд
    # в кавычках. Применяется во всех испанских переводах.
    if short_name and re.search(r"[А-Яа-я]", short_name):
        es_short_full = _shorten_opf_es(full_es) if full_es else ""
        if es_short_full:
            pairs.append((short_name, es_short_full))
        else:
            # Fallback: GOST-транслит short_name (когда full_es пустой)
            translit = transliterate_name(short_name)
            if translit:
                pairs.append((short_name, translit.upper()))

    return pairs


# ============================================================================
# Pack 34.9 — сокращение испанской ОПФ для короткой формы подстановки
# ============================================================================
# Используется в _build_company_subs (Пара 2) — для company.short_name
# вместо голого ядра в кавычках подставляется сокращённая полная форма.
# Применяется ко всем испанским переводам (договор, акты, счета, employer
# letter, CV, выписка) — потому что substitutions общие для всех типов.
#
# Pack 34.4 в bank_statement_generator.py — симметрия для русского:
#   «Общество с ограниченной ответственностью» → «ООО»
# Pack 34.9 — для испанского:
#   «Sociedad de Responsabilidad Limitada» → «Sociedad Limitada»
#   «Sociedad Anónima Abierta/Cerrada» → «Sociedad Anónima»
#
# Длинная форма (full_name_ru → full_name_es) НЕ затрагивается — она
# остаётся «Sociedad de Responsabilidad Limitada ...» как сейчас.

_OPF_SHORTEN_ES_MAP = [
    # Порядок: более длинные паттерны раньше
    (r"^\s*Sociedad\s+de\s+Responsabilidad\s+Limitada\s+", "Sociedad Limitada "),
    (r"^\s*Sociedad\s+An[óo]nima\s+(?:Abierta|P[úu]blica)\s+", "Sociedad Anónima "),
    (r"^\s*Sociedad\s+An[óo]nima\s+(?:Cerrada|Privada)\s+", "Sociedad Anónima "),
]


def _shorten_opf_es(full_name_es: str) -> str:
    """
    Pack 34.9: сокращает испанскую ОПФ в начале названия компании.

    >>> _shorten_opf_es('Sociedad de Responsabilidad Limitada "FAKTOR STROY"')
    'Sociedad Limitada "FAKTOR STROY"'
    >>> _shorten_opf_es('Sociedad Limitada "X"')
    'Sociedad Limitada "X"'
    >>> _shorten_opf_es('Sociedad Anónima Abierta "Y"')
    'Sociedad Anónima "Y"'
    >>> _shorten_opf_es('')
    ''
    """
    if not full_name_es:
        return full_name_es
    for pattern, replacement in _OPF_SHORTEN_ES_MAP:
        new_name, count = re.subn(pattern, replacement, full_name_es, count=1, flags=re.IGNORECASE)
        if count:
            return new_name
    return full_name_es

def _extract_company_core(es_name: str) -> str:
    """Достаёт «ядро» названия компании из испанского варианта."""
    # Пробуем извлечь из кавычек
    match = re.search(r'[«"\'""]([^«"\'""]+)[»"\'""]', es_name)
    if match:
        return match.group(1).strip()

    # Иначе убираем хвост S.L. / S.A. / Ltd
    cleaned = re.sub(r"[,\s]+(?:S\.?L\.?|S\.?A\.?|Ltd\.?|LLC)\.?\s*$", "", es_name, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:Sociedad\s+(?:Limitada|An[óo]nima)\s+)", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(' "«»\'')


def build_substitution_dict(
    application: Application,
    applicant: Optional[Applicant],
    company: Optional[Company],
) -> SubstitutionDict:
    """
    Главная функция: строит словарь замен для одной заявки.

    Pack 15.2: добавлены LABEL_SUBSTITUTIONS — фиксированные замены меток
    реквизитов (ИНН → NIF и т.п.). Они идут ПОСЛЕДНИМИ — после имён
    (длинные сначала), но ДО собственно отправки в LLM.
    """
    all_pairs: list[tuple[str, str]] = []

    all_pairs.extend(_build_applicant_subs(applicant))
    all_pairs.extend(_build_director_subs(company))
    all_pairs.extend(_build_company_subs(company))

    # Дедупликация
    seen_keys: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for ru, lat in all_pairs:
        if ru in seen_keys:
            continue
        if not ru.strip() or not lat.strip():
            continue
        seen_keys.add(ru)
        deduped.append((ru, lat))

    # Сортируем по убыванию длины ru-ключа (longest match first)
    deduped.sort(key=lambda pair: len(pair[0]), reverse=True)

    # Pack 15.2: LABEL_SUBSTITUTIONS добавляем В КОНЕЦ — они короткие,
    # но универсальные. В порядке как написаны (ИНН → NIF до КПП → KPP).
    final_pairs = deduped + LABEL_SUBSTITUTIONS

    log.info(
        f"[name_sub] Built {len(final_pairs)} substitutions for app {application.id} "
        f"({len(deduped)} dynamic + {len(LABEL_SUBSTITUTIONS)} labels): "
        f"top={[(ru[:30], lat[:30]) for ru, lat in deduped[:5]]}"
    )

    return SubstitutionDict(pairs=final_pairs)
