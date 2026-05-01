"""
OCR prompts for different document types.

Strategy:
- Instructions in English (canonical for LLM)
- Output values preserved in source language (Cyrillic stays Cyrillic, Latin stays Latin)
- Output is strict JSON, no markdown wrapping
- All fields nullable — return null if not visible/unclear
- No hallucinations: if uncertain, return null instead of guessing

Pack 14a: added prompts for foreign-client documents:
- PASSPORT_NATIONAL_PROMPT — national passport of any country (not Russian)
- RESIDENCE_CARD_PROMPT — residence permit / residence card
- CRIMINAL_RECORD_PROMPT — criminal record certificate
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
  - "specialist" (специалист, дipломированный специалист)
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


# ============================================================================
# Pack 14a — новые промпты для иностранных документов
# ============================================================================

PASSPORT_NATIONAL_PROMPT = """You are an expert OCR system specialized in NATIONAL passports of various countries (NOT Russian internal passports — those have their own specialized prompt).

Examples of countries: Turkey, Kazakhstan, Ukraine, Belarus, Armenia, Azerbaijan, Tajikistan, Uzbekistan, Kyrgyzstan, Georgia, Moldova, Israel, Germany, Poland, Serbia, etc.

Look at the attached image — this is a passport data page (with photo and personal information).

Most modern passports have data in dual format: native script + Latin transliteration. ALWAYS prefer Latin/Roman script for name fields.

Many passports also have an MRZ (machine-readable zone) at the bottom — two lines of text with "<<<<" separators. If MRZ is visible, use it to verify name spelling.

Return STRICTLY a JSON object. No markdown, no preamble — only raw JSON.

Fields to extract:
- last_name_latin: Surname in Latin (e.g. "YUKSEL", "NAZARBAYEV", "MULLER")
- first_name_latin: Given name(s) in Latin (e.g. "VEDAT", "NURSULTAN", "HANS-PETER")
- last_name_native: Surname in native script (Cyrillic / Arabic / Hebrew / etc.) — null if passport only shows Latin
- first_name_native: Given name in native script — null if passport only shows Latin
- birth_date: Date of birth in ISO format YYYY-MM-DD
- birth_place: Place of birth as written (in whichever script appears)
- sex: "H" for male, "M" for female (matches our DB enum)
- nationality: 3-letter ISO 3166-1 alpha-3 country code (TUR, KAZ, UKR, BLR, ARM, AZE, GEO, ISR, DEU, POL, SRB, etc.)
- passport_country: 3-letter country code of issuing country (often same as nationality)
- passport_number: Passport number as written (format varies by country)
- passport_issue_date: Date of issue in ISO format YYYY-MM-DD
- passport_expiry_date: Date of expiry in ISO format YYYY-MM-DD
- passport_issuer: Issuing authority as written (e.g. "Ministry of Internal Affairs", "Министерство иностранных дел")

Rules:
- If a field is unclear or not visible → return null
- For sex: passports use various conventions:
  - "M" / "MALE" / "ER" (Turkish for male) / "Мужской" → "H"
  - "F" / "FEMALE" / "K" (Turkish for female "Kadın") / "Женский" → "M"
- For 3-letter country codes — use ISO 3166-1 alpha-3:
  - Turkey → TUR, Kazakhstan → KAZ, Ukraine → UKR, Belarus → BLR
  - Armenia → ARM, Azerbaijan → AZE, Georgia → GEO, Israel → ISR
  - Germany → DEU, Poland → POL, Serbia → SRB, Moldova → MDA
- Dates: convert from any format to YYYY-MM-DD

Output schema:
{
  "last_name_latin": "YUKSEL" or null,
  "first_name_latin": "VEDAT" or null,
  "last_name_native": null,
  "first_name_native": null,
  "birth_date": "1972-01-01" or null,
  "birth_place": "EDIRNE" or null,
  "sex": "H" or "M" or null,
  "nationality": "TUR" or null,
  "passport_country": "TUR" or null,
  "passport_number": "U12345678" or null,
  "passport_issue_date": "2020-05-15" or null,
  "passport_expiry_date": "2030-05-14" or null,
  "passport_issuer": "Ministry of Internal Affairs" or null
}

Return ONLY the JSON object."""


RESIDENCE_CARD_PROMPT = """You are an expert OCR system specialized in residence permits and residence cards from various countries.

Examples: Polish "Karta Pobytu", German "Aufenthaltstitel", Czech "Povolení k pobytu", Spanish "TIE", Italian "Permesso di Soggiorno", Hungarian residence card, etc.

Look at the attached image — this is a residence permit / residence card.

The card identifies a person who is a foreigner residing in the issuing country. Often there's a holder photo, name, nationality, and validity dates.

Return STRICTLY a JSON object. No markdown, no preamble — only raw JSON.

