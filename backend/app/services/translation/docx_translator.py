"""
Pack 15 — DOCX translator (v3 — Pack 15.2).

Pack 15.2 changes vs Pack 15.1:
- Промпт явно требует переводить ИНН → NIF, КПП → KPP, ОГРН → OGRN, БИК → BIC
  (раньше говорил «keep as-is» — это была ошибка)
- Few-shot пример с реквизитной таблицей
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


BATCH_SIZE = 30

_SKIP_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^[\d\s.,\-/:]+$"),
    re.compile(r"^[A-Z]{2,5}\s*\d{6,}$"),
]


# Pack 15.2: jurada-style промпт со словарём из реальных подач.
# КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: ИНН/КПП/ОГРН/БИК ВСЕГДА переводятся (раньше «keep as-is»).
SYSTEM_PROMPT = """You are translating Russian business/legal documents to Spanish as a DRAFT for a sworn translator (traductor jurado MAE) who will review and finalize. Your goal: match the established Spanish jurada conventions so the jurado has minimal corrections to make.

Input: JSON array of text fragments from a Russian document.
Output: JSON array of Spanish translations, EXACTLY same length and order. No commentary. No markdown fences.

═══ ABSOLUTE RULES ═══

1. NEVER MODIFY any Latin-script text already in the input — names of people, companies, addresses, banks. They have been pre-substituted from official documents (passports, EGRYL extracts) and must be preserved character-for-character. If you see "Yuksel Vedat", "INZHGEOSERVIS", "SBERBANK" — output them unchanged.

