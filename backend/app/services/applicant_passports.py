"""
applicant_passports.py — Pack 41.0-B

Утилиты для работы со списком паспортов клиента (applicant.passports[]).

Контракт PassportRecord (JSON):
  {
    "id": "p_xxxxxxxx",           # короткий uuid
    "number": "BD9805365",        # уникален внутри applicant; .strip().upper().replace(' ','')
    "issue_date": "2025-05-22",   # ISO date, обязательно
    "expiry_date": "2035-05-21",  # ISO date | None
    "issuer": "MPB",              # str | None — латиница как в MRZ
    "issuer_ru": "МВД ...",       # str | None — для русских доков
    "passport_type": "P",         # 'P' | 'PP' | 'D' | 'O' | None
    "is_primary": True,           # ровно один True на applicant
    "notes": None,                # str | None
    "source": "ocr",              # 'ocr' | 'manual' | 'legacy_backfill'
    "created_at": "...",          # ISO datetime
    "updated_at": "...",          # ISO datetime
  }

Инварианты, поддерживаемые recompute_primary():
  1. Если passports пуст → все скалярные passport_* = None
  2. Если passports непуст → ровно один is_primary=True
  3. Primary = max(issue_date). Tie-break: max(created_at). Final: min(id).
  4. После пересчёта primary скалярные passport_* зеркалят его.
  5. Если passport_id_for_ru_docs ссылается на удалённый id → сбрасывается в None.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Базовые утилиты
# ---------------------------------------------------------------------------

def _short_uid() -> str:
    return "p_" + secrets.token_hex(4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_number(num: str | None) -> str:
    if num is None:
        return ""
    return num.strip().upper().replace(" ", "")


# ---------------------------------------------------------------------------
# Pack 41.0-C0 — типы паспортов и эвристика определения
# ---------------------------------------------------------------------------

# Типы, которые НИКОГДА не могут быть primary (не идут в MI-T/EX-17/испанские формы).
# RU_INTERNAL — паспорт гражданина РФ. Нужен только в русских документах.
RU_INTERNAL_TYPES: frozenset[str] = frozenset({"RU_INTERNAL"})


def detect_passport_type(
    *,
    number: str | None,
    nationality: str | None,
) -> str | None:
    """
    Эвристика типа паспорта по номеру и гражданству.

    Возвращает один из:
      "RU_INTERNAL"  — паспорт РФ (10 цифр + RUS)
      "RU_FOREIGN"   — российский загранник (9 цифр или буква+цифры + RUS)
      "FOREIGN"      — иностранный паспорт (nationality ≠ RUS)
      None           — определить не удалось (мусорный номер, нет nationality)

    Используется в Pack 41.0-C0 для бэкфилла legacy записей и в Pack 41.0-C
    для OCR-pipeline когда LLM не вернул passport_type.
    """
    norm = normalize_number(number)
    if not norm:
        return None

    nat = (nationality or "").strip().upper() if nationality else ""

    # Только цифры?
    is_all_digits = norm.isdigit()
    has_latin = any(ch.isalpha() for ch in norm)

    if nat == "RUS":
        if is_all_digits and len(norm) == 10:
            return "RU_INTERNAL"
        if is_all_digits and len(norm) == 9:
            return "RU_FOREIGN"
        if has_latin and any(ch.isdigit() for ch in norm):
            return "RU_FOREIGN"
        return None

    if nat and nat != "RUS":
        # Иностранец — что бы ни было в номере (мусор или нет), помечаем FOREIGN
        # если хотя бы что-то осмысленное. Совсем мусор (только буквы, например
        # SDFSDFS) — лучше None, чтобы менеджер разобрался.
        if is_all_digits or (has_latin and any(ch.isdigit() for ch in norm)):
            return "FOREIGN"
        return None

    # nationality пустой
    return None


def make_passport_record(
    *,
    number: str,
    issue_date: str | None,
    expiry_date: str | None = None,
    issuer: str | None = None,
    issuer_ru: str | None = None,
    passport_type: str | None = None,
    notes: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    """Создаёт PassportRecord. is_primary всегда False — выставляется recompute."""
    now = _now_iso()
    return {
        "id": _short_uid(),
        "number": normalize_number(number),
        "issue_date": issue_date,
        "expiry_date": expiry_date,
        "issuer": issuer,
        "issuer_ru": issuer_ru,
        "passport_type": passport_type,
        "is_primary": False,
        "notes": notes,
        "source": source,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Поиск и upsert
# ---------------------------------------------------------------------------

def find_by_id(passports: list[dict], passport_id: str) -> dict | None:
    for p in passports:
        if p.get("id") == passport_id:
            return p
    return None


def find_by_number(passports: list[dict], number: str) -> dict | None:
    norm = normalize_number(number)
    for p in passports:
        if normalize_number(p.get("number")) == norm:
            return p
    return None


def upsert_by_number(
    passports: list[dict],
    *,
    number: str,
    issue_date: str | None = None,
    expiry_date: str | None = None,
    issuer: str | None = None,
    issuer_ru: str | None = None,
    passport_type: str | None = None,
    source: str = "ocr",
) -> tuple[list[dict], dict, bool]:
    """
    Идемпотентный upsert по нормализованному номеру.

    Возвращает (new_passports_list, affected_record, created_flag).
    created_flag=True если запись добавлена, False если обновлена.

    Политика обновления существующей: НЕ перетираем непустое поле пустым.
    Это защита от OCR-промпта, который иногда возвращает None для уже известных полей.
    """
    norm = normalize_number(number)
    if not norm:
        raise ValueError("passport number is empty after normalization")

    new_list = list(passports)
    existing = find_by_number(new_list, norm)

    if existing is None:
        rec = make_passport_record(
            number=norm,
            issue_date=issue_date,
            expiry_date=expiry_date,
            issuer=issuer,
            issuer_ru=issuer_ru,
            passport_type=passport_type,
            source=source,
        )
        new_list.append(rec)
        return new_list, rec, True

    # Обновление: не перетираем непустое пустым
    changed = False
    fields = {
        "issue_date": issue_date,
        "expiry_date": expiry_date,
        "issuer": issuer,
        "issuer_ru": issuer_ru,
        "passport_type": passport_type,
    }
    for k, v in fields.items():
        if v in (None, ""):
            continue
        if existing.get(k) != v:
            existing[k] = v
            changed = True

    if changed:
        existing["updated_at"] = _now_iso()

    return new_list, existing, False


def remove_by_id(passports: list[dict], passport_id: str) -> list[dict]:
    return [p for p in passports if p.get("id") != passport_id]


# ---------------------------------------------------------------------------
# Primary recompute
# ---------------------------------------------------------------------------

def _primary_sort_key(p: dict) -> tuple:
    """
    Sort DESC: max issue_date → max created_at → min id (для детерминизма).
    Пустые issue_date уходят в конец.
    """
    issue = p.get("issue_date") or ""
    created = p.get("created_at") or ""
    pid = p.get("id") or ""
    # min id — инвертируем строку для DESC sort: проще обернём в кортеж
    return (issue, created, pid)


def recompute_primary(passports: list[dict]) -> list[dict]:
    """
    Пересчитывает is_primary по правилу max(issue_date) → max(created_at) → min(id).
    Возвращает новый список (не мутирует входной).

    Pack 41.0-C0: примарным может стать ТОЛЬКО паспорт у которого
    passport_type не в RU_INTERNAL_TYPES. Если все паспорта RU_INTERNAL —
    primary не выставляется (никто), и скалярные passport_* синкаются в None.
    """
    if not passports:
        return []

    # Pack 41.0-C0: фильтр кандидатов на primary — исключаем RU_INTERNAL
    eligible = [
        p for p in passports
        if p.get("passport_type") not in RU_INTERNAL_TYPES
    ]

    # Если ни одного eligible — все is_primary=False (RU_INTERNAL не идёт в MI-T)
    if not eligible:
        result = []
        for p in passports:
            new_p = dict(p)
            new_p["is_primary"] = False
            result.append(new_p)
        return result

    # Сортируем по убыванию ключа; для min(id) при тае — отдельный шаг
    # 1. Найдём кандидатов с max(issue_date) — ТОЛЬКО среди eligible
    sorted_by_issue = sorted(
        eligible, key=lambda p: p.get("issue_date") or "", reverse=True
    )
    top_issue = sorted_by_issue[0].get("issue_date") or ""
    issue_candidates = [
        p for p in sorted_by_issue if (p.get("issue_date") or "") == top_issue
    ]

    if len(issue_candidates) == 1:
        winner = issue_candidates[0]
    else:
        # 2. Tie-break по max(created_at)
        sorted_by_created = sorted(
            issue_candidates, key=lambda p: p.get("created_at") or "", reverse=True
        )
        top_created = sorted_by_created[0].get("created_at") or ""
        created_candidates = [
            p for p in sorted_by_created if (p.get("created_at") or "") == top_created
        ]
        if len(created_candidates) == 1:
            winner = created_candidates[0]
        else:
            # 3. Final tie-break по min(id) для детерминизма
            winner = min(created_candidates, key=lambda p: p.get("id") or "")

    result = []
    for p in passports:
        new_p = dict(p)
        new_p["is_primary"] = (new_p.get("id") == winner.get("id"))
        result.append(new_p)
    return result


def get_primary(passports: list[dict]) -> dict | None:
    for p in passports:
        if p.get("is_primary"):
            return p
    return None


def get_passport_for_ru_docs(
    passports: list[dict],
    passport_id_for_ru_docs: str | None,
) -> dict | None:
    """
    Возвращает паспорт для русских документов (договор, акты, счета и т.д.).
    Если passport_id_for_ru_docs указан и существует → его.
    Иначе → primary.
    Если passports пуст → None.
    """
    if not passports:
        return None
    if passport_id_for_ru_docs:
        chosen = find_by_id(passports, passport_id_for_ru_docs)
        if chosen is not None:
            return chosen
        # ссылка битая — fallback на primary
    return get_primary(passports)


# ---------------------------------------------------------------------------
# Sync с legacy скалярными полями applicant
# ---------------------------------------------------------------------------

LEGACY_FIELDS = (
    "passport_number",
    "passport_issue_date",
    "passport_expiry_date",
    "passport_issuer",
    "passport_issuer_ru",
)


def sync_primary_to_legacy_fields(applicant) -> None:
    """
    Зеркалит поля primary паспорта в скалярные applicant.passport_*.
    Если passports пуст → все скалярные = None.

    Принимает SQLModel/SQLAlchemy инстанс applicant с атрибутами:
      passports: list[dict]
      passport_number: str | None
      passport_issue_date: date | None
      ...

    Мутирует applicant in-place. Caller обязан вызвать session.add() и commit.
    """
    from datetime import date as _date

    passports = applicant.passports or []
    primary = get_primary(passports)

    if primary is None:
        for f in LEGACY_FIELDS:
            setattr(applicant, f, None)
        return

    applicant.passport_number = primary.get("number") or None

    # issue_date / expiry_date — конвертим ISO → date если нужно
    def _to_date(v):
        if v is None or v == "":
            return None
        if isinstance(v, _date):
            return v
        try:
            return _date.fromisoformat(str(v)[:10])
        except (ValueError, TypeError):
            return None

    applicant.passport_issue_date = _to_date(primary.get("issue_date"))
    applicant.passport_expiry_date = _to_date(primary.get("expiry_date"))
    applicant.passport_issuer = primary.get("issuer") or None
    applicant.passport_issuer_ru = primary.get("issuer_ru") or None


def validate_passport_id_for_ru_docs(applicant) -> bool:
    """
    Если passport_id_for_ru_docs указывает на несуществующий id → сбрасывает в None.
    Возвращает True если потребовалась чистка.
    """
    pid = getattr(applicant, "passport_id_for_ru_docs", None)
    if pid is None:
        return False
    passports = applicant.passports or []
    if find_by_id(passports, pid) is None:
        applicant.passport_id_for_ru_docs = None
        return True
    return False


def reconcile_applicant_passports(applicant) -> None:
    """
    Главная точка входа: после любой мутации passports[] (через API, OCR, ручной правки)
    вызвать reconcile_applicant_passports(applicant) перед commit.

    Делает:
      1. recompute_primary
      2. validate_passport_id_for_ru_docs
      3. sync_primary_to_legacy_fields
    """
    applicant.passports = recompute_primary(applicant.passports or [])
    validate_passport_id_for_ru_docs(applicant)
    sync_primary_to_legacy_fields(applicant)
