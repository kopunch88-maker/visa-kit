"""
Pack 19.1 — генератор work_history для applicant'а.

Pack 20.3 (05.05.2026): добавлено заполнение `duties` снапшотом из Position.

Алгоритм:
  1. Резолвим specialty (как Pack 19.0.2 fallback chain — без изменений)
  2. Решаем количество job'ов (1/2/3) и уровни (как Pack 19.1a — без изменений)
  3. Для каждого job — находим Position по (primary_specialty_id, level)
     - Если есть → берём title_ru + duties (СНАПШОТ копией)
     - Если нет → fallback на CareerTrack для title (duties=[] как раньше)
  4. Подбираем компанию из LegendCompany (без изменений)

Tie-breaker для дубликатов уровня (например 08.03.01 L2 имеет id=13
"Инженер-проектировщик II категории" + id=2 "инженер-геодезист (камеральщик)"):
  - Сортируем кандидаты по `salary_rub_default DESC`. Это даёт preference
    более актуальным/лучше оплачиваемым позициям (наши новые Pack 20.2 имеют
    более высокие зарплаты чем старые legacy позиции типа геодезиста)
  - Если salary одинаковая — берём первого по id ASC

Без обращений к LLM — чисто детерминированный алгоритм с rng.

Ссылки:
  - applicant.inn_kladr_code → регион (первые 2 цифры)
  - applicant.education[-1].specialty → специальность (если уже сгенерирована)
  - applicant.work_history[0].position → специальность (fallback)
  - application.position.title_ru → специальность (Pack 19.0.2 fallback)

Если для региона нет компаний → fallback на Москву (FALLBACK_REGION_CODE='77').
Если специальность не определилась — generic '38.03.02 Менеджмент'.

Минимум 3.5 года в последней работе — для DN-визы нужно ≥3 года стажа.
"""
from __future__ import annotations
import re

import logging
import random
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import Applicant, Position
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

