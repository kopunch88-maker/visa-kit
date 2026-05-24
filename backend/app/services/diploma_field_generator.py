# -*- coding: utf-8 -*-
"""
Pack 46.0 — LLM-генератор 6 недостающих полей диплома.

Когда менеджер уже ввёл institution + specialty + graduation_year (+ опционально degree),
этот сервис делает один LLM-вызов и возвращает правдоподобные значения для:
  - diploma_number       (формат 6+7 цифр, маска бланков Госзнака 2014+ для конкретного ВУЗа)
  - registration_number  (формат внутреннего журнала конкретного ВУЗа)
  - protocol_number      (маленькое число)
  - protocol_date        (ISO date, за 5-15 дней до issue_date)
  - issue_date           (ISO date, конец июня / начало июля выпускного года)
  - signers              (list[{name, position}], реальные имена руководства ВУЗа на дату)

В БД НЕ пишет — возвращает dict, фронт кладёт в state, потом обычный PATCH.

ВАЖНО: номера сгенерированы в правильном ФОРМАТЕ для конкретного ВУЗа, но это НЕ
реальные идентификаторы конкретного выпускника. Это рабочая копия для хурадо.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from app.services.llm import get_llm_client

log = logging.getLogger(__name__)


# ============================================================ Pydantic
class _Signer(BaseModel):
    name: str
    position: Optional[str] = None


class _GeneratedDiplomaFields(BaseModel):
    diploma_number: str = Field(..., min_length=5)
    registration_number: str = Field(..., min_length=3)
    protocol_number: str = Field(..., min_length=1)
    protocol_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    issue_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    signers: List[_Signer] = Field(..., min_length=1, max_length=3)


class DiplomaFieldsInput(BaseModel):
    """Что передаёт фронт."""
    institution: str = Field(..., min_length=3)
    specialty: str = Field(..., min_length=3)
    graduation_year: int = Field(..., ge=1950, le=2030)
    degree: Optional[str] = None
    full_name_native: Optional[str] = None  # для контекста промпта (пол подписантов)


_SYSTEM_PROMPT = """Ты — эксперт по оформлению российских дипломов о высшем образовании. Твоя задача — по краткой вводной (название ВУЗа, специальность, год выпуска, степень) сгенерировать 6 ПРАВДОПОДОБНЫХ полей для титульного листа диплома.

ВАЖНО: ты НЕ должен выдумывать реальные номера конкретных выпускников. Цель — сгенерировать значения в ПРАВИЛЬНОМ ФОРМАТЕ для бланков Госзнака и внутренних систем конкретного ВУЗа. Это рабочая копия для передачи переводчику-хурадо в Испании.

6 полей на выходе:

1. **diploma_number** — номер бланка Госзнака.
   - Формат для дипломов с 2014 года: 6 цифр + ДВА пробела + 7 цифр. Пример: "107724  0170246"
   - Первые 6 цифр зависят от типа диплома и года: 107724 — стандартные синие бланки бакалавра/специалиста 2014-2017. Для других периодов и ВУЗов уровня МГУ/СПбГУ/ВШЭ могут начинаться с 107725, 107726, 108100 и т.п. Используй правдоподобный префикс для указанного года выпуска.
   - Последние 7 цифр — случайные, но без явных паттернов (НЕ 1234567, НЕ 0000001).

2. **registration_number** — внутренний регистрационный номер ВУЗа.
   - Формат СИЛЬНО зависит от ВУЗа.
   - Для ВШЭ типовой формат: "2.10.3-13.1/423" (точечно-дефисная многоуровневая иерархия)
   - Для МГУ типовой формат: "АА-12345" или "Б-12345/2015"
   - Для СПбГУ типовой формат: "01/А-1234"
   - Для региональных ВУЗов часто проще: "123" или "Д-1234" или "001-456"
   - Подбери формат правдоподобный для УКАЗАННОГО ВУЗА. Если ВУЗ не знаешь — выбери стандартный формат "Д-NNNN" где NNNN случайное 3-4 значное число.

3. **protocol_number** — номер протокола ГЭК (государственной экзаменационной комиссии).
   - Маленькое целое число 1-30, чаще всего 1-10.
   - Возвращай как строку: "1", "2", "12".

4. **protocol_date** — дата заседания ГЭК. ISO формат YYYY-MM-DD.
   - За 5-15 дней до issue_date.
   - Обычно конец мая / середина июня выпускного года.

