# -*- coding: utf-8 -*-
"""
Pack 50.7-B — генератор цели командировки для Приказа Т-9 (найм).

Цель: при создании новой должности в админке менеджер жмёт кнопку
"🪄 Сгенерировать цель командировки", сервис делает ОДИН вызов LLM
по контексту должности (title_ru, profile_description, tech_opinion_description_ru)
и возвращает текст для подстановки в Position.business_trip_purpose.

Текст должен быть в стиле эталонов 9 кейсов найма, которые подавались в UGE:
- "мониторинга изменений в законодательстве и международных санкциях,
   участия в информационном сопровождении деятельности компании,
   презентации фирмы на международных выставках и бизнес-форумах."
- "изучения международного опыта в строительстве и проектировании,
   нормативно-правовой базы, организации инспекционного контроля..."
- "отслеживания изменений в законодательстве и нормативах в ЕС, касающихся ВЭД,
   особенностей внешнеторговой деятельности..."

Возвращает текст (1-3 предложения, в родительном падеже после "с целью...").
В БД НЕ пишет.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import BaseModel, Field

from app.services.llm import get_llm_client

log = logging.getLogger(__name__)


# ============================================================== Input schema
class BusinessTripPurposeInput(BaseModel):
    """Контекст для генерации цели командировки."""
    title_ru: str = Field(..., min_length=2, description="Название должности на русском")
    profile_description: Optional[str] = Field(
        default=None,
        description="Краткое описание профиля должности (если есть)",
    )
    tech_opinion_description_ru: Optional[str] = Field(
        default=None,
        description="§1 tech_opinion на русском (если есть) — даёт богатый контекст",
    )
    international_analog_ru: Optional[str] = Field(
        default=None,
        description="Международный аналог должности (например 'quantity surveyor')",
    )


# ============================================================== Output schema
class BusinessTripPurposeOutput(BaseModel):
    """Результат генерации."""
    business_trip_purpose: str = Field(..., min_length=20)


# ============================================================== System prompt
_SYSTEM_PROMPT = """Ты — помощник кадрового делопроизводства в российской компании,
которая отправляет сотрудников в длительные командировки в Испанию (на ~3 года)
по визе работника. Тебе нужно сформулировать ЦЕЛЬ КОМАНДИРОВКИ для Приказа Т-9
о направлении работника в командировку.

Требования к тексту:
1. Длина: 1-3 предложения, обычно 1-2 строки текста (50-200 слов).
2. Стиль: официальный, деловой, в духе кадровых документов.
3. Падеж: РОДИТЕЛЬНЫЙ — текст ставится после фразы "с целью..."
   (т.е. начинается со слов "изучения...", "мониторинга...", "проведения..." и т.п.)
4. Содержание ДОЛЖНО быть связано с международной/зарубежной деятельностью —
   изучение зарубежного опыта, мониторинг международного законодательства, ВЭД,
   презентации на международных выставках, переговоры с иностранными контрагентами,
   и т.п.
5. НЕЛЬЗЯ упоминать визу, оформление документов, переезд, проживание —
   только профессиональные цели.
6. Текст должен быть РЕАЛИСТИЧНЫМ для конкретной должности — учитывай специализацию.

Эталоны (для примера и стиля):
- Менеджер по импортным закупкам металлообрабатывающих станков:
  "мониторинга изменений в законодательстве и международных санкциях,
   участия в информационном сопровождении деятельности компании,
   презентации фирмы на международных выставках и бизнес-форумах."

- Ведущий инженер-проектировщик (строительство):
  "изучения международного опыта в строительстве и проектировании,
   нормативно-правовой базы, организации инспекционного контроля,
   механизма сертификации и лицензирования подрядчиков,
   а также внедрения инновационных технологий."

- Специалист по внешнеэкономической деятельности:
  "отслеживания изменений в законодательстве и нормативах в ЕС, касающихся ВЭД,
   особенностей внешнеторговой деятельности с контрагентами,
   местной специфики ведения бизнеса и законодательства."

ВАЖНО: верни СТРОГО JSON-объект:
{"business_trip_purpose": "<текст>"}

Никаких ```json``` блоков, никаких пояснений до или после.
"""


# ============================================================== Helpers
def _extract_json(raw: str) -> str:
    """Извлекает JSON из ответа LLM, убирая ```json``` если есть."""
    # Убрать кодовые блоки
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _build_user_payload(inp: BusinessTripPurposeInput) -> str:
    parts = [
        f"Должность: {inp.title_ru}",
    ]
    if inp.international_analog_ru:
        parts.append(f"Международный аналог: {inp.international_analog_ru}")
    if inp.profile_description:
        parts.append(f"Краткое описание: {inp.profile_description}")
    if inp.tech_opinion_description_ru:
        # Обрежем чтобы не передавать слишком много
        desc = inp.tech_opinion_description_ru.strip()
        if len(desc) > 800:
            desc = desc[:800] + "..."
        parts.append(f"Описание деятельности (контекст): {desc}")

    payload_lines = "\n".join(parts)
    return (
        "Сгенерируй ЦЕЛЬ КОМАНДИРОВКИ для Приказа Т-9 по должности ниже.\n\n"
        "ВХОДНЫЕ ДАННЫЕ:\n"
        + payload_lines
        + "\n\nВерни СТРОГО JSON-объект {\"business_trip_purpose\": \"<текст>\"}. "
          "Никаких пояснений до или после."
    )


# ============================================================== main entry
async def generate_business_trip_purpose(inp: BusinessTripPurposeInput) -> str:
    """Генерирует текст цели командировки для Приказа Т-9.

    Returns: text для подстановки в Position.business_trip_purpose.
    Raises:
        ValueError — если LLM вернула невалидный JSON или не прошла валидация
        RuntimeError — если LLM-клиент не настроен
    """
    import json
    from pydantic import ValidationError

    client = get_llm_client()
    user_payload = _build_user_payload(inp)

    log.info(
        "Pack 50.7-B: generating business_trip_purpose for title_ru=%r",
        inp.title_ru,
    )

    raw = await client.complete(
        system=_SYSTEM_PROMPT,
        user=user_payload,
        max_tokens=512,
        temperature=0.4,
    )

    try:
        clean = _extract_json(raw)
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        log.error("Pack 50.7-B: invalid JSON from LLM: %s\nRAW: %s", e, raw[:500])
        raise ValueError(f"LLM вернула невалидный JSON: {e}") from e

    try:
        validated = BusinessTripPurposeOutput.model_validate(data)
    except ValidationError as e:
        log.error("Pack 50.7-B: schema validation failed: %s\nDATA: %s", e, data)
        raise ValueError(f"Ответ LLM не прошёл валидацию: {e}") from e

    log.info(
        "Pack 50.7-B: generated for %r — %d chars",
        inp.title_ru, len(validated.business_trip_purpose),
    )
    return validated.business_trip_purpose
