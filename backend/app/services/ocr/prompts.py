"""
OCR prompts for different document types.

Strategy:
- Instructions in English (canonical for LLM)
- Output values preserved in source language (Cyrillic stays Cyrillic, Latin stays Latin)
- Output is strict JSON, no markdown wrapping
- All fields nullable — return null if not visible/unclear
- No hallucinations: if uncertain, return null instead of guessing

Each prompt returns a flat JSON object with snake_case keys.
The recognizer parses this JSON and maps fields to ApplicantData / education entries.
"""


RUSSIAN_PASSPORT_MAIN_PROMPT = """You are an expert OCR system specialized in Russian internal passports (общегражданский паспорт РФ).

Look at the attached image of the main spread of a Russian passport (the page with the photo).

Extract the following fields and return STRICTLY a JSON object. No markdown, no preamble, no commentary — only raw JSON.

Fields to extract:
- last_name_native: Фамилия (Cyrillic, exactly as written)
- first_name_native: Имя (Cyrillic, exactly as written)
- middle_name_native: Отчество (Cyrillic, exactly as written; null if absent)
- birth_date: Дата рождения in ISO format YYYY-MM-DD
- birth_place_native: Место рождения (Cyrillic, exactly as written, with all abbreviations preserved)
- sex: "H" for мужской (male), "M" for женский (female)
- passport_series: Серия паспорта (4 digits, may have a space — return without space)
- passport_number: Номер паспорта (6 digits)
- passport_issue_date: Дата выдачи in ISO format YYYY-MM-DD
- passport_issuer: Кем выдан (Cyrillic, full text as written)
- passport_issuer_code: Код подразделения (format NNN-NNN)

Rules:
- If a field is not visible, blurred, or you are uncertain → return null for that field
- DO NOT guess or extrapolate
- DO NOT translate Russian to English
- Dates: convert from DD.MM.YYYY to YYYY-MM-DD
- Names: preserve original capitalization (usually all caps in passport)

Output schema:
{
  "last_name_native": "ИВАНОВ" or null,
  "first_name_native": "СЕРГЕЙ" or null,
  "middle_name_native": "ПЕТРОВИЧ" or null,
  "birth_date": "1985-03-15" or null,
  "birth_place_native": "ГОР. МОСКВА" or null,
  "sex": "H" or "M" or null,
  "passport_series": "4510" or null,
  "passport_number": "123456" or null,
  "passport_issue_date": "2010-05-20" or null,
  "passport_issuer": "ОТДЕЛОМ УФМС РОССИИ ПО ГОР. МОСКВЕ" or null,
  "passport_issuer_code": "770-001" or null
}

Return ONLY the JSON object."""


RUSSIAN_PASSPORT_ADDRESS_PROMPT = """You are an expert OCR system specialized in Russian internal passports.

Look at the attached image — this is the page with the registration stamp (страница 5 — прописка).

Extract the registration address.

Return STRICTLY a JSON object. No markdown, no preamble — only raw JSON.

Fields to extract:
- registration_address: Полный адрес регистрации one line (Cyrillic, with all abbreviations preserved as written)
- registration_date: Дата регистрации in ISO format YYYY-MM-DD (the most recent registration if multiple stamps)

Rules:
- If multiple registration stamps exist, return the LATEST (most recent) one
- If no registration is visible, return null for both fields
- Preserve original abbreviations: г., ул., д., кв., обл., р-н, etc.
- Single line, comma-separated parts

Output schema:
{
  "registration_address": "г. Москва, ул. Ленина, д. 10, кв. 5" or null,
  "registration_date": "2015-09-12" or null
}

Return ONLY the JSON object."""


