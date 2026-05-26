
"""
Миграции БД — добавление полей и таблиц после первоначального schema.

Каждая миграция идемпотентна — можно вызывать многократно безопасно.
Используем SQLAlchemy Inspector — работает и в SQLite, и в PostgreSQL.
"""

import json
import logging
from sqlalchemy import text, inspect
from app.db.session import engine
from app.db.migration_pack17_6 import apply_pack17_6_migration
from app.db.migration_pack18_0 import apply_pack18_0_migration
apply_pack17_6_migration(engine)

# Pack 18.0 — справочники ИФНС и МФЦ
apply_pack18_0_migration(engine)

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


def apply_pack28_0_migration():
    """
    Pack 28.0 (07.05.2026): создание таблицы npd_candidate для пула чистых
    самозанятых из rmsp-pp.nalog.ru, верифицированных через EGRUL + NPD API.

    Создание самой таблицы делает SQLModel.metadata.create_all() в init_db
    после того как модель зарегистрирована в app.models.__init__.py.

    Эта миграция:
      - Проверяет наличие таблицы (если нет — лог + return, ждём init_db)
      - Создаёт индексы для быстрого подбора:
          * (region_code, status) — основной запрос «verified кандидаты в регионе»
          * (status) — общая статистика
          * (used_by_applicant_id) — для проверки идемпотентности
          * Частичный индекс (region_code) WHERE status='verified' — самый частый
            запрос в горячем пути выдачи.

    Идемпотентна: CREATE INDEX IF NOT EXISTS работает в Postgres.
    """
    with engine.begin() as conn:
        if not _table_exists(conn, "npd_candidate"):
            log.info(
                "[migration:pack28_0] Table npd_candidate not found — "
                "expected to be created by SQLModel.metadata.create_all() in init_db. "
                "Make sure app.models.npd_candidate is imported in app.models.__init__.py"
            )
            return

        try:
            # Основной hot-path: подбор verified кандидатов по региону
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_npd_candidate_region_status "
                "ON npd_candidate (region_code, status)"
            ))

            # Для статистики
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_npd_candidate_status "
                "ON npd_candidate (status)"
            ))

            # Идемпотентность inn-accept — проверка «кому был выдан»
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_npd_candidate_used_by_applicant "
                "ON npd_candidate (used_by_applicant_id)"
            ))

            # Для cron «давно ли был последний refill»
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_npd_candidate_fetched_at "
                "ON npd_candidate (fetched_at)"
            ))

            # Postgres-only: частичный индекс на самый горячий запрос
            if _is_postgres():
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_npd_candidate_verified_region "
                    "ON npd_candidate (region_code) "
                    "WHERE status = 'verified'"
                ))

            log.info("[migration:pack28_0] Indexes verified on npd_candidate")
        except Exception as e:
            log.warning(f"[migration:pack28_0] Index creation failed: {e}")


def apply_pack28_2_migration():
    """
    Pack 28 ????? 2 (08.05.2026): ??????? npd_refill_task.

    ????????? ????? SQLModel.metadata.create_all() ? init_db, ??? ??????
    ??????? ??? performance.
    """
    with engine.begin() as conn:
        if not _table_exists(conn, "npd_refill_task"):
            log.info(
                "[migration:pack28_2] Table npd_refill_task not found - "
                "expected to be created by SQLModel.metadata.create_all()"
            )
            return

        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_npd_refill_task_status "
                "ON npd_refill_task (status)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_npd_refill_task_kind "
                "ON npd_refill_task (kind)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_npd_refill_task_region_code "
                "ON npd_refill_task (region_code)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_npd_refill_task_created_at "
                "ON npd_refill_task (created_at)"
            ))
            if _is_postgres():
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_npd_refill_task_active_lazy "
                    "ON npd_refill_task (region_code, created_at) "
                    "WHERE kind = 'lazy_region' AND status IN ('pending', 'running')"
                ))
            log.info("[migration:pack28_2] Indexes verified on npd_refill_task")
        except Exception as e:
            log.warning(f"[migration:pack28_2] Index creation failed: {e}")


