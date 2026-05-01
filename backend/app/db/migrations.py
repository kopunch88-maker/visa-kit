"""
Миграции БД — добавление полей и таблиц после первоначального schema.

Каждая миграция идемпотентна — можно вызывать многократно безопасно.
Используем SQLAlchemy Inspector — работает и в SQLite, и в PostgreSQL.
"""

import logging
from sqlalchemy import text, inspect
from app.db.session import engine

log = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str) -> bool:
    inspector = inspect(conn)
    columns = {col["name"] for col in inspector.get_columns(table)}
    return column in columns


def _table_exists(conn, table: str) -> bool:
    inspector = inspect(conn)
    return table in inspector.get_table_names()


def _is_postgres() -> bool:
    return engine.url.get_backend_name() in ("postgresql", "postgres")


def apply_pack10_migration():
    """Pack 10: is_archived, archived_at в application."""
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
    """Pack 11: password_hash в user (для bcrypt-аутентификации)."""
    with engine.begin() as conn:
        if not _column_exists(conn, "user", "password_hash"):
            conn.execute(text(
                'ALTER TABLE "user" ADD COLUMN password_hash VARCHAR(128)'
            ))
            log.info("[migration:pack11] Added column user.password_hash")
        else:
            log.debug("[migration:pack11] Column user.password_hash already exists")


def apply_pack11_2_migration():
    """Pack 11.2: снимает NOT NULL с полей applicant для пошагового сохранения."""
    if not _is_postgres():
        log.debug("[migration:pack11_2] Skipping (only needed for PostgreSQL)")
        return

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
                err = str(e).lower()
                if "is in a column without not null" in err or "does not exist" in err:
                    log.debug(f"[migration:pack11_2] applicant.{field} already nullable or missing")
                else:
                    log.warning(f"[migration:pack11_2] Failed to drop NOT NULL on {field}: {e}")


def apply_pack13_migration():
    """
    Pack 13: создание таблицы applicant_document для OCR-документов.

    Таблица создаётся через init_db() (SQLModel.metadata.create_all),
    но если она ещё не существует — мы явно создадим тут как fallback.
    Также добавим индексы.
    """
    with engine.begin() as conn:
        if not _table_exists(conn, "applicant_document"):
            log.info(
                "[migration:pack13] Table applicant_document not found — "
                "expected to be created by SQLModel.metadata.create_all() in init_db()"
            )
            # Не создаём руками — пусть init_db() сделает.
            # Если здесь нет таблицы, значит модель ещё не подцепилась —
            # это надо поправить отдельно (импортировать модель в app.models.__init__).
            return

        # Создаём индексы (если их нет)
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_applicant_document_application_id "
                "ON applicant_document (application_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_applicant_document_doc_type "
                "ON applicant_document (doc_type)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_applicant_document_status "
                "ON applicant_document (status)"
            ))
            log.info("[migration:pack13] Indexes verified on applicant_document")
        except Exception as e:
            log.warning(f"[migration:pack13] Index creation failed: {e}")


def apply_pack15_migration():
    """
    Pack 15: создание таблицы translation для испанских переводов.

    Таблица создаётся через init_db() (SQLModel.metadata.create_all).
    Здесь только индексы для быстрого поиска по application_id и status.
    """
    with engine.begin() as conn:
        if not _table_exists(conn, "translation"):
            log.info(
                "[migration:pack15] Table translation not found — "
                "expected to be created by SQLModel.metadata.create_all() in init_db()"
            )
            return

        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_translation_application_id "
                "ON translation (application_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_translation_kind "
                "ON translation (kind)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_translation_status "
                "ON translation (status)"
            ))
            # Композитный индекс — быстрый GET всех переводов заявки
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_translation_app_kind "
                "ON translation (application_id, kind)"
            ))
            log.info("[migration:pack15] Indexes verified on translation")
        except Exception as e:
            log.warning(f"[migration:pack15] Index creation failed: {e}")
