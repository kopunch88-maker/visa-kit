# -*- coding: utf-8 -*-
"""
Pack 43.0 — переводчик полей Position на испанский.

Цель: при добавлении новой должности через UI менеджер заполняет только
русские поля tech_opinion_*. Кнопка "Сгенерировать испанский" в редакторе
дёргает endpoint /admin/positions/{id}/translate-spanish, который через
LLM (Sonnet 4.6 по умолчанию, через OpenRouter) переводит все ES-поля
одним вызовом и возвращает dict — фронт кладёт в state и сохраняет через
обычный PATCH /admin/positions/{id}. В БД этот сервис НЕ пишет.

Поля на выходе (5 обязательных + 1 опциональное):
- tech_opinion_description_es   (str, длинный текст)
- tech_opinion_tools_es         (list[{name, purpose}])
- tech_opinion_steps_es         (list[{title, body}])
- tech_opinion_grounds_es       (list[str])
- tech_opinion_contract_clause_es (str)
- title_es                      (опционально — только если на входе пусто)

Стиль эталона — Position id=13 (инженер-проектировщик II категории).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from app.models import Position
from app.services.llm import get_llm_client

log = logging.getLogger(__name__)


# ============================================================== Pydantic schema
class _Tool(BaseModel):
    name: str
    purpose: str


class _Step(BaseModel):
    title: str
    body: str


class _TranslatedFields(BaseModel):
    """Структура JSON-ответа LLM. Все поля — обязательные, кроме title_es."""
    tech_opinion_description_es: str = Field(..., min_length=1)
    tech_opinion_tools_es: List[_Tool] = Field(..., min_length=1)
    tech_opinion_steps_es: List[_Step] = Field(..., min_length=1)
    tech_opinion_grounds_es: List[str] = Field(..., min_length=1)
    tech_opinion_contract_clause_es: str = Field(..., min_length=1)
    title_es: Optional[str] = None  # генерируется только если title_es пустой


# ============================================================== System prompt
_SYSTEM_PROMPT = """Ты — профессиональный переводчик с русского на испанский, специализирующийся на оформлении документов для визы Digital Nomad Visa Испании. Твоя задача — перевести описание должности и связанные поля для документа "DICTAMEN TÉCNICO sobre el carácter de trabajo a distancia" (техническое заключение о дистанционном характере деятельности), который подаётся в испанское консульство.

ТРЕБОВАНИЯ К ПЕРЕВОДУ:
1. Стиль — формальный, юридический, как в официальных испанских административных документах. Используй обороты вроде "el especialista trabaja exclusivamente con...", "presta servicios de forma remota...", "la profesión está reconocida como...".
2. Сохраняй структуру массивов 1-в-1: на сколько элементов вход, столько же на выходе.
3. В объектах с ключами {name, purpose} и {title, body} ключи НЕ переводи, переводи только значения. Названия программ/сервисов (AutoCAD, Power BI, SAP, ERP, MES, BIM 360, Jira, Confluence, GitHub, и т.д.) оставляй БЕЗ перевода. Если в названии есть русское описание (например, "Credo (Кредо-Диалог)") — переводи только русскую часть ("Credo (software geodésico)").
4. Аббревиатуры технических систем (ERP, MES, BI, CAD, BIM, KPI, API) оставляй как есть.
5. НЕ ВЫДУМЫВАЙ факты, которых нет в исходных данных. Если на входе короткий текст — на выходе тоже короткий. Если на входе 5 шагов — на выходе ровно 5.
6. В поле contract_clause переводи именно как формулировку договора (формальный язык контракта).
7. Если на входе передано пустое значение title_es — сгенерируй краткое название должности на испанском (2-4 слова, нижний регистр, без артикля). Если title_es непустое — НЕ включай его в ответ.

ФОРМАТ ОТВЕТА — СТРОГО JSON, без markdown-блоков, без префиксов, без пояснений. Только валидный JSON со следующими ключами:
{
  "tech_opinion_description_es": "...",
  "tech_opinion_tools_es": [{"name": "...", "purpose": "..."}, ...],
  "tech_opinion_steps_es": [{"title": "...", "body": "..."}, ...],
  "tech_opinion_grounds_es": ["...", "..."],
  "tech_opinion_contract_clause_es": "..."
}
(плюс "title_es": "..." только если на входе он был пустым)

