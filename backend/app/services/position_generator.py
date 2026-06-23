# -*- coding: utf-8 -*-
"""
Pack 45.0 — генератор русских полей Position по названию и специальности.

Цель: при добавлении новой должности менеджер вводит 4 обязательных поля
(title_ru, title_es, specialty_name, level), жмёт кнопку "Сгенерировать всё"
в редакторе. Этот сервис делает ОДИН вызов LLM (Sonnet 4.6 по умолчанию,
через OpenRouter) и возвращает 9 русских полей одним dict'ом.

Поля на выходе:
- duties                            (list[str], 9-11 пунктов)
- tags                              (list[str], 5-8 тегов)
- profile_description               (str, краткое описание для LLM-матчинга)
- tech_opinion_description_ru       (str, длинный текст §1)
- tech_opinion_tools_ru             (list[{name, purpose}], 5-7 инструментов)
- tech_opinion_steps_ru             (list[{title, body}], 6-8 шагов)
- tech_opinion_grounds_ru           (list[str], 2-3 основания)
- tech_opinion_contract_clause_ru   (str, формулировка для договора)
- international_analog_ru           (str, аналог должности на английском)

В БД НЕ пишет. Возвращает dict для PositionCreate/Update.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from app.services.llm import get_llm_client

log = logging.getLogger(__name__)


# ============================================================== Pydantic schema
class _Tool(BaseModel):
    name: str
    purpose: str


class _Step(BaseModel):
    title: str
    body: str


class _Certificate(BaseModel):
    """Pack CV-AUTO — один сертификат/курс из пула должности."""
    name: str = Field(..., min_length=4)
    issuer: str = Field(..., min_length=2)
    year_offset: int = Field(..., ge=0, le=5)


class _GeneratedFields(BaseModel):
    duties: List[str] = Field(..., min_length=5)
    tags: List[str] = Field(..., min_length=3)
    profile_description: str = Field(..., min_length=30)
    tech_opinion_description_ru: str = Field(..., min_length=100)
    tech_opinion_tools_ru: List[_Tool] = Field(..., min_length=3)
    tech_opinion_steps_ru: List[_Step] = Field(..., min_length=4)
    tech_opinion_grounds_ru: List[str] = Field(..., min_length=2)
    tech_opinion_contract_clause_ru: str = Field(..., min_length=30)
    international_analog_ru: str = Field(..., min_length=3)
    # Pack 50.22 — код ОКЗ (Optional: если LLM не уверена, пусто)
    okz_code: Optional[str] = Field(default="")
    # Pack CV-AUTO — поля для блоков CV
    cv_skills_summary_ru: str = Field(..., min_length=40)
    cv_hobbies_pool_ru: List[str] = Field(..., min_length=6, max_length=6)
    cv_certificates_pool: List["_Certificate"] = Field(..., min_length=6, max_length=6)


# ============================================================== Input schema
class PositionGenerateInput(BaseModel):
    """Тело запроса к /admin/positions/generate-russian."""
    title_ru: str = Field(..., min_length=2)
    title_es: str = Field(..., min_length=2)
    primary_specialty_id: int = Field(...)
    level: int = Field(..., ge=1, le=4)
    # Опциональные подсказки если менеджер ввёл
    title_ru_genitive: Optional[str] = None
    profile_description_existing: Optional[str] = None
    salary_rub_default: Optional[float] = None
    # Имя специальности для контекста (резолвится в endpoint'е)
    specialty_name: Optional[str] = None
    specialty_code: Optional[str] = None


# ============================================================== System prompt
_LEVEL_NAMES = {
    1: "Junior (начинающий специалист, до 1 года опыта)",
    2: "Middle (самостоятельный специалист, 1+ год опыта)",
    3: "Senior (эксперт, наставник, 5+ лет опыта)",
    4: "Lead (руководитель направления/команды)",
}


_SYSTEM_PROMPT = """Ты — эксперт по составлению должностных профилей и документов для виз Digital Nomad Visa Испании. Твоя задача — по краткой вводной (название должности, специальность, уровень) сгенерировать ПОЛНЫЙ профиль должности на русском языке для базы данных.

