# -*- coding: utf-8 -*-
"""
Pack 29.0 — Реестр шаблонов договоров.

Единая точка правды: slug ↔ путь к шаблону + метаданные.
Используется в:
  - docx_renderer.render_contract: резолвит template_path по company.contract_template_slug
  - admin/companies UI: список доступных слагов в dropdown при создании компании
  - migrations: pre-seeding company.contract_template_slug по company.tax_id_primary

Структура: templates/docx/contracts/by_company/<slug>/contract_template.docx
Базовый шаблон (fallback): templates/docx/contract_template.docx
"""

from typing import Optional

# Реестр всех шаблонов договоров (slug → метаданные)
CONTRACT_TEMPLATES_REGISTRY = {
    "default": {
        "label": "Базовый шаблон (стандартный возмездный)",
        "path": "templates/docx/contract_template.docx",
        "archetype": "vozmezdnoe",
        "description": "Используется как fallback для компаний без явной привязки.",
    },
    "sk10": {
        "label": "СК10 — Строительная компания",
        "path": "templates/docx/contracts/by_company/sk10/contract_template.docx",
        "archetype": "vozmezdnoe",
        "description": "Договор возмездного оказания услуг, фиксированный месячный оклад.",
    },
    "ssk": {
        "label": "ССК — Сербская строительная компания",
        "path": "templates/docx/contracts/by_company/ssk/contract_template.docx",
        "archetype": "vozmezdnoe",
        "description": "Договор возмездного оказания услуг, есть пункт о валютных расчётах.",
    },
    "kns_grupp": {
        "label": "КНС Групп",
        "path": "templates/docx/contracts/by_company/kns_grupp/contract_template.docx",
        "archetype": "vozmezdnoe_hourly",
        "description": "Договор возмездного оказания услуг с почасовой ставкой.",
    },
    "hayat": {
        "label": "Хаят Консюмер Гудс",
        "path": "templates/docx/contracts/by_company/hayat/contract_template.docx",
        "archetype": "vozmezdnoe",
        "description": "Возмездный + блок конфиденциальности; паспорт в шапке.",
    },
    "avtodom": {
        "label": "АВТОДОМ (АО)",
        "path": "templates/docx/contracts/by_company/avtodom/contract_template.docx",
        "archetype": "vozmezdnoe",
        "description": "Договор АО, возмездное оказание + блок конфиденциальности.",
    },
    "factor_stroy": {
        "label": "ФАКТОР СТРОЙ",
        "path": "templates/docx/contracts/by_company/factor_stroy/contract_template.docx",
        "archetype": "vozmezdnoe",
        "description": "Возмездное; есть пункт пролонгации; форс-мажор; нет КПП в банковских реквизитах.",
    },
    "protech": {
        "label": "ПроТехнологии (АО)",
        "path": "templates/docx/contracts/by_company/protech/contract_template.docx",
        "archetype": "vozmezdnoe",
        "description": "АО Санкт-Петербург, возмездное + блок конфиденциальности.",
    },
    "buki_vedi": {
        "label": "БУКИ ВЕДИ",
        "path": "templates/docx/contracts/by_company/buki_vedi/contract_template.docx",
        "archetype": "vozmezdnoe_hourly",
        "description": "Возмездный с почасовой ставкой; паспорт исполнителя в шапке.",
    },
    "tikompani": {
        "label": "ТИКОмпани",
        "path": "templates/docx/contracts/by_company/tikompani/contract_template.docx",
        "archetype": "vozmezdnoe",
        "description": "Возмездное; есть блок конфиденциальности; пункт об электронном документообороте.",
    },
    "king_david": {
        "label": "КИНГ ДАВИД",
        "path": "templates/docx/contracts/by_company/king_david/contract_template.docx",
        "archetype": "gph",
        "description": "ГПХ (договор подряда с физическим лицом), 'Подрядчик' вместо 'Исполнителя'.",
    },
}

# Маппинг tax_id_primary (ИНН) → slug, для авто-привязки existing компаний
# при применении Pack 29.0 миграции (backfill).
COMPANY_INN_TO_SLUG = {
    "6168006148": "sk10",
    "9705067089": "ssk",
    "7701411241": "kns_grupp",
    "4003040489": "hayat",
    "7714709349": "avtodom",
    "7727286316": "factor_stroy",
    "7810890724": "protech",
    "7706796034": "buki_vedi",
    "7729634103": "tikompani",
    "7731579629": "king_david",
}


def resolve_contract_template_path(company) -> str:
    """
    Резолвит путь к шаблону договора для данной компании.

    Порядок:
      1. company.contract_template_slug — если задан и есть в реестре, возвращает его путь.
      2. fallback: COMPANY_INN_TO_SLUG[company.tax_id_primary] — если ИНН в маппинге.
      3. default: путь базового шаблона (templates/docx/contract_template.docx).

    Возвращает str — путь относительно репозитория.

    ВАЖНО: backend должен ПЕРЕД генерацией проверять что для company есть слаг,
    и если slug==None И ИНН не в маппинге — возвращать 409 с needs_contract_template=True
    чтобы фронт открыл модалку выбора. См. _ensure_company_has_contract_template_or_409().
    """
    slug = getattr(company, 'contract_template_slug', None)
    if slug and slug in CONTRACT_TEMPLATES_REGISTRY:
        return CONTRACT_TEMPLATES_REGISTRY[slug]["path"]

    inn = getattr(company, 'tax_id_primary', None)
    if inn and inn in COMPANY_INN_TO_SLUG:
        fallback_slug = COMPANY_INN_TO_SLUG[inn]
        return CONTRACT_TEMPLATES_REGISTRY[fallback_slug]["path"]

    return CONTRACT_TEMPLATES_REGISTRY["default"]["path"]


def get_available_template_options() -> list:
    """
    Возвращает список опций для UI dropdown'а при создании/редактировании компании.
    Каждая опция: {slug, label, archetype, description}.
    'default' всегда первый, потом остальные в алфавитном порядке slug'а.
    """
    options = []
    for slug in ["default"] + sorted(s for s in CONTRACT_TEMPLATES_REGISTRY if s != "default"):
        meta = CONTRACT_TEMPLATES_REGISTRY[slug]
        options.append({
            "slug": slug,
            "label": meta["label"],
            "archetype": meta["archetype"],
            "description": meta["description"],
        })
    return options


def is_template_slug_valid(slug: Optional[str]) -> bool:
    """True если слаг валиден (есть в реестре). None или пустая строка → False."""
    return bool(slug) and slug in CONTRACT_TEMPLATES_REGISTRY
