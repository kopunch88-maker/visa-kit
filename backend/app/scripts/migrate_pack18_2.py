"""
Pack 18.2 миграция — добавляет колонки is_invalid и last_npd_check_at
в self_employed_registry.

Запустить ОДИН РАЗ локально:

    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:DATABASE_URL = "postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"
    python -m app.scripts.migrate_pack18_2

После этого Railway бэкенд перезапустится — модель уже совместима с обновлённой схемой.

Скрипт идемпотентный: если колонки уже есть, ничего не делает.
"""
from __future__ import annotations

import logging
import os
import sys

import sqlalchemy as sa
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("migrate_pack18_2")


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL не установлен. Установите перед запуском:")
        log.error('  $env:DATABASE_URL = "postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"')
        sys.exit(1)

    log.info("Pack 18.2 migration — добавляем is_invalid и last_npd_check_at в self_employed_registry")
    log.info(f"Connecting to: {db_url[:60]}...")

    engine = create_engine(db_url)

    with engine.begin() as conn:
        # Проверка существующих колонок
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'self_employed_registry'
            AND column_name IN ('is_invalid', 'last_npd_check_at')
        """))
        existing_columns = {row[0] for row in result}
        log.info(f"Already existing columns from Pack 18.2: {existing_columns or '(none)'}")

        # is_invalid
        if 'is_invalid' not in existing_columns:
            log.info("Adding column: is_invalid BOOLEAN NOT NULL DEFAULT FALSE")
            conn.execute(text(
                "ALTER TABLE self_employed_registry "
                "ADD COLUMN is_invalid BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            log.info("✅ is_invalid column added")
        else:
            log.info("⏭️  is_invalid already exists, skipping")

        # last_npd_check_at
        if 'last_npd_check_at' not in existing_columns:
            log.info("Adding column: last_npd_check_at TIMESTAMP NULL")
            conn.execute(text(
                "ALTER TABLE self_employed_registry "
                "ADD COLUMN last_npd_check_at TIMESTAMP NULL"
            ))
            log.info("✅ last_npd_check_at column added")
        else:
            log.info("⏭️  last_npd_check_at already exists, skipping")

        # Индекс на is_invalid для быстрой фильтрации (если нам понадобится)
        result = conn.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'self_employed_registry'
            AND indexname = 'idx_self_employed_invalid'
        """))
        if result.fetchone() is None:
            log.info("Creating index: idx_self_employed_invalid (partial, WHERE is_invalid=TRUE)")
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_self_employed_invalid "
                "ON self_employed_registry (inn) WHERE is_invalid = TRUE"
            ))
            log.info("✅ Index created")
        else:
            log.info("⏭️  Index idx_self_employed_invalid already exists, skipping")

    # Финальная диагностика
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_invalid THEN 1 ELSE 0 END) AS invalid_count,
                SUM(CASE WHEN last_npd_check_at IS NOT NULL THEN 1 ELSE 0 END) AS checked_count
            FROM self_employed_registry
        """))
        row = result.fetchone()
        log.info(f"Final state: total={row.total} invalid={row.invalid_count} ever_checked={row.checked_count}")

    log.info("Pack 18.2 migration completed successfully")


if __name__ == "__main__":
    main()
