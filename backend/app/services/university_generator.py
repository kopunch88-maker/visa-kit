"""
Pack 19.0 — генератор образования для applicant'а.

Основная функция: `suggest_education(applicant, session)` — возвращает
один подходящий вуз+специальность+год выпуска на основе:
  - applicant.inn_kladr_code → регион (первые 2 цифры)
  - applicant.work_history[0].position → специальность через PositionSpecialtyMap
  - applicant.birth_date → год выпуска (~ 22 года + случайный 0-5 лет стажа)

Если для региона нет вузов → fallback на Москву ('77') с пометкой fallback_used=True.
Если должность не матчится ни с одним паттерном → используем generic паттерн
  'инженер' (priority=90) или 'менеджер' (priority=90) как finally fallback.

Без обращений к LLM — чистый детерминированный алгоритм.
"""
from __future__ import annotations

import logging
import random
from datetime import date
from typing import Optional

from sqlmodel import Session, select

from app.models import Applicant
from app.models.university import (
    University,
    Specialty,
    UniversitySpecialtyLink,
    PositionSpecialtyMap,
    UniversitySuggestion,
)

log = logging.getLogger(__name__)

# Москва — fallback регион если в регионе клиента нет подходящих вузов
FALLBACK_REGION_CODE = "77"

# Если в work_history нет должности — генерим как «менеджер» (общая специальность)
DEFAULT_POSITION_FALLBACK = "менеджер"

# Уровень → русское название для CV (Бакалавр / Специалист / Магистр)
LEVEL_NAMES = {
    "bachelor": "Бакалавр",
    "specialist": "Специалист",
    "master": "Магистр",
}

# Pack 19.0.1: возрастные диапазоны выпуска для разных гражданств.
#
# Резиденты РФ оканчивают вуз в 22-23 (классика 4 года бакалавриата).
# Нерезиденты получают 22-32 — потому что часто:
#   - заканчивают вуз позже из-за службы / переезда
#   - получают второе образование уже в России / Европе
#   - идут в магистратуру после переезда
RESIDENT_GRADUATION_AGE_RANGE = (22, 23)
NON_RESIDENT_GRADUATION_AGE_RANGE = (22, 32)
RESIDENT_NATIONALITIES = {"RUS"}

# Pack 19.0.1: верхний cap по году выпуска. Не позже 2022 чтобы у клиента
# было минимум 3 года стажа до текущего момента (2026 - 2022 = 4 года).
# Это требование DN-визы: подтверждённый трудовой стаж по специальности.
MAX_GRADUATION_YEAR = 2022


def _calculate_graduation_year(
    birth_date: Optional[date],
    nationality: Optional[str],
    rng: random.Random,
    today: Optional[date] = None,
) -> int:
    """
    Pack 19.0.1: год выпуска = год_рождения + случайный_возраст_выпуска,
    но не позже MAX_GRADUATION_YEAR (= 2022) и не позже текущего года - 1.

    Логика возраста:
      - Резиденты РФ (nationality='RUS'): возраст ∈ [22, 23]
      - Нерезиденты: возраст ∈ [22, 32] (учёт поздних программ, миграции)

    Если birth_date нет — fallback на «5 лет назад от MAX_GRADUATION_YEAR»
    как разумная середина для типичного DN-кандидата.
    """
    if today is None:
        today = date.today()

    cap_year = min(MAX_GRADUATION_YEAR, today.year - 1)

    if birth_date is None:
        # Без даты рождения — допустим середину диапазона: 2017 для 2022-ного cap
        return cap_year - 5

    # Выбираем возрастной диапазон по гражданству
    is_resident = (nationality or "").upper() in RESIDENT_NATIONALITIES
    age_range = (
        RESIDENT_GRADUATION_AGE_RANGE if is_resident
        else NON_RESIDENT_GRADUATION_AGE_RANGE
    )

    age_at_graduation = rng.randint(*age_range)
    candidate = birth_date.year + age_at_graduation

    # Не позже cap (2022 или today.year-1, что меньше)
    return min(candidate, cap_year)


