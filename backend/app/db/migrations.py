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
    """Pack 11: password_hash в user."""
    with engine.begin() as conn:
        if not _column_exists(conn, "user", "password_hash"):
            conn.execute(text(
                'ALTER TABLE "user" ADD COLUMN password_hash VARCHAR(128)'
            ))
            log.info("[migration:pack11] Added column user.password_hash")
        else:
            log.debug("[migration:pack11] Column user.password_hash already exists")


def apply_pack11_2_migration():
    """Pack 11.2: снимает NOT NULL с полей applicant."""
    if not _is_postgres():
        log.debug("[migration:pack11_2] Skipping (only needed for PostgreSQL)")
        return

    nullable_fields = [
        "passport_number", "birth_date", "birth_place_latin", "nationality",
        "sex", "marital_status", "home_address", "home_country", "email", "phone",
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
    """Pack 13: индексы на applicant_document."""
    with engine.begin() as conn:
        if not _table_exists(conn, "applicant_document"):
            return
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_applicant_document_application_id ON applicant_document (application_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_applicant_document_doc_type ON applicant_document (doc_type)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_applicant_document_status ON applicant_document (status)"))
            log.info("[migration:pack13] Indexes verified on applicant_document")
        except Exception as e:
            log.warning(f"[migration:pack13] Index creation failed: {e}")


def apply_pack15_migration():
    """Pack 15: индексы на translation."""
    with engine.begin() as conn:
        if not _table_exists(conn, "translation"):
            return
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_translation_application_id ON translation (application_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_translation_kind ON translation (kind)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_translation_status ON translation (status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_translation_app_kind ON translation (application_id, kind)"))
            log.info("[migration:pack15] Indexes verified on translation")
        except Exception as e:
            log.warning(f"[migration:pack15] Index creation failed: {e}")


def apply_pack15_1_migration():
    """Pack 15.1: company.director_full_name_latin."""
    with engine.begin() as conn:
        if not _column_exists(conn, "company", "director_full_name_latin"):
            conn.execute(text(
                "ALTER TABLE company ADD COLUMN director_full_name_latin VARCHAR(128)"
            ))
            log.info("[migration:pack15_1] Added column company.director_full_name_latin")
        else:
            log.debug("[migration:pack15_1] Column company.director_full_name_latin already exists")


def apply_pack16_migration():
    """
    Pack 16: справочник банков + поле applicant.bank_id.

    1. Создаёт таблицу `bank` (через init_db / SQLModel.metadata.create_all,
       здесь только индексы и seed Альфа-Банка)
    2. Добавляет колонку applicant.bank_id (FK на bank)
    3. Создаёт индексы для уникальности bank_account + поиска по bank_id
    4. Заполняет seed-record для Альфа-Банка если таблица пустая
    """
    with engine.begin() as conn:
        # 1. Таблица bank — должна быть создана init_db() через SQLModel
        if not _table_exists(conn, "bank"):
            log.info(
                "[migration:pack16] Table bank not found — "
                "expected to be created by SQLModel.metadata.create_all() in init_db()"
            )
            # Не делаем ALTER applicant если таблицы bank нет — вернёмся следующим запуском
            return

        # 2. applicant.bank_id (FK на bank)
        if not _column_exists(conn, "applicant", "bank_id"):
            try:
                conn.execute(text(
                    "ALTER TABLE applicant ADD COLUMN bank_id INTEGER REFERENCES bank(id)"
                ))
                log.info("[migration:pack16] Added column applicant.bank_id")
            except Exception as e:
                log.warning(f"[migration:pack16] Failed to add applicant.bank_id: {e}")

        # 3. Индексы
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bank_bik ON bank (bik)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bank_name ON bank (name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_applicant_bank_id ON applicant (bank_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_applicant_bank_account ON applicant (bank_account)"))
            log.info("[migration:pack16] Indexes verified")
        except Exception as e:
            log.warning(f"[migration:pack16] Index creation failed: {e}")

        # 4. Seed Альфа-Банка если таблица пустая
        try:
            count_result = conn.execute(text("SELECT COUNT(*) FROM bank")).scalar()
            if count_result == 0:
                from datetime import datetime
                now = datetime.utcnow()
                # Используем SQLAlchemy text с параметрами — безопаснее против SQL injection
                conn.execute(text("""
                    INSERT INTO bank (
                        name, short_name, bik, inn, kpp, correspondent_account,
                        address, phone, email, website, is_active,
                        created_at, updated_at
                    ) VALUES (
                        :name, :short_name, :bik, :inn, :kpp, :corr,
                        :addr, :phone, :email, :web, :active,
                        :created, :updated
                    )
                """), {
                    "name": "АО «АЛЬФА-БАНК»",
                    "short_name": "Альфа-Банк",
                    "bik": "044525593",
                    "inn": "7728168971",
                    "kpp": "770801001",
                    "corr": "30101810200000000593",
                    "addr": "ул. Каланчёвская, 27, Москва, 107078",
                    "phone": "+7 495 620 91 91",
                    "email": "mail@alfabank.ru",
                    "web": "alfabank.ru",
                    "active": True,
                    "created": now,
                    "updated": now,
                })
                log.info("[migration:pack16] Seeded Альфа-Банк")
            else:
                log.debug(f"[migration:pack16] Banks already exist ({count_result}), skipping seed")
        except Exception as e:
            log.warning(f"[migration:pack16] Seed failed: {e}")