def apply_pack28_5_migration():
    """
    Pack 28.5 (08.05.2026): добавление поля result_registration_date
    в таблицу npd_refill_task для бинпоиска даты регистрации НПД.

    Также пометка существующих applicants с inn_source='npd_pool' как
    'npd_pool_synthetic' (они получили синтетическую дату по Pack 18.3.4).
    """
    with engine.begin() as conn:
        # === Добавление колонки result_registration_date в npd_refill_task
        if not _table_exists(conn, "npd_refill_task"):
            log.info(
                "[migration:pack28_5] Table npd_refill_task not found — "
                "skip column add (Pack 28.2 migration не применился?)"
            )
        elif not _column_exists(conn, "npd_refill_task", "result_registration_date"):
            try:
                conn.execute(text(
                    "ALTER TABLE npd_refill_task "
                    "ADD COLUMN result_registration_date DATE"
                ))
                log.info(
                    "[migration:pack28_5] Added npd_refill_task.result_registration_date"
                )
            except Exception as e:
                log.warning(f"[migration:pack28_5] Add column failed: {e}")
        else:
            log.info(
                "[migration:pack28_5] result_registration_date already exists"
            )

        # === Backfill: применять только если есть applicant с inn_source='npd_pool'
        # (Pack 28.2 default). Меняем на 'npd_pool_synthetic' потому что у них
        # точно синтетическая дата (бинпоиск на момент Pack 28.2 не делался).
        try:
            result = conn.execute(text(
                "UPDATE applicant SET inn_source = 'npd_pool_synthetic' "
                "WHERE inn_source = 'npd_pool'"
            ))
            count = result.rowcount if hasattr(result, 'rowcount') else 0
            if count > 0:
                log.info(
                    f"[migration:pack28_5] Backfilled {count} applicants: "
                    f"npd_pool → npd_pool_synthetic"
                )
        except Exception as e:
            log.warning(f"[migration:pack28_5] Backfill failed: {e}")

# ============================================================================
# Pack 29.0 — Per-company contract template slug
# ============================================================================
def apply_pack29_0_migration():
    """
    Pack 29.0 — добавление company.contract_template_slug + индекс +
    backfill по ИНН для известных компаний.

    Идемпотентна. Применяется при каждом старте через lifespan.
    """
    from sqlalchemy import create_engine, text as sa_text
    from app.config import settings

    # Маппинг ИНН → slug. Должен совпадать с
    # contracts_registry.COMPANY_INN_TO_SLUG (Pack 29.0).
    COMPANY_INN_TO_SLUG = {
        "6168006148": "sk10",
        "9705067089": "ssk",
        "7701411241": "kns_grupp",
        "4003040489": "hayat",
        "7714709349": "avtodom",
        "7727286316": "factor_stroy",
        "7810890724": "protech",
        "7706796034": "buki_vedi",
        "7729634103": "tikompani",
        "7731579629": "king_david",
    }

    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        # 1. ADD COLUMN IF NOT EXISTS
        col_exists = conn.execute(sa_text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'company' AND column_name = 'contract_template_slug'
        """)).first()
        if not col_exists:
            conn.execute(sa_text("""
                ALTER TABLE company
                ADD COLUMN contract_template_slug VARCHAR(64) NULL
            """))
            print("  ✓ Pack 29.0: ADD COLUMN company.contract_template_slug")

        # 2. CREATE INDEX IF NOT EXISTS
        idx_exists = conn.execute(sa_text("""
            SELECT 1 FROM pg_indexes
            WHERE indexname = 'ix_company_contract_template_slug'
        """)).first()
        if not idx_exists:
            conn.execute(sa_text("""
                CREATE INDEX ix_company_contract_template_slug
                ON company (contract_template_slug)
            """))
            print("  ✓ Pack 29.0: CREATE INDEX ix_company_contract_template_slug")

        # 3. Backfill — только для компаний с известным ИНН и пустым slug
        for inn, slug in COMPANY_INN_TO_SLUG.items():
            conn.execute(sa_text("""
                UPDATE company
                SET contract_template_slug = :slug
                WHERE tax_id_primary = :inn
                  AND (contract_template_slug IS NULL OR contract_template_slug = '')
            """), {"slug": slug, "inn": inn})



# ============================================================================
# Pack 30.0 — флаг is_urgent на Application
# ============================================================================

def apply_pack30_0_migration() -> None:
    """Pack 30.0 миграция:
       - ALTER TABLE application ADD COLUMN is_urgent BOOLEAN NOT NULL DEFAULT FALSE
       - CREATE INDEX ix_application_is_urgent
       Идемпотентна — IF NOT EXISTS на обоих шагах.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS is_urgent BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_application_is_urgent "
            "ON application (is_urgent)"
        ))
    print("[migration] Pack 30.0: application.is_urgent ready")