5. **issue_date** — дата выдачи диплома. ISO формат YYYY-MM-DD.
   - Конец июня / начало июля указанного выпускного года (как правило 20-30 июня или 1-15 июля).
   - Для большинства ВУЗов — 28-30 июня.

6. **signers** — подписанты на титульном листе диплома (1-3 человека).
   - Обычно: председатель ГЭК + ректор (или проректор по учебной работе).
   - Для крупных ВУЗов (ВШЭ, МГУ, СПбГУ, МФТИ и др.) ты ДОЛЖЕН использовать РЕАЛЬНЫЕ ФИО руководства на указанную дату выпуска. Например, для ВШЭ 2015 года: ректор Кузьминов Я.И. до 2021, проректор Радаев В.В., и т.п.
   - Для неизвестных ВУЗов — придумай правдоподобные русские ФИО в формате "Фамилия И.О." (без полных имён).
   - Формат: [{"name": "Афанасьев А.П.", "position": "Председатель ГЭК"}, {"name": "Радаев В.В.", "position": "Проректор"}]
   - position может быть null если неизвестно.
   - ВАЖНО: 1-3 подписанта, чаще всего 2.

ФОРМАТ ОТВЕТА — СТРОГО JSON, без markdown-блоков, без префиксов:
{
  "diploma_number": "107724  0170246",
  "registration_number": "2.10.3-13.1/423",
  "protocol_number": "1",
  "protocol_date": "2015-06-17",
  "issue_date": "2015-06-28",
  "signers": [{"name": "Афанасьев А.П.", "position": "Председатель ГЭК"}, {"name": "Радаев В.В.", "position": "Проректор"}]
}
"""


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    if not raw.startswith("{"):
        m = _JSON_BLOCK_RE.search(raw)
        if m:
            raw = m.group(0)
    return raw.strip()


def _build_user_payload(inp: DiplomaFieldsInput) -> str:
    parts = [
        f"ВУЗ: {inp.institution}",
        f"Специальность: {inp.specialty}",
        f"Год выпуска: {inp.graduation_year}",
    ]
    if inp.degree:
        parts.append(f"Степень: {inp.degree}")
    if inp.full_name_native:
        parts.append(f"ФИО выпускника (для контекста, НЕ выдумывай совпадений с подписантами): {inp.full_name_native}")
    payload_lines = "\n".join(parts)
    return (
        "Сгенерируй 6 полей титульного листа диплома по этим вводным.\n\n"
        "ВХОДНЫЕ ДАННЫЕ:\n"
        + payload_lines
        + "\n\nВерни СТРОГО JSON по схеме из system prompt. "
          "Никаких ```json``` блоков, никаких пояснений до или после."
    )


async def generate_diploma_fields(inp: DiplomaFieldsInput) -> Dict[str, Any]:
    """Pack 46.0: главный entry. Возвращает dict для PATCH в applicant.education[idx].

    Raises:
        ValueError — невалидный JSON / не прошла Pydantic-валидация
        RuntimeError — LLM-клиент не настроен
    """
    client = get_llm_client()
    user_payload = _build_user_payload(inp)

    log.info(
        "Pack 46.0: generating diploma fields for institution=%r specialty=%r year=%d",
        inp.institution[:50], inp.specialty[:50], inp.graduation_year,
    )

    raw = await client.complete(
        system=_SYSTEM_PROMPT,
        user=user_payload,
        max_tokens=1024,
        temperature=0.5,  # больше разнообразия в номерах
    )

    try:
        clean = _extract_json(raw)
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        log.error("Pack 46.0: invalid JSON from LLM: %s\nRAW: %s", e, (raw or "")[:500])
        raise ValueError(f"LLM вернула невалидный JSON: {e}") from e

    try:
        validated = _GeneratedDiplomaFields.model_validate(data)
    except ValidationError as e:
        log.error("Pack 46.0: schema validation failed: %s\nDATA: %s", e, data)
        raise ValueError(f"Ответ LLM не прошёл валидацию: {e}") from e

    result: Dict[str, Any] = {
        "diploma_number": validated.diploma_number,
        "registration_number": validated.registration_number,
        "protocol_number": validated.protocol_number,
        "protocol_date": validated.protocol_date,
        "issue_date": validated.issue_date,
        "signers": [s.model_dump() for s in validated.signers],
    }

    log.info(
        "Pack 46.0: generated — diploma=%r registration=%r protocol=%s issue=%s signers=%d",
        result["diploma_number"], result["registration_number"],
        result["protocol_date"], result["issue_date"], len(result["signers"]),
    )
    return result
