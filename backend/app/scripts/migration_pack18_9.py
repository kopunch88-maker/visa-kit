"""
Pack 18.9 — поля для редактируемого подписанта апостиля.

Добавляет в applicant:
- apostille_signer_short        — "Фамилия И.О." для таблицы (обязательно если задано)
- apostille_signer_signature    — "И.О. Фамилия" для подписи (обязательно если задано)
- apostille_signer_position     — должность (обязательно если задано)

Все 3 поля NULLABLE. При генерации апостиля если какое-то поле NULL —
используется дефолт «Байрамов Н.А.» / стандартная должность Минюста по Москве.

Запуск:
  python -m app.scripts.migration_pack18_9
"""
from __future__ import annotations

import logging
from sqlalchemy import text

from app.db.session import engine

log = logging.getLogger(__name__)


def run() -> None:
    log.warning("[Pack 18.9] applying apostille signer fields migration...")

    with engine.begin() as conn:
        for col_name, col_type in [
            ("apostille_signer_short", "VARCHAR(100)"),
            ("apostille_signer_signature", "VARCHAR(100)"),
            ("apostille_signer_position", "VARCHAR(500)"),
        ]:
            conn.execute(
                text(
                    f"""
                    ALTER TABLE applicant
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                    """
                )
            )
            log.warning(
                "[Pack 18.9] column %s %s added (or already exists)",
                col_name, col_type,
            )

    log.warning("[Pack 18.9] migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