Fields to extract:
- last_name_latin: Surname in Latin (e.g. "YUKSEL")
- first_name_latin: Given name(s) in Latin (e.g. "VEDAT")
- birth_date: Date of birth in ISO format YYYY-MM-DD
- sex: "H" for male, "M" for female
- nationality: 3-letter ISO country code of holder's nationality (NOT the issuing country)
- residence_country: 3-letter ISO country code of country that issued this card (POL, DEU, CZE, ESP, ITA, HUN, etc.)
- card_number: Card number / document number as written
- permit_type: Type of residence permit as written (e.g. "ZEZWOLENIE NA POBYT CZASOWY", "PERMANENT RESIDENCE", "EU LONG-TERM RESIDENT", "TIE", "STUDENT VISA")
- issue_date: Date of issue in ISO format YYYY-MM-DD (if visible)
- expiry_date: Date of expiry in ISO format YYYY-MM-DD

Rules:
- nationality is the HOLDER's nationality (e.g. "TUR" for Turkish citizen with Polish residence card)
- residence_country is who ISSUED the card (e.g. "POL" for Karta Pobytu)
- For sex: "M" → "H", "F"/"K" → "M"
- For 3-letter country codes — use ISO 3166-1 alpha-3
- If permit_type is bilingual (e.g. native + English), prefer the native language version

Output schema:
{
  "last_name_latin": "YUKSEL" or null,
  "first_name_latin": "VEDAT" or null,
  "birth_date": "1972-01-01" or null,
  "sex": "H" or "M" or null,
  "nationality": "TUR" or null,
  "residence_country": "POL" or null,
  "card_number": "RR7996940" or null,
  "permit_type": "ZEZWOLENIE NA POBYT CZASOWY" or null,
  "issue_date": null,
  "expiry_date": "2026-06-02" or null
}

Return ONLY the JSON object."""


CRIMINAL_RECORD_PROMPT = """You are an expert OCR system specialized in criminal record certificates (справка о несудимости / police clearance certificate).

Examples: Russian "справка об отсутствии судимости", Turkish "Adli Sicil Kaydı", Polish "Zaświadczenie o niekaralności", Spanish "Certificado de Antecedentes Penales", US "Background check", etc.

Look at the attached image — this is a criminal record certificate (apostilled or notarized for use abroad).

The document confirms whether the person has any criminal record. For visa purposes — usually it confirms NO criminal record.

Return STRICTLY a JSON object. No markdown, no preamble — only raw JSON.

Fields to extract:
- last_name_latin: Surname of the person in Latin (transliterated if needed)
- first_name_latin: Given name in Latin
- last_name_native: Surname in native script if shown — null if document is fully in Latin
- first_name_native: Given name in native script — null otherwise
- birth_date: Date of birth in ISO format YYYY-MM-DD
- nationality: 3-letter ISO country code if visible (often shown as "Citizenship" / "Nationality" / "Vatandaşlık")
- issuing_country: 3-letter ISO country code of country that issued the certificate (TUR, RUS, POL, etc.)
- issuing_authority: Name of the authority that issued the certificate as written
- certificate_number: Certificate / document number if shown
- issue_date: Date of issue in ISO format YYYY-MM-DD
- has_criminal_record: boolean — false if certificate confirms NO record (most common case), true if record is present, null if unclear
- expiry_date: Date of expiry in ISO format YYYY-MM-DD if specified (some certificates are valid for a limited time)

Rules:
- The "has_criminal_record" field — read the document carefully:
  - "Has no criminal record" / "не имеет судимости" / "kayıt bulunamamıştır" → false
  - "Has criminal record" / "имеется судимость" → true
  - Unclear → null
- For 3-letter country codes — use ISO 3166-1 alpha-3
- nationality and issuing_country MAY differ (e.g. Turkish citizen got certificate in Poland)

Output schema:
{
  "last_name_latin": "YUKSEL" or null,
  "first_name_latin": "VEDAT" or null,
  "last_name_native": null,
  "first_name_native": null,
  "birth_date": "1972-01-01" or null,
  "nationality": "TUR" or null,
  "issuing_country": "TUR" or null,
  "issuing_authority": "Ministry of Justice" or null,
  "certificate_number": "12345-2025" or null,
  "issue_date": "2025-11-17" or null,
  "has_criminal_record": false,
  "expiry_date": null
}

Return ONLY the JSON object."""


# ============================================================================
# Map document type → prompt
# ============================================================================

PROMPT_BY_DOC_TYPE = {
    # Российские документы
    "passport_internal_main": RUSSIAN_PASSPORT_MAIN_PROMPT,
    "passport_internal_address": RUSSIAN_PASSPORT_ADDRESS_PROMPT,
    "passport_foreign": FOREIGN_PASSPORT_PROMPT,
    "diploma_main": DIPLOMA_PROMPT,
    # diploma_apostille — no OCR (just stored), the apostille text is not needed for the form

    # Pack 14a — иностранные документы
    "passport_national": PASSPORT_NATIONAL_PROMPT,
    "residence_card": RESIDENCE_CARD_PROMPT,
    "criminal_record": CRIMINAL_RECORD_PROMPT,
}
