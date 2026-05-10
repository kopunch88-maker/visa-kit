# -*- coding: utf-8 -*-
"""
Pack 29.0 — Патч для docx_renderer.py

ЦЕЛЬ: render_contract выбирает шаблон договора динамически по company.contract_template_slug,
а не использует один общий contract_template.docx.

ИНТЕГРАЦИЯ В backend/app/templates_engine/docx_renderer.py:

В вашем существующем render_contract(application, ...) НАЙТИ загрузку шаблона:
    # СТАРОЕ:
    template_path = TEMPLATES_DIR / "contract_template.docx"
    template = DocxTemplate(template_path)

И ЗАМЕНИТЬ на:

    from .contracts_registry import resolve_contract_template_path
    relative_path = resolve_contract_template_path(application.company)
    template_path = REPO_ROOT / relative_path  # подставьте свой root
    template = DocxTemplate(template_path)

REPO_ROOT — это `Path(__file__).resolve().parents[2]` или аналогичный анкер
указывающий на корень репозитория (там где лежит templates/).

Также добавьте в render-pipeline ПРОВЕРКУ перед генерацией:

    from .contracts_registry import (
        is_template_slug_valid,
        COMPANY_INN_TO_SLUG,
        get_available_template_options,
    )
    from fastapi import HTTPException

    def ensure_company_has_contract_template_or_409(company):
        '''
        Проверяет что для данной компании есть привязка к шаблону.
        Если slug отсутствует и ИНН не в маппинге → 409 + список опций для UI.
        '''
        if is_template_slug_valid(getattr(company, 'contract_template_slug', None)):
            return  # ОК
        inn = getattr(company, 'tax_id_primary', None)
        if inn and inn in COMPANY_INN_TO_SLUG:
            return  # есть fallback-маппинг по ИНН
        # Слага нет и ИНН не в маппинге — фронт должен показать модалку выбора
        raise HTTPException(
            status_code=409,
            detail={
                "code": "NEEDS_CONTRACT_TEMPLATE",
                "message": (
                    f"Для компании '{company.short_name}' (id={company.id}) "
                    f"не выбран шаблон договора. Выберите шаблон в модальном окне."
                ),
                "company_id": company.id,
                "available_templates": get_available_template_options(),
            },
        )

И вызывайте `ensure_company_has_contract_template_or_409(application.company)` в начале
render_contract или в endpoint'е /applications/{id}/generate-package ПЕРЕД render-вызовами.

НОВЫЙ ENDPOINT (для модалки):

    @router.post("/companies/{company_id}/contract-template")
    async def set_company_contract_template(
        company_id: int,
        body: dict,  # {"slug": "sk10"}
        db: Session = Depends(get_db),
    ):
        slug = body.get("slug")
        if not is_template_slug_valid(slug):
            raise HTTPException(400, "Invalid contract template slug")
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(404, "Company not found")
        company.contract_template_slug = slug
        db.commit()
        return {"ok": True, "company_id": company_id, "slug": slug}

    @router.get("/contract-templates")
    async def list_contract_templates():
        '''Список доступных шаблонов для UI dropdown'а.'''
        return {"templates": get_available_template_options()}
"""
