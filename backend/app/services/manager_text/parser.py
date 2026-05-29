"""
Pack 50.38 — Парсер текста менеджера → структурированные поля заявки.

Менеджер присылает в Telegram полуструктурированное сообщение со всей инфой
по кейсу (applicant, company, position, адрес в Испании, представитель подачи,
диплом). Этот сервис извлекает поля через LLM (text-only, как company_extractor
и generate_declensions) в строгий JSON.

Образец входа:
  "Юсуф Ерул  Nombre: YUSUF  Apellidos: ERUL  Fecha de nacimiento: 20/06/2001
   Sexo: Hombre  Nacionalidad: Turquía ... Компания SOCIEDAD LIMITADA "RENKONS..."
   Должность Аналитик ... Подача через сертификат ANNA TELEPNEVA Z3314769Z ..."

Выход — dict с секциями: applicant / company / position / spain_address /
representative / dates / diploma + unrecognized[] (что не распозналось/неясно).

Используется на этапе apply (Pack 50.40) для заполнения заявки; нераспознанное
кладётся в notes заявки.

Паттерн повторяет app/services/company_extractor.py (text → LLM → dict).
"""
import json
import logging
from typing import Optional

from app.services.llm import get_llm_client

log = logging.getLogger(__name__)


class ManagerTextParseError(Exception):
    """Не удалось распарсить текст менеджера."""
    pass


MANAGER_TEXT_PROMPT = """You are an expert data-extraction assistant for a Spanish visa agency.

A manager sends a free-form message (mixing Russian, Spanish, and Latin text) containing all the data needed to fill a visa application case. Extract the data into a STRICT JSON object.

Return ONLY raw JSON — no markdown, no preamble, no commentary.

ALL fields are nullable: if a value is not present or you are uncertain, return null. NEVER guess or invent values.

Preserve source script:
- Latin names/values stay Latin (e.g. "YUSUF", "ERUL", "RENKONS KHEVI INDASTRIS")
- Cyrillic stays Cyrillic
- Do NOT translate or transliterate — copy exactly as written

Extract into this schema:

{
  "applicant": {
    "first_name_latin": "YUSUF" or null,
    "last_name_latin": "ERUL" or null,
    "first_name_native": null,         // Cyrillic given name if present
    "last_name_native": null,          // Cyrillic surname if present
    "middle_name_native": null,        // отчество (Cyrillic) if present
    "birth_date": "2001-06-20" or null,   // ISO YYYY-MM-DD (convert from DD/MM/YYYY or DD.MM.YYYY)
    "sex": "H" or "M" or null,         // H = male (Hombre/Мужской), M = female (Mujer/Женский)
    "nationality": "TUR" or null,      // ISO 3-letter (Turquía→TUR, Rusia→RUS, etc.)
    "birth_country": "TUR" or null,    // ISO 3-letter country of birth
    "birth_place_latin": "BATMAN" or null,  // city/place of birth in Latin
    "passport_number": "U25998306" or null,
    "father_name": "MEHMET ALI" or null,
    "mother_name": "CANAN" or null,
    "email": "yusuf.erul@icloud.com" or null,
    "phone": "627901730" or null       // phone as written (keep + and digits)
  },
  "spain_address": {
    "raw": "Carrer de Llull, 185, Piso 5 puerta 2, 08005 Barcelona" or null,  // full address one line
    "street": "Carrer de Llull, 185" or null,
    "floor_door": "Piso 5 puerta 2" or null,
    "postal_code": "08005" or null,
    "city": "Barcelona" or null
  },
  "company": {
    "name": "SOCIEDAD LIMITADA \\"RENKONS KHEVI INDASTRIS\\"" or null,  // exactly as written
    "inn": null,                       // ИНН if present
    "kpp": null
  },
  "position": {
    "title": "Аналитик производственных процессов" or null  // exactly as written
  },
  "representative": {
    "full_name": "ANNA TELEPNEVA" or null,   // person submitting via certificate
    "nie": "Z3314769Z" or null,              // NIE/NIF of representative
    "address": "Carrer de Valencia 178, 5-1, 08011 Barcelona" or null,
    "phone": "661853441" or null,
    "email": "Moscu27918@gmail.com" or null,
    "submission_method": "certificate" or null  // "certificate" if "через сертификат", else null
  },
  "submission": {
    "city": "Barcelona" or null,       // city where application is SUBMITTED (подача): "подача Barcelona/Madrid", or a standalone "Barcelona"/"Madrid" indicating submission. NOT the residential address city.
    "province": null                   // province of submission if explicitly stated (usually omitted)
  },
  "dates": {
    "submission_date": null,           // ISO date if a submission date is mentioned
    "contract_sign_date": null
  },
  "diploma": {
    "status": "awaiting" or null       // "awaiting" if "диплом жду"/"diploma жду"; "ready" if present
  },
  "unrecognized": [
    // array of strings: any meaningful pieces of the message you could NOT confidently
    // map to a field above. Include them so the manager can review.
    // Example: "Barcelona Extra 🍬" (unclear tag)
  ]
}

Rules:
- sex: "Hombre"/"мужской"/"М" → "H"; "Mujer"/"женский"/"Ж" → "M"
- nationality & birth_country: country name → ISO 3-letter (Turquía→TUR, España→ESP, Rusia→RUS)
- Dates: any format → ISO YYYY-MM-DD
- For company.name and position.title: copy the FULL text exactly, do not abbreviate
- submission_method: "certificate" when message says "через сертификат" / "via certificate"
- submission.city: the city where the case is SUBMITTED (подача). Look for "подача Barcelona", "подача Madrid", "подача в Барселоне/Мадриде", or a standalone city tag. This is usually Barcelona or Madrid. Do NOT confuse with the residential address (spain_address) — that is where the applicant LIVES. If only the residential address is given and no separate submission city, leave submission.city null.
- If the same datum appears twice, use the most complete version
- Put anything ambiguous or unmappable into "unrecognized"

Return ONLY the JSON object."""


