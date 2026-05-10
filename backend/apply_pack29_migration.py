# -*- coding: utf-8 -*-
"""
Pack 29.0 — добавление company.contract_template_slug + backfill по ИНН.

Применять (как и предыдущие миграции):
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:DATABASE_URL="postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"
    $env:PYTHONIOENCODING="utf-8"
    python -m apply_pack29_migration

Идемпотентна (проверяет существование колонки до ADD).
"""
import os
from sqlalchemy import create_engine, text


# Маппинг ИНН → slug (см. также contracts_registry.COMPANY_INN_TO_SLUG)
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


def apply():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL env var is not set")
    engine = create_engine(db_url)

    with engine.begin() as conn:
        # 1. Проверим есть ли колонка
        col_exists = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'company' AND column_name = 'contract_template_slug'
        """)).first()

        if not col_exists:
            print("→ ADD COLUMN company.contract_template_slug")
            conn.execute(text("""
                ALTER TABLE company
                ADD COLUMN contract_template_slug VARCHAR(64) NULL
            """))
            print("  ✓ done")
        else:
            print("→ Column company.contract_template_slug already exists, skipping ADD")

        # 2. Создать индекс (для быстрого поиска компаний без шаблона)
        idx_exists = conn.execute(text("""
            SELECT 1 FROM pg_indexes
            WHERE indexname = 'ix_company_contract_template_slug'
        """)).first()

        if not idx_exists:
            print("→ CREATE INDEX ix_company_contract_template_slug")
            conn.execute(text("""
                CREATE INDEX ix_company_contract_template_slug
                ON company (contract_template_slug)
            """))
            print("  ✓ done")
        else:
            print("→ Index already exists, skipping")

        # 3. Backfill — для компаний с известным ИНН проставим slug
        print("→ Backfill: проставляем slug по company.tax_id_primary для известных ИНН")
        backfilled = 0
        for inn, slug in COMPANY_INN_TO_SLUG.items():
            result = conn.execute(text("""
                UPDATE company
                SET contract_template_slug = :slug
                WHERE tax_id_primary = :inn
                  AND (contract_template_slug IS NULL OR contract_template_slug = '')
            """), {"slug": slug, "inn": inn})
            if result.rowcount > 0:
                print(f"  ✓ {inn} → {slug} ({result.rowcount} row(s))")
                backfilled += result.rowcount

        print(f"\nBackfilled: {backfilled} компаний")

        # 4. Diagnostic dump
        print("\n→ Состояние company.contract_template_slug:")
        rows = conn.execute(text("""
            SELECT id, short_name, tax_id_primary, contract_template_slug
            FROM company
            ORDER BY id
        """)).fetchall()
        for r in rows:
            slug = r.contract_template_slug or "—"
            print(f"  id={r.id:3d} {r.short_name[:40]:40s} ИНН={r.tax_id_primary:15s} slug={slug}")


if __name__ == "__main__":
    apply()
    print("\n✅ Pack 29.0 migration applied")
