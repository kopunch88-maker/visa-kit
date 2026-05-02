
"""
Миграции БД — добавление полей и таблиц после первоначального schema.

Каждая миграция идемпотентна — можно вызывать многократно безопасно.
Используем SQLAlchemy Inspector — работает и в SQLite, и в PostgreSQL.
"""

import json
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




def apply_pack17_0_migration():
    """
    Pack 17.0: создание таблицы region + поля Applicant для авто-ИНН самозанятого.

    1. Создаёт таблицу `region` (если её нет)
    2. Добавляет в `applicant` поля:
       - inn_registration_date (date)  — дата регистрации НПД
       - inn_source (varchar(32))      — 'auto-generated' | 'manual'
       - inn_kladr_code (varchar(13))  — KLADR региона из которого взят ИНН
    3. Сидит 10 базовых регионов (Москва, СПб, Сочи, Краснодар, Ростов-на-Дону,
       Махачкала, Грозный, Казань, Уфа, Нижний Новгород)

    Идемпотентна.
    """
    with engine.begin() as conn:
        # === 1. Таблица region ===
        if not _table_exists(conn, "region"):
            if _is_postgres():
                conn.execute(text("""
                    CREATE TABLE region (
                        id SERIAL PRIMARY KEY,
                        kladr_code VARCHAR(13) NOT NULL UNIQUE,
                        region_code VARCHAR(2) NOT NULL,
                        name VARCHAR(128) NOT NULL,
                        name_full VARCHAR(256) NOT NULL,
                        type VARCHAR(32) NOT NULL DEFAULT 'city',
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        diaspora_for_countries JSON NOT NULL DEFAULT '[]'::json,
                        notes VARCHAR(512),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """))
                conn.execute(text(
                    "CREATE INDEX ix_region_region_code ON region (region_code)"
                ))
            else:
                conn.execute(text("""
                    CREATE TABLE region (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kladr_code VARCHAR(13) NOT NULL UNIQUE,
                        region_code VARCHAR(2) NOT NULL,
                        name VARCHAR(128) NOT NULL,
                        name_full VARCHAR(256) NOT NULL,
                        type VARCHAR(32) NOT NULL DEFAULT 'city',
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        diaspora_for_countries TEXT NOT NULL DEFAULT '[]',
                        notes VARCHAR(512),
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text(
                    "CREATE INDEX ix_region_region_code ON region (region_code)"
                ))
            log.info("[migration:pack17_0] Created table region")
        else:
            log.debug("[migration:pack17_0] Table region already exists")

        # === 2. Поля в applicant ===
        if not _column_exists(conn, "applicant", "inn_registration_date"):
            conn.execute(text(
                "ALTER TABLE applicant ADD COLUMN inn_registration_date DATE"
            ))
            log.info("[migration:pack17_0] Added applicant.inn_registration_date")

        if not _column_exists(conn, "applicant", "inn_source"):
            conn.execute(text(
                "ALTER TABLE applicant ADD COLUMN inn_source VARCHAR(32)"
            ))
            log.info("[migration:pack17_0] Added applicant.inn_source")

        if not _column_exists(conn, "applicant", "inn_kladr_code"):
            conn.execute(text(
                "ALTER TABLE applicant ADD COLUMN inn_kladr_code VARCHAR(13)"
            ))
            log.info("[migration:pack17_0] Added applicant.inn_kladr_code")

        # === 3. Seed базовых регионов ===
        try:
            count_result = conn.execute(text("SELECT COUNT(*) FROM region")).scalar()
            if count_result == 0:
                _seed_pack17_regions(conn)
                log.info("[migration:pack17_0] Seeded 10 base regions")
            else:
                log.debug(
                    f"[migration:pack17_0] region table has {count_result} rows, skipping seed"
                )
        except Exception as e:
            log.warning(f"[migration:pack17_0] Seed failed: {e}")


def _seed_pack17_regions(conn):
    """
    Базовые 10 регионов для старта. Менеджер дополнит через UI.

    KLADR коды проверены через https://kladr-rf.ru/.
    Диаспоры — на основе общеизвестных миграционных потоков:
    - Сочи: TUR, AZE
    - Краснодар: ARM, AZE, TUR
    - Ростов-на-Дону: ARM, GEO
    - Махачкала, Грозный: AZE
    - Казань, Уфа: TUR (тюркская связь)
    - Москва, СПб, Нижний Новгород: универсальные (пустой список)
    """
    regions = [
        # KLADR,           code, name,           name_full,                                              type,    diaspora
        ("7700000000000", "77", "Москва",          "г. Москва",                                                  "city", []),
        ("7800000000000", "78", "Санкт-Петербург", "г. Санкт-Петербург",                                        "city", []),
        ("2300000700000", "23", "Сочи",            "Краснодарский край, городской округ Сочи",                  "city", ["TUR", "AZE"]),
        ("2300000100000", "23", "Краснодар",       "Краснодарский край, городской округ Краснодар",             "city", ["ARM", "AZE", "TUR"]),
        ("6100000100000", "61", "Ростов-на-Дону",  "Ростовская область, городской округ Ростов-на-Дону",        "city", ["ARM", "GEO"]),
        ("0500000100000", "05", "Махачкала",       "Республика Дагестан, городской округ Махачкала",            "city", ["AZE"]),
        ("2000000100000", "20", "Грозный",         "Чеченская Республика, городской округ Грозный",             "city", ["AZE"]),
        ("1600000100000", "16", "Казань",          "Республика Татарстан, городской округ Казань",              "city", ["TUR"]),
        ("0200000100000", "02", "Уфа",             "Республика Башкортостан, городской округ Уфа",              "city", ["TUR"]),
        ("5200000100000", "52", "Нижний Новгород", "Нижегородская область, городской округ Нижний Новгород",    "city", []),
    ]

    from datetime import datetime
    now = datetime.utcnow()

    for kladr, region_code, name, name_full, type_, diaspora in regions:
        diaspora_json = json.dumps(diaspora)
        if _is_postgres():
            sql = text("""
                INSERT INTO region
                    (kladr_code, region_code, name, name_full, type,
                     is_active, diaspora_for_countries, created_at, updated_at)
                VALUES
                    (:kladr_code, :region_code, :name, :name_full, :type,
                     TRUE, CAST(:diaspora AS JSON), :created, :updated)
                ON CONFLICT (kladr_code) DO NOTHING
            """)
        else:
            sql = text("""
                INSERT OR IGNORE INTO region
                    (kladr_code, region_code, name, name_full, type,
                     is_active, diaspora_for_countries, created_at, updated_at)
                VALUES
                    (:kladr_code, :region_code, :name, :name_full, :type,
                     1, :diaspora, :created, :updated)
            """)
        conn.execute(sql, {
            "kladr_code": kladr,
            "region_code": region_code,
            "name": name,
            "name_full": name_full,
            "type": type_,
            "diaspora": diaspora_json,
            "created": now,
            "updated": now,
        })



def apply_pack17_2_4_migration():
    """
    Pack 17.2.4: создание таблиц self_employed_registry и registry_import_log
    для локальной БД самозанятых из открытого дампа ФНС.

    1. Таблица self_employed_registry:
       - PK = inn (varchar(12))
       - Индексы по region_code, is_used, imported_at
    2. Таблица registry_import_log — история импортов

    Идемпотентна. Таблицы создаются через SQLModel.metadata.create_all() в init_db(),
    эта миграция только добавляет недостающие индексы и проверяет наличие таблиц.
    """
    with engine.begin() as conn:
        # === self_employed_registry ===
        if not _table_exists(conn, "self_employed_registry"):
            log.info(
                "[migration:pack17_2_4] Table self_employed_registry not found — "
                "expected to be created by SQLModel.metadata.create_all() in init_db()"
            )
            # Таблицы создаст init_db через SQLModel — на следующем запуске будем здесь
            return

        # Индексы (CREATE INDEX IF NOT EXISTS работает и в Postgres, и в SQLite)
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_self_employed_registry_region_code "
                "ON self_employed_registry (region_code)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_self_employed_registry_is_used "
                "ON self_employed_registry (is_used)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_self_employed_registry_imported_at "
                "ON self_employed_registry (imported_at)"
            ))
            # Композитный индекс — для запроса WHERE is_used=FALSE ORDER BY RANDOM()
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_self_employed_registry_unused "
                "ON self_employed_registry (is_used) WHERE is_used = FALSE"
            )) if _is_postgres() else None
            log.info("[migration:pack17_2_4] Indexes verified on self_employed_registry")
        except Exception as e:
            log.warning(f"[migration:pack17_2_4] Index creation failed: {e}")

        # === registry_import_log ===
        if _table_exists(conn, "registry_import_log"):
            try:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_registry_import_log_started_at "
                    "ON registry_import_log (started_at)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_registry_import_log_status "
                    "ON registry_import_log (status)"
                ))
                log.info("[migration:pack17_2_4] Indexes verified on registry_import_log")
            except Exception as e:
                log.warning(f"[migration:pack17_2_4] registry_import_log index creation failed: {e}")


def apply_pack17_2_4_1_migration():
    """
    Pack 17.2.4.1: меняет тип колонок registry_import_log.zip_size_bytes
    и xml_size_bytes с INTEGER на BIGINT.

    Причина: реальный распакованный XML дампа ФНС ~12.25 ГБ, что не
    помещается в обычный 32-битный INTEGER (макс ~2.1 ГБ). Это вызывало
    NumericValueOutOfRange при первом импорте.

    Идемпотентна — если колонки уже BIGINT, просто пропускаем.
    Только для PostgreSQL (в SQLite типы динамические — не нужно).
    """
    if not _is_postgres():
        log.debug("[migration:pack17_2_4_1] Skipping (only needed for PostgreSQL)")
        return

    with engine.begin() as conn:
        if not _table_exists(conn, "registry_import_log"):
            log.debug("[migration:pack17_2_4_1] Table registry_import_log not yet created")
            return

        for col in ("zip_size_bytes", "xml_size_bytes"):
            try:
                # Проверим текущий тип
                row = conn.execute(text("""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = 'registry_import_log' AND column_name = :col
                """), {"col": col}).first()

                if row is None:
                    log.warning(f"[migration:pack17_2_4_1] Column {col} not found")
                    continue

                current_type = row[0]
                if current_type == "bigint":
                    log.debug(f"[migration:pack17_2_4_1] {col} already BIGINT, skip")
                    continue

                conn.execute(text(
                    f"ALTER TABLE registry_import_log "
                    f"ALTER COLUMN {col} TYPE BIGINT"
                ))
                log.info(f"[migration:pack17_2_4_1] Changed {col} from {current_type} to BIGINT")
            except Exception as e:
                log.warning(f"[migration:pack17_2_4_1] Failed to alter {col}: {e}")

        # Также сбросим зависшие 'queued' и 'running' импорты (они уже мертвы — это другой контейнер)
        try:
            result = conn.execute(text("""
                UPDATE registry_import_log
                SET status = 'failed',
                    finished_at = COALESCE(finished_at, NOW()),
                    error_message = COALESCE(error_message,
                        'Reset by pack17_2_4_1 migration: container restarted before completion')
                WHERE status IN ('queued', 'running')
            """))
            reset_count = result.rowcount or 0
            if reset_count > 0:
                log.info(f"[migration:pack17_2_4_1] Reset {reset_count} stuck import(s) to 'failed'")
        except Exception as e:
            log.warning(f"[migration:pack17_2_4_1] Failed to reset stuck imports: {e}")