Профиль состоит из 9 полей:

1. **duties** (список из 9-11 строк) — конкретные обязанности, КАЖДАЯ начинается с глагола несовершенного вида («разработка», «ведение», «контроль», «координация»). Каждая обязанность 6-15 слов. Должны отражать офисный/удалённый характер труда, использование цифровых инструментов. БЕЗ нумерации и маркеров — просто строки.

2. **tags** (список из 5-8 строк) — ключевые слова для LLM-матчинга кандидатов: технологии, ПО, отрасли, навыки. Короткие (1-3 слова). Пример для аналитика: ["SQL", "Power BI", "ETL", "аналитика данных", "Python", "статистика"].

3. **profile_description** (строка 200-400 символов) — описание «как выглядит идеальный кандидат» для LLM-матчинга. Один абзац. Включает: тип специалиста, опыт, основные технологии/задачи, тип компаний где работает.

4. **tech_opinion_description_ru** (строка 250-450 символов) — официальное описание деятельности для §1 «Технического заключения о дистанционном характере». Перечисляет конкретные виды работ через точку с запятой, в третьем лице. Пример: «сбор данных из ERP-систем; построение отчётов в Power BI; разработка моделей прогнозирования; ведение технической документации в облачной среде; координация с межфункциональными командами через видеоконференции; электронный документооборот, подписание актов оказанных услуг.»

5. **tech_opinion_tools_ru** (список из 5-7 объектов {name, purpose}) — цифровые инструменты которые работник использует. Формат:
   - name: название ПО или категория, например «SAP / Oracle ERP» или «Microsoft Excel»
   - purpose: для чего, 4-8 слов, например «удалённый доступ к производственным данным» или «статистический анализ»
   Должны быть РЕАЛИСТИЧНЫМИ для специальности — не «Photoshop» для бухгалтера.

6. **tech_opinion_steps_ru** (список из 6-8 объектов {title, body}) — шаги типового рабочего процесса. Формат:
   - title: краткое название шага, 2-5 слов, пример «Получение задачи от заказчика»
   - body: описание что делается на этом шаге, 2-3 предложения. КАЖДЫЙ шаг подчёркивает что выполняется онлайн/удалённо.

7. **tech_opinion_grounds_ru** (список из 2-3 строк) — основания почему физическое присутствие не требуется для ЭТОЙ профессии. Каждая — связное предложение 30-60 слов. Должна быть СПЕЦИФИЧНА для данной профессии (упоминать конкретные инструменты, технологии, отраслевые практики), а не общие фразы.

8. **tech_opinion_contract_clause_ru** (строка 80-180 символов) — формулировка о дистанционности для договора. Формальный язык. Пример: «Услуги по сбору, обработке и визуализации данных оказываются дистанционно с использованием специализированного программного обеспечения и облачных систем совместной работы.»

9. **international_analog_ru** (строка 20-80 символов) — английский эталон должности (через «или» если несколько вариантов), пример: «data analyst или business intelligence analyst». Используется во фразе «должность аналогична позиции ___ в международной практике».

11. **cv_skills_summary_ru** (строка 80-220 символов) — короткое описание ключевых навыков и инструментов специалиста для блока «Дополнительная информация» в CV. 1-3 предложения, разделённых точкой с запятой или точкой. КОНКРЕТНО упоминай технологии/методологии/инструменты, без воды. Пример для PM в IT: «Навыки координации проектов с использованием цифровых платформ и систем управления задачами. Опыт работы по методологиям Agile и Scrum, владение Jira, Confluence, BPMN, UML, SQL и инструментами бизнес-анализа.» Пример для геодезиста: «Уверенное владение AutoCAD, MicroStation, Credo Топоплан, обработка данных лазерного сканирования. Опыт работы с ортофотопланами и кадастровым программным обеспечением.»