# ======================================
# Pack 38.1 — флаг is_paid на Application
# ======================================
def apply_pack38_1_migration() -> None:
    from sqlalchemy import text
    from app.db.session import engine
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS is_paid BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_application_is_paid "
            "ON application (is_paid)"
        ))
    print("[migration] Pack 38.1: application.is_paid ready")


# ============================================================================
# Pack 34.2 — флаг is_ready_for_pickup на Application («Готово, можно забирать»)
# ============================================================================

def apply_pack34_2_migration() -> None:
    """Pack 34.2 миграция:
       - ALTER TABLE application ADD COLUMN is_ready_for_pickup BOOLEAN
         NOT NULL DEFAULT FALSE
       - CREATE INDEX ix_application_is_ready_for_pickup
       Идемпотентна — IF NOT EXISTS на обоих шагах.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS is_ready_for_pickup BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_application_is_ready_for_pickup "
            "ON application (is_ready_for_pickup)"
        ))
    print("[migration] Pack 34.2: application.is_ready_for_pickup ready")


# ============================================================================
# Pack 35.2 — applicant.passport_issuer_ru (локализованное название органа)
# ============================================================================

def apply_pack35_2_migration() -> None:
    """Pack 35.2 миграция:
       - ALTER TABLE applicant ADD COLUMN passport_issuer_ru VARCHAR(256)
       Идемпотентна — IF NOT EXISTS / column check.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        if not _column_exists(conn, "applicant", "passport_issuer_ru"):
            try:
                conn.execute(text(
                    "ALTER TABLE applicant ADD COLUMN passport_issuer_ru VARCHAR(256)"
                ))
                log.info("[migration:pack35_2] Added applicant.passport_issuer_ru")
            except Exception as e:
                log.warning(f"[migration:pack35_2] Add column failed: {e}")
        else:
            log.debug("[migration:pack35_2] applicant.passport_issuer_ru already exists")
    print("[migration] Pack 35.2: applicant.passport_issuer_ru ready")


# ============================================================================
# Pack 36.1 — application.nie и application.fingerprint_date (TIE формы)
# ============================================================================

