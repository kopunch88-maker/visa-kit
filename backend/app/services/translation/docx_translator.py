"""
Pack 15 — DOCX translator (v2 — Pack 15.1).

Берёт готовый русский DOCX (bytes), извлекает текст из всех параграфов
(включая ячейки таблиц), переводит через LLM батчами, раскладывает обратно
с сохранением форматирования на уровне параграфа.

Pack 15.1 changes:
- Опциональный SubstitutionDict — заменяет имена на латиницу ДО LLM
- Расширенный jurada-style промпт с глоссарием реальных терминов из подач
- Few-shot пример из реального jurada-перевода

Стратегия сохранения формата:
- Заголовки, выравнивание, шрифты, размеры, цвета — сохраняются (это свойства параграфа)
- Таблицы, списки, отступы — сохраняются (структура XML не трогается)
- Внутри-абзацный жирный/курсив — теряется (текст всех run'ов параграфа
  объединяется и кладётся в первый run; остальные run'ы зачищаются)
"""

import io
import json
import logging
import re
from typing import Optional

from docx import Document
from docx.text.paragraph import Paragraph

from app.services.llm import get_llm_client

from .name_substitution import SubstitutionDict

log = logging.getLogger(__name__)


# Сколько параграфов отправляем за один LLM-вызов
BATCH_SIZE = 30

# Маркер пропуска перевода — числа, даты, реквизиты остаются как есть
_SKIP_PATTERNS = [
    re.compile(r"^\s*$"),                           # пустые
    re.compile(r"^[\d\s.,\-/:]+$"),                 # только цифры/даты/спецсимволы
    re.compile(r"^[A-Z]{2,5}\s*\d{6,}$"),           # типа "RUS 1234567"
]


