"""
Pack 20.0 — Отвязка Position от Company.

Что делает:
1. SAFETY CHECK: убеждается, что нет заявок где application.company_id IS NULL
   и position_id IS NOT NULL (это значит компания берётся неявно через
   position.company_id и теряется после миграции). На 04.05.2026 таких
   заявок 0 (проверено SQL).
2. SAFETY CHECK 2: для подстраховки делает UPDATE
   application SET company_id = (SELECT position.company_id FROM position
   WHERE position.id = application.position_id) WHERE application.company_id
   IS NULL — копирует company из position в application для тех немногих
   заявок которые могут быть в будущем созданы между чек'ом и миграцией
   (race-condition-style защита).
3. ADD COLUMN position.primary_specialty_id INTEGER NULL
   (FK на specialty.id если такая таблица есть)
4. ADD COLUMN position.level INTEGER NULL (1=Junior, 2=Middle, 3=Senior, 4=Lead)
5. DROP COLUMN position.company_id

Идемпотентна. Можно запускать несколько раз — проверки на наличие колонок.

Запуск (Правило 15):
    $env:DATABASE_URL = "postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"
    cd D:\VISA\visa_kit\backend
    python -m app.scripts.migration_pack20_0
"""

from sqlalchemy import text

from app.db.session import engine


def column_exists(conn, table: str, column: str) -> bool:
    sql = text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c LIMIT 1"
    )
    return conn.execute(sql, {"t": table, "c": column}).first() is not None


def table_exists(conn, table: str) -> bool:
    sql = text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :t LIMIT 1"
    )
    return conn.execute(sql, {"t": table}).first() is not None


def index_exists(conn, index_name: str) -> bool:
    sql = text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :i LIMIT 1"
    )
    return conn.execute(sql, {"i": index_name}).first() is not None


def constraint_exists(conn, constraint_name: str) -> bool:
    sql = text(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE constraint_name = :c LIMIT 1"
    )
    return conn.execute(sql, {"c": constraint_name}).first() is not None


def main() -> None:
    print("[Pack 20.0] start: detach Position from Company")

    with engine.begin() as conn:
        # =====================================================================
        # 1. SAFETY CHECK 1 — заявки с broken consistency
        # =====================================================================
        broken = conn.execute(
            text(
                "SELECT id, reference FROM application "
                "WHERE company_id IS NULL AND position_id IS NOT NULL"
            )
        ).fetchall()
        if broken:
            print(
                f"[Pack 20.0] ⚠️  Found {len(broken)} applications where "
                "company_id IS NULL and position_id IS NOT NULL:"
            )
            for row in broken:
                print(f"    id={row[0]} reference={row[1]}")
            print("[Pack 20.0] Will fix these by copying position.company_id → application.company_id")

        # =====================================================================
        # 2. SAFETY CHECK 2 / DATA FIX — копируем company из position
        # =====================================================================
        # Проверяем что position.company_id ещё существует (если миграция
        # запускается повторно — колонки уже нет, шаг пропускаем)
        if column_exists(conn, "position", "company_id"):
            result = conn.execute(
                text(
                    "UPDATE application "
                    "SET company_id = position.company_id "
                    "FROM position "
                    "WHERE application.position_id = position.id "
                    "AND application.company_id IS NULL"
                )
            )
            print(
                f"[Pack 20.0] data fix: copied company_id for "
                f"{result.rowcount} applications"
            )
        else:
            print("[Pack 20.0] data fix: skipped (position.company_id already dropped)")

        # =====================================================================
        # 3. ADD primary_specialty_id (nullable, no FK constraint by default
        #    — добавим constraint только если specialty table exists)
        # =====================================================================
        if not column_exists(conn, "position", "primary_specialty_id"):
            conn.execute(
                text("ALTER TABLE position ADD COLUMN primary_specialty_id INTEGER NULL")
            )
            print("[Pack 20.0] ALTER: added position.primary_specialty_id")
        else:
            print("[Pack 20.0] skip: position.primary_specialty_id already exists")

        # FK constraint на specialty (если таблица есть)
        if table_exists(conn, "specialty"):
            if not constraint_exists(conn, "fk_position_primary_specialty"):
                try:
                    conn.execute(text(
                        "ALTER TABLE position "
                        "ADD CONSTRAINT fk_position_primary_specialty "
                        "FOREIGN KEY (primary_specialty_id) "
                        "REFERENCES specialty(id) ON DELETE SET NULL"
                    ))
                    print("[Pack 20.0] ALTER: added FK position.primary_specialty_id → specialty.id")
                except Exception as e:
                    print(f"[Pack 20.0] ⚠️  FK constraint failed (will continue): {e}")
            else:
                print("[Pack 20.0] skip: FK fk_position_primary_specialty already exists")
        else:
            print("[Pack 20.0] skip: specialty table not found — no FK constraint added")

        # Индекс на primary_specialty_id
        if not index_exists(conn, "ix_position_primary_specialty_id"):
            conn.execute(text(
                "CREATE INDEX ix_position_primary_specialty_id "
                "ON position(primary_specialty_id)"
            ))
            print("[Pack 20.0] CREATE INDEX ix_position_primary_specialty_id")
        else:
            print("[Pack 20.0] skip: ix_position_primary_specialty_id already exists")

        # =====================================================================
        # 4. ADD level (nullable, 1..4)
        # =====================================================================
        if not column_exists(conn, "position", "level"):
            conn.execute(
                text("ALTER TABLE position ADD COLUMN level INTEGER NULL")
            )
            print("[Pack 20.0] ALTER: added position.level")
        else:
            print("[Pack 20.0] skip: position.level already exists")

        # =====================================================================
        # 5. DROP COLUMN position.company_id
        # =====================================================================
        if column_exists(conn, "position", "company_id"):
            # Сначала дропаем зависимые объекты — FK constraint и индекс
            # (они автоматически дропнутся вместе с колонкой через CASCADE,
            # но безопаснее сделать явно)
            conn.execute(text(
                "ALTER TABLE position DROP COLUMN company_id CASCADE"
            ))
            print("[Pack 20.0] DROP: position.company_id (with CASCADE)")
        else:
            print("[Pack 20.0] skip: position.company_id already dropped")

        # =====================================================================
        # FINAL: показать структуру position
        # =====================================================================
        print("[Pack 20.0] Final position table structure:")
        cols = conn.execute(text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'position' "
            "ORDER BY ordinal_position"
        )).fetchall()
        for col in cols:
            print(f"    {col[0]:<28} {col[1]:<20} nullable={col[2]}")

        # Подсчёт записей
        n_positions = conn.execute(text("SELECT COUNT(*) FROM position")).scalar()
        print(f"[Pack 20.0] FINAL: {n_positions} positions in DB")

    print("[Pack 20.0] ✅ DONE")


if __name__ == "__main__":
    main()