def apply_pack36_1_migration() -> None:
    """Pack 36.1 миграция:
       - ALTER TABLE application ADD COLUMN nie VARCHAR(16)
       - ALTER TABLE application ADD COLUMN fingerprint_date DATE
       Идемпотентна — IF NOT EXISTS на обоих шагах.

       nie заполняется после одобрения заявления MI-T (полиция выдаёт
       номер). fingerprint_date — дата визита в комиссариат для снятия
       отпечатков, после неё генерятся 15_MI-TIE.pdf и 16_EX-17.pdf.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS nie VARCHAR(16)"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS fingerprint_date DATE"
        ))
    print("[migration] Pack 36.1: application.nie + fingerprint_date ready")
# ============================================================================
# Pack 37.0 — AI Document Audit
# ============================================================================
#
# ВСТАВИТЬ В КОНЕЦ ФАЙЛА backend/app/db/migrations.py
# (перед последней закрывающей строкой если есть, или просто дописать в конец)
#
# Сами таблицы application_audit_report и audit_finding создаются автоматически
# через SQLModel.metadata.create_all(engine) в init_db() — нужно только чтобы
# модели были зарегистрированы в app/models/__init__.py (см. файл 2/5).
#
# Эта миграция создаёт дополнительные композитные индексы для производительности
# (поиск открытых findings по category, история прогонов по application_id+started_at).
# Идемпотентна — IF NOT EXISTS на всех CREATE INDEX.
# ============================================================================

def apply_pack37_0_migration():
    """
    Pack 37.0 — AI Document Audit система.

    Создаёт композитные индексы для двух таблиц:
    - application_audit_report (история прогонов)
    - audit_finding (findings внутри прогона)

    Сами таблицы создаст SQLModel.metadata.create_all() в init_db() — здесь
    проверяем наличие и докручиваем индексы.

    Идемпотентна, безопасна для многократного запуска.
    """
    from sqlalchemy import text, inspect
    from app.db.session import engine

    log_prefix = "[migrations:pack37.0]"
    print(f"{log_prefix} Starting...")

    # 1. Проверка наличия таблиц (создаются автоматически через init_db).
    #    Если их нет — значит init_db ещё не отработал, выходим и ждём
    #    следующего старта (паттерн как в apply_pack16_migration).
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    required_tables = {"application_audit_report", "audit_finding"}
    missing = required_tables - existing_tables
    if missing:
        print(
            f"{log_prefix} ⚠️ Tables not yet created: {missing}. "
            f"Will be created by SQLModel.metadata.create_all() in init_db(). "
            f"Re-run migration on next startup."
        )
        return

    print(f"{log_prefix} ✓ Tables exist: {required_tables}")

    # 2. Композитные индексы для частых запросов
    indexes_to_create = [
        # Самый частый запрос: «последние прогоны для заявки»
        # SELECT * FROM application_audit_report
        # WHERE application_id = X ORDER BY started_at DESC
        (
            "ix_audit_report_app_started",
            "application_audit_report",
            "application_id, started_at DESC",
        ),
        # Активные прогоны для polling'а (is_running=true редко, индекс selective)
        (
            "ix_audit_report_running",
            "application_audit_report",
            "is_running",
            "WHERE is_running = true",
        ),
        # Список findings отчёта с фильтром по статусу
        # SELECT * FROM audit_finding WHERE report_id = X AND status = 'open'
        # ORDER BY severity, sort_order
        (
            "ix_finding_report_status",
            "audit_finding",
            "report_id, status",
        ),
        # Список open findings по категориям (для UI группировки)
        (
            "ix_finding_report_category_severity",
            "audit_finding",
            "report_id, category, severity",
        ),
    ]

    with engine.connect() as conn:
        for idx_spec in indexes_to_create:
            if len(idx_spec) == 4:
                name, table, cols, where_clause = idx_spec
                sql = (
                    f"CREATE INDEX IF NOT EXISTS {name} "
                    f"ON {table} ({cols}) {where_clause}"
                )
            else:
                name, table, cols = idx_spec
                sql = (
                    f"CREATE INDEX IF NOT EXISTS {name} "
                    f"ON {table} ({cols})"
                )
            try:
                conn.execute(text(sql))
                print(f"{log_prefix} ✓ Index {name} ready")
            except Exception as e:
                # Не критично — индексы оптимизация. Логируем и идём дальше.
                print(f"{log_prefix} ⚠️ Failed to create {name}: {e}")
        conn.commit()

    # 3. Проверка что enum-значения в строковых полях не нарушены
    # (на случай если в БД остались legacy записи — для свежего деплоя no-op)
    with engine.connect() as conn:
        # Проверка verdict
        result = conn.execute(text(
            "SELECT DISTINCT verdict FROM application_audit_report"
        )).all()
        valid_verdicts = {"PASS", "WARN", "FAIL"}
        for row in result:
            if row[0] not in valid_verdicts:
                print(
                    f"{log_prefix} ⚠️ Found invalid verdict='{row[0]}' "
                    f"in application_audit_report — manual cleanup needed"
                )

        # Проверка severity
        result = conn.execute(text(
            "SELECT DISTINCT severity FROM audit_finding"
        )).all()
        valid_severities = {"critical", "warning", "info"}
        for row in result:
            if row[0] not in valid_severities:
                print(
                    f"{log_prefix} ⚠️ Found invalid severity='{row[0]}' "
                    f"in audit_finding — manual cleanup needed"
                )

    print(f"{log_prefix} Done.")


# ============================================================================
# Pack 39.0 — Final Submission Audit (физическая проверка перед подачей)
# ============================================================================
def apply_pack39_0_migration() -> None:
    """Pack 39.0 миграция:
       Создаёт 3 таблицы для финальной проверки физических документов:
         - final_submission_document       (с историей версий)
         - final_submission_audit_report
         - final_submission_finding

       ON DELETE CASCADE на applicant_id во всех таблицах.
       Частичный UNIQUE index на (applicant_id, sha256) WHERE is_active=TRUE.
       Идемпотентна — CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        # ----- final_submission_document -----
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS final_submission_document (
                id                       SERIAL PRIMARY KEY,
                applicant_id             INTEGER NOT NULL REFERENCES applicant(id) ON DELETE CASCADE,
                application_id           INTEGER REFERENCES application(id) ON DELETE SET NULL,

                original_filename        VARCHAR(512) NOT NULL,
                mime_type                VARCHAR(128) NOT NULL,
                file_size_bytes          BIGINT NOT NULL,
                s3_key                   VARCHAR(512) NOT NULL,
                sha256                   VARCHAR(64) NOT NULL,

                doc_category             VARCHAR(50),
                doc_category_confidence  NUMERIC(4,3),
                doc_category_source      VARCHAR(20) NOT NULL DEFAULT 'ai',

                extracted_text           TEXT,
                extraction_method        VARCHAR(20),
                extraction_cost_usd      NUMERIC(10,4) NOT NULL DEFAULT 0,
                page_count               INTEGER,

                is_active                BOOLEAN NOT NULL DEFAULT TRUE,
                previous_version_id      INTEGER REFERENCES final_submission_document(id) ON DELETE SET NULL,
                replaced_at              TIMESTAMP,

                uploaded_at              TIMESTAMP NOT NULL DEFAULT NOW(),
                uploaded_by              VARCHAR(255)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsd_applicant
                ON final_submission_document(applicant_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsd_application
                ON final_submission_document(application_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsd_applicant_active
                ON final_submission_document(applicant_id, is_active)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsd_doc_category
                ON final_submission_document(doc_category)
        """))
        # Частичный UNIQUE: среди активных файлов клиента не может быть двух одинаковых.
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fsd_applicant_sha_active
                ON final_submission_document(applicant_id, sha256)
                WHERE is_active = TRUE
        """))

        # ----- final_submission_audit_report -----
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS final_submission_audit_report (
                id                            SERIAL PRIMARY KEY,
                application_id                INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
                applicant_id                  INTEGER NOT NULL REFERENCES applicant(id) ON DELETE CASCADE,

                verdict                       VARCHAR(20) NOT NULL DEFAULT 'WARN',

                model_used                    VARCHAR(100),
                prompt_version                VARCHAR(20),
                input_tokens                  INTEGER,
                output_tokens                 INTEGER,
                vision_pages                  INTEGER DEFAULT 0,
                cost_usd                      NUMERIC(10,4),

                included_document_ids         JSON,
                document_categories_snapshot  JSON,

                is_running                    BOOLEAN NOT NULL DEFAULT TRUE,
                started_at                    TIMESTAMP NOT NULL DEFAULT NOW(),
                finished_at                   TIMESTAMP,
                duration_ms                   INTEGER,
                error                         JSON,

                triggered_by                  VARCHAR(255),
                summary_counts                JSON,
                inspector_summary             TEXT,

                created_at                    TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsar_application
                ON final_submission_audit_report(application_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsar_applicant
                ON final_submission_audit_report(applicant_id)
        """))

        # ----- final_submission_finding -----
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS final_submission_finding (
                id                  SERIAL PRIMARY KEY,
                report_id           INTEGER NOT NULL REFERENCES final_submission_audit_report(id) ON DELETE CASCADE,

                category            VARCHAR(30) NOT NULL,
                severity            VARCHAR(20) NOT NULL,

                title               VARCHAR(500) NOT NULL,
                description         TEXT,
                recommendation      TEXT,

                affected_documents  JSON,
                field_name          VARCHAR(128),
                values_found        JSON,

                status              VARCHAR(20) NOT NULL DEFAULT 'open',
                resolved_at         TIMESTAMP,
                resolved_by         VARCHAR(255),
                resolution_note     TEXT,

                sort_order          INTEGER NOT NULL DEFAULT 0,
                created_at          TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsf_report
                ON final_submission_finding(report_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsf_category
                ON final_submission_finding(category)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsf_severity
                ON final_submission_finding(severity)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fsf_status
                ON final_submission_finding(status)
        """))

    print("[migration] Pack 39.0: Final Submission Audit tables ready")


# ============================================================================
# Pack 39.0-A2 — переименование s3_key → storage_key + original_storage_key
# ============================================================================
def apply_pack39_0_A2_migration() -> None:
    """Pack 39.0-A2:
       - RENAME COLUMN final_submission_document.s3_key → storage_key
         (если ещё не переименовано — проверка через information_schema)
       - ADD COLUMN IF NOT EXISTS original_storage_key VARCHAR(512)

       Идемпотентна. Безопасна: таблица пустая на момент применения.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        # RENAME — только если ещё есть старая колонка s3_key
        has_old = conn.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'final_submission_document'
              AND column_name = 's3_key'
        """)).first()

        if has_old:
            conn.execute(text("""
                ALTER TABLE final_submission_document
                RENAME COLUMN s3_key TO storage_key
            """))
            print("[migration] Pack 39.0-A2: renamed s3_key → storage_key")
        else:
            print("[migration] Pack 39.0-A2: storage_key already exists, skipping rename")

        # ADD original_storage_key
        conn.execute(text("""
            ALTER TABLE final_submission_document
            ADD COLUMN IF NOT EXISTS original_storage_key VARCHAR(512)
        """))

    print("[migration] Pack 39.0-A2: final_submission_document schema updated")


