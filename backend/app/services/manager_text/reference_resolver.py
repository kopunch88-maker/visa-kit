"""
Pack 50.38-D1 — поиск сущностей в справочниках по тексту менеджера.

Менеджер пишет названия компании/должности/представителя/адреса в свободной
форме, с возможными опечатками и разной транслитерацией (RENKONS vs Rekkons).
Этот сервис ищет соответствие в справочниках БД нечётким сравнением (difflib,
без внешних зависимостей и без LLM). Список кандидатов берётся из БД динамически
— при добавлении новых записей ничего менять не нужно.

Все resolve_* возвращают (id | None, debug_info). Если ничего выше порога —
None (вызывающий код кладёт «не найдено» в заметки).

Порог по умолчанию 0.72 — на реальных данных (где ключевая часть названия
совпадает) уверенно отделяет совпадение от мусора (цель ~0.9+, мусор <0.4).
"""
import difflib
import re
from typing import Optional, Tuple

from sqlmodel import Session, select

from app.models import Company, Position, Representative, SpainAddress


SIM_THRESHOLD = 0.72


# Орг-формы и шум, которые убираем перед сравнением
_ORG_JUNK = [
    "общество с ограниченной ответственностью",
    "акционерное общество",
    "публичное акционерное общество",
    "sociedad de responsabilidad limitada",
    "sociedad limitada",
    "ооо", "оао", "зао", "пао", "ао",
    "s.l.u.", "s.l.", "s.a.", "sl", "sa", "ltd", "llc",
]


