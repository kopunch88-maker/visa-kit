# -*- coding: utf-8 -*-
"""
Pack 50.1-C/G — Реестр шаблонов Трудового договора (найм).

Аналог contracts_registry.py (Pack 29.0), но для документов найма.
Используется в:
  - docx_renderer.render_employment_contract: резолвит template_path
    приоритет: company.employment_contract_template_slug → fallback по ИНН
    → None (вызывающий код поднимает 409 NEEDS_EMPLOYMENT_CONTRACT_TEMPLATE).
  - api/companies.list_employment_contract_templates: dropdown для UI.
  - admin/companies UI (CompanyDrawer): вкладка «Найм» в секции «Шаблоны
    договоров».

Структура файлов:
  templates/docx/contracts/naim/by_company/<slug>/employment_contract_template.docx

================================================================================
КАК ДОБАВИТЬ НОВЫЙ ШАБЛОН ТРУДОВОГО ДОГОВОРА
================================================================================

Когда нужно подключить новую наёмную компанию (например, "ТРИУМФ"):

1) Положи docx-шаблон по правильному пути:
   templates/docx/contracts/naim/by_company/triumph/employment_contract_template.docx

   Плейсхолдеры jinja2 используют тот же набор переменных что у factor_stroy:
   {{ company.short_name }}, {{ company.full_name_ru }}, {{ company.tax_id_primary }},
   {{ company.tax_id_secondary }}, {{ company.ogrn }}, {{ company.email }},
   {{ company.legal_address }}, {{ company.bank_name }}, {{ company.bank_account }},
   {{ company.bank_bic }}, {{ company.director_full_name_genitive_ru }},
   {{ company.director_position_ru }}, {{ company.director_short_ru }},
   {{ applicant.full_name_native }}, {{ applicant.citizen_phrase }},
   {{ applicant.passport_formatted }}, {{ applicant.passport_issue_date }},
   {{ applicant.passport_issuer }}, {{ applicant.inn }}, {{ applicant.snils }},
   {{ applicant.home_address }}, {{ applicant.bank_account }},
   {{ applicant.bank_name }}, {{ applicant.bank_bic }},
   {{ applicant.initials_native }}, {{ applicant.email }},
   {{ contract.number }}, {{ contract.sign_city }}, {{ contract.sign_date_str }},
   {{ position.title_ru }}, {{ fmt_money(contract.salary_rub) }},
   {{ contract.salary_rub_words }}, и т.д.

2) Добавь запись в EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY:

     "triumph": {
         "label": "ТРИУМФ — Трудовой договор",
         "path": "templates/docx/contracts/naim/by_company/triumph/employment_contract_template.docx",
         "description": "Кратко: тип занятости, отпускные, особые пункты.",
     },

3) (опционально) Добавь автоматический маппинг по ИНН компании. Тогда менеджеру
   не нужно вручную выбирать шаблон — он подхватится автоматически:

     EMPLOYMENT_COMPANY_INN_TO_SLUG = {
         ...,
         "5038181475": "triumph",  # АО «ТРИУМФ»
     }

4) Если ИНН-маппинг не добавлен — менеджер увидит модалку
   ContractTemplatePickerModal с kind="employment" при попытке генерации
   Трудового договора, выберет шаблон, и slug сохранится в
   company.employment_contract_template_slug.

5) Проверка:
   - Открой Settings → выбери компанию → вкладка «Найм» в секции «Шаблоны
     договоров» → новый slug должен быть в dropdown.
   - Открой EMPLOYMENT-заявку этой компании → скачай 01_Трудовой_договор.docx.

================================================================================
"""

from typing import Optional


# Реестр всех шаблонов Трудовых договоров (slug → метаданные).
# Pack 50.1-C: добавлен factor_stroy.
# Будущие паки добавят: triumph, protech и т.д.
EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY = {
    "factor_stroy": {
        "label": "ФАКТОР СТРОЙ — Трудовой договор",
        "path": "templates/docx/contracts/naim/by_company/factor_stroy/employment_contract_template.docx",
        "description": "Удалённый дистанционный найм; 28 дней отпуск; аванс 18-22/5-7.",
    },
}


# Маппинг tax_id_primary (ИНН) → slug. Используется для авто-резолва шаблона
# по ИНН компании когда у компании нет отдельного employment_contract_template_slug.
EMPLOYMENT_COMPANY_INN_TO_SLUG = {
    "7727286316": "factor_stroy",  # ООО «ФАКТОР СТРОЙ»
    # TODO Pack 50.1-X: после построения шаблонов добавить:
    # "5038181475": "triumph",    # АО «ТРИУМФ»
    # "7810890724": "protech",    # АО «ПроТехнологии»
}


def resolve_employment_contract_template_path(company) -> Optional[str]:
    """
    Pack 50.1-G — резолвит путь к шаблону Трудового договора.

    Порядок:
      1. company.employment_contract_template_slug — если задан и есть
         в реестре, возвращает путь.
      2. fallback: company.tax_id_primary в EMPLOYMENT_COMPANY_INN_TO_SLUG
         — возвращает путь.
      3. Если ничего не нашлось — возвращает None (вызывающий код
         должен поднять 409 NEEDS_EMPLOYMENT_CONTRACT_TEMPLATE).
    """
    # 1. Slug из БД (Pack 50.1-G)
    slug = getattr(company, "employment_contract_template_slug", None)
    if slug and slug in EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY:
        return EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY[slug]["path"]

    # 2. Fallback по ИНН (Pack 50.1-C)
    inn = getattr(company, "tax_id_primary", None)
    if inn and inn in EMPLOYMENT_COMPANY_INN_TO_SLUG:
        fallback_slug = EMPLOYMENT_COMPANY_INN_TO_SLUG[inn]
        return EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY[fallback_slug]["path"]

    # 3. Не найден шаблон
    return None


def get_available_employment_template_options() -> list:
    """
    Возвращает список опций для UI dropdown'а вкладки «Найм».
    Каждая опция: {slug, label, archetype, description}.

    Все элементы помечаются archetype="employment" — UI использует это для
    отображения единого бейджа (в отличие от самозанятых, где есть
    vozmezdnoe / vozmezdnoe_hourly / gph).
    """
    options = []
    for slug in sorted(EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY.keys()):
        meta = EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY[slug]
        options.append({
            "slug": slug,
            "label": meta["label"],
            "archetype": "employment",
            "description": meta["description"],
        })
    return options


def is_employment_template_slug_valid(slug: Optional[str]) -> bool:
    """True если slug валиден (есть в реестре). None или пустая строка → False."""
    return bool(slug) and slug in EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY


def is_employment_template_supported(company) -> bool:
    """Pack 50.1-C — True если для компании есть шаблон (по slug либо по ИНН)."""
    return resolve_employment_contract_template_path(company) is not None
