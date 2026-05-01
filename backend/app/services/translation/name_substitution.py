"""
Pack 15.1 — Pre-substitution имён до перевода через LLM.

Принцип: до отправки текста в LLM, заменяем в DOCX все вхождения русских имён
(applicant, директора компании, название компании) на латинские эквиваленты.

LLM получает уже частично-латинизированный русский текст. Промпт явно говорит
«латиницу не трогай — это уже корректные имена из официальных документов».

Это решает три проблемы которые видны в реальных подачах:
1. LLM раньше иногда транслитерировал имена сам — получался разнобой
   (один документ "Yuksel", другой "Yuksel'" или "Iuksel'" по ГОСТу)
2. LLM иногда переводил название компании смыслом ("ИНЖГЕОСЕРВИС" → "Engineering...")
   вместо транслита, как принято у jurada-переводчиков
3. Менеджер потом руками правил — теперь не нужно

Источники латинских форм:
- Applicant.last_name_latin / first_name_latin — из паспорта (приоритет)
- Company.full_name_es — заполнен менеджером в drawer (приоритет)
- Company.director_full_name_latin — заполнен менеджером в drawer (приоритет)
- Если что-то не заполнено — fallback на GOST 52535.1-2006 транслит
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.models import Applicant, Application, Company
from app.services.transliteration import transliterate_name

log = logging.getLogger(__name__)


@dataclass
class SubstitutionDict:
    """
    Словарь замен ru → lat для одной заявки.

    Замены применяются в порядке: longest first (длинные сначала),
    чтобы «Иванов Иван Иванович» заменилось целиком, прежде чем «Иванов» отдельно.
    """
    pairs: list[tuple[str, str]]  # [(ru_text, lat_text), ...] длинные сначала

    def apply(self, text: str) -> str:
        """Применяет все замены к тексту."""
        result = text
        for ru, lat in self.pairs:
            if ru and lat and ru in result:
                result = result.replace(ru, lat)
        return result

    def __len__(self) -> int:
        return len(self.pairs)


def _safe(value: Optional[str]) -> str:
    """None → '', strip whitespace."""
    return (value or "").strip()


def _build_applicant_subs(applicant: Optional[Applicant]) -> list[tuple[str, str]]:
    """
    Замены для имени заявителя.

    Источник латиницы: applicant.last_name_latin + first_name_latin (из паспорта).
    Если латиница не заполнена — пропускаем (LLM сам разберётся).

    Возвращаем замены вида:
    - "Юксель Ведат" → "Yuksel Vedat"  (полное)
    - "Юкселя Ведата" → "Yuksel Vedat"  (родительный — если есть в genitive_ru)
    - "Юксель" → "Yuksel"  (только фамилия)
    - "Ведат" → "Vedat"  (только имя)

    Не покрываем все падежи русского — это слишком хрупко. Покрываем только
    Им. падеж и Род. падеж (если есть в applicant). LLM остальное само поймёт
    по контексту.
    """
    if not applicant:
        return []

    last_native = _safe(applicant.last_name_native)
    first_native = _safe(applicant.first_name_native)
    middle_native = _safe(applicant.middle_name_native)

    last_latin = _safe(applicant.last_name_latin)
    first_latin = _safe(applicant.first_name_latin)
    middle_latin = _safe(applicant.middle_name_latin) if hasattr(applicant, "middle_name_latin") else ""

    if not last_latin or not first_latin:
        log.info(
            f"[name_sub] Applicant {applicant.id}: latin name fields empty, "
            f"no substitution"
        )
        return []

    # Собираем латинские формы: «Фамилия Имя [Отчество]» и просто фамилию/имя
    full_latin_parts = [last_latin, first_latin]
    if middle_latin:
        full_latin_parts.append(middle_latin)
    full_latin = " ".join(full_latin_parts)
    short_latin = f"{last_latin} {first_latin}"

    pairs: list[tuple[str, str]] = []

    # Полные формы (длинные сначала)
    if last_native and first_native and middle_native:
        pairs.append((f"{last_native} {first_native} {middle_native}", full_latin))
    if last_native and first_native:
        pairs.append((f"{last_native} {first_native}", short_latin))
        pairs.append((f"{first_native} {last_native}", short_latin))  # обратный порядок

    # Genitive (Род. падеж) — у Applicant есть last_name_genitive_native?
    last_genitive = _safe(getattr(applicant, "last_name_genitive_native", None))
    first_genitive = _safe(getattr(applicant, "first_name_genitive_native", None))
    if last_genitive and first_genitive:
        pairs.append((f"{last_genitive} {first_genitive}", short_latin))

    # Одиночные (только фамилия / только имя)
    if last_native:
        pairs.append((last_native, last_latin))
    if first_native:
        pairs.append((first_native, first_latin))
    if middle_native and middle_latin:
        pairs.append((middle_native, middle_latin))

    return pairs


def _gost_director_full(director_ru: str) -> str:
    """GOST-транслит имени директора в формате "Фамилия Имя Отчество"."""
    if not director_ru:
        return ""
    return transliterate_name(director_ru)


def _build_director_subs(company: Optional[Company]) -> list[tuple[str, str]]:
    """
    Замены для имени директора компании.

    Источник латиницы: company.director_full_name_latin (если заполнено),
    иначе GOST-транслит из company.director_full_name_ru.

    Покрываем:
    - director_full_name_ru (Им. падеж)
    - director_full_name_genitive_ru (Род. падеж — обязательное поле)
    - director_short_ru ("Тараскин Ю.А.")
    """
    if not company:
        return []

    full_ru = _safe(company.director_full_name_ru)
    genitive_ru = _safe(company.director_full_name_genitive_ru)
    short_ru = _safe(company.director_short_ru)

    if not full_ru:
        return []

    # Латинская версия — приоритет на заполненном поле
    full_latin = _safe(getattr(company, "director_full_name_latin", None))
    if not full_latin:
        full_latin = _gost_director_full(full_ru)

    if not full_latin:
        return []

    # Короткая форма из латинского полного: "Tarakin Yury Aleksandrovich" → "Tarakin Y.A."
    short_latin = _short_form(full_latin)

    pairs: list[tuple[str, str]] = []

    # Длинные сначала
    if full_ru:
        pairs.append((full_ru, full_latin))
    if genitive_ru:
        pairs.append((genitive_ru, full_latin))
    if short_ru:
        pairs.append((short_ru, short_latin))

    return pairs


def _short_form(full_name_latin: str) -> str:
    """
    "Tarakin Yury Aleksandrovich" → "Tarakin Y.A."
    "Vuykovich Darko Stevanovich" → "Vuykovich D.S."
    """
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

    Источник: company.full_name_es (заполнено менеджером).
    Если пусто — пропускаем (LLM решит сам — это редкий случай, поле обязательное в БД).
    """
    if not company:
        return []

    full_ru = _safe(company.full_name_ru)
    full_es = _safe(company.full_name_es)
    short_name = _safe(company.short_name)

    if not full_ru or not full_es:
        return []

    pairs: list[tuple[str, str]] = []

    # Длинные сначала
    pairs.append((full_ru, full_es))

    # Если short_name содержит кириллицу и отличается от full_ru — тоже заменяем
    # (например full_ru = «ООО ИНЖГЕОСЕРВИС», short_name = «ИНЖГЕОСЕРВИС»)
    if short_name and short_name != full_ru and re.search(r"[А-Яа-я]", short_name):
        # Берём латинскую часть из full_es (после ООО/S.L.)
        # Это эвристика: вытаскиваем то что в кавычках или после «ООО»/«S.L.»
        es_core = _extract_company_core(full_es)
        if es_core:
            pairs.append((short_name, es_core))

    return pairs


def _extract_company_core(es_name: str) -> str:
    """
    Достаёт «ядро» названия компании из испанского варианта.

    «Sociedad Limitada "INZHGEOSERVIS"» → "INZHGEOSERVIS"
    «"INZHGEOSERVIS", S.L.» → "INZHGEOSERVIS"
    «INZHGEOSERVIS S.L.» → "INZHGEOSERVIS"
    """
    # Сначала пробуем извлечь из кавычек (обычные/ёлочки/смарт)
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

    Замены упорядочены по убыванию длины — длинные совпадения применяются
    первыми, чтобы «Иванов Иван Иванович» заменилось целиком прежде чем
    срабатывало правило «Иванов» → «Ivanov» отдельно.
    """
    all_pairs: list[tuple[str, str]] = []

    all_pairs.extend(_build_applicant_subs(applicant))
    all_pairs.extend(_build_director_subs(company))
    all_pairs.extend(_build_company_subs(company))

    # Дедупликация по ключу
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

    log.info(
        f"[name_sub] Built {len(deduped)} substitutions for app {application.id}: "
        f"{[(ru[:30], lat[:30]) for ru, lat in deduped[:5]]}..."
    )

    return SubstitutionDict(pairs=deduped)
