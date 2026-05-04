"""
Pack 18.10 — поле birth_country (страна рождения, ISO-3) в applicant.

Было: País (страна рождения) в форме MI-T дублировалось с гражданством
(applicant.nationality). Это работает в большинстве случаев, но неточно
если клиент родился в одной стране а гражданство получил в другой.

Стало: отдельное поле applicant.birth_country (NULLABLE VARCHAR(3) ISO-3),
которое подставляется в DEX_PAIS / Texto11. Если NULL — fallback на
nationality (для обратной совместимости с уже существующими applicant'ами,
у которых поле не заполнено).

Запуск:
  python -m app.scripts.migration_pack18_10
"""
from __future__ import annotations

import logging
from sqlalchemy import text

from app.db.session import engine

log = logging.getLogger(__name__)


def run() -> None:
    log.warning("[Pack 18.10] applying birth_country field migration...")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE applicant
                ADD COLUMN IF NOT EXISTS birth_country VARCHAR(3)
                """
            )
        )
        log.warning("[Pack 18.10] column birth_country VARCHAR(3) added (or already exists)")

    log.warning("[Pack 18.10] migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
