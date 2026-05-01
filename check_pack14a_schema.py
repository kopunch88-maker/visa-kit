"""
Pack 14a — проверка что схема БД готова принять новые типы документов.

В нашей модели applicant_document.doc_type объявлен как
ApplicantDocumentType (str enum) без sa_column для PG enum,
поэтому в Postgres колонка должна быть VARCHAR — никакой миграции не нужно.

Этот скрипт ПРОВЕРЯЕТ что колонка действительно VARCHAR (или TEXT).
Если вдруг она PG ENUM — выводит инструкции.

Запуск:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:DATABASE_URL="postgresql://postgres:ПАРОЛЬ@switchyard.proxy.rlwy.net:34408/railway"
    python check_pack14a_schema.py
    $env:DATABASE_URL=$null
"""
import os
import sys

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("ERROR: установи .venv и активируй его")
    sys.exit(1)


db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL не установлен")
    sys.exit(1)

if "ПАРОЛЬ" in db_url:
    print("ERROR: вставь реальный пароль в DATABASE_URL")
    sys.exit(1)

engine = create_engine(db_url)

print(f"Подключаюсь к {db_url.split('@')[-1] if '@' in db_url else '?'}...")
with engine.connect() as conn:
    # Проверяем тип колонки doc_type
    result = conn.execute(text("""
        SELECT data_type, udt_name
        FROM information_schema.columns
        WHERE table_name = 'applicant_document'
          AND column_name = 'doc_type'
    """))
    row = result.first()
    if not row:
        print("❌ Колонка applicant_document.doc_type не найдена")
        sys.exit(1)
    data_type, udt_name = row[0], row[1]
    print(f"  data_type: {data_type}")
    print(f"  udt_name:  {udt_name}")
    print()

    if data_type in ("character varying", "text", "varchar"):
        print("✅ Колонка VARCHAR/TEXT — никакой миграции не нужно.")
        print("   Pack 14a новые типы документов будут работать сразу после деплоя.")
        sys.exit(0)

    if data_type == "USER-DEFINED":
        # Это PG enum — нужна миграция
        print("⚠ Колонка является PG ENUM — нужна миграция!")
        print()
        print("Выполни эти SQL команды (PostgreSQL 9.6+):")
        print()
        print(f"  ALTER TYPE {udt_name} ADD VALUE IF NOT EXISTS 'passport_national';")
        print(f"  ALTER TYPE {udt_name} ADD VALUE IF NOT EXISTS 'residence_card';")
        print(f"  ALTER TYPE {udt_name} ADD VALUE IF NOT EXISTS 'criminal_record';")
        print()
        print("Можешь запустить через тот же скрипт, добавив их в connection.execute(text(...))")
        sys.exit(1)

    print(f"⚠ Неожиданный тип колонки: {data_type}")
    print("Свяжись с Костей — нестандартная схема.")
    sys.exit(1)
