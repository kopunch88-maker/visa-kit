# -*- coding: utf-8 -*-
"""
Pack 29.2 — Обновление КПП у ООО «БУКИ ВЕДИ» (id=3).

Источник: ФНС/ЕГРЮЛ (через RusProfile, Чекко, Audit-it — все сходятся).
БУКИ ВЕДИ переехала в ИФНС № 27 по г. Москве 27.10.2023, новый КПП = 772701001.
В БД лежит устаревший КПП 770601001 (от ИФНС № 6).

Идемпотентен (UPDATE WHERE).
"""
import os
from sqlalchemy import create_engine, text


def apply():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL env var is not set")
    engine = create_engine(db_url)

    print("=" * 75)
    print("Pack 29.2 — Обновление КПП у ООО «БУКИ ВЕДИ»")
    print("=" * 75)

    with engine.begin() as conn:
        # ДО
        row = conn.execute(text("""
            SELECT id, short_name, tax_id_primary, tax_id_secondary, contract_template_slug
            FROM company WHERE id = 3
        """)).first()

        if not row:
            print("⚠️ id=3 не найдена в БД")
            return

        print(f"\n→ ДО: id={row.id} {row.short_name}")
        print(f"   ИНН={row.tax_id_primary}  КПП={row.tax_id_secondary}  slug={row.contract_template_slug}")

        if row.tax_id_secondary == "772701001":
            print("\n= Уже актуально, skip")
            return

        # UPDATE
        conn.execute(text("""
            UPDATE company
            SET tax_id_secondary = '772701001'
            WHERE id = 3 AND tax_id_primary = '7706796034'
        """))

        # ПОСЛЕ
        row = conn.execute(text("""
            SELECT id, short_name, tax_id_primary, tax_id_secondary, contract_template_slug
            FROM company WHERE id = 3
        """)).first()

        print(f"\n→ ПОСЛЕ: id={row.id} {row.short_name}")
        print(f"   ИНН={row.tax_id_primary}  КПП={row.tax_id_secondary}  slug={row.contract_template_slug}")
        print(f"\n✅ КПП обновлён: 770601001 → 772701001 (актуальная ИФНС №27)")
        print(f"   Источник: RusProfile + Checko + Audit-it (все сошлись на 772701001)")


if __name__ == "__main__":
    apply()
    print("\n✅ Pack 29.2 applied")