12. **cv_hobbies_pool_ru** (массив РОВНО 6 строк) — пул правдоподобных хобби, подходящих под профиль должности и под нарратив digital-nomad (готовность к жизни в новой стране). Должны быть РАЗНЫМИ по характеру: смесь интеллектуальных, активных, культурных и социальных интересов. Каждая строка 2-6 слов. Запрещены клише («чтение книг» без уточнения, «прогулки»). Хорошие примеры: «путешествия по Европе», «изучение испанского языка», «фотография архитектуры», «велотуризм», «современная литература», «приготовление национальной кухни», «настольный теннис», «йога и медитация», «волонтёрские IT-проекты», «коллекционирование винила». Хобби должны быть РЕАЛИСТИЧНЫМИ для специалиста этой профессии и уровня.

13. **cv_certificates_pool** (массив РОВНО 6 объектов {name, issuer, year_offset}) — пул правдоподобных профильных сертификатов/курсов:
    - name: название сертификата/курса, 4-12 слов на русском (название самого сертификата может содержать английские термины — «PMI Project Management Professional», «AWS Certified Solutions Architect» и т.п.)
    - issuer: организация-эмитент (Coursera, Stepik, Skillbox, PMI, Microsoft, локальный учебный центр, профильный вуз)
    - year_offset: целое 0..5 — на сколько лет ПОСЛЕ окончания вуза получен сертификат. 0 = в год выпуска, 3 = через 3 года. Распределяй разные offset для разных сертификатов, чтобы видна была карьерная динамика.
    
    Сертификаты должны быть СПЕЦИФИЧНЫ для должности и реалистичны для уровня. Не назначай Senior-сертификаты Junior'у. Эмитенты должны существовать в реальности.

10. **okz_code** (строка, формат «NNNN.N») — код по Общероссийскому классификатору занятий (ОКЗ ОК 010-2014) для этой профессии. ВАЖНО: это юридически значимый код для справки СФР (СТД-Р), указывай НАИБОЛЕЕ ТОЧНЫЙ 4-значный код базовой группы с подгруппой через точку. Примеры: бизнес-аналитик — «2421.9», инженер-проектировщик — «2142.9», разработчик ПО — «2512.1», врач-терапевт — «2211.1». Если профессия не вписывается точно — выбери ближайшую группу ОКЗ. НЕ выдумывай несуществующие коды.

ВАЖНЫЕ ПРАВИЛА:
- НЕ копируй мой шаблон фраз — пиши под КОНКРЕТНУЮ должность
- НЕ выдумывай факты которые не относятся к этой профессии
- Все массивы — БЕЗ нумерации и маркеров
- Стиль формальный, как в документах для консульства
- Названия программ (AutoCAD, SAP, Power BI и т.д.) — БЕЗ перевода
- Не используй термин «удалёнка» — только «дистанционно», «удалённый доступ»

