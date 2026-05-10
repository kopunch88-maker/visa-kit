# -*- coding: utf-8 -*-
"""
Pack 29.0 — Патч для backend/app/models.py (или где у вас модель Company).

В классе Company ДОБАВИТЬ поле:

    contract_template_slug = Column(
        String(64),
        nullable=True,
        index=True,
        comment="Slug шаблона договора (см. contracts_registry.CONTRACT_TEMPLATES_REGISTRY). "
                "NULL → fallback на COMPANY_INN_TO_SLUG[tax_id_primary] или 'default'."
    )

В Pydantic-схеме CompanySchema/CompanyCreate/CompanyUpdate ДОБАВИТЬ поле:

    contract_template_slug: Optional[str] = None

В endpoint POST /companies (создание) ДОБАВИТЬ валидацию:

    from .templates_engine.contracts_registry import is_template_slug_valid

    @router.post("/companies", response_model=CompanySchema)
    def create_company(body: CompanyCreate, db: Session = Depends(get_db)):
        if body.contract_template_slug and not is_template_slug_valid(body.contract_template_slug):
            raise HTTPException(400, f"Unknown contract_template_slug: {body.contract_template_slug}")
        ...

В endpoint PATCH /companies/{id} (обновление) — то же самое.
"""
