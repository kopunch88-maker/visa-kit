"""
Pack 14 fix — синхронизация схемы applicant с Python моделью.

Проблема: в Python модели (Pack 11 fix) большинство полей сделаны Optional,
но в PostgreSQL они остались NOT NULL — миграция ALTER TABLE не была применена.

Из-за этого создание Applicant с пустым passport_number падает с:
    null value in column "passport_number" of relation "applicant" violates not-null constraint

Этот скрипт делает ALTER COLUMN ... DROP NOT NULL для всех колонок которые
в Python модели Optional, но в Postgres NOT NULL.

Использование:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:DATABASE_URL="postgresql://postgres:ПАРОЛЬ@switchyard.proxy.rlwy.net:34408/railway"
    python migrate_applicant_nullable.py
    $env:DATABASE_URL=$null
"""
import os
import sys

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("ERROR: sqlalchemy не установлен")
    sys.exit(1)


# Все колонки applicant которые ДОЛЖНЫ быть NULLABLE согласно Python модели
# (всё кроме id, last_name_native, first_name_native, last_name_latin, first_name_latin
#  и timestamps created_at/updated_at)
NULLABLE_COLUMNS = [
    "middle_name_native",
    "birth_date",
    "birth_place_latin",
    "nationality",
    "sex",
    "marital_status",
    "father_name_latin",
    "mother_name_latin",
    "passport_number",
    "passport_issue_date",
    "passport_expiry_date",
    "passport_issuer",
    "inn",
    "bank_account",
    "bank_name",
    "bank_bic",
    "bank_correspondent_account",
    "home_address_line1",
    "home_address_line2",
    "home_address",
    "home_country",
    "email",
    "phone",
]


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL не установлен")
        sys.exit(1)

    if "ПАРОЛЬ" in db_url:
        print("ERROR: вставь реальный пароль")
        sys.exit(1)

    print("[1/3] Подключаюсь к production...")
    print(f"      Хост: {db_url.split('@')[-1] if '@' in db_url else '?'}")

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("[2/3] Проверяю текущие NOT NULL колонки в applicant...")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'applicant'
              AND column_name = ANY(:columns)
            ORDER BY column_name
        """), {"columns": NULLABLE_COLUMNS})
        rows = result.fetchall()

    not_null_columns = []
    nullable_columns = []
    for col_name, is_nullable in rows:
        if is_nullable == "NO":
            not_null_columns.append(col_name)
        else:
            nullable_columns.append(col_name)

    print()
    print(f"      Уже NULLABLE: {len(nullable_columns)}")
    for c in nullable_columns:
        print(f"        ✓ {c}")
    print()
    print(f"      ❌ NOT NULL (нужно исправить): {len(not_null_columns)}")
    for c in not_null_columns:
        print(f"        ! {c}")

    if not not_null_columns:
        print()
        print("✅ Все колонки уже NULLABLE — миграция не нужна!")
        return

    print()
    answer = input(f"[3/3] Сделать NULLABLE {len(not_null_columns)} колонок? (yes/no): ").strip().lower()
    if answer != "yes":
        print("Отменено.")
        return

    print()
    print("Выполняю...")

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for col in not_null_columns:
            try:
                conn.execute(text(f"ALTER TABLE applicant ALTER COLUMN {col} DROP NOT NULL"))
                print(f"  ✓ {col} → NULLABLE")
            except Exception as e:
                print(f"  ❌ ошибка для {col}: {e}")

    print()
    print("✅ Миграция завершена!")
    print()
    print("Можно сразу пробовать импорт — backend перезапускать не нужно")
    print("(изменение схемы видно драйверу немедленно).")
    print()
    print("Затем удали этот скрипт:")
    print("  Remove-Item migrate_applicant_nullable.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано.")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