2. NEVER MODIFY: numbers (1234.56, 100 000), dates in any format (04.05.2025, 2025-05-04, «04» мая 2025 г. — translate ONLY the Russian month name, keep digits/structure), tax IDs and account numbers (the digit strings — but DO translate the LABEL before them, see rule 4), email addresses, phone numbers, document codes (#2026-0003).

3. If a fragment is already in Spanish or English — return it unchanged. If a fragment is a Jinja template marker like {{ var }} — return unchanged.

4. ALWAYS TRANSLATE THESE LABELS (jurada convention — Russian abbreviations are NEVER kept in Cyrillic in the final document):
   - ИНН → NIF (always — it's the equivalent for "tax ID")
   - КПП → KPP (transliteration — Spanish has no equivalent, keep this Latin form)
   - ОГРН → OGRN (transliteration)
   - БИК → BIC (Spanish has its own BIC, same letters)
   - СНИЛС → SNILS (transliteration)
   - ОКПО → OKPO
   - р/с / Р/с / расчётный счёт → c/c (cuenta corriente) or "Cuenta corriente"
   - к/с / К/с / корреспондентский счёт → c/corr or "Cuenta corresponsal"
   - БИК банка → BIC del banco

═══ JURADA GLOSSARY (use these exact translations) ═══

Document types:
- Договор оказания услуг → Contrato de prestación de servicios remunerados
- Акт об оказании услуг / Акт оказанных услуг → Acta de servicios prestados
- Счёт на оплату → Factura
- Резюме → Curriculum Vitae
- Письмо от компании / Письмо-поручение → Carta de la empresa
- Выписка по счёту → Extracto de cuenta
- Справка → Certificado

Roles:
- Исполнитель → el Contratista
- Заказчик → el Cliente
- Генеральный директор → Director General
- Стороны → las Partes

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

Use D. before male names, Dña. before female names.

Legal terms:
- ООО → Sociedad Limitada (in body) / S.L. (after company name in details)
- АО / ОАО → Sociedad Anónima / S.A.
- в дальнейшем именуемый → en lo sucesivo, el / en lo sucesivo denominado
- в лице → representada por
- именуемые в дальнейшем → denominados conjuntamente

Contract structure (section headings):
- Предмет договора → Objeto del Contrato
- Права и обязанности сторон → Derechos y obligaciones de las Partes
- Цена договора и порядок оплаты → Precio del Contrato y procedimiento de pago
- Сроки оказания услуг → Plazos de prestación de los Servicios
- Ответственность сторон → Responsabilidad de las Partes
- Порядок разрешения споров → Procedimiento de Resolución de Disputas
- Прочие условия → Otras Condiciones
- Адреса и реквизиты сторон → Direcciones y datos de las Partes
- Подписи сторон → Firmas de las Partes

Banking and finance:
- руб. / рублей → rublos
- 290 000 (двести девяносто тысяч) рублей → 290 000 (doscientos noventa mil) rublos
- Сбербанк / Сбер → "SBERBANK", S.A.
- Альфа-Банк → "ALFA-BANK", S.A.
- ВТБ → "VTB", S.A.
- день / дни → día / días
- рабочий день → día hábil
- банковский день → día hábil bancario

Addresses:
- ул. / улица → c/ (calle)
- г. → ciudad de
- д. (дом) → № (or just keep house number)
- кв. → piso
- область → región
- проспект → avenida
- Москва → Moscú
- Санкт-Петербург → San Petersburgo
- Other Russian city/street names — TRANSLITERATE (Краснодонская → Krasnodonskaya)
- Юрид. адрес / Юридический адрес → Domicilio social
- Почт. адрес / Почтовый адрес → Dirección postal

Months (translate within dates):
- января → enero, февраля → febrero, марта → marzo, апреля → abril
- мая → mayo, июня → junio, июля → julio, августа → agosto
- сентября → septiembre, октября → octubre, ноября → noviembre, декабря → diciembre

Markers:
- (подпись) → (firma:)
- (печать) / М.П. → (Sello:)

═══ STYLE ═══

- Use formal Spanish (Spain Spanish).
- Use "0,1%" style (comma decimal separator).
- Use «» for inner quotes when copying from Russian.

═══ FEW-SHOT EXAMPLES ═══

Example 1 (body):
Input: ["Граждане Российской Федерации Иванов Иван Иванович, в дальнейшем именуемый «Исполнитель», и ООО «Ромашка», в лице Генерального директора Петрова П.П., именуемое в дальнейшем «Заказчик»"]
Output: ["el ciudadano de la Federación de Rusia D. Ivanov Ivan Ivanovich, en lo sucesivo denominado el «Contratista», y la Sociedad Limitada «Romashka», representada por el Director General D. Petrov P.P., en lo sucesivo denominada el «Cliente»"]

Example 2 (requisites — multi-line cell):
Input: ["Заказчик\\nИНЖГЕОСЕРВИС\\nИНН 2320219620, КПП 232001001\\nЮрид. адрес: ул. Ленина, д. 5, г. Сочи\\nР\\\\с: 40702810000000000001\\nСбербанк\\nБИК банка: 044525225\\nК\\\\с: 30101810400000000225"]
Output: ["El Cliente\\n«INZHGEOSERVIS», S.L.\\nNIF 2320219620, KPP 232001001\\nDomicilio social: c/ Lenina, № 5, ciudad de Sochi\\nc/c: 40702810000000000001\\n«SBERBANK», S.A.\\nBIC del banco: 044525225\\nc/corr: 30101810400000000225"]

Example 3 (requisites with empty fields):
Input: ["Исполнитель:\\nYuksel Vedat\\nПаспорт U23616456,\\nвыдан 08.10.2020 ELAZIĞ\\nNIF\\n—\\n\\nc/c\\nв\\nBIC del banco:\\nc/corr:"]
Output: ["el Contratista:\\nYuksel Vedat\\nPasaporte U23616456,\\nexpedido el 08.10.2020 ELAZIĞ\\nNIF\\n—\\n\\nc/c\\nen\\nBIC del banco:\\nc/corr:"]

Note: Latin-script names (Yuksel Vedat) stay unchanged. Russian abbreviation labels (ИНН, КПП, БИК, ОГРН) ALWAYS become Latin labels (NIF, KPP, BIC, OGRN). Empty values stay as "—".
"""


def _should_skip(text: str) -> bool:
    """Быстрая проверка: нужно ли отправлять текст в LLM."""
    if not text or not text.strip():
        return True
    for pattern in _SKIP_PATTERNS:
        if pattern.match(text):
            return True
    if not re.search(r"[А-Яа-яЁё]", text):
        return True
    return False


def _extract_paragraph_text(p: Paragraph) -> str:
    return "".join(run.text for run in p.runs)


def _set_paragraph_text(p: Paragraph, new_text: str) -> None:
    if not p.runs:
        return
    p.runs[0].text = new_text
    for run in p.runs[1:]:
        run.text = ""


def _collect_all_paragraphs(doc: Document) -> list[Paragraph]:
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
    log.info(f"[translation] Falling back to one-by-one translation for {len(texts)} fragments")
    client = get_llm_client()
    results = []
    single_system = (
        "Translate the following Russian business/legal text to formal Spanish (Spain). "
        "Keep all Latin-script text (names, companies) unchanged. "
        "Translate Russian abbreviations: ИНН→NIF, КПП→KPP, ОГРН→OGRN, БИК→BIC. "
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

    Pack 15.2: pre-substitution теперь покрывает метки ИНН/КПП/ОГРН/БИК → NIF/KPP/etc
    + applicant.full_name_native + company.short_name + None → —.
    """
    doc = Document(io.BytesIO(docx_bytes))
    paragraphs = _collect_all_paragraphs(doc)
    log.info(
        f"[translation] DOCX has {len(paragraphs)} paragraphs"
        + (f", {len(substitutions)} pre-substitutions" if substitutions else "")
    )

    targets: list[tuple[int, str]] = []
    for idx, p in enumerate(paragraphs):
        text = _extract_paragraph_text(p)
        original_text = text  # для сравнения с результатом подстановки

        if substitutions:
            text = substitutions.apply(text)

        # Pack 15.5: КРИТИЧНЫЙ ФИКС.
        # Если pre-substitution что-то заменила, но текст после неё уже не нужно
        # отправлять в LLM (нет кириллицы) — мы ОБЯЗАНЫ записать его в DOCX
        # сейчас. Иначе параграф останется в исходном русском виде, потому что
        # _set_paragraph_text() позже вызывается только для targets (тех что
        # пошли в LLM).
        if text != original_text and _should_skip(text):
            _set_paragraph_text(p, text)
            log.info(f"[translation] Pre-sub-only update for paragraph {idx}")
            continue

        if not _should_skip(text):
            targets.append((idx, text))

    if not targets:
        log.info("[translation] Nothing to translate in this DOCX")
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()

    log.info(f"[translation] {len(targets)} fragments to translate")

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

    for (paragraph_idx, _original), translated_text in zip(targets, all_translations):
        _set_paragraph_text(paragraphs[paragraph_idx], translated_text)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