# Pack 15.1: jurada-style промпт со словарём из реальных подач
SYSTEM_PROMPT = """You are translating Russian business/legal documents to Spanish as a DRAFT for a sworn translator (traductor jurado MAE) who will review and finalize. Your goal: match the established Spanish jurada conventions so the jurado has minimal corrections to make.

Input: JSON array of text fragments from a Russian document.
Output: JSON array of Spanish translations, EXACTLY same length and order. No commentary. No markdown fences.

═══ ABSOLUTE RULES ═══

1. NEVER MODIFY any Latin-script text already in the input — names of people, companies, addresses, banks. They have been pre-substituted from official documents (passports, EGRYL extracts) and must be preserved character-for-character. If you see "Yuksel Vedat", "INZHGEOSERVIS", "SBERBANK" — output them unchanged.

2. NEVER MODIFY: numbers (1234.56, 100 000), dates in any format (04.05.2025, 2025-05-04, «04» мая 2025 г. — translate ONLY the Russian month name, keep digits/structure), tax IDs (NIF, OGRN, KPP, BIC, SNILS, account numbers), email addresses, phone numbers, document codes (#2026-0003).

3. NEVER MODIFY Russian abbreviations: ИНН, ОГРН, КПП, БИК, СНИЛС, ОКПО — keep them as-is (they have no Spanish equivalent).

4. If a fragment is already in Spanish or English — return it unchanged.

5. If a fragment is a Jinja template marker like {{ var }} — return unchanged.

═══ JURADA GLOSSARY (use these exact translations) ═══

Document types:
- Договор оказания услуг → Contrato de prestación de servicios remunerados
- Акт об оказании услуг / Акт оказанных услуг → Acta de servicios prestados
- Счёт на оплату → Factura
- Счёт-фактура → Factura
- Резюме → Curriculum Vitae
- Письмо от компании / Письмо-поручение → Carta de la empresa
- Выписка по счёту → Extracto de cuenta
- Справка → Certificado

Roles:
- Исполнитель → el Contratista
- Заказчик → el Cliente
- Генеральный директор → Director General
- Стороны → las Partes
- Подписавшие ниже / Нижеподписавшиеся → Los abajo firmantes

Citizenship phrases (use exact form, with "el ciudadano de la"):
- Гражданин Российской Федерации → ciudadano de la Federación de Rusia
- Гражданин Турецкой Республики → ciudadano de la República de Turquía
- Гражданин Республики Албания → ciudadano de la República de Albania
- Гражданин Республики Косово → ciudadano de la República de Kosovo
- Гражданин Республики Азербайджан → ciudadano de la República de Azerbaiyán
- Гражданин Украины → ciudadano de Ucrania
- Гражданин Республики Узбекистан → ciudadano de la República de Uzbekistán
- Гражданин Республики Казахстан → ciudadano de la República de Kazajistán
- Гражданин Республики Беларусь → ciudadano de la República de Belarús
- Гражданин Грузии → ciudadano de Georgia
- Гражданин Республики Армения → ciudadano de la República de Armenia
- Гражданин Республики Таджикистан → ciudadano de la República de Tayikistán

Use D. before male names, Dña. before female names (Don/Doña form).

Legal terms:
- ООО (full: Общество с ограниченной ответственностью) → Sociedad Limitada (in body) / S.L. (in details block)
- АО / ОАО (Акционерное общество) → Sociedad Anónima / S.A.
- в дальнейшем именуемый → en lo sucesivo, el / en lo sucesivo denominado
- в лице → representada por
- именуемые в дальнейшем → denominados conjuntamente
- настоящим подтверждает → confirma lo siguiente / por el presente confirma

Contract structure (section headings):
- Предмет договора → Objeto del Contrato
- Права и обязанности сторон → Derechos y obligaciones de las Partes
- Цена договора и порядок оплаты → Precio del Contrato y procedimiento de pago
- Сроки оказания услуг → Plazos de prestación de los Servicios
- Ответственность сторон → Responsabilidad de las Partes
- Порядок разрешения споров → Procedimiento de Resolución de Disputas
- Прочие условия / Иные условия → Otras Condiciones
- Адреса и реквизиты сторон → Direcciones y datos de las Partes
- Подписи сторон → Firmas de las Partes

References within document:
- статья → cláusula
- пункт / п. → cláusula (or "p.")
- раздел → sección
- приложение → anexo
- настоящего Договора → del presente Contrato
- настоящий Договор → el presente Contrato

Banking and finance:
- ИНН → NIF (when listed in details block as company tax ID — leave "ИНН" if standalone label)
- расчётный счёт / р/с → c/c (cuenta corriente)
- корреспондентский счёт / к/с → c/corr
- БИК → BIC
- ОГРН → OGRN
- руб. / рублей → rublos
- 290 000 (двести девяносто тысяч) рублей → 290 000 (doscientos noventa mil) rublos
- Сбербанк → "SBERBANK", S.A.
- Альфа-Банк → "ALFA-BANK", S.A.
- ВТБ → "VTB", S.A.
- Тинькофф / Т-Банк → "TINKOFF", S.A.
- Центральный банк Российской Федерации → Banco Central de la Federación Rusa
- день / дни → día / días
- рабочий день → día hábil
- банковский день → día hábil bancario

Addresses:
- ул. → c/ (calle)
- г. → ciudad de
- д. (дом) → № (or just keep house number with comma)
- кв. → piso
- область → región
- район → distrito
- проспект → avenida / pr.
- Москва → Moscú
- Санкт-Петербург → San Petersburgo
- For all other Russian city/street names — TRANSLITERATE (Краснодонская → Krasnodonskaya, Каменск-Шахтинский → Kamensk-Shakhtinskiy)

Months (translate within dates):
- января → enero, февраля → febrero, марта → marzo, апреля → abril
- мая → mayo, июня → junio, июля → julio, августа → agosto
- сентября → septiembre, октября → octubre, ноября → noviembre, декабря → diciembre

Signature/seal markers in Russian docs:
- (подпись) / [подпись] → (firma:)
- (печать) / М.П. → (Sello:)

═══ STYLE ═══

- Use formal Spanish (Spain Spanish, vos forms NEVER).
- Use Title Case for section headings (1. Objeto del Contrato), but lowercase after numeric prefix in subsections (1.1. El Contratista...).
- Use "0,1%" style (comma decimal separator) — Spanish convention.
- Use «» for inner quotes when copying from Russian, "" elsewhere.

═══ FEW-SHOT EXAMPLE ═══

Input: ["Граждане Российской Федерации Иванов Иван Иванович, в дальнейшем именуемый «Исполнитель», и ООО «Ромашка», в лице Генерального директора Петрова П.П., именуемое в дальнейшем «Заказчик»"]

Output: ["el ciudadano de la Federación de Rusia D. Ivanov Ivan Ivanovich, en lo sucesivo denominado el «Contratista», y la Sociedad Limitada «Romashka», representada por el Director General D. Petrov P.P., en lo sucesivo denominada el «Cliente»"]

Note how:
- "Граждане" became "el ciudadano de la Federación de Rusia D." (with D. honorific)
- Names "Иванов Иван Иванович" stay (in real input they would already be Latin via pre-substitution)
- "ООО" became "Sociedad Limitada"
- Quote style preserved
"""


def _should_skip(text: str) -> bool:
    """Быстрая проверка: нужно ли отправлять текст в LLM."""
    if not text or not text.strip():
        return True
    for pattern in _SKIP_PATTERNS:
        if pattern.match(text):
            return True
    # Если в тексте нет ни одной кириллической буквы — не переводим
    if not re.search(r"[А-Яа-яЁё]", text):
        return True
    return False


def _extract_paragraph_text(p: Paragraph) -> str:
    """Собирает текст параграфа из всех runs."""
    return "".join(run.text for run in p.runs)


def _set_paragraph_text(p: Paragraph, new_text: str) -> None:
    """Кладёт переведённый текст в первый run, остальные зачищает."""
    if not p.runs:
        return
    p.runs[0].text = new_text
    for run in p.runs[1:]:
        run.text = ""


