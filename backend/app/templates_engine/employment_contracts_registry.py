# -*- coding: utf-8 -*-
"""
Pack 50.1-C — Реестр шаблонов Трудового договора (найм).

Аналог contracts_registry.py (Pack 29.0), но для документов найма.
Используется в:
  - docx_renderer.render_employment_contract: резолвит template_path
    по company.tax_id_primary (а в будущем — по отдельному
    company.employment_contract_template_slug, если потребуется).
  - в будущем — admin/companies UI для выбора шаблона трудового договора.

Структура: templates/docx/contracts/naim/by_company/<slug>/employment_contract_template.docx
"""

from typing import Optional


# Реестр всех шаблонов трудовых договоров (slug → метаданные).
# Пока 1 запись — ФАКТОР СТРОЙ. По мере подключения новых наёмных компаний
# добавляются новые слаги: triumph, protech и т.д.
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
    # TODO Pack 50.1-D: после построения шаблонов добавить:
    # "5038181475": "triumph",    # АО «ТРИУМФ»
    # "7810890724": "protech",    # АО «ПроТехнологии»
}


def resolve_employment_contract_template_path(company) -> Optional[str]:
    """
    Pack 50.1-C — резолвит путь к шаблону Трудового договора для компании.

    Порядок:
      1. company.tax_id_primary в EMPLOYMENT_COMPANY_INN_TO_SLUG → возвращает путь.
      2. Если ИНН не в маппинге — возвращает None (вызывающий код должен поднять 409).

    Возвращает str (путь относительно репозитория) либо None.
    """
    inn = getattr(company, "tax_id_primary", None)
    if inn and inn in EMPLOYMENT_COMPANY_INN_TO_SLUG:
        slug = EMPLOYMENT_COMPANY_INN_TO_SLUG[inn]
        return EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY[slug]["path"]
    return None


def get_available_employment_template_options() -> list:
    """
    Возвращает список опций для UI (на будущее).
    Каждая опция: {slug, label, description}.
    """
    options = []
    for slug in sorted(EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY.keys()):
        meta = EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY[slug]
        options.append({
            "slug": slug,
            "label": meta["label"],
            "description": meta["description"],
        })
    return options


def is_employment_template_supported(company) -> bool:
    """True если для компании есть шаблон Трудового договора в реестре."""
    return resolve_employment_contract_template_path(company) is not None
