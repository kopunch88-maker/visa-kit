"""
Pack 17.6 — region_code в self_employed_registry.

Цель: добавить region_code (smallint) для быстрой выборки кандидатов из реестра
по региону. region_code = первые 2 цифры ИНН (= код субъекта РФ по налоговой
номенклатуре).

Шаги:
  1. ALTER TABLE ADD COLUMN region_code SMALLINT (NULL allowed для постепенной миграции)
  2. UPDATE на всех 546k записей — region_code = LEFT(inn::text, 2)::int
  3. CREATE INDEX (region_code, is_used) WHERE is_used = FALSE — частичный индекс,
     быстрый SELECT свободных кандидатов в регионе
  4. ALTER COLUMN SET NOT NULL после UPDATE

ВАЖНО: миграция идемпотентна (можно запускать повторно).

Запускается автоматически при старте backend через apply_pack17_6_migration().
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session

log = logging.getLogger(__name__)


def apply_pack17_6_migration(engine) -> None:
    """
    Применить миграцию Pack 17.6.
    Идемпотентна: повторный запуск безопасен.
    """
    log.warning("[Pack 17.6] applying region_code migration...")

    with Session(engine) as s:
        # 1. Проверяем — есть ли уже колонка
        col_exists = s.exec(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'self_employed_registry'
                  AND column_name = 'region_code'
                LIMIT 1
                """
            )
        ).first()

        if not col_exists:
            log.warning("[Pack 17.6] adding column region_code...")
            s.exec(
                text(
                    "ALTER TABLE self_employed_registry "
                    "ADD COLUMN region_code SMALLINT"
                )
            )
            s.commit()
        else:
            log.warning("[Pack 17.6] column region_code already exists, skipping ADD")

        # 2. Backfill для всех записей где region_code IS NULL
        # Используем LEFT(inn::text, 2)::smallint — первые 2 цифры ИНН = код субъекта
        # ИНН ИП всегда 12 цифр, первые 2 = регион (по налоговой номенклатуре ФНС)
        log.warning("[Pack 17.6] backfilling region_code from INN prefix...")
        result = s.exec(
            text(
                """
                UPDATE self_employed_registry
                SET region_code = LEFT(inn::text, 2)::smallint
                WHERE region_code IS NULL
                """
            )
        )
        s.commit()
        # rowcount может быть -1 в зависимости от драйвера, не падаем
        try:
            updated = result.rowcount
            log.warning(f"[Pack 17.6] backfilled rows: {updated}")
        except Exception:
            log.warning("[Pack 17.6] backfill done (rowcount unavailable)")

        # 3. Частичный индекс для быстрых запросов "свободные в регионе X"
        idx_exists = s.exec(
            text(
                """
                SELECT 1
                FROM pg_indexes
                WHERE tablename = 'self_employed_registry'
                  AND indexname = 'idx_self_employed_region_available'
                LIMIT 1
                """
            )
        ).first()

        if not idx_exists:
            log.warning("[Pack 17.6] creating partial index on (region_code) WHERE is_used=FALSE...")
            # CONCURRENTLY нельзя в транзакции SQLAlchemy — обычный CREATE INDEX
            # На 546k записей в Postgres это ~10-30 секунд, ОК для миграции
            s.exec(
                text(
                    """
                    CREATE INDEX idx_self_employed_region_available
                    ON self_employed_registry (region_code)
                    WHERE is_used = FALSE
                    """
                )
            )
            s.commit()
        else:
            log.warning("[Pack 17.6] index idx_self_employed_region_available already exists")

        # 4. SET NOT NULL после backfill (только если ещё не стоит)
        nullable_check = s.exec(
            text(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_name = 'self_employed_registry'
                  AND column_name = 'region_code'
                """
            )
        ).first()

        if nullable_check and nullable_check[0] == 'YES':
            # Сначала проверим что нет NULL (на всякий случай)
            null_count_row = s.exec(
                text(
                    "SELECT COUNT(*) FROM self_employed_registry WHERE region_code IS NULL"
                )
            ).first()
            null_count = null_count_row[0] if null_count_row else 0

            if null_count == 0:
                log.warning("[Pack 17.6] setting region_code NOT NULL...")
                s.exec(
                    text(
                        "ALTER TABLE self_employed_registry "
                        "ALTER COLUMN region_code SET NOT NULL"
                    )
                )
                s.commit()
            else:
                log.warning(
                    f"[Pack 17.6] WARNING: {null_count} rows still have NULL region_code, "
                    "leaving column nullable (probably bad INN data)"
                )

    log.warning("[Pack 17.6] migration complete")


def get_region_distribution(engine) -> list[tuple[int, int, int]]:
    """
    Диагностика: распределение записей по region_code.
    Возвращает [(region_code, total, available), ...].
    Полезно для проверки что регионов хватит.
    """
    with Session(engine) as s:
        rows = s.exec(
            text(
                """
                SELECT
                    region_code,
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_used = FALSE THEN 1 ELSE 0 END) AS available
                FROM self_employed_registry
                GROUP BY region_code
                ORDER BY total DESC
                """
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]