def _collect_all_paragraphs(doc: Document) -> list[Paragraph]:
    """Собирает ВСЕ параграфы документа: тело + ячейки таблиц + headers/footers."""
    paragraphs: list[Paragraph] = []
    paragraphs.extend(doc.paragraphs)

    def _walk_tables(tables):
        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    paragraphs.extend(cell.paragraphs)
                    _walk_tables(cell.tables)

    _walk_tables(doc.tables)

    for section in doc.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            paragraphs.extend(header.paragraphs)
            _walk_tables(header.tables)
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            paragraphs.extend(footer.paragraphs)
            _walk_tables(footer.tables)

    return paragraphs


async def _translate_batch(texts: list[str]) -> list[str]:
    """
    Переводит батч строк через LLM. Возвращает массив переводов той же длины.
    Если LLM вернул не то количество — fallback на по-одному.
    """
    if not texts:
        return []

    client = get_llm_client()
    user_payload = json.dumps(texts, ensure_ascii=False)

    try:
        response = await client.complete(
            system=SYSTEM_PROMPT,
            user=user_payload,
            max_tokens=8192,
            temperature=0.0,
        )
    except Exception as e:
        log.warning(f"[translation] LLM call failed for batch of {len(texts)}: {e}")
        return list(texts)

    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        translated = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.warning(f"[translation] LLM returned non-JSON: {e}. Response head: {cleaned[:300]}")
        return await _translate_one_by_one(texts)

    if not isinstance(translated, list) or len(translated) != len(texts):
        log.warning(
            f"[translation] LLM returned wrong shape: "
            f"expected list of {len(texts)}, got {type(translated).__name__} of "
            f"len={len(translated) if hasattr(translated, '__len__') else '?'}"
        )
        return await _translate_one_by_one(texts)

    result = []
    for i, item in enumerate(translated):
        if isinstance(item, str):
            result.append(item)
        else:
            log.warning(f"[translation] item {i} is not a string: {type(item).__name__}, falling back")
            result.append(texts[i])
    return result


async def _translate_one_by_one(texts: list[str]) -> list[str]:
    """Fallback: переводит каждую строку отдельным LLM-вызовом."""
    log.info(f"[translation] Falling back to one-by-one translation for {len(texts)} fragments")
    client = get_llm_client()
    results = []
    single_system = (
        "Translate the following Russian business/legal text to formal Spanish (Spain). "
        "Keep all Latin-script text (names, companies) unchanged. "
        "Return ONLY the translation, no commentary, no quotes, no markdown."
    )
    for text in texts:
        try:
            response = await client.complete(
                system=single_system,
                user=text,
                max_tokens=1024,
                temperature=0.0,
            )
            results.append(response.strip())
        except Exception as e:
            log.warning(f"[translation] one-by-one failed for text {text[:50]!r}: {e}")
            results.append(text)
    return results


async def translate_docx(
    docx_bytes: bytes,
    substitutions: Optional[SubstitutionDict] = None,
) -> bytes:
    """
    Главная функция: переводит DOCX с русского на испанский.

    Args:
        docx_bytes: содержимое исходного DOCX
        substitutions: Pack 15.1 — словарь замен ru→lat, применяется к каждому
                       параграфу ДО отправки в LLM. Если None — работаем как раньше.

    Returns:
        bytes переведённого DOCX

    Raises:
        Exception: если LLM упал или DOCX невалидный (вверх по стеку — orchestrator
                   ловит и помечает Translation.status = FAILED)
    """
    doc = Document(io.BytesIO(docx_bytes))
    paragraphs = _collect_all_paragraphs(doc)
    log.info(
        f"[translation] DOCX has {len(paragraphs)} paragraphs"
        + (f", {len(substitutions)} pre-substitutions" if substitutions else "")
    )

    # Собираем индексы параграфов которые нужно переводить
    targets: list[tuple[int, str]] = []
    for idx, p in enumerate(paragraphs):
        text = _extract_paragraph_text(p)

        # Pack 15.1: применяем pre-substitution до проверки на skip
        if substitutions:
            text = substitutions.apply(text)

        if not _should_skip(text):
            targets.append((idx, text))

    if not targets:
        log.info("[translation] Nothing to translate in this DOCX")
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()

    log.info(f"[translation] {len(targets)} fragments to translate")

    # Бьём на батчи и переводим
    all_translations: list[str] = []
    for batch_start in range(0, len(targets), BATCH_SIZE):
        batch = targets[batch_start:batch_start + BATCH_SIZE]
        batch_texts = [t[1] for t in batch]
        translated = await _translate_batch(batch_texts)
        all_translations.extend(translated)
        log.info(
            f"[translation] Batch {batch_start // BATCH_SIZE + 1} "
            f"({batch_start + 1}-{batch_start + len(batch)} / {len(targets)}) done"
        )

    # Раскладываем переводы обратно в параграфы
    for (paragraph_idx, _original), translated_text in zip(targets, all_translations):
        _set_paragraph_text(paragraphs[paragraph_idx], translated_text)

    # Сохраняем результат
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