# ============================================================================
# Pack 50.0-A — application.application_type (Самозанятый / Найм)
# ============================================================================
def apply_pack50_0_A_migration() -> None:
    """Pack 50.0-A:
       - ALTER TABLE application ADD COLUMN application_type VARCHAR(16)
         NOT NULL DEFAULT 'SELF_EMPLOYED'
       - CREATE INDEX ix_application_application_type
       - Backfill: все существующие NULL → 'SELF_EMPLOYED' (на случай если
         колонка уже была без NOT NULL DEFAULT — двойная защита).

       Идемпотентна — IF NOT EXISTS на всех шагах.

       Значения enum (см. app.models.application.ApplicationType):
         - 'SELF_EMPLOYED' — самозанятый (бывшая DN-логика, дефолт для legacy)
         - 'EMPLOYMENT'    — найм (трудовой договор + работодатель)
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        # 1. ADD COLUMN
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS application_type VARCHAR(16) "
            "NOT NULL DEFAULT 'SELF_EMPLOYED'"
        ))

        # 2. Backfill — защитный шаг, если колонка уже существовала без NOT NULL
        result = conn.execute(text(
            "UPDATE application SET application_type = 'SELF_EMPLOYED' "
            "WHERE application_type IS NULL"
        ))
        if result.rowcount:
            print(f"[migration] Pack 50.0-A: backfilled {result.rowcount} rows to SELF_EMPLOYED")

        # 3. INDEX
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_application_application_type "
            "ON application (application_type)"
        ))

    print("[migration] Pack 50.0-A: application.application_type ready")


# ============================================================================
# Pack 50.7-A — Приказ Т-9 о командировке (найм)
# ============================================================================
def apply_pack50_7_A_migration() -> None:
    """Pack 50.7-A — поля для генерации Приказа Т-9 о командировке.

    company:
      - okpo VARCHAR(8) NULL — код ОКПО (8 цифр), для шапки Т-9.

    position:
      - business_trip_purpose TEXT NULL — цель командировки (текст для §"с целью"
        в Т-9). Генерируется LLM при создании должности, может правиться вручную.

    application:
      - business_trip_order_number VARCHAR(16) — номер приказа Т-9 ("37/к").
      - business_trip_order_date DATE — дата приказа (дефолт = contract_sign_date).
      - business_trip_start_date DATE — начало командировки.
      - business_trip_end_date DATE — конец командировки.
      - business_trip_purpose_override TEXT — override цели для конкретной заявки
        (если NULL — берётся position.business_trip_purpose).
      - business_trip_duration_words VARCHAR(32) — срок словами ("Сорок шесть").
      - business_trip_duration_unit VARCHAR(16) — единица: "days"/"months"/"years".
      - business_trip_place_short BOOLEAN DEFAULT FALSE — короткий формат адреса
        (True = "Испания, г. Барселона"; False = полный с индексом).
      - employee_tab_number VARCHAR(16) — табельный номер сотрудника.

    Идемпотентна — все ADD COLUMN IF NOT EXISTS.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        # === company ===
        conn.execute(text(
            "ALTER TABLE company ADD COLUMN IF NOT EXISTS okpo VARCHAR(8)"
        ))

        # === position ===
        conn.execute(text(
            "ALTER TABLE position ADD COLUMN IF NOT EXISTS business_trip_purpose TEXT"
        ))

        # === application — Приказ Т-9 ===
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS business_trip_order_number VARCHAR(16)"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS business_trip_order_date DATE"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS business_trip_start_date DATE"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS business_trip_end_date DATE"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS business_trip_purpose_override TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS business_trip_duration_words VARCHAR(32)"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS business_trip_duration_unit VARCHAR(16)"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS business_trip_place_short BOOLEAN "
            "NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE application "
            "ADD COLUMN IF NOT EXISTS employee_tab_number VARCHAR(16)"
        ))

    print("[migration] Pack 50.7-A: business trip fields ready (company.okpo, "
          "position.business_trip_purpose, application.business_trip_*)")


