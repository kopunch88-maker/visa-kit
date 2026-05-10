# -*- coding: utf-8 -*-
"""
Pack 29.1 — Корректировка ИНН компаний по официальным данным ЕГРЮЛ + бэкфилл слагов.

Источники:
- Официальные jurada-переводы хургадо (выписки ЕГРЮЛ)
- ФНС/ЕГРЮЛ через РБК Компании, Контур.Фокус, Чекко, Rusprofile, Saby (08.05.2026)

Применять:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:DATABASE_URL="postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"
    $env:PYTHONIOENCODING="utf-8"
    python apply_pack29_1_correction.py

Идемпотентна (UPDATE WHERE для безопасности).
"""
import os
from sqlalchemy import create_engine, text


# Точные данные из официальных источников.
# Формат: id_in_db -> {short_name_for_display, tax_id_primary, tax_id_secondary, slug, comment}
CORRECTIONS = [
    {
        "id": 4,
        "expected_name_substring": "KING DAVID",
        "tax_id_primary": "7731579629",
        "tax_id_secondary": "771501001",
        "slug": "king_david",
        "source": "выписка ЕГРЮЛ (jurada хургадо) + checko.ru + rbc.ru",
    },
    {
        "id": 5,
        "expected_name_substring": "ProTech",
        "tax_id_primary": "7810890724",
        "tax_id_secondary": "781001001",
        "slug": "protech",
        "source": "выписка ЕГРЮЛ (jurada хургадо), параметр 30 + spark-interfax.ru",
    },
    {
        "id": 6,
        "expected_name_substring": "TIKOmpani",
        "tax_id_primary": "7729634103",
        "tax_id_secondary": "772901001",
        "slug": "tikompani",
        "source": "выписка ЕГРЮЛ (jurada хургадо), шапка + rbc.ru + saby.ru",
    },
    {
        "id": 8,
        "expected_name_substring": "KNS GRUPP",
        "tax_id_primary": "7701411241",
        "tax_id_secondary": "770301001",
        "slug": "kns_grupp",
        "source": "выписка ЕГРЮЛ (jurada хургадо) + rbc.ru + checko.ru + saby.ru",
    },
    {
        "id": 9,
        "expected_name_substring": "AVTODOM",
        "tax_id_primary": "7714709349",
        "tax_id_secondary": "771401001",
        "slug": "avtodom",
        "source": "выписка ЕГРЮЛ (jurada хургадо), шапка",
    },
    {
        "id": 16,
        "expected_name_substring": "АГАЛАРОВ",
        "tax_id_primary": "7707038266",  # уже верно, не меняем
        "tax_id_secondary": "773001001",   # обновлённый КПП после переезда (13.06.2024)
        "slug": None,  # выписка пока не доступна (jurada не готова)
        "source": "rbc.ru + spark-interfax.ru + companium.ru (КПП обновлён в ИФНС №30)",
    },
]

# Также - для уже корректных компаний - на всякий случай поставим slug
# (Pack 29 backfill это сделал, но проверим повторно).
SLUG_REINFORCE = [
    {"id": 2, "slug": "sk10",      "tax_id_primary": "6168006148"},
    {"id": 3, "slug": "buki_vedi", "tax_id_primary": "7706796034"},
    {"id": 15, "slug": None, "tax_id_primary": "2320219620"},  # ИНЖГЕОСЕРВИС - правильный ИНН, нет шаблона
]


