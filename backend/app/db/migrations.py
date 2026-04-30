"""
Миграции БД — добавление полей которые появились после первоначального schema.

Каждая миграция идемпотентна — можно вызывать многократно безопасно.

Pack 11.2 fix: поддержка и SQLite (для dev), и PostgreSQL (для production).
Используем SQLAlchemy Inspector — он работает с обоими движками одинаково.
"""

import logging
from sqlalchemy import text, inspect
from app.db.session import engine

log = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str) -> bool:
    """Универсально через SQLAlchemy Inspector — SQLite + PostgreSQL."""
    inspector = inspect(conn)
    columns = {col["name"] for col in inspector.get_columns(table)}
    return column in columns


def _is_postgres() -> bool:
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
            conn.execute(text(
                'ALTER TABLE "user" ADD COLUMN password_hash VARCHAR(128)'
            ))
            log.info("[migration:pack11] Added column user.password_hash")
        else:
            log.debug("[migration:pack11] Column user.password_hash already exists")


def apply_pack11_2_migration():
    """
    Pack 11.2: снимает NOT NULL constraint с полей applicant которые теперь Optional.
    
    Это критично для production: в SQLite NOT NULL мог быть не строгим, в PostgreSQL
    он строгий. Чтобы клиент мог сохранять анкету по шагам, эти поля должны
    допускать NULL в БД.
    
    Только PostgreSQL — в SQLite ALTER COLUMN сложен и не нужен.
    """
    if not _is_postgres():
        log.debug("[migration:pack11_2] Skipping (only needed for PostgreSQL)")
        return

    # Список полей в applicant, с которых снимаем NOT NULL
    nullable_fields = [
        "passport_number",
        "birth_date",
        "birth_place_latin",
        "nationality",
        "sex",
        "marital_status",
        "home_address",
        "home_country",
        "email",
        "phone",
    ]

    with engine.begin() as conn:
        for field in nullable_fields:
            try:
                conn.execute(text(
                    f"ALTER TABLE applicant ALTER COLUMN {field} DROP NOT NULL"
                ))
                log.info(f"[migration:pack11_2] DROPPED NOT NULL on applicant.{field}")
            except Exception as e:
                # Если уже nullable или столбец не существует — пропускаем
                err = str(e).lower()
                if "is in a column without not null" in err or "does not exist" in err:
                    log.debug(f"[migration:pack11_2] applicant.{field} already nullable or missing")
                else:
                    log.warning(f"[migration:pack11_2] Failed to drop NOT NULL on {field}: {e}")