"""
Pack 19.1 — генератор work_history для applicant'а.

Основная функция: `suggest_work_history(applicant, session)` — возвращает
1-3 записи трудового стажа с правдоподобной career progression на основе:
  - applicant.inn_kladr_code → регион (первые 2 цифры)
  - applicant.education[-1].specialty → специальность (если уже сгенерирована)
  - applicant.work_history[0].position → специальность (fallback)
  - application.position.title_ru → специальность (Pack 19.0.2 fallback)

Если для региона нет компаний → fallback на Москву (FALLBACK_REGION_CODE='77').
Если специальность не определилась — generic '38.03.02 Менеджмент'.

Минимум 3.5 года в последней работе — для DN-визы нужно ≥3 года стажа.

Pack 19.1a: возвращает duties=[] для каждой записи (заполнится в 19.1b).

Без обращений к LLM — чисто детерминированный алгоритм с rng.
"""
from __future__ import annotations

import logging
import random
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import Applicant
from app.models.legend_company import (
    LegendCompany,
    CareerTrack,
    WorkRecordSuggestion,
    WorkHistorySuggestion,
)
from app.models.university import (
    Specialty,
    PositionSpecialtyMap,
)

log = logging.getLogger(__name__)

# Москва — fallback регион если в регионе клиента нет подходящих компаний.
FALLBACK_REGION_CODE = "77"

# Generic specialty если ни в education, ни в work_history не нашли подходящего паттерна.
DEFAULT_FALLBACK_SPECIALTY_CODE = "38.03.02"  # Менеджмент

# Если в education пусто И в work_history пусто И applications нет —
# берём это как должность для определения специальности.
DEFAULT_POSITION_FALLBACK = "менеджер"

# Распределение количества записей в легенде:
# - 1 работа: 20% (минималистичная легенда — только текущая 3.5+ года)
# - 2 работы: 50% (наиболее частый сценарий — текущая + предыдущая)
# - 3 работы: 30% (полная career progression от Junior до Senior)
COUNT_DISTRIBUTION = [(1, 0.2), (2, 0.5), (3, 0.3)]

# Уровни должностей в зависимости от количества записей (порядок: новейшая → ранняя)
LEVELS_BY_COUNT: dict[int, list[list[int]]] = {
    1: [[3], [4]],                    # Senior или Lead на единственной записи
    2: [[3, 2], [4, 3]],              # Senior+Middle или Lead+Senior
    3: [[3, 2, 1], [4, 3, 2]],        # Senior+Middle+Junior или Lead+Senior+Middle
}

# Длительность последней работы (в годах) — минимум 3.5 для DN-визы.
LAST_JOB_YEARS_RANGE = (3.5, 5.0)

# Длительность предыдущих работ (в годах).
PREV_JOB_YEARS_RANGE_MIDDLE = (1.5, 3.0)  # Запись 1 (когда count >= 2)
PREV_JOB_YEARS_RANGE_EARLY = (1.0, 2.0)   # Запись 2 (когда count == 3)

# Промежуток между концом одной работы и началом следующей (в месяцах).
GAP_MONTHS_RANGE = (0, 3)

# Русские названия месяцев для форматирования period_start/period_end.
RU_MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


# ============================================================================
# === Determining specialty from applicant ===
# ============================================================================

def _get_region_code(applicant: Applicant) -> Optional[str]:
    """Достаёт 2-зн region_code из inn_kladr_code (первые 2 символа)."""
    if not applicant.inn_kladr_code:
        return None
    code = applicant.inn_kladr_code.strip()
    if len(code) < 2:
        return None
    return code[:2]