def _get_region_code(applicant: Applicant) -> Optional[str]:
    """Достаёт 2-зн region_code из inn_kladr_code (первые 2 символа)."""
    if not applicant.inn_kladr_code:
        return None
    code = applicant.inn_kladr_code.strip()
    if len(code) < 2:
        return None
    return code[:2]


def _get_position(applicant: Applicant, session: Session) -> str:
    """
    Pack 19.0.2: ищем должность в трёх местах в порядке приоритета:
      1. applicant.work_history[0].position (классика — если клиент заполнил)
      2. application.position.title (Pack 19.0.2 — должность из заявки;
         менеджер задаёт через UI «Компания и договор»)
      3. DEFAULT_POSITION_FALLBACK = "менеджер" (последний fallback)
    """
    # 1. work_history клиента
    work = applicant.work_history or []
    if work:
        first = work[0]
        if isinstance(first, dict):
            position = (first.get("position") or "").strip()
        else:
            position = (getattr(first, "position", "") or "").strip()
        if position:
            return position

    # 2. Pack 19.0.2: позиция из applications
    # Один applicant может иметь несколько заявок — берём самую свежую
    # (не-archived, по дате создания DESC). Через relationships:
    #
    # Pack 19.0.3 fix: вместо `created_at or 0` (TypeError при сравнении
    # datetime с int) используем datetime.min для пустых дат.
    try:
        from datetime import datetime
        from app.models import Application, Position
        apps = sorted(
            [a for a in (applicant.applications or []) if not a.is_archived],
            key=lambda a: a.created_at or datetime.min,
            reverse=True,
        )
        for app in apps:
            if app.position_id:
                pos = session.get(Position, app.position_id)
                if pos and getattr(pos, "title_ru", None):
                    log.info(
                        "_get_position: applicant_id=%s application=%s position_id=%s → title_ru=%r",
                        applicant.id, app.id, app.position_id, pos.title_ru,
                    )
                    return pos.title_ru.strip()
    except Exception as e:
        # Pack 19.0.3 fix: было log.debug — не видно в проде. Поставил warning.
        log.warning(
            "could not load position from application for applicant_id=%s: %s: %s",
            applicant.id, type(e).__name__, e,
        )

    # 3. Fallback
    return DEFAULT_POSITION_FALLBACK


def _match_specialty(
    position: str, session: Session
) -> tuple[Optional[Specialty], Optional[str]]:
    """
    Подбор специальности по должности через PositionSpecialtyMap.

    Возвращает (specialty, matched_pattern):
      - specialty — найденная Specialty или None
      - matched_pattern — текст паттерна который сработал, для отладки

    Алгоритм:
      1. Берём все паттерны с is_active=True, сортируем по priority ASC
      2. Первый паттерн где `pattern.lower() in position.lower()` — победитель
    """
    position_lower = position.lower()

    # Все активные паттерны, отсортированные по priority (меньше = выше приоритет)
    patterns = session.exec(
        select(PositionSpecialtyMap)
        .where(PositionSpecialtyMap.is_active == True)  # noqa: E712
        .order_by(PositionSpecialtyMap.priority)
    ).all()

    for psm in patterns:
        if psm.position_pattern in position_lower:
            specialty = session.get(Specialty, psm.specialty_id)
            return specialty, psm.position_pattern

    return None, None