def _extract_json(text: str) -> dict:
    """Парсит JSON из ответа LLM (снимает markdown-обёртку если есть)."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    fb = text.find("{")
    lb = text.rfind("}")
    if fb != -1 and lb != -1 and lb > fb:
        text = text[fb:lb + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ManagerTextParseError(f"Failed to parse LLM response as JSON: {e}\nResponse: {text[:500]}")


async def parse_manager_text(text: str) -> dict:
    """Извлекает поля заявки из свободного текста менеджера.

    Returns: dict со секциями applicant/company/position/spain_address/
    representative/dates/diploma + unrecognized[].

    Raises ManagerTextParseError при пустом вводе или ошибке LLM.
    """
    if not text or not text.strip():
        raise ManagerTextParseError("Empty manager text")

    client = get_llm_client()
    user_message = f"{MANAGER_TEXT_PROMPT}\n\n=== MANAGER MESSAGE ===\n{text.strip()}\n=== END ==="

    try:
        if hasattr(client, "complete_text"):
            response_text = await client.complete_text(
                system="You are a precise data-extraction assistant. Always return strict JSON.",
                user=user_message,
                max_tokens=2048,
                temperature=0.0,
            )
        else:
            # Fallback — text-only через vision с 1×1 заглушкой (как generate_declensions)
            import io
            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (1, 1), color="white").save(buf, format="JPEG")
            response_text = await client.complete_vision(
                system="You are a precise data-extraction assistant. Always return strict JSON.",
                user=user_message,
                image_bytes=buf.getvalue(),
                image_media_type="image/jpeg",
                max_tokens=2048,
                temperature=0.0,
            )
    except Exception as e:
        log.error(f"Manager-text LLM error: {e}", exc_info=True)
        raise ManagerTextParseError(f"LLM API error: {e}")

    parsed = _extract_json(response_text)
    if not isinstance(parsed, dict):
        raise ManagerTextParseError(f"Expected JSON object, got {type(parsed).__name__}")

    # гарантируем наличие секций (чтобы потребитель не падал на отсутствии ключей)
    for section in ("applicant", "spain_address", "company", "position",
                    "representative", "submission", "dates", "diploma"):
        parsed.setdefault(section, {})
    parsed.setdefault("unrecognized", [])

    log.info(f"Manager-text parsed sections: {[k for k, v in parsed.items() if v]}")
    return parsed