def _get_position_for_matching(applicant: Applicant, session: Session) -> str:
    """
    Определяет должность клиента в порядке приоритета:
      1. applicant.work_history[0].position (если уже что-то заполнил)
      2. application.position.title_ru (Pack 19.0.2 fallback — должность из заявки)
      3. DEFAULT_POSITION_FALLBACK = "менеджер"

    Зеркалит логику из university_generator._get_position(), чтобы Education
    и WorkHistory сходились на одной и той же специальности.
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

    # 2. Позиция из applications (Pack 19.0.2 fallback)
    try:
        from datetime import datetime
        apps = list(applicant.applications or [])
        # Не-archived, по дате создания DESC, datetime.min для NULL'ов
        active_apps = [a for a in apps if not getattr(a, "is_archived", False)]
        active_apps.sort(
            key=lambda a: a.created_at or datetime.min,
            reverse=True,
        )
        for app in active_apps:
            if app.position_id is None:
                continue
            from app.models import Position
            position_obj = session.get(Position, app.position_id)
            if position_obj and position_obj.title_ru:
                title = position_obj.title_ru.strip()
                if title:
                    log.info(
                        "work_history generator: position from application %s "
                        "(applicant_id=%s): %r",
                        app.id, applicant.id, title,
                    )
                    return title
    except Exception as e:
        log.warning(
            "work_history generator: error reading position from applications "
            "(applicant_id=%s): %r",
            applicant.id, e,
        )

    return DEFAULT_POSITION_FALLBACK


def _match_specialty_by_education(
    applicant: Applicant,
    session: Session,
) -> tuple[Optional[Specialty], Optional[str]]:
    """
    Если у applicant'а уже есть education[] — вытаскиваем specialty оттуда.

    education[i].specialty имеет формат "08.03.01 Строительство" — берём
    префикс до первого пробела как code и ищем Specialty.

    Возвращает (specialty, matched_pattern_or_None).
    matched_pattern в этом случае = "education[N]" для отладки.
    """
    education = applicant.education or []
    if not education:
        return None, None

    # Берём ПОСЛЕДНЮЮ запись (самое свежее образование, если их несколько)
    for idx in range(len(education) - 1, -1, -1):
        edu = education[idx]
        if isinstance(edu, dict):
            spec_text = (edu.get("specialty") or "").strip()
        else:
            spec_text = (getattr(edu, "specialty", "") or "").strip()

        if not spec_text:
            continue

        # Парсим: "08.03.01 Строительство" → code="08.03.01"
        parts = spec_text.split(maxsplit=1)
        if not parts:
            continue
        code_candidate = parts[0]

        # Ищем в Specialty
        stmt = select(Specialty).where(Specialty.code == code_candidate)
        spec = session.exec(stmt).first()
        if spec:
            log.info(
                "work_history generator: specialty from education[%d] (%r): %s %s",
                idx, spec_text, spec.code, spec.name,
            )
            return spec, f"education[{idx}]"

    return None, None


def _match_specialty_by_position(
    position: str,
    session: Session,
) -> tuple[Optional[Specialty], Optional[str]]:
    """
    Ищет specialty по паттерну позиции через PositionSpecialtyMap.
    Копия логики из university_generator._match_specialty().
    """
    if not position:
        return None, None

    position_lower = position.lower()

    # Получаем все активные паттерны, отсортированные по приоритету (меньше = выше)
    stmt = (
        select(PositionSpecialtyMap, Specialty)
        .join(Specialty, Specialty.id == PositionSpecialtyMap.specialty_id)
        .where(PositionSpecialtyMap.is_active == True)  # noqa: E712
        .order_by(PositionSpecialtyMap.priority.asc())
    )
    rows = session.exec(stmt).all()

    for psm, spec in rows:
        if psm.position_pattern in position_lower:
            return spec, psm.position_pattern

    return None, None


def _resolve_specialty(
    applicant: Applicant,
    session: Session,
) -> tuple[Optional[Specialty], Optional[str]]:
    """
    Главная функция определения специальности с приоритетами:
      1. education[-1].specialty → specialty (точная привязка)
      2. work_history[0].position → specialty через PositionSpecialtyMap
      3. application.position.title_ru → specialty через PositionSpecialtyMap
      4. DEFAULT_FALLBACK_SPECIALTY_CODE (38.03.02 Менеджмент)
    """
    # 1. Education
    spec, pattern = _match_specialty_by_education(applicant, session)
    if spec:
        return spec, pattern

    # 2-3. Position → PositionSpecialtyMap
    position = _get_position_for_matching(applicant, session)
    spec, pattern = _match_specialty_by_position(position, session)
    if spec:
        log.info(
            "work_history generator: specialty by position %r → %s %s (pattern=%r)",
            position, spec.code, spec.name, pattern,
        )
        return spec, pattern

    # 4. Generic fallback
    stmt = select(Specialty).where(Specialty.code == DEFAULT_FALLBACK_SPECIALTY_CODE)
    spec = session.exec(stmt).first()
    if spec:
        log.warning(
            "work_history generator: no specialty match for position %r — "
            "falling back to %s (applicant_id=%s)",
            position, DEFAULT_FALLBACK_SPECIALTY_CODE, applicant.id,
        )
        return spec, "default_fallback"

    return None, None


# ============================================================================
# === Picking companies and titles ===
# ============================================================================

def _pick_companies_for_track(
    region_code: Optional[str],
    specialty: Specialty,
    count: int,
    session: Session,
    rng: random.Random,
) -> tuple[list[LegendCompany], bool]:
    """
    Подбирает count компаний для легенды.

    Алгоритм:
      1. Все активные компании в region_code с primary_specialty_id == specialty.id
      2. Если меньше count → добираем из Москвы (fallback)
      3. Если в Москве нет — добираем из любых компаний этой specialty в БД
      4. Если совсем ничего нет — возвращаем пустой список (генерация провалится)

    Возвращает (companies, fallback_used).
    Внутри легенды одна компания не повторяется.
    """
    fallback_used = False

    def find_companies(rc: Optional[str]) -> list[LegendCompany]:
        stmt = (
            select(LegendCompany)
            .where(
                LegendCompany.is_active == True,  # noqa: E712
                LegendCompany.primary_specialty_id == specialty.id,
            )
        )
        if rc:
            stmt = stmt.where(LegendCompany.region_code == rc)
        return list(session.exec(stmt).all())

    # 1. Регион клиента
    candidates: list[LegendCompany] = []
    if region_code:
        candidates = find_companies(region_code)

    # 2. Fallback на Москву
    if len(candidates) < count and region_code != FALLBACK_REGION_CODE:
        moscow_candidates = find_companies(FALLBACK_REGION_CODE)
        # Добавляем московские, исключая уже выбранные (по id)
        existing_ids = {c.id for c in candidates}
        for c in moscow_candidates:
            if c.id not in existing_ids:
                candidates.append(c)
                fallback_used = True

    # 3. Глобальный fallback — любые компании этой специальности
    if len(candidates) < count:
        all_candidates = find_companies(None)
        existing_ids = {c.id for c in candidates}
        for c in all_candidates:
            if c.id not in existing_ids:
                candidates.append(c)
                fallback_used = True

    if not candidates:
        return [], fallback_used

    # Перемешиваем и берём count первых уникальных
    rng.shuffle(candidates)
    picked = candidates[:count]

    return picked, fallback_used


def _pick_title_for_level(
    specialty: Specialty,
    level: int,
    session: Session,
    rng: random.Random,
) -> Optional[str]:
    """
    Достаёт title_ru должности из career_track для заданной (specialty, level).
    Если на этом уровне нет (теоретически в seed на каждой specialty есть всё —
    1, 2, 3, 4) — пытается соседние уровни.
    """
    stmt = (
        select(CareerTrack)
        .where(
            CareerTrack.is_active == True,  # noqa: E712
            CareerTrack.specialty_id == specialty.id,
            CareerTrack.level == level,
        )
    )
    candidates = list(session.exec(stmt).all())
    if candidates:
        return rng.choice(candidates).title_ru

    # Соседние уровни — попробуем level-1, потом level+1
    for fallback_level in (level - 1, level + 1, 1, 2, 3, 4):
        if fallback_level < 1 or fallback_level > 4:
            continue
        stmt = (
            select(CareerTrack)
            .where(
                CareerTrack.is_active == True,  # noqa: E712
                CareerTrack.specialty_id == specialty.id,
                CareerTrack.level == fallback_level,
            )
        )
        candidates = list(session.exec(stmt).all())
        if candidates:
            log.warning(
                "work_history generator: no career_track for specialty=%s level=%d, "
                "fell back to level=%d",
                specialty.code, level, fallback_level,
            )
            return rng.choice(candidates).title_ru

    return None


# ============================================================================
# === Date formatting ===
# ============================================================================

def _format_period_start(d: date) -> str:
    """date(2022, 9, 15) → 'Сентябрь 2022'."""
    return f"{RU_MONTHS[d.month - 1]} {d.year}"


def _format_period_end(d: Optional[date]) -> str:
    """date → 'Август 2025'. None → 'по настоящее время'."""
    if d is None:
        return "по настоящее время"
    return f"{RU_MONTHS[d.month - 1]} {d.year}"


def _years_to_days(years: float) -> int:
    return int(years * 365.25)


# ============================================================================
# === Main entry point ===
# ============================================================================

def _pick_count(rng: random.Random) -> int:
    """Выбирает количество записей по распределению COUNT_DISTRIBUTION."""
    counts, weights = zip(*COUNT_DISTRIBUTION)
    return rng.choices(counts, weights=weights, k=1)[0]


def _pick_levels(count: int, rng: random.Random) -> list[int]:
    """Выбирает уровни должностей для count записей."""
    options = LEVELS_BY_COUNT.get(count, [[3]])
    return rng.choice(options)


def suggest_work_history(
    applicant: Applicant,
    session: Session,
    rng: Optional[random.Random] = None,
    today: Optional[date] = None,
) -> Optional[WorkHistorySuggestion]:
    """
    Главная точка входа: возвращает WorkHistorySuggestion для applicant'а
    с массивом 1-3 записей трудового стажа.

    Параметры:
      - applicant: Applicant модель (должны быть прочитаны .education,
        .work_history, .applications)
      - session: SQLModel session для запросов в legend_company / career_track / specialty
      - rng: random.Random для тестируемости (по умолчанию свежий)
      - today: date для тестируемости (по умолчанию date.today())

    Возвращает None если:
      - не удалось определить специальность (даже DEFAULT_FALLBACK_SPECIALTY_CODE
        не нашёлся в БД — это сигнал что Pack 19.0 не применён)
      - не удалось найти ни одной компании
      - не удалось найти должность в career_track
    """
    if rng is None:
        rng = random.Random()
    if today is None:
        today = date.today()

    # 1. Specialty
    specialty, matched_pattern = _resolve_specialty(applicant, session)
    if specialty is None:
        log.warning(
            "work_history generator: no specialty resolved (applicant_id=%s) — "
            "Pack 19.0 (specialty seed) might not be applied",
            applicant.id,
        )
        return None

    # 2. Region
    region_code = _get_region_code(applicant)

    # 3. Count + levels
    count = _pick_count(rng)
    levels = _pick_levels(count, rng)
    # levels отсортированы: первый — старший level (новейшая работа),
    # последний — младший (самая ранняя). Длина levels == count.

    # 4. Companies (count штук, без повторов в одной легенде)
    companies, fallback_used = _pick_companies_for_track(
        region_code, specialty, count, session, rng,
    )
    if not companies:
        log.warning(
            "work_history generator: no companies for region=%s specialty=%s "
            "(applicant_id=%s)",
            region_code, specialty.code, applicant.id,
        )
        return None

    # Если из-за fallback'ов не хватило компаний для count — уменьшаем count
    actual_count = min(count, len(companies))
    if actual_count < count:
        log.warning(
            "work_history generator: requested %d companies but only %d available, "
            "trimming legend (applicant_id=%s)",
            count, actual_count, applicant.id,
        )
        levels = levels[:actual_count]

    # 5. Titles для каждой записи
    titles: list[str] = []
    for level in levels:
        title = _pick_title_for_level(specialty, level, session, rng)
        if title is None:
            log.warning(
                "work_history generator: no title for specialty=%s level=%d "
                "(applicant_id=%s)",
                specialty.code, level, applicant.id,
            )
            return None
        titles.append(title)

    # 6. Даты — генерируем в обратном порядке от today
    # records[0] = самая новая, records[-1] = самая старая
    records: list[WorkRecordSuggestion] = []

    # Запись 0: текущая работа (end=NULL, start = today - 3.5..5 лет)
    last_job_years = rng.uniform(*LAST_JOB_YEARS_RANGE)
    rec0_start = today - timedelta(days=_years_to_days(last_job_years))
    rec0_end: Optional[date] = None
    records.append(WorkRecordSuggestion(
        period_start=_format_period_start(rec0_start),
        period_end=_format_period_end(rec0_end),
        company=companies[0].name_full,
        position=titles[0],
        duties=[],  # Pack 19.1a: пустой массив, заполнится в 19.1b
    ))

    # Запись 1: предыдущая работа (если actual_count >= 2)
    prev_period_start = rec0_start
    if actual_count >= 2:
        gap_days = rng.randint(*GAP_MONTHS_RANGE) * 30
        rec1_end = prev_period_start - timedelta(days=gap_days + 1)
        prev_years = rng.uniform(*PREV_JOB_YEARS_RANGE_MIDDLE)
        rec1_start = rec1_end - timedelta(days=_years_to_days(prev_years))
        records.append(WorkRecordSuggestion(
            period_start=_format_period_start(rec1_start),
            period_end=_format_period_end(rec1_end),
            company=companies[1].name_full,
            position=titles[1],
            duties=[],
        ))
        prev_period_start = rec1_start

    # Запись 2: самая ранняя работа (если actual_count == 3)
    if actual_count >= 3:
        gap_days = rng.randint(*GAP_MONTHS_RANGE) * 30
        rec2_end = prev_period_start - timedelta(days=gap_days + 1)
        prev_years = rng.uniform(*PREV_JOB_YEARS_RANGE_EARLY)
        rec2_start = rec2_end - timedelta(days=_years_to_days(prev_years))
        records.append(WorkRecordSuggestion(
            period_start=_format_period_start(rec2_start),
            period_end=_format_period_end(rec2_end),
            company=companies[2].name_full,
            position=titles[2],
            duties=[],
        ))

    log.info(
        "work_history generator: applicant_id=%s region=%s specialty=%s → "
        "%d records (fallback=%s, pattern=%r)",
        applicant.id, region_code, specialty.code,
        len(records), fallback_used, matched_pattern,
    )

    specialty_text = f"{specialty.code} {specialty.name}"
    return WorkHistorySuggestion(
        records=records,
        fallback_used=fallback_used,
        specialty_used=specialty_text,
        matched_pattern=matched_pattern,
    )