def _normalize(s: Optional[str]) -> str:
    """Приводит название к канону для сравнения: нижний регистр, без орг-форм,
    кавычек и лишних пробелов."""
    if not s:
        return ""
    s = s.lower()
    for junk in _ORG_JUNK:
        s = s.replace(junk, " ")
    s = re.sub(r'[«»""\'`(),.№]', " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _sim(a: str, b: str) -> float:
    """Похожесть двух уже нормализованных (или сырых) строк 0..1."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _best_match(query: str, candidates: list, fields: list) -> Tuple[Optional[object], float]:
    """Находит кандидата с максимальной похожестью по любому из полей.

    candidates — list объектов; fields — имена строковых атрибутов для сравнения.
    Возвращает (объект | None, score).
    """
    if not query or not query.strip():
        return None, 0.0
    best, best_score = None, 0.0
    for c in candidates:
        for f in fields:
            val = getattr(c, f, None)
            score = _sim(query, val or "")
            if score > best_score:
                best, best_score = c, score
    return best, best_score


# ============================================================================
# Resolvers
# ============================================================================
def resolve_company(session: Session, name: Optional[str], threshold: float = SIM_THRESHOLD) -> Tuple[Optional[int], dict]:
    """Ищет компанию по названию (short_name / full_name_ru / full_name_es).

    Привязка по русскому (id), сравнение по всем трём (менеджер мог дать исп.
    транслитерацию). Возвращает (company_id | None, debug)."""
    if not name or not name.strip():
        return None, {"reason": "empty"}
    companies = session.exec(select(Company)).all()
    best, score = _best_match(name, companies, ["full_name_es", "full_name_ru", "short_name"])
    if best and score >= threshold:
        return best.id, {"matched": best.full_name_ru, "score": round(score, 3)}
    return None, {"reason": "no_match", "best": getattr(best, "full_name_ru", None), "score": round(score, 3)}


def resolve_position(session: Session, title: Optional[str], threshold: float = SIM_THRESHOLD) -> Tuple[Optional[int], dict]:
    """Ищет должность по title_ru / title_es."""
    if not title or not title.strip():
        return None, {"reason": "empty"}
    positions = session.exec(select(Position)).all()
    best, score = _best_match(title, positions, ["title_ru", "title_es"])
    if best and score >= threshold:
        return best.id, {"matched": best.title_ru, "score": round(score, 3)}
    return None, {"reason": "no_match", "best": getattr(best, "title_ru", None), "score": round(score, 3)}


def resolve_representative(
    session: Session,
    full_name: Optional[str],
    nie: Optional[str] = None,
    threshold: float = SIM_THRESHOLD,
) -> Tuple[Optional[int], dict]:
    """Ищет представителя. Сначала по NIE (если менеджер всё же указал) —
    точное совпадение; иначе fuzzy по полному имени first+last."""
    reps = session.exec(select(Representative)).all()

    # 1. NIE — если есть, точное совпадение (бонус, менеджер обычно не пишет)
    if nie and nie.strip():
        nie_clean = nie.strip().upper()
        for r in reps:
            if (getattr(r, "nie", "") or "").strip().upper() == nie_clean:
                return r.id, {"matched_by": "nie", "name": f"{r.first_name} {r.last_name}"}

    # 2. По имени (fuzzy)
    if not full_name or not full_name.strip():
        return None, {"reason": "empty"}
    best, best_score = None, 0.0
    for r in reps:
        combos = [
            f"{r.first_name} {r.last_name}",
            f"{r.last_name} {r.first_name}",
        ]
        for combo in combos:
            score = _sim(full_name, combo)
            if score > best_score:
                best, best_score = r, score
    if best and best_score >= threshold:
        return best.id, {"matched_by": "name", "name": f"{best.first_name} {best.last_name}", "score": round(best_score, 3)}
    return None, {"reason": "no_match", "best": (f"{best.first_name} {best.last_name}" if best else None), "score": round(best_score, 3)}


# Pack 50.38-D1-fix — шум адреса (тип улицы, этаж, индекс, город)
_ADDR_NOISE = [
    "carrer de la", "carrer del", "carrer de", "carrer",
    "calle de la", "calle del", "calle de", "calle", "c/",
    "avenida de", "avenida", "avda", "av", "passeig de", "passeig",
    "piso", "puerta", "planta", "esc", "escalera", "bajo",
    "atico", "\u00e1tico", "izquierda", "derecha", "izq", "der",
    "barcelona", "madrid", "montmelo", "montmel\u00f3",
    "espana", "espa\u00f1a",
]


def _addr_core(s):
    """Извлекает ядро адреса: улица + номер дома, без типа улицы,
    этажа/двери, почтового индекса и города. Для устойчивого сравнения."""
    s = _normalize(s)
    s = re.sub(r"\b\d{5}\b", " ", s)  # почтовый индекс
    for w in _ADDR_NOISE:
        s = re.sub(r"\b" + re.escape(w) + r"\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def resolve_spain_address(
    session: Session,
    raw: Optional[str] = None,
    city: Optional[str] = None,
    street: Optional[str] = None,
    threshold: float = SIM_THRESHOLD,
) -> Tuple[Optional[int], dict]:
    """Ищет адрес в Испании по street/label/city. Сравнивает с raw (полная
    строка адреса) и/или street."""
    addrs = session.exec(select(SpainAddress)).all()
    query = (raw or street or "").strip()
    if not query and not city:
        return None, {"reason": "empty"}

    # Pack 50.38-D1-fix: сравниваем по ЯДРУ (улица+номер), отбросив шум
    q_core = _addr_core(query)
    best, best_score = None, 0.0
    for a in addrs:
        street = getattr(a, "street", "") or ""
        label = getattr(a, "label", "") or ""
        acity = getattr(a, "city", "") or ""
        # ядра кандидата: label (обычно «Улица Номер, Город») и street+label
        cand_cores = [
            _addr_core(label),
            _addr_core(f"{street} {label}"),
            _addr_core(f"{street} {acity}"),
        ]
        score = max(_sim(q_core, c) for c in cand_cores if c)
        if score > best_score:
            best, best_score = a, score
    if best and best_score >= threshold:
        return best.id, {"matched": getattr(best, "label", None), "score": round(best_score, 3)}
    return None, {"reason": "no_match", "best": getattr(best, "label", None), "score": round(best_score, 3)}
