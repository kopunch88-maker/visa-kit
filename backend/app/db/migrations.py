"""
Миграции БД — добавление полей которые появились после первоначального schema.

Каждая миграция идемпотентна — можно вызывать многократно безопасно.

Подключение в app/main.py:
    from app.db.migrations import apply_pack10_migration, apply_pack11_migration
    apply_pack10_migration()
    apply_pack11_migration()
"""

import logging
from sqlalchemy import text
from app.db.session import engine

log = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str) -> bool:
    """Проверяет существует ли колонка в таблице SQLite."""
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    columns = {row[1] for row in result}  # row[1] — имя колонки
    return column in columns


def apply_pack10_migration():
    """
    Pack 10: добавляет is_archived (BOOLEAN) и archived_at (DATETIME) в application.
    """
    with engine.begin() as conn:
        if not _column_exists(conn, "application", "is_archived"):
            conn.execute(text(
                "ALTER TABLE application ADD COLUMN is_archived BOOLEAN DEFAULT 0 NOT NULL"
            ))
            log.info("[migration:pack10] Added column application.is_archived")

        if not _column_exists(conn, "application", "archived_at"):
            conn.execute(text(
                "ALTER TABLE application ADD COLUMN archived_at DATETIME"
            ))
            log.info("[migration:pack10] Added column application.archived_at")

        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_application_is_archived "
            "ON application (is_archived)"
        ))


def apply_pack11_migration():
    """
    Pack 11: добавляет password_hash в user (для bcrypt-аутентификации).
    """
    with engine.begin() as conn:
        if not _column_exists(conn, "user", "password_hash"):
            # Nullable, чтобы не сломать существующих юзеров
            conn.execute(text(
                "ALTER TABLE \"user\" ADD COLUMN password_hash VARCHAR(128)"
            ))
            log.info("[migration:pack11] Added column user.password_hash")
        else:
            log.debug("[migration:pack11] Column user.password_hash already exists")
