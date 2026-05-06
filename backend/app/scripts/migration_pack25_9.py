"""
Pack 25.9 — миграция: добавление поля application.bank_statement_date.

ЦЕЛЬ:
- Поле для ручного override даты формирования банковской выписки.
- Если NULL (по умолчанию) — генератор Pack 25.8 считает автоматически (today - random(7..10)).
- Если задано — генератор использует эту дату как statement_date,
  а период считается как [statement_date - 3 мес, statement_date].

КАК ПРИМЕНИТЬ:
    $env:DATABASE_URL = "postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"
    $env:PYTHONIOENCODING = "utf-8"
    cd D:\\VISA\\visa_kit\\backend
    python -m app.scripts.migration_pack25_9

Идемпотентно: проверяет наличие колонки перед добавлением.
"""

from sqlalchemy import text
from app.db.session import engine


def column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return result is not None


def main():
    with engine.begin() as conn:
        print("=== Pack 25.9: bank_statement_date ===")

        if column_exists(conn, "application", "bank_statement_date"):
            print("[skip] application.bank_statement_date уже существует")
        else:
            conn.execute(
                text(
                    "ALTER TABLE application "
                    "ADD COLUMN bank_statement_date DATE NULL"
                )
            )
            print("[ok] application.bank_statement_date добавлен")

        # Sanity check
        result = conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'application' "
                "AND column_name = 'bank_statement_date'"
            )
        ).first()
        if result:
            print(f"[verify] {result.column_name}: {result.data_type}, nullable={result.is_nullable}")
        else:
            print("[FAIL] колонка не найдена после миграции")
            raise RuntimeError("Migration verification failed")

    print("\n=== Pack 25.9 миграция применена ===")


if __name__ == "__main__":
    main()
