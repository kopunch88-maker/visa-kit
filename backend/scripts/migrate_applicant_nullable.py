"""
Делает все поля Applicant nullable в БД.

Запуск:
    python scripts/migrate_applicant_nullable.py
"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import sqlite3

DB_PATH = BACKEND_ROOT / "dev.db"


def main():
    if not DB_PATH.exists():
        print(f"[ERROR] DB not found: {DB_PATH}")
        return 1

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Удаляем applicant_new если осталась с прошлого раза
    c.execute("DROP TABLE IF EXISTS applicant_new")

    # Создаём новую таблицу с тем же порядком колонок что в оригинале,
    # но без NOT NULL ограничений (кроме PK)
    c.execute("""
        CREATE TABLE applicant_new (
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            id INTEGER NOT NULL,
            last_name_native VARCHAR(64),
            first_name_native VARCHAR(64),
            middle_name_native VARCHAR(64),
            last_name_latin VARCHAR(64),
            first_name_latin VARCHAR(64),
            birth_date DATE,
            birth_place_latin VARCHAR(128),
            nationality VARCHAR(3),
            sex VARCHAR(1),
            marital_status VARCHAR(2),
            father_name_latin VARCHAR(64),
            mother_name_latin VARCHAR(64),
            passport_number VARCHAR(32),
            passport_issue_date DATE,
            passport_expiry_date DATE,
            passport_issuer VARCHAR(128),
            inn VARCHAR(12),
            bank_account VARCHAR(32),
            bank_name VARCHAR(128),
            bank_bic VARCHAR(16),
            bank_correspondent_account VARCHAR(32),
            home_address_line1 VARCHAR(256),
            home_address_line2 VARCHAR(256),
            home_address VARCHAR(512),
            home_country VARCHAR(3),
            email VARCHAR(128),
            phone VARCHAR(32),
            education JSON,
            work_history JSON,
            languages JSON,
            PRIMARY KEY (id)
        )
    """)
    print("[OK] Created applicant_new with nullable fields")

    # Копируем данные с явным перечислением колонок
    columns = [
        "created_at", "updated_at", "id",
        "last_name_native", "first_name_native", "middle_name_native",
        "last_name_latin", "first_name_latin",
        "birth_date", "birth_place_latin",
        "nationality", "sex", "marital_status",
        "father_name_latin", "mother_name_latin",
        "passport_number", "passport_issue_date", "passport_expiry_date",
        "passport_issuer", "inn",
        "bank_account", "bank_name", "bank_bic", "bank_correspondent_account",
        "home_address_line1", "home_address_line2", "home_address",
        "home_country", "email", "phone",
        "education", "work_history", "languages",
    ]
    cols_str = ", ".join(columns)
    c.execute(f"INSERT INTO applicant_new ({cols_str}) SELECT {cols_str} FROM applicant")
    rows_copied = c.rowcount
    print(f"[OK] Copied {rows_copied} row(s)")

    # Удаляем старую и переименовываем новую
    c.execute("DROP TABLE applicant")
    c.execute("ALTER TABLE applicant_new RENAME TO applicant")
    print("[OK] Renamed table")

    conn.commit()
    conn.close()
    print()
    print("[DONE] Migration successful. Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())