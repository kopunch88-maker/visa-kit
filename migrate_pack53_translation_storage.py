"""
Pack 53 — миграция: добавить колонку bank_statement_translation_storage_key на Application.

Хранит R2-ключ сохранённого перевода выписки (на испанский, без печатей).
NULL = перевод не делался; не-NULL = есть кешированный перевод в R2,
download/bank_statement должен отдавать combined PDF (RU+ES).

Идемпотентно — пропускает если колонка уже есть.

ЗАПУСК (из корня репо D:\\VISA\\visa_kit):
    $env:DATABASE_URL = "postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway"
    python migrate_pack53_translation_storage.py
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ ERROR: переменная окружения DATABASE_URL не установлена")
        print(r'   Пример: $env:DATABASE_URL = "postgresql://postgres:...@host:port/railway"')
        return 1

    # Pack 50.41 урок: защита от «задвоенного» URL
    if db_url.count("postgresql") > 1:
        db_url = "postgresql" + db_url.rsplit("postgresql", 1)[1]
        print(f"⚠ DATABASE_URL содержал дубль 'postgresql' — нормализовали")

    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("❌ ERROR: SQLAlchemy не установлен. Активируйте venv: .venv\\Scripts\\Activate.ps1")
        return 1

    print(f"→ Подключаюсь к БД...")
    engine = create_engine(db_url)

    with engine.begin() as conn:
        # Проверка существования колонки
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'application'
              AND column_name = 'bank_statement_translation_storage_key'
        """))
        if result.fetchone():
            print("· SKIP: колонка bank_statement_translation_storage_key уже существует")
            return 0

        # Добавляем колонку
        conn.execute(text("""
            ALTER TABLE application
            ADD COLUMN bank_statement_translation_storage_key VARCHAR(255) NULL
        """))
        print("✅ OK: колонка bank_statement_translation_storage_key добавлена (VARCHAR(255) NULL)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
