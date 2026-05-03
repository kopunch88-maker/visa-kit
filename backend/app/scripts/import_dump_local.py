"""
Pack 17.2.5 — Standalone скрипт для локального импорта дампа SNRIP в Postgres Railway.

Использует УЖЕ СКАЧАННЫЙ ZIP, если он лежит в одном из стандартных мест:
  D:\\VISA\\visa_kit\\data-20260425-structure-20241025.zip
  D:\\VISA\\data-20260425-structure-20241025.zip
  D:\\VISA\\snrip_dump.zip

Иначе скачивает свежайший дамп с портала ФНС.

Использование:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    python -m app.scripts.import_dump_local
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("import_dump_local")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


ENV_FILE = Path(__file__).resolve().parents[3] / ".env.local"

# Где искать уже скачанный ZIP
LOCAL_ZIP_PATHS = [
    Path("D:/VISA/visa_kit/data-20260425-structure-20241025.zip"),
    Path("D:/VISA/data-20260425-structure-20241025.zip"),
    Path("D:/VISA/snrip_dump.zip"),
]


def find_local_zip() -> Optional[Path]:
    """Ищет валидный локальный ZIP файл."""
    for p in LOCAL_ZIP_PATHS:
        if not p.exists():
            continue
        if p.stat().st_size < 100_000_000:  # должен быть >100 МБ
            continue
        with open(p, "rb") as f:
            magic = f.read(2)
        if magic == b"PK":
            return p
    return None


def load_or_prompt_database_url() -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        log.info("Using DATABASE_URL from environment")
        return env_url

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                if url:
                    log.info(f"Using DATABASE_URL from {ENV_FILE}")
                    return url

    print()
    print("=" * 70)
    print("ПЕРВЫЙ ЗАПУСК — нужен DATABASE_PUBLIC_URL от Railway Postgres")
    print("=" * 70)
    print()
    print("Где взять:")
    print("  1. Railway -> твой проект visa-kit")
    print("  2. Кликни на сервис Postgres (НЕ visa-kit)")
    print("  3. Вкладка Variables")
    print("  4. Скопируй значение DATABASE_PUBLIC_URL")
    print()
    url = input("DATABASE_URL: ").strip()
    if not url.startswith("postgresql://") and not url.startswith("postgres://"):
        log.error("Это не похоже на postgres URL.")
        sys.exit(1)

    ENV_FILE.write_text(f'DATABASE_URL="{url}"\n', encoding="utf-8")
    log.info(f"DATABASE_URL сохранён в {ENV_FILE}")
    log.info("ВАЖНО: этот файл содержит пароль - не коммить в git!")
    return url


def main():
    database_url = load_or_prompt_database_url()
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    os.environ["DATABASE_URL"] = database_url

    log.info(f"Connecting to: {_redact_url(database_url)}")

    from sqlmodel import Session, create_engine
    from app.services.inn_generator.dump_importer import (
        import_dump,
        resolve_latest_dump_url,
    )

    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 30,
            # Таймаут на ОДИН SQL statement: 60 секунд.
            # Если INSERT висит дольше — psycopg2 прервёт и поднимет ошибку.
            # Backend retry в _insert_batch это поймает.
            "options": "-c statement_timeout=60000",
            # TCP keepalive — чтобы соединение не "тихо" умирало
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )

    # === Проверка БД ===
    log.info("Checking DB connection and schema...")
    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())

        for required in ("self_employed_registry", "registry_import_log"):
            if required not in table_names:
                log.error(f"Таблица {required} не найдена. Сначала задеплой миграции на Railway.")
                sys.exit(1)

        total = conn.execute(text("SELECT COUNT(*) FROM self_employed_registry")).scalar()
        used = conn.execute(text("SELECT COUNT(*) FROM self_employed_registry WHERE is_used = TRUE")).scalar()
        log.info(f"DB OK. Current state: total={total}, used={used}, available={total - used}")

    # === Ищем локальный ZIP ===
    local_zip = find_local_zip()
    dump_url: Optional[str] = None

    if local_zip:
        log.info(f"✅ Found local ZIP: {local_zip} ({local_zip.stat().st_size / 1e6:.1f} MB)")
        log.info("Будем использовать его (не качаем заново)")
    else:
        log.info("Локальный ZIP не найден — резолвим URL свежайшего дампа SNRIP...")
        dump_url = resolve_latest_dump_url()
        log.info(f"Будем качать: {dump_url}")

    # === Подтверждение ===
    print()
    print("=" * 70)
    print("ГОТОВО К ИМПОРТУ (SNRIP / ИП на спецрежимах, отбор только НПД)")
    print("=" * 70)
    if local_zip:
        print(f"Источник:        локальный файл {local_zip}")
    else:
        print(f"Источник:        качаем {dump_url}")
    print(f"Целевая БД:      {_redact_url(database_url)}")
    print(f"Текущих записей: {total} (used={used})")
    print()
    print("Что произойдёт:")
    if not local_zip:
        print("  1. Скачать ZIP (~265 МБ) — 1-3 минуты")
    print("  2. Удалить НЕиспользованные записи в БД (used не трогаем)")
    print("  3. Парсить XML прямо из ZIP (без распаковки на диск)")
    print("  4. Извлечь только ИП с режимом НПД (~565,000 записей)")
    print("  5. Bulk-insert в Postgres Railway")
    print()
    confirm = input("Продолжить? (yes/no): ").strip().lower()
    if confirm not in ("y", "yes", "да", "д"):
        log.info("Отменено пользователем")
        sys.exit(0)

    # === Запуск импорта ===
    started = time.time()
    log.info("=" * 70)
    log.info("STARTING IMPORT")
    log.info("=" * 70)

    log_status = "?"
    log_records_total = 0
    log_records_imported = 0
    log_records_skipped = 0
    log_zip_size = 0
    log_xml_size = 0
    log_error = None

    with Session(engine) as session:
        try:
            log_entry = import_dump(
                session=session,
                dump_url=dump_url,
                purge_old=True,
                local_zip_path=local_zip,
            )
            # Считываем поля ВНУТРИ session — потом session закроется
            log_status = log_entry.status
            log_records_total = log_entry.records_total
            log_records_imported = log_entry.records_imported
            log_records_skipped = log_entry.records_skipped
            log_zip_size = log_entry.zip_size_bytes or 0
            log_xml_size = log_entry.xml_size_bytes or 0
            log_error = log_entry.error_message
        except Exception as e:
            log.exception(f"Импорт упал: {e}")
            sys.exit(1)

    elapsed = time.time() - started

    print()
    print("=" * 70)
    print("ИМПОРТ ЗАВЕРШЁН")
    print("=" * 70)
    print(f"Status:           {log_status}")
    print(f"Records total:    {log_records_total:,}")
    print(f"NPD imported:     {log_records_imported:,}")
    print(f"Skipped (no NPD): {log_records_skipped:,}")
    print(f"ZIP size:         {log_zip_size / 1e6:.1f} MB")
    print(f"XML size:         {log_xml_size / 1e9:.2f} GB")
    print(f"Time:             {elapsed / 60:.1f} minutes")
    if log_error:
        print(f"Error:            {log_error}")

    # Финальная статистика
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM self_employed_registry")).scalar()
        used = conn.execute(text("SELECT COUNT(*) FROM self_employed_registry WHERE is_used = TRUE")).scalar()
        print()
        print(f"DB final: total={total:,}, used={used:,}, available={total - used:,}")


def _redact_url(url: str) -> str:
    import re
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


if __name__ == "__main__":
    main()
