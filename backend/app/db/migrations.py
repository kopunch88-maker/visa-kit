"""
Миграции БД — добавление полей которые появились после первоначального schema.

Каждая миграция идемпотентна — можно вызывать многократно безопасно.

Pack 11.2 fix: поддержка и SQLite (для dev), и PostgreSQL (для production).
SQLite использует PRAGMA table_info, PostgreSQL — information_schema.
Используем SQLAlchemy Inspector — он работает с обоими движками одинаково.
"""

import logging
from sqlalchemy import text, inspect
from app.db.session import engine

log = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str) -> bool:
    """
    Проверяет существует ли колонка в таблице.
    Универсально через SQLAlchemy Inspector — работает и в SQLite, и в PostgreSQL.
    """
    inspector = inspect(conn)
    columns = {col["name"] for col in inspector.get_columns(table)}
    return column in columns


def _is_postgres() -> bool:
    """Определяет диалект БД."""
    return engine.url.get_backend_name() in ("postgresql", "postgres")


def apply_pack10_migration():
    """
    Pack 10: добавляет is_archived (BOOLEAN) и archived_at в application.
    """
    with engine.begin() as conn:
        if not _column_exists(conn, "application", "is_archived"):
            if _is_postgres():
                conn.execute(text(
                    "ALTER TABLE application "
                    "ADD COLUMN is_archived BOOLEAN DEFAULT FALSE NOT NULL"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE application "
                    "ADD COLUMN is_archived BOOLEAN DEFAULT 0 NOT NULL"
                ))
            log.info("[migration:pack10] Added column application.is_archived")

        if not _column_exists(conn, "application", "archived_at"):
            if _is_postgres():
                conn.execute(text(
                    "ALTER TABLE application ADD COLUMN archived_at TIMESTAMP"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE application ADD COLUMN archived_at DATETIME"
                ))
            log.info("[migration:pack10] Added column application.archived_at")

        # Индекс — синтаксис одинаковый для обоих диалектов
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
            # `user` — зарезервированное слово в PostgreSQL, нужны двойные кавычки.
            # В SQLite двойные кавычки тоже допустимы, поэтому используем единый синтаксис.
            conn.execute(text(
                'ALTER TABLE "user" ADD COLUMN password_hash VARCHAR(128)'
            ))
            log.info("[migration:pack11] Added column user.password_hash")
        else:
            log.debug("[migration:pack11] Column user.password_hash already exists")