FOREIGN_PASSPORT_PROMPT = """You are an expert OCR system specialized in Russian international passports (загранпаспорт РФ).

Look at the attached image — this is the data page of a Russian foreign passport.

The passport contains data in BOTH Russian (Cyrillic) and English (Latin transliteration).
Extract the LATIN versions for name fields, but extract the original passport metadata as written.

Return STRICTLY a JSON object. No markdown, no preamble — only raw JSON.

Fields to extract:
- last_name_latin: Фамилия (LATIN/English transliteration, e.g. "IVANOV")
- first_name_latin: Имя (LATIN/English, e.g. "SERGEI" or "SERGEY")
- last_name_native: Фамилия (Cyrillic)
- first_name_native: Имя (Cyrillic)
- birth_date: Дата рождения in ISO format YYYY-MM-DD
- birth_place_latin: Место рождения in LATIN (e.g. "MOSCOW", "SAINT-PETERSBURG")
- sex: "H" for male/M, "M" for female/F
- nationality: Country code (3-letter, e.g. "RUS")
- passport_number: Номер паспорта (9 digits, e.g. "123456789")
- passport_issue_date: Дата выдачи in ISO format YYYY-MM-DD
- passport_expiry_date: Дата окончания in ISO format YYYY-MM-DD
- passport_issuer: Кем выдан (as written, may be like "ФМС 77001")

Rules:
- If a field is unclear or not visible → return null
- For sex: passport shows "M / М" for male, "F / Ж" for female. Return "H" for male, "M" for female (this matches our DB enum)
- For nationality: convert "RUS" / "RUSSIAN FEDERATION" → "RUS"
- For Latin names: preserve as written in passport (capitalization)

Output schema:
{
  "last_name_latin": "IVANOV" or null,
  "first_name_latin": "SERGEI" or null,
  "last_name_native": "ИВАНОВ" or null,
  "first_name_native": "СЕРГЕЙ" or null,
  "birth_date": "1985-03-15" or null,
  "birth_place_latin": "MOSCOW" or null,
  "sex": "H" or "M" or null,
  "nationality": "RUS" or null,
  "passport_number": "123456789" or null,
  "passport_issue_date": "2020-01-15" or null,
  "passport_expiry_date": "2030-01-14" or null,
  "passport_issuer": "ФМС 77001" or null
}

Return ONLY the JSON object."""


DIPLOMA_PROMPT = """You are an expert OCR system specialized in higher education diplomas (диплом о высшем образовании).

Look at the attached image — this is a diploma page (Russian or post-Soviet).

Extract education information.

Return STRICTLY a JSON object. No markdown, no preamble — only raw JSON.

Fields to extract:
- institution: Полное название учебного заведения (university/institute name, in original language as written)
- graduation_year: Год окончания (4-digit year as integer)
- degree: Степень — one of these exact values:
  - "bachelor" (бакалавр)
  - "specialist" (специалист, dipломированный специалист)
  - "master" (магистр)
  - "phd" (кандидат наук, доктор наук)
  - "secondary" (средне-специальное / колледж / техникум)
  - null if cannot determine
- specialty: Специальность / направление подготовки (full text as written, in original language)
- diploma_number: Номер диплома (if visible, format may vary)
- diploma_series: Серия диплома (if separate from number)
- issue_date: Дата выдачи диплома in ISO format YYYY-MM-DD (if visible)

Rules:
- If field not visible/unclear → null
- For degree: choose ONLY from the listed values, do not invent new values
- Preserve original language for institution and specialty (Russian, English, etc.)
- Old Soviet diplomas: "инженер", "учитель" etc. → "specialist"
- "Магистр" → "master", "Бакалавр" → "bachelor"

Output schema:
{
  "institution": "Московский Государственный Университет им. М.В. Ломоносова" or null,
  "graduation_year": 2007 or null,
  "degree": "specialist" or null,
  "specialty": "Прикладная математика и информатика" or null,
  "diploma_number": "1234567" or null,
  "diploma_series": "АВ" or null,
  "issue_date": "2007-06-30" or null
}

Return ONLY the JSON object."""


# Map document type → prompt
PROMPT_BY_DOC_TYPE = {
    "passport_internal_main": RUSSIAN_PASSPORT_MAIN_PROMPT,
    "passport_internal_address": RUSSIAN_PASSPORT_ADDRESS_PROMPT,
    "passport_foreign": FOREIGN_PASSPORT_PROMPT,
    "diploma_main": DIPLOMA_PROMPT,
    # diploma_apostille — no OCR (just stored), the apostille text is not needed for the form
}