def _pick_university(
    region_code: Optional[str],
    specialty: Specialty,
    session: Session,
    rng: random.Random,
) -> tuple[Optional[University], bool]:
    """
    Выбор вуза для региона + специальности.

    Возвращает (university, fallback_used):
      - university — выбранный вуз или None если ни в регионе, ни в Москве не нашлось
      - fallback_used — True если пришлось взять московский вуз (региона нет)

    Алгоритм:
      1. Все вузы в region_code где specialty в их списке
      2. Если пусто — все вузы в FALLBACK_REGION_CODE с этой специальностью
      3. Из найденного списка случайно выбираем один (rng)
    """
    fallback_used = False

    def find_universities_for(rc: str) -> list[University]:
        # JOIN University ↔ UniversitySpecialtyLink ↔ Specialty
        stmt = (
            select(University)
            .join(
                UniversitySpecialtyLink,
                UniversitySpecialtyLink.university_id == University.id,  # type: ignore
            )
            .where(
                University.region_code == rc,
                University.is_active == True,  # noqa: E712
                UniversitySpecialtyLink.specialty_id == specialty.id,
            )
        )
        return list(session.exec(stmt).all())

    # 1. Регион клиента
    candidates: list[University] = []
    if region_code:
        candidates = find_universities_for(region_code)

    # 2. Fallback на Москву
    if not candidates and region_code != FALLBACK_REGION_CODE:
        candidates = find_universities_for(FALLBACK_REGION_CODE)
        if candidates:
            fallback_used = True
            log.info(
                "university generator: fallback to '%s' for region '%s' specialty '%s'",
                FALLBACK_REGION_CODE, region_code, specialty.code,
            )

    if not candidates:
        return None, fallback_used

    return rng.choice(candidates), fallback_used


def suggest_education(
    applicant: Applicant,
    session: Session,
    rng: Optional[random.Random] = None,
) -> Optional[UniversitySuggestion]:
    """
    Главная точка входа: возвращает UniversitySuggestion для applicant'а.

    Возвращает None если совсем ничего не подобралось (нет вузов в БД,
    или специальность не определилась). Это редкий случай — обычно хотя бы
    один из fallback'ов сработает.

    Параметры:
      - applicant: Applicant модель
      - session: SQLModel session
      - rng: random.Random для тестируемости (по умолчанию свежий генератор)

    Использование:
      ```python
      suggestion = suggest_education(applicant, session)
      if suggestion:
          # Сохраним в applicant.education[0]:
          new_record = {
              "institution": suggestion.institution,
              "graduation_year": suggestion.graduation_year,
              "degree": suggestion.degree,
              "specialty": suggestion.specialty,
          }
      ```
    """
    if rng is None:
        rng = random.Random()

    # 1. Должность → специальность
    position = _get_position(applicant, session)
    specialty, matched_pattern = _match_specialty(position, session)

    if specialty is None:
        log.warning(
            "university generator: no specialty for position %r (applicant_id=%s)",
            position, applicant.id,
        )
        return None

    # 2. Регион → вуз
    region_code = _get_region_code(applicant)
    university, fallback_used = _pick_university(region_code, specialty, session, rng)

    if university is None:
        log.warning(
            "university generator: no university for region=%s specialty=%s (applicant_id=%s)",
            region_code, specialty.code, applicant.id,
        )
        return None

    # 3. Год выпуска (с учётом гражданства — резиденты vs нерезиденты)
    graduation_year = _calculate_graduation_year(
        applicant.birth_date,
        applicant.nationality,
        rng,
    )

    # 4. Собираем результат
    degree = LEVEL_NAMES.get(specialty.level, "Бакалавр")
    specialty_text = f"{specialty.code} {specialty.name}"

    log.info(
        "university generator: applicant_id=%s region=%s position=%r → "
        "uni=%s specialty=%s grad=%d (fallback=%s, pattern=%r)",
        applicant.id, region_code, position,
        university.name_short, specialty.code, graduation_year,
        fallback_used, matched_pattern,
    )

    return UniversitySuggestion(
        institution=university.name_full,
        institution_short=university.name_short,
        degree=degree,
        specialty=specialty_text,
        graduation_year=graduation_year,
        matched_pattern=matched_pattern,
        fallback_used=fallback_used,
    )