def apply():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL env var is not set")
    engine = create_engine(db_url)

    print("=" * 75)
    print("Pack 29.1 — Корректировка ИНН компаний + привязка слагов")
    print("=" * 75)

    with engine.begin() as conn:
        # ---------------------------------------------------------------
        # 1. Сначала покажем текущее состояние
        # ---------------------------------------------------------------
        print("\n→ Состояние ДО:")
        rows = conn.execute(text("""
            SELECT id, short_name, tax_id_primary, tax_id_secondary, contract_template_slug
            FROM company
            ORDER BY id
        """)).fetchall()
        for r in rows:
            slug = r.contract_template_slug or "—"
            kpp = r.tax_id_secondary or "—"
            print(f"  id={r.id:3d} {(r.short_name or '')[:38]:38s} ИНН={(r.tax_id_primary or '—'):15s} КПП={kpp:11s} slug={slug}")

        # ---------------------------------------------------------------
        # 2. Применяем корректировки
        # ---------------------------------------------------------------
        print("\n→ Применяем корректировки:")
        for fix in CORRECTIONS:
            # Сначала проверим что такая компания есть
            row = conn.execute(text("""
                SELECT id, short_name, tax_id_primary, tax_id_secondary, contract_template_slug
                FROM company WHERE id = :id
            """), {"id": fix["id"]}).first()

            if not row:
                print(f"  ⚠️  id={fix['id']} ({fix['expected_name_substring']}) — не найдена в БД, пропускаю")
                continue

            # Покажу что будем менять
            changes = []
            if row.tax_id_primary != fix["tax_id_primary"]:
                changes.append(f"ИНН: {row.tax_id_primary} → {fix['tax_id_primary']}")
            if (row.tax_id_secondary or "") != fix["tax_id_secondary"]:
                changes.append(f"КПП: {row.tax_id_secondary or '—'} → {fix['tax_id_secondary']}")
            if fix.get("slug") and (row.contract_template_slug or "") != fix["slug"]:
                changes.append(f"slug: {row.contract_template_slug or '—'} → {fix['slug']}")

            if not changes:
                print(f"  = id={fix['id']} {fix['expected_name_substring']:25s} — уже актуально, skip")
                continue

            # Применим
            conn.execute(text("""
                UPDATE company
                SET tax_id_primary = :tax_id_primary,
                    tax_id_secondary = :tax_id_secondary,
                    contract_template_slug = COALESCE(:slug, contract_template_slug)
                WHERE id = :id
            """), {
                "id": fix["id"],
                "tax_id_primary": fix["tax_id_primary"],
                "tax_id_secondary": fix["tax_id_secondary"],
                "slug": fix.get("slug"),
            })
            print(f"  ✓ id={fix['id']} {fix['expected_name_substring']:25s}: {'; '.join(changes)}")
            print(f"      источник: {fix['source']}")

        # ---------------------------------------------------------------
        # 3. Бэкфилл слагов для компаний которые УЖЕ имели правильный ИНН
        # ---------------------------------------------------------------
        print("\n→ Дополнительный backfill слагов:")
        for sr in SLUG_REINFORCE:
            if not sr.get("slug"):
                continue
            result = conn.execute(text("""
                UPDATE company
                SET contract_template_slug = :slug
                WHERE id = :id
                  AND tax_id_primary = :inn
                  AND (contract_template_slug IS NULL OR contract_template_slug = '')
            """), {
                "id": sr["id"],
                "inn": sr["tax_id_primary"],
                "slug": sr["slug"],
            })
            if result.rowcount > 0:
                print(f"  ✓ id={sr['id']} → slug={sr['slug']}")
            else:
                print(f"  = id={sr['id']} → slug={sr['slug']} (уже стоит, skip)")

        # ---------------------------------------------------------------
        # 4. Покажем финальное состояние
        # ---------------------------------------------------------------
        print("\n→ Состояние ПОСЛЕ:")
        rows = conn.execute(text("""
            SELECT id, short_name, tax_id_primary, tax_id_secondary, contract_template_slug
            FROM company
            ORDER BY id
        """)).fetchall()
        for r in rows:
            slug = r.contract_template_slug or "—"
            kpp = r.tax_id_secondary or "—"
            marker = "✅" if slug != "—" else ("⚠️" if (r.short_name or "").lower() in ("xzcxzc", "gfgdfgdfgfd") else "  ")
            print(f"  {marker} id={r.id:3d} {(r.short_name or '')[:38]:38s} ИНН={(r.tax_id_primary or '—'):15s} КПП={kpp:11s} slug={slug}")

        # ---------------------------------------------------------------
        # 5. Сводка
        # ---------------------------------------------------------------
        stats = conn.execute(text("""
            SELECT
              COUNT(*) AS total,
              COUNT(contract_template_slug) AS with_slug,
              COUNT(*) FILTER (WHERE contract_template_slug IS NULL) AS without_slug
            FROM company
        """)).first()

        print(f"\n→ Итого: {stats.total} компаний")
        print(f"   с привязкой к шаблону: {stats.with_slug}")
        print(f"   без привязки (модалка при генерации): {stats.without_slug}")


if __name__ == "__main__":
    apply()
    print("\n✅ Pack 29.1 correction applied")