# ============================================================================
# Pack 50.7-C-prep — applicant.full_name_accusative для Приказа Т-9
# ============================================================================
def apply_pack50_7_C_prep_migration() -> None:
    """Pack 50.7-C-prep — добавляет applicant.full_name_accusative (винительный
    падеж ФИО для подстановки в Приказ Т-9 в фразу "Направить в командировку...").

    Идемпотентна — ADD COLUMN IF NOT EXISTS.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE applicant "
            "ADD COLUMN IF NOT EXISTS full_name_accusative VARCHAR(128)"
        ))

    print("[migration] Pack 50.7-C-prep: applicant.full_name_accusative ready")


# ============================================================================
# Pack 50.1-A — Трудовой договор (найм): поля компании ogrn + email
# ============================================================================
def apply_pack50_1_A_migration() -> None:
    """Pack 50.1-A — добавляет поля для Трудового договора.

    company:
      - ogrn VARCHAR(15) NULL — ОГРН (13 цифр для ЮЛ или 15 для ИП).
      - email VARCHAR(128) NULL — email компании для электронного
        документооборота (используется в Трудовом договоре, п.1.7).

    Идемпотентна — ADD COLUMN IF NOT EXISTS.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE company ADD COLUMN IF NOT EXISTS ogrn VARCHAR(15)"
        ))
        conn.execute(text(
            "ALTER TABLE company ADD COLUMN IF NOT EXISTS email VARCHAR(128)"
        ))

    print("[migration] Pack 50.1-A: company.ogrn + company.email ready")


