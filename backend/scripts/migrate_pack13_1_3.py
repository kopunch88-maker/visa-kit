"""
Pack 13.1.3 — миграция для добавления полей оригинала PDF.
Запускать ОДИН РАЗ.
"""
import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: установи переменную DATABASE_URL")
    print("Пример (PowerShell):")
    print('  $env:DATABASE_URL="postgresql://postgres:PASSWORD@switchyard.proxy.rlwy.net:34408/railway"')
    sys.exit(1)

engine = create_engine(DATABASE_URL)

migrations = [
    "ALTER TABLE applicant_document ADD COLUMN IF NOT EXISTS original_storage_key VARCHAR(500)",
    "ALTER TABLE applicant_document ADD COLUMN IF NOT EXISTS original_file_name VARCHAR(255)",
    "ALTER TABLE applicant_document ADD COLUMN IF NOT EXISTS original_file_size INTEGER",
    "ALTER TABLE applicant_document ADD COLUMN IF NOT EXISTS original_content_type VARCHAR(100)",
]

with engine.connect() as conn:
    for sql in migrations:
        print(f"Executing: {sql}")
        conn.execute(text(sql))
    conn.commit()

print("\n✅ Migration completed successfully!")

# Проверка — посмотрим колонки
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'applicant_document'
        ORDER BY ordinal_position
    """))
    print("\nColumns in applicant_document:")
    for row in result:
        print(f"  {row[0]:35} {row[1]}")