# Pack 34.8: для одиночек (подача без семьи) запрещаем Senior (3) и Lead (4).
# Бизнес-правило: «без семьи в CV не может быть Главный/Ведущий».
# Используется когда applicant.applications не содержит family_members.
LEVELS_BY_COUNT_SOLO: dict[int, list[list[int]]] = {
    1: [[2]],                         # Middle на единственной записи
    2: [[2, 1]],                      # Middle + Junior
    3: [[2, 1, 1]],                   # Middle + Junior + Junior
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
    """
    work = applicant.work_history or []
    if work:
        first = work[0]
        if isinstance(first, dict):
            position = (first.get("position") or "").strip()
        else:
            position = (getattr(first, "position", "") or "").strip()
        if position:
            return position

    try:
        from datetime import datetime
        apps = list(applicant.applications or [])
        active_apps = [a for a in apps if not getattr(a, "is_archived", False)]
        active_apps.sort(
            key=lambda a: a.created_at or datetime.min,
            reverse=True,
        )
        for app in active_apps:
            if app.position_id is None:
                continue
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
    education = applicant.education or []
    if not education:
        return None, None

    for idx in range(len(education) - 1, -1, -1):
        edu = education[idx]
        if isinstance(edu, dict):
            spec_text = (edu.get("specialty") or "").strip()
        else:
            spec_text = (getattr(edu, "specialty", "") or "").strip()

        if not spec_text:
            continue

        parts = spec_text.split(maxsplit=1)
        if not parts:
            continue
        code_candidate = parts[0]

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
    if not position:
        return None, None

    position_lower = position.lower()

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
    spec, pattern = _match_specialty_by_education(applicant, session)
    if spec:
        return spec, pattern

    position = _get_position_for_matching(applicant, session)
    spec, pattern = _match_specialty_by_position(position, session)
    if spec:
        log.info(
            "work_history generator: specialty by position %r → %s %s (pattern=%r)",
            position, spec.code, spec.name, pattern,
        )
        return spec, pattern

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
# === Picking companies ===
# ============================================================================

def _pick_companies_for_track(
    region_code: Optional[str],
    specialty: Specialty,
    count: int,
    session: Session,
    rng: random.Random,
) -> tuple[list[LegendCompany], bool]:
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

    candidates: list[LegendCompany] = []
    if region_code:
        candidates = find_companies(region_code)

    if len(candidates) < count and region_code != FALLBACK_REGION_CODE:
        moscow_candidates = find_companies(FALLBACK_REGION_CODE)
        existing_ids = {c.id for c in candidates}
        for c in moscow_candidates:
            if c.id not in existing_ids:
                candidates.append(c)
                fallback_used = True

    if len(candidates) < count:
        all_candidates = find_companies(None)
        existing_ids = {c.id for c in candidates}
        for c in all_candidates:
            if c.id not in existing_ids:
                candidates.append(c)
                fallback_used = True

    if not candidates:
        return [], fallback_used

    rng.shuffle(candidates)
    picked = candidates[:count]

    return picked, fallback_used


# ============================================================================
# === Picking title + duties (Pack 20.3 / Pack 61: alignment with current position hint) ===
# ============================================================================

# Pack 61: токены, отбрасываемые при токенизации hint и кандидатов.
# Это служебные слова, грейды и общие профессиональные термины, которые
# создают ложные пересечения (например «специалист»/«инженер»/«менеджер»
# встречаются почти в каждом title).
# Стопы применяются ДО стемминга. Длинные слова можно перечислять
# в нескольких падежных формах для надёжности — стемминг сделает то же,
# но прямой матч короче.
_HINT_STOP_WORDS = frozenset({
    # служебные
    "и", "в", "на", "с", "со", "о", "об", "по", "для", "при", "от", "до",
    "из", "под", "над", "за", "к", "у", "не", "ни", "же", "ли", "бы", "или",
    # обобщающие профессиональные (одной формы достаточно: длинные стемятся
    # одинаково, фильтр сработает уже после, но прямой матч экономит цикл).
    "специалист", "специалиста",
    "инженер", "инженера",
    "менеджер", "менеджера",
    "руководитель", "руководителя",
    "сотрудник", "сотрудника",
    "работник", "работника",
    "консультант", "консультанта",
    # грейды
    "ведущий", "ведущего",
    "главный", "главного",
    "старший", "старшего",
    "младший", "младшего",
    "помощник", "помощника",
    "i", "ii", "iii", "iv",
    "категории", "категория", "уровня", "уровень",
    # общие "процессные"
    "работы", "работа", "работ",
    "отдела", "отдел",
    "группы", "группа",
    "проекта", "проекту", "проектами", "проектов", "проектная", "проекты",
})


# Pack 61: длина стема для нормализации морфологии русского.
# Берём первые _STEM_LEN символов токена (длина >= _STEM_LEN). Короткие
# токены (BIM, SQL, ГИП, ОКЗ) оставляем как есть. Это лёгкий fallback вместо
# pymorphy3 — достаточно для alignment внутри одной специальности.
_STEM_LEN = 5


def _stem(tok: str) -> str:
    return tok[:_STEM_LEN] if len(tok) > _STEM_LEN else tok


def _tokenize_hint(text: str) -> frozenset[str]:
    """
    Pack 61: разбивает строку должности в множество значимых СТЕМОВ.

    - lower-case;
    - сплит по non-alphanumeric (пробелы, дефисы, скобки, точки, слэш);
    - длина токена >= 3;
    - не входит в _HINT_STOP_WORDS (стопы проверяются ДО стемминга, чтобы
      «специалист»/«проектами»/«категории» не превратились в значимые стемы);
    - не чисто цифровой;
    - после фильтрации — стем (token[:5]). Это сводит падежные формы к
      одной канонической: «строительными»/«строительные» → «строи»,
      «управлению»/«управление» → «управ», «цифровому»/«цифровое» → «цифро».

    Возвращает frozenset для дешёвого пересечения.
    """
    if not text:
        return frozenset()
    s = text.lower()
    # Заменяем не-alphanumeric (учитывая кириллицу) на пробел.
    buf = []
    for ch in s:
        if ch.isalnum():
            buf.append(ch)
        else:
            buf.append(" ")
    raw_tokens = "".join(buf).split()
    out = set()
    for tok in raw_tokens:
        if len(tok) < 3:
            continue
        if tok in _HINT_STOP_WORDS:
            continue
        if tok.isdigit():
            continue
        out.add(_stem(tok))
    return frozenset(out)


# Pack 61: узкоспециализированные ключевые слова — де-приоритезируем такие
# Position только когда hint их НЕ содержит. Если у клиента в договоре стоит
# «инженер-геодезист» — токен «геодезист» окажется в hint_tokens и геодезист
# попадёт в strong/weak pool вместо специфического fallback.
_NARROW_SPECIFIC_KEYWORDS = (
    "геодезист", "геодезия", "камеральщик", "топограф",
    "сметчик", "крановщик",
)


def _pick_position_for_level(
    specialty: Specialty,
    level: int,
    session: Session,
    rng: random.Random,
    hint_tokens: Optional[frozenset[str]] = None,  # Pack 61
) -> Optional[Position]:
    """
    Pack 20.3 + Pack 61: ищет Position в справочнике по (specialty_id, level)
    с alignment по текущей должности заявителя.

    Алгоритм выбора (Pack 61):
      1. Собираем всех активных Position для (specialty_id, level).
      2. Если hint_tokens непустой — скорим каждого кандидата как
            score = |hint_tokens ∩ tokens(title_ru | tags | profile_description[:240])|
         и делим на strong (>=2) / weak (=1) / neutral (=0). Берём первую
         непустую группу.
      3. Если hint_tokens пустой ИЛИ pool вышел neutral
         (ничего не совпало) — применяем старый де-приоритет
         узкоспециализированных позиций (геодезия/сметы/камералка):
         generic кандидаты в pool, иначе specific.
         Старая семантика сохранена для backward compatibility.
      4. Внутри финального pool — сорт по len(duties) DESC, rng.choice
         среди тех, у кого duties максимально.

    Возвращает None если для (specialty, level) нет ни одной активной Position.
    """
    stmt = (
        select(Position)
        .where(
            Position.is_active == True,  # noqa: E712
            Position.primary_specialty_id == specialty.id,
            Position.level == level,
        )
    )
    candidates = list(session.exec(stmt).all())
    if not candidates:
        return None

    # ── Pack 61: alignment with current position hint ────────────────────────
    def _candidate_tokens(p: Position) -> frozenset[str]:
        parts: list[str] = []
        if p.title_ru:
            parts.append(p.title_ru)
        for t in (p.tags or []):
            parts.append(str(t))
        if p.profile_description:
            parts.append(p.profile_description[:240])
        return _tokenize_hint(" ".join(parts))

    pool: list[Position]
    used_hint = False
    if hint_tokens:
        scored = [(p, len(hint_tokens & _candidate_tokens(p))) for p in candidates]
        # Pack 61.2: rank inside bucket by score
        score_by_id = {p.id: s for p, s in scored}
        strong = [p for p, s in scored if s >= 2]
        weak = [p for p, s in scored if s == 1]
        if strong:
            pool = strong
            used_hint = True
            log.info(
                "work_history generator [Pack 61]: aligned by hint (strong, "
                "%d candidates) specialty=%s level=%d",
                len(strong), specialty.code, level,
            )
        elif weak:
            pool = weak
            used_hint = True
            log.info(
                "work_history generator [Pack 61]: aligned by hint (weak, "
                "%d candidates) specialty=%s level=%d",
                len(weak), specialty.code, level,
            )
        else:
            pool = list(candidates)
            log.info(
                "work_history generator [Pack 61]: no hint alignment "
                "(all neutral) specialty=%s level=%d — falling back to "
                "narrow-specific de-prioritization",
                specialty.code, level,
            )
    else:
        pool = list(candidates)
        score_by_id = {}  # Pack 61.2

    # ── Старый де-приоритет узкоспециализированных Position ──────────────────
    # Применяется только когда hint не помог (или его не было) —
    # обратная совместимость с поведением до Pack 61.
    if not used_hint:
        def _is_narrow_specific(p: Position) -> bool:
            t = (p.title_ru or "").lower()
            tags_l = [str(x).lower() for x in (p.tags or [])]
            for kw in _NARROW_SPECIFIC_KEYWORDS:
                if kw in t:
                    return True
                for tag in tags_l:
                    if kw in tag:
                        return True
            return False

        generic = [p for p in pool if not _is_narrow_specific(p)]
        specific = [p for p in pool if _is_narrow_specific(p)]
        pool = generic if generic else specific

    # ── Финальный пик: max duties, rng.choice среди top ──────────────────────
    # Pack 61.2: rank by score (primary) then duties (secondary)
    pool.sort(key=lambda p: (-score_by_id.get(p.id, 0), -len(p.duties or [])))
    top_score = score_by_id.get(pool[0].id, 0)
    top_duties = len(pool[0].duties or [])
    top_candidates = [
        p for p in pool
        if score_by_id.get(p.id, 0) == top_score
        and len(p.duties or []) == top_duties
    ]

    return rng.choice(top_candidates)



def _pick_title_and_duties_for_level(
    specialty: Specialty,
    level: int,
    session: Session,
    rng: random.Random,
    hint_tokens: Optional[frozenset[str]] = None,  # Pack 61
) -> tuple[Optional[str], list[str]]:
    """
    Pack 20.3 + Pack 61: возвращает (title_ru, duties[]) для записи work_history.

    Алгоритм:
      1. Position лучше всего — берём title + duties снапшотом
      2. Position для соседних уровней (level-1, level+1) — если на точном уровне нет
      3. CareerTrack fallback — если нигде нет Position (для специальностей без Pack 20.2 разметки)
      4. Если совсем ничего — возвращаем (None, [])

    Pack 61: при наличии hint_tokens пробрасывает их в _pick_position_for_level
    на каждом шаге Position-фоллбэков (career_track-фоллбэки hint не учитывают,
    у них тоже нет tags/description).
    """
    # 1. Точное совпадение (specialty, level)
    pos = _pick_position_for_level(specialty, level, session, rng, hint_tokens=hint_tokens)
    if pos:
        log.info(
            "work_history generator: matched Position id=%s '%s' "
            "for specialty=%s level=%d (%d duties)",
            pos.id, pos.title_ru, specialty.code, level, len(pos.duties or []),
        )
        return pos.title_ru, list(pos.duties or [])

    # 2. Соседние уровни в Position — попробуем level-1, потом level+1
    for fallback_level in (level - 1, level + 1, 1, 2, 3, 4):
        if fallback_level < 1 or fallback_level > 4 or fallback_level == level:
            continue
        pos = _pick_position_for_level(specialty, fallback_level, session, rng, hint_tokens=hint_tokens)
        if pos:
            log.warning(
                "work_history generator: no Position for specialty=%s level=%d, "
                "fell back to Position id=%s level=%d ('%s', %d duties)",
                specialty.code, level, pos.id, fallback_level,
                pos.title_ru, len(pos.duties or []),
            )
            return pos.title_ru, list(pos.duties or [])

    # 3. CareerTrack fallback — на случай если Pack 20.2 не покрыл специальность
    log.warning(
        "work_history generator: no Position for specialty=%s — falling back "
        "to CareerTrack (no duties)",
        specialty.code,
    )
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
        return rng.choice(candidates).title_ru, []

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
                "fell back to level=%d (no duties)",
                specialty.code, level, fallback_level,
            )
            return rng.choice(candidates).title_ru, []

    return None, []


# ============================================================================
# === Date formatting ===
# ============================================================================

def _format_period_start(d: date) -> str:
    return f"{RU_MONTHS[d.month - 1]} {d.year}"


def _format_period_end(d: Optional[date]) -> str:
    if d is None:
        return "по настоящее время"
    return f"{RU_MONTHS[d.month - 1]} {d.year}"


def _years_to_days(years: float) -> int:
    return int(years * 365.25)


# ============================================================================
# === Main entry point ===
# ============================================================================

def _is_solo_applicant(applicant: Applicant) -> bool:
    """
    Pack 34.8: True если клиент подаётся в одиночку (нет members семьи)
    ни в одной из активных заявок.

    Активная заявка = не архивная, не удалённая. Если хотя бы одна заявка
    содержит family_members — клиент НЕ одиночка, возвращаем False.

    Если у applicant нет ни одной заявки — считаем одиночкой (default True).
    Это самый безопасный default: не выдадим «Главного инженера» там, где
    мы ещё не знаем что подача семейная.

    Защищается от исключений (по аналогии с _get_position_for_matching).
    """
    try:
        apps = list(applicant.applications or [])
    except Exception as e:
        log.warning(
            "_is_solo_applicant: error reading applications "
            "(applicant_id=%s): %r — defaulting to solo=True",
            applicant.id, e,
        )
        return True

    active_apps = [
        a for a in apps
        if not getattr(a, "is_archived", False)
        and not getattr(a, "deleted_at", None)
    ]
    if not active_apps:
        return True

    for app in active_apps:
        try:
            members = list(app.family_members or [])
        except Exception:
            members = []
        if members:
            log.info(
                "_is_solo_applicant: applicant_id=%s has family in application_id=%s "
                "(%d members) → not solo",
                applicant.id, app.id, len(members),
            )
            return False

    return True


def _pick_count(rng: random.Random) -> int:
    counts, weights = zip(*COUNT_DISTRIBUTION)
    return rng.choices(counts, weights=weights, k=1)[0]


def _pick_levels(count: int, rng: random.Random, is_solo: bool = False) -> list[int]:
    """
    Pack 34.8: при is_solo=True использует LEVELS_BY_COUNT_SOLO (только
    Junior/Middle), иначе LEVELS_BY_COUNT (Senior/Lead разрешены).
    """
    if is_solo:
        options = LEVELS_BY_COUNT_SOLO.get(count, [[2]])
    else:
        options = LEVELS_BY_COUNT.get(count, [[3]])
    return rng.choice(options)


# ============================================================================
# === Pack 64: stretch earliest record to fill education gap ===
# ============================================================================

# Допустимый gap между окончанием вуза и первой работой (в годах).
# Стандартный сценарий «учился, потом год искал работу» — gap=1.
MAX_GAP_FROM_EDUCATION_YEARS = 2

# Максимальная длительность самой ранней записи (в годах) при растягивании.
# Длиннее — выглядит подозрительно (вечный junior 10+ лет в одной компании).
MAX_EARLIEST_RECORD_LENGTH_YEARS = 8.0



# ============================================================================
# === Pack 75: junior stretch cap ===
# ============================================================================

# Максимальная длительность самой ранней записи если она Junior-грейда.
# Junior-роль (стажёр, помощник, младший специалист) в отрасли длится 1–3 года,
# 8 лет в одной юниорской позиции читается инспектором UGE как ложь.
MAX_JUNIOR_STRETCH_YEARS = 3.0

# Паттерн для распознавания Junior-грейда по названию должности или первой
# фразе обязанностей. Case-insensitive. Русская морфология покрыта корнями.
_JUNIOR_TITLE_PATTERN = re.compile(
    r"\b(?:junior|jr\.?|"
    r"младш|стажёр|стажер|помощ|ассистент|начинающ|"
    r"участи|под\s+руководств|под\s+супервизи)",
    re.IGNORECASE,
)


def _is_junior_record(record) -> bool:
    """Pack 75: True если запись Junior-грейда.

    Проверяет title и duties[0] на regex-паттерн. Field names безопасны через
    getattr — совместимо со всеми ревизиями WorkRecordSuggestion.
    """
    title = getattr(record, "title", None) or getattr(record, "position_title", None) or ""
    if _JUNIOR_TITLE_PATTERN.search(str(title)):
        return True
    duties = getattr(record, "duties", None) or []
    if duties and _JUNIOR_TITLE_PATTERN.search(str(duties[0])):
        return True
    return False



# ============================================================================
# === Pack 69: minimum work start age clamp ===
# ============================================================================

# Минимальный возраст начала трудового стажа в годах. Все записи work_history
# с period_start раньше чем applicant.birth_date + MIN_WORK_START_AGE_YEARS
# обрезаются или удаляются. Применяется после Pack 64 как страховка от
# «начал работать в 15 лет» — частый артефакт растягивания (Pack 64 без bound
# по birth_date) или generic count=3 на молодом заявителе (3.5+1.5+1.5 ≈ 6.5 лет
# вспять от today: для 22-летнего → старт в 15-16).
MIN_WORK_START_AGE_YEARS = 18


def _parse_ru_period_label(label):
    """'Январь 2020' → date(2020, 1, 1). None если не распарсилось."""
    if not label:
        return None
    parts = str(label).strip().split()
    if len(parts) != 2:
        return None
    month_ru, year_str = parts
    try:
        month_idx = RU_MONTHS.index(month_ru)
    except ValueError:
        return None
    try:
        return date(int(year_str), month_idx + 1, 1)
    except (ValueError, TypeError):
        return None


def _extract_education_end_year(applicant):
    """Берёт max graduation_year из applicant.education (если есть)."""
    edu = getattr(applicant, "education", None) or []
    years = []
    for e in edu:
        if isinstance(e, dict):
            y = e.get("graduation_year")
        else:
            y = getattr(e, "graduation_year", None)
        try:
            years.append(int(y))
        except (TypeError, ValueError):
            continue
    return max(years) if years else None


def _stretch_earliest_record_for_education_gap(records, applicant):
    """Pack 64: растягивает самую раннюю запись назад чтобы закрыть gap до диплома.

    Если applicant.education содержит graduation_year и gap между earliest.start
    и (graduation_year + 1) > MAX_GAP_FROM_EDUCATION_YEARS — двигаем
    earliest.period_start назад, но не дальше чем (graduation_year + 1) И не так,
    чтобы общая длительность записи превысила MAX_EARLIEST_RECORD_LENGTH_YEARS.

    Срабатывает только при len(records) >= 2 — чтобы не двигать единственную
    запись (она будет переписана work_history_sync.py на DN-работодателя).
    """
    if len(records) < 2:
        return
    edu_year = _extract_education_end_year(applicant)
    if not edu_year:
        return

    earliest = records[-1]  # records сортированы от новых к старым
    start_date = _parse_ru_period_label(earliest.period_start)
    if start_date is None:
        return
    end_label = earliest.period_end
    if not end_label or "настоящее" in str(end_label).lower():
        end_date = date.today()
    else:
        end_date = _parse_ru_period_label(end_label)
        if end_date is None:
            return

    target_start_year = edu_year + 1  # +1 год на поиск работы после диплома
    # Pack 69: не уходим раньше чем applicant исполнилось MIN_WORK_START_AGE_YEARS.
    # Защита от диплома, выданного несовершеннолетнему (вунд/экстернат/опечатка).
    birth = getattr(applicant, "birth_date", None)
    if birth is not None:
        min_year_by_age = birth.year + MIN_WORK_START_AGE_YEARS
        if min_year_by_age > target_start_year:
            target_start_year = min_year_by_age
    gap_years = start_date.year - target_start_year
    if gap_years <= MAX_GAP_FROM_EDUCATION_YEARS:
        return  # gap приемлемый, ничего не делаем

    # Сколько максимум можем растянуть назад
    current_length_days = (end_date - start_date).days
    # Pack 75: cap ниже если earliest — Junior-грейд
    if _is_junior_record(earliest):
        max_length_years = MAX_JUNIOR_STRETCH_YEARS
    else:
        max_length_years = MAX_EARLIEST_RECORD_LENGTH_YEARS
    max_total_length_days = int(max_length_years * 365.25)
    max_extension_days = max(0, max_total_length_days - current_length_days)
    if max_extension_days <= 0:
        return

    # Желаемое смещение — до target_start_year (того же месяца, что у start_date)
    try:
        target_start_date = date(target_start_year, start_date.month, 1)
    except ValueError:
        return
    desired_extension_days = (start_date - target_start_date).days
    extension_days = min(desired_extension_days, max_extension_days)
    if extension_days <= 0:
        return

    new_start_date = start_date - timedelta(days=extension_days)
    old_label = earliest.period_start
    earliest.period_start = _format_period_start(new_start_date)
    log.info(
        "work_history generator [Pack 64]: stretched earliest record "
        "from %r to %r (edu_year=%d, gap was %d years, extension %.1f years)",
        old_label, earliest.period_start, edu_year, gap_years,
        extension_days / 365.25,
    )


def _clamp_records_to_min_work_age(records, applicant):
    """Pack 69: обрезает части records, попадающие в возраст < MIN_WORK_START_AGE_YEARS.

    Применяется как финальный пост-пасс после Pack 64. Гарантирует что
    period_start ни одной записи не раньше чем applicant.birth_date + 18 лет.

    Поведение:
      - applicant.birth_date is None → no-op (возврат исходного списка).
      - Запись целиком >= min_start → без изменений.
      - Запись пересекает min_start → period_start = min_start.
      - Запись целиком до min_start → дропается.

    Edge-case 29 февраля: birth_date = 29.02.YYYY → min_start = 28.02.(YYYY+18)
    в невисокосный год (стандартная legal-возрастная конвенция).

    Возвращает новый список (может быть короче входа). Сами WorkRecordSuggestion
    мутируются in-place (для consistency с Pack 64).
    """
    birth = getattr(applicant, "birth_date", None)
    if birth is None:
        return records

    try:
        min_start = date(
            birth.year + MIN_WORK_START_AGE_YEARS,
            birth.month,
            birth.day,
        )
    except ValueError:
        # 29 февраля високосного → в невисокосном году берём 28 февраля
        min_start = date(
            birth.year + MIN_WORK_START_AGE_YEARS,
            birth.month,
            28,
        )

    out = []
    dropped = 0
    clipped = 0
    for rec in records:
        start_date_rec = _parse_ru_period_label(rec.period_start)
        if start_date_rec is None:
            # Метку не распарсили — оставляем без изменений (страховка)
            out.append(rec)
            continue

        end_label = rec.period_end
        if not end_label or "настоящее" in str(end_label).lower():
            end_date_rec = date.today()
        else:
            end_date_parsed = _parse_ru_period_label(end_label)
            if end_date_parsed is None:
                out.append(rec)
                continue
            end_date_rec = end_date_parsed

        if start_date_rec >= min_start:
            out.append(rec)
            continue

        if end_date_rec > min_start:
            rec.period_start = _format_period_start(min_start)
            out.append(rec)
            clipped += 1
            continue

        # Запись целиком до min_start — дропаем
        dropped += 1

    if dropped or clipped:
        log.info(
            "work_history generator [Pack 69]: MIN_WORK_START_AGE=%d "
            "(applicant_id=%s, birth=%r, min_start=%r): "
            "clipped=%d, dropped=%d",
            MIN_WORK_START_AGE_YEARS, getattr(applicant, "id", None),
            birth, min_start, clipped, dropped,
        )

    if not out:
        log.warning(
            "work_history generator [Pack 69]: all records dropped "
            "(applicant_id=%s) — applicant too young for any work history. "
            "DN sync will inject the current job as the only record.",
            getattr(applicant, "id", None),
        )

    return out


def suggest_work_history(
    applicant: Applicant,
    session: Session,
    rng: Optional[random.Random] = None,
    today: Optional[date] = None,
) -> Optional[WorkHistorySuggestion]:
    """
    Главная точка входа: возвращает WorkHistorySuggestion для applicant'а
    с массивом 1-3 записей трудового стажа.

    Pack 20.3: каждая запись теперь содержит duties[] — снапшот из Position.duties.
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
    # Pack 34.8: для одиночек (нет family_members) используем только Junior/Middle.
    is_solo = _is_solo_applicant(applicant)
    count = _pick_count(rng)
    levels = _pick_levels(count, rng, is_solo=is_solo)
    if is_solo:
        log.info(
            "work_history generator: applicant_id=%s is solo → Junior/Middle only",
            applicant.id,
        )

    # 4. Companies
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

    actual_count = min(count, len(companies))
    if actual_count < count:
        log.warning(
            "work_history generator: requested %d companies but only %d available, "
            "trimming legend (applicant_id=%s)",
            count, actual_count, applicant.id,
        )
        levels = levels[:actual_count]

    # 5. Pack 20.3 + Pack 61 + Pack 61.1: extended hint resolution
    #    с alignment по текущей должности заявителя.
    #    Pack 61.1: extended hint resolution — конкатенируем title_ru +
    #    tags + profile_description из реального Position объекта,
    #    если он резолвится через application.position_id.
    current_position_hint = _get_position_for_matching(applicant, session)
    hint_source = "title_only"  # для логов
    hint_text = current_position_hint or ""

    # Пытаемся найти Position объект, чтобы расширить hint
    try:
        from datetime import datetime as _dt
        _apps = list(applicant.applications or [])
        _active = [a for a in _apps if not getattr(a, "is_archived", False)]
        _active.sort(key=lambda a: a.created_at or _dt.min, reverse=True)
        for _app in _active:
            if _app.position_id is None:
                continue
            _pos = session.get(Position, _app.position_id)
            if _pos is None:
                continue
            _parts = []
            if _pos.title_ru:
                _parts.append(_pos.title_ru)
            for _t in (_pos.tags or []):
                _parts.append(str(_t))
            if _pos.profile_description:
                _parts.append(_pos.profile_description[:400])
            if _parts:
                hint_text = " ".join(_parts)
                hint_source = (
                    f"position_id={_pos.id} (title+{len(_pos.tags or [])} tags"
                    f"+profile_desc)"
                )
                break
    except Exception as _e:
        log.warning(
            "work_history generator [Pack 61.1]: error expanding hint "
            "(applicant_id=%s): %r — falling back to title-only",
            applicant.id, _e,
        )

    hint_tokens = _tokenize_hint(hint_text) if hint_text else None
    if hint_tokens:
        log.info(
            "work_history generator [Pack 61 / 61.1]: hint source=%s → tokens=%s "
            "(applicant_id=%s)",
            hint_source, sorted(hint_tokens), applicant.id,
        )
    else:
        log.info(
            "work_history generator [Pack 61]: no hint tokens (source=%s, "
            "position=%r) — alignment disabled, falling back to legacy pick "
            "(applicant_id=%s)",
            hint_source, current_position_hint, applicant.id,
        )

    titles_and_duties: list[tuple[str, list[str]]] = []
    for level in levels:
        title, duties = _pick_title_and_duties_for_level(
            specialty, level, session, rng, hint_tokens=hint_tokens,
        )
        if title is None:
            log.warning(
                "work_history generator: no title for specialty=%s level=%d "
                "(applicant_id=%s)",
                specialty.code, level, applicant.id,
            )
            return None
        titles_and_duties.append((title, duties))

    # 6. Даты — генерируем в обратном порядке от today
    records: list[WorkRecordSuggestion] = []

    # Запись 0: текущая работа (end=NULL, start = today - 3.5..5 лет)
    last_job_years = rng.uniform(*LAST_JOB_YEARS_RANGE)
    rec0_start = today - timedelta(days=_years_to_days(last_job_years))
    rec0_end: Optional[date] = None
    title0, duties0 = titles_and_duties[0]
    records.append(WorkRecordSuggestion(
        period_start=_format_period_start(rec0_start),
        period_end=_format_period_end(rec0_end),
        company=companies[0].name_full,
        position=title0,
        duties=duties0,  # Pack 20.3: снапшот из Position
    ))

    prev_period_start = rec0_start
    if actual_count >= 2:
        gap_days = rng.randint(*GAP_MONTHS_RANGE) * 30
        rec1_end = prev_period_start - timedelta(days=gap_days + 1)
        prev_years = rng.uniform(*PREV_JOB_YEARS_RANGE_MIDDLE)
        rec1_start = rec1_end - timedelta(days=_years_to_days(prev_years))
        title1, duties1 = titles_and_duties[1]
        records.append(WorkRecordSuggestion(
            period_start=_format_period_start(rec1_start),
            period_end=_format_period_end(rec1_end),
            company=companies[1].name_full,
            position=title1,
            duties=duties1,  # Pack 20.3
        ))
        prev_period_start = rec1_start

    if actual_count >= 3:
        gap_days = rng.randint(*GAP_MONTHS_RANGE) * 30
        rec2_end = prev_period_start - timedelta(days=gap_days + 1)
        prev_years = rng.uniform(*PREV_JOB_YEARS_RANGE_EARLY)
        rec2_start = rec2_end - timedelta(days=_years_to_days(prev_years))
        title2, duties2 = titles_and_duties[2]
        records.append(WorkRecordSuggestion(
            period_start=_format_period_start(rec2_start),
            period_end=_format_period_end(rec2_end),
            company=companies[2].name_full,
            position=title2,
            duties=duties2,  # Pack 20.3
        ))

    # Pack 64: stretch earliest record to fill education gap
    _stretch_earliest_record_for_education_gap(records, applicant)

    # Pack 69: clamp to MIN_WORK_START_AGE_YEARS = 18 (страховка от «работал с 15»)
    records = _clamp_records_to_min_work_age(records, applicant)

    total_duties = sum(len(r.duties) for r in records)
    log.info(
        "work_history generator: applicant_id=%s region=%s specialty=%s → "
        "%d records, %d total duties (fallback=%s, pattern=%r)",
        applicant.id, region_code, specialty.code,
        len(records), total_duties, fallback_used, matched_pattern,
    )

    specialty_text = f"{specialty.code} {specialty.name}"
    return WorkHistorySuggestion(
        records=records,
        fallback_used=fallback_used,
        specialty_used=specialty_text,
        matched_pattern=matched_pattern,
    )