# ============================================================================
# Pack 50.1-F2 — СНИЛС работника для Трудового договора
# ============================================================================
def apply_pack50_1_F2_migration() -> None:
    """Pack 50.1-F2 — добавляет applicant.snils.

    applicant:
      - snils VARCHAR(14) NULL — Страховой номер индивидуального лицевого счёта.
        Формат: XXX-XXX-XXX XX (14 символов с дефисами и пробелом).
        Используется в Трудовом договоре в реквизитах работника.

    Идемпотентна — ADD COLUMN IF NOT EXISTS.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE applicant ADD COLUMN IF NOT EXISTS snils VARCHAR(14)"
        ))

    print("[migration] Pack 50.1-F2: applicant.snils ready")


# ============================================================================
# Pack 50.1-H — Шрифт для договора самозанятого (01_Договор.docx)
# ============================================================================
def apply_pack50_1_H_migration() -> None:
    """Pack 50.1-H — добавляет company.contract_font_family.

    company:
      - contract_font_family VARCHAR(64) NULL — имя шрифта для рендера
        01_Договор.docx. Если NULL — используется шрифт из самого шаблона
        (обычно Microsoft Sans Serif).
        Возможные значения: "Times New Roman", "Arial", "Calibri",
        "Microsoft Sans Serif".

    Идемпотентна — ADD COLUMN IF NOT EXISTS.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE company ADD COLUMN IF NOT EXISTS contract_font_family VARCHAR(64)"
        ))

    print("[migration] Pack 50.1-H: company.contract_font_family ready")


# ============================================================================
# Pack 50.1-G — Шаблон + шрифт Трудового договора (per-company)
# ============================================================================
def apply_pack50_1_G_migration() -> None:
    """Pack 50.1-G — добавляет per-company настройки Трудового договора.

    company:
      - employment_contract_template_slug VARCHAR(64) NULL — slug шаблона
        в EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY. Если NULL — fallback
        на EMPLOYMENT_COMPANY_INN_TO_SLUG[tax_id_primary]. Если ни то ни
        другое — render_employment_contract вернёт 409.
      - employment_contract_font_family VARCHAR(64) NULL — шрифт для
        Трудового договора. Если NULL — шрифт из самого шаблона.

    Идемпотентна — ADD COLUMN IF NOT EXISTS.
    """
    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE company ADD COLUMN IF NOT EXISTS "
            "employment_contract_template_slug VARCHAR(64)"
        ))
        conn.execute(text(
            "ALTER TABLE company ADD COLUMN IF NOT EXISTS "
            "employment_contract_font_family VARCHAR(64)"
        ))

    print("[migration] Pack 50.1-G: company.employment_contract_template_slug + "
          "company.employment_contract_font_family ready")