ФОРМАТ ОТВЕТА — СТРОГО JSON, без markdown-блоков, без префиксов:
{
  "duties": ["...", "...", ...],
  "tags": ["...", "...", ...],
  "profile_description": "...",
  "tech_opinion_description_ru": "...",
  "tech_opinion_tools_ru": [{"name": "...", "purpose": "..."}, ...],
  "tech_opinion_steps_ru": [{"title": "...", "body": "..."}, ...],
  "tech_opinion_grounds_ru": ["...", "..."],
  "tech_opinion_contract_clause_ru": "...",
  "international_analog_ru": "...",
  "okz_code": "2421.9",
  "cv_skills_summary_ru": "Навыки... Опыт работы по методологиям...",
  "cv_hobbies_pool_ru": ["путешествия по Европе", "изучение испанского", "фотография архитектуры", "велотуризм", "современная литература", "йога"],
  "cv_certificates_pool": [
    {"name": "PMI Project Management Professional", "issuer": "PMI", "year_offset": 2},
    {"name": "Certified Scrum Master (CSM)", "issuer": "Scrum Alliance", "year_offset": 1},
    {"name": "Системный анализ и моделирование", "issuer": "Coursera", "year_offset": 0},
    {"name": "SQL для аналитиков данных", "issuer": "Stepik", "year_offset": 0},
    {"name": "Agile-практики в IT-проектах", "issuer": "Skillbox", "year_offset": 1},
    {"name": "Управление продуктом", "issuer": "Yandex Practicum", "year_offset": 3}
  ]
}
"""


# ============================================================== helper
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    if not raw.startswith("{"):
        m = _JSON_BLOCK_RE.search(raw)
        if m:
            raw = m.group(0)
    return raw.strip()


def _build_user_payload(inp: PositionGenerateInput) -> str:
    level_str = _LEVEL_NAMES.get(inp.level, f"L{inp.level}")
    parts = [
        f"Название должности (рус): {inp.title_ru}",
        f"Название должности (исп): {inp.title_es}",
        f"Специальность: {inp.specialty_code or '?'} {inp.specialty_name or '?'}",
        f"Уровень: L{inp.level} {level_str}",
    ]
    if inp.title_ru_genitive:
        parts.append(f"Название в род. падеже: {inp.title_ru_genitive}")
    if inp.profile_description_existing:
        parts.append(f"Существующее краткое описание (учти как hint): {inp.profile_description_existing}")
    if inp.salary_rub_default:
        parts.append(f"Зарплата ₽/мес: {int(inp.salary_rub_default)} (для контекста уровня и индустрии)")

    payload_lines = "\n".join(parts)
    return (
        "Сгенерируй ПОЛНЫЙ профиль должности для базы данных.\n\n"
        "ВХОДНЫЕ ДАННЫЕ:\n"
        + payload_lines
        + "\n\nВерни СТРОГО JSON по схеме из system prompt. "
          "Никаких ```json``` блоков, никаких пояснений до или после."
    )


# ============================================================== main entry
async def generate_position_fields(inp: PositionGenerateInput) -> Dict[str, Any]:
    """
    Генерирует 9 русских полей Position через LLM.

    Returns: dict в формате PositionUpdate-payload (RU-поля).
    Raises:
        ValueError — если LLM вернула невалидный JSON или не прошла валидация
        RuntimeError — если LLM-клиент не настроен
    """
    client = get_llm_client()
    user_payload = _build_user_payload(inp)

    log.info(
        "Pack 45.0: generating Position fields for title_ru=%r specialty_code=%r level=L%d",
        inp.title_ru, inp.specialty_code, inp.level,
    )

    raw = await client.complete(
        system=_SYSTEM_PROMPT,
        user=user_payload,
        max_tokens=8192,  # Pack CV-AUTO: +3 поля в выводе
        temperature=0.3,
    )

    try:
        clean = _extract_json(raw)
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        log.error("Pack 45.0: invalid JSON from LLM: %s\nRAW: %s", e, raw[:500])
        raise ValueError(f"LLM вернула невалидный JSON: {e}") from e

    try:
        validated = _GeneratedFields.model_validate(data)
    except ValidationError as e:
        log.error("Pack 45.0: schema validation failed: %s\nDATA: %s", e, data)
        raise ValueError(f"Ответ LLM не прошёл валидацию: {e}") from e

    result: Dict[str, Any] = {
        "duties": validated.duties,
        "tags": validated.tags,
        "profile_description": validated.profile_description,
        "tech_opinion_description_ru": validated.tech_opinion_description_ru,
        "tech_opinion_tools_ru": [t.model_dump() for t in validated.tech_opinion_tools_ru],
        "tech_opinion_steps_ru": [s.model_dump() for s in validated.tech_opinion_steps_ru],
        "tech_opinion_grounds_ru": validated.tech_opinion_grounds_ru,
        "tech_opinion_contract_clause_ru": validated.tech_opinion_contract_clause_ru,
        "international_analog_ru": validated.international_analog_ru,
        "okz_code": validated.okz_code or "",  # Pack 50.22
        # Pack CV-AUTO
        "cv_skills_summary_ru": validated.cv_skills_summary_ru,
        "cv_hobbies_pool_ru": validated.cv_hobbies_pool_ru,
        "cv_certificates_pool": [c.model_dump() for c in validated.cv_certificates_pool],
    }

    log.info(
        "Pack 45.0: generated for %r — %d duties, %d tags, %d tools, %d steps, %d grounds",
        inp.title_ru,
        len(result["duties"]),
        len(result["tags"]),
        len(result["tech_opinion_tools_ru"]),
        len(result["tech_opinion_steps_ru"]),
        len(result["tech_opinion_grounds_ru"]),
    )
    return result