ЭТАЛОН СТИЛЯ для tools_es: {"name": "Autodesk Revit / AutoCAD", "purpose": "entorno de trabajo principal — diseño y cálculos"}
ЭТАЛОН СТИЛЯ для steps_es: {"title": "Recepción de los términos de referencia", "body": "El cliente envía términos de referencia, datos iniciales, requisitos vía portal corporativo o email..."}
ЭТАЛОН СТИЛЯ для grounds_es: "La profesión de «ingeniero proyectista» se basa en el trabajo con software especializado (AutoCAD y análogos), que funciona en ordenador estándar y no requiere presencia física en oficina."
ЭТАЛОН СТИЛЯ для contract_clause_es: "Los servicios de diseño y cálculos de ingeniería se prestan a distancia mediante software especializado y sistemas cloud colaborativos."
"""


# ============================================================== helper: build user payload
def _build_user_payload(position: Position) -> str:
    """Собирает русские поля Position в один JSON-вход для LLM."""
    payload: Dict[str, Any] = {
        "title_ru": position.title_ru,
        "title_ru_genitive": position.title_ru_genitive or "",
        "title_es": position.title_es or "",  # пусто = LLM должен сгенерировать
        "profile_description": position.profile_description or "",
        "tech_opinion_description_ru": position.tech_opinion_description_ru or "",
        "tech_opinion_tools_ru": position.tech_opinion_tools_ru or [],
        "tech_opinion_steps_ru": position.tech_opinion_steps_ru or [],
        "tech_opinion_grounds_ru": position.tech_opinion_grounds_ru or [],
        "tech_opinion_contract_clause_ru": position.tech_opinion_contract_clause_ru or "",
        "international_analog_ru": position.international_analog_ru or "",
        "international_analog_es": position.international_analog_es or "",
    }
    return (
        "Переведи на испанский следующие поля должности.\n"
        "ВХОД (JSON):\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\nВерни СТРОГО JSON по схеме из system prompt. "
          "Никаких ```json``` блоков, никаких пояснений до или после."
    )


# ============================================================== JSON extraction
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> str:
    """LLM иногда оборачивает в ```json ... ``` — снимаем обёртку."""
    raw = raw.strip()
    # snip markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    # if there's text before/after JSON — extract the {...} block
    if not raw.startswith("{"):
        m = _JSON_BLOCK_RE.search(raw)
        if m:
            raw = m.group(0)
    return raw.strip()


# ============================================================== main entry
async def translate_position_to_spanish(position: Position) -> Dict[str, Any]:
    """
    Переводит русские tech_opinion поля Position на испанский.

    Returns: dict с ключами для PositionUpdate-payload:
        {
          "tech_opinion_description_es": "...",
          "tech_opinion_tools_es": [...],
          "tech_opinion_steps_es": [...],
          "tech_opinion_grounds_es": [...],
          "tech_opinion_contract_clause_es": "...",
          # title_es — только если был пустой на входе
        }

    Raises:
        ValueError — если LLM вернула невалидный JSON или не прошла валидация
        RuntimeError — если LLM-клиент не настроен
    """
    # Минимальная проверка входа — нечего переводить если все RU-поля пустые
    has_any_ru = any([
        position.tech_opinion_description_ru,
        position.tech_opinion_tools_ru,
        position.tech_opinion_steps_ru,
        position.tech_opinion_grounds_ru,
        position.tech_opinion_contract_clause_ru,
    ])
    if not has_any_ru:
        raise ValueError(
            "Position не содержит русских tech_opinion полей — нечего переводить. "
            "Заполните русские поля и нажмите кнопку снова."
        )

    client = get_llm_client()
    user_payload = _build_user_payload(position)

    log.info(
        "Pack 43.0: translating Position id=%s title_ru=%r to Spanish",
        position.id, position.title_ru,
    )

    raw = await client.complete(
        system=_SYSTEM_PROMPT,
        user=user_payload,
        max_tokens=4096,
        temperature=0.2,
    )

    # parse + validate
    try:
        clean = _extract_json(raw)
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        log.error("Pack 43.0: LLM returned invalid JSON: %s\nRAW: %s", e, raw[:500])
        raise ValueError(f"LLM вернула невалидный JSON: {e}") from e

    try:
        validated = _TranslatedFields.model_validate(data)
    except ValidationError as e:
        log.error("Pack 43.0: LLM response failed schema validation: %s\nDATA: %s", e, data)
        raise ValueError(f"Ответ LLM не прошёл валидацию: {e}") from e

    # build response dict — пропускаем title_es если он не был запрошен
    result: Dict[str, Any] = {
        "tech_opinion_description_es": validated.tech_opinion_description_es,
        "tech_opinion_tools_es": [t.model_dump() for t in validated.tech_opinion_tools_es],
        "tech_opinion_steps_es": [s.model_dump() for s in validated.tech_opinion_steps_es],
        "tech_opinion_grounds_es": validated.tech_opinion_grounds_es,
        "tech_opinion_contract_clause_es": validated.tech_opinion_contract_clause_es,
    }
    # title_es включаем только если на входе был пустой И LLM что-то предложила
    if not (position.title_es or "").strip() and validated.title_es:
        result["title_es"] = validated.title_es.strip()

    log.info(
        "Pack 43.0: translation done for Position id=%s — %d tools, %d steps, %d grounds",
        position.id,
        len(result["tech_opinion_tools_es"]),
        len(result["tech_opinion_steps_es"]),
        len(result["tech_opinion_grounds_es"]),
    )
    return result
