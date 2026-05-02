"""
Standalone скрипт для локального импорта дампа ФНС → Postgres Railway.

Запускать с локального ПК (НЕ из Railway-контейнера) — там 16+ ГБ RAM
и можно спокойно обработать 12 ГБ XML.

Использование:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\activate

    # Установить зависимости (если ещё не установлены)
    pip install lxml httpx sqlmodel psycopg2-binary python-dotenv tqdm

    # Запустить импорт
    python -m app.scripts.import_dump_local

При первом запуске спросит DATABASE_URL и сохранит в .env.local
(этот файл не должен попасть в git — добавлен в .gitignore).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("import_dump_local")

# Заглушим лишний шум sqlalchemy
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# === 1. Загрузка DATABASE_URL ===

ENV_FILE = Path(__file__).resolve().parents[3] / ".env.local"
# .env.local лежит в корне visa_kit/ (рядом с frontend/, backend/)


def load_or_prompt_database_url() -> str:
    """Читает DATABASE_URL из .env.local или просит ввести в первый раз."""
    # Если есть переменная окружения — используем её (priority)
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        log.info(f"Using DATABASE_URL from environment")
        return env_url

    # Читаем .env.local
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                if url:
                    log.info(f"Using DATABASE_URL from {ENV_FILE}")
                    return url

    # Просим пользователя ввести
    print()
    print("=" * 70)
    print("ПЕРВЫЙ ЗАПУСК — нужен DATABASE_PUBLIC_URL от Railway Postgres")
    print("=" * 70)
    print()
    print("Где взять:")
    print("  1. Railway → твой проект visa-kit")
    print("  2. Кликни на сервис Postgres (НЕ visa-kit)")
    print("  3. Вкладка Variables")
    print("  4. Скопируй значение DATABASE_PUBLIC_URL")
    print("     (выглядит как postgresql://postgres:...@viaduct.proxy.rlwy.net:42569/railway)")
    print()
    url = input("DATABASE_URL: ").strip()
    if not url.startswith("postgresql://") and not url.startswith("postgres://"):
        log.error("Это не похоже на postgres URL. Должно начинаться с postgresql://")
        sys.exit(1)

    # Сохраняем в .env.local
    ENV_FILE.write_text(f'DATABASE_URL="{url}"\n', encoding="utf-8")
    log.info(f"DATABASE_URL сохранён в {ENV_FILE}")
    log.info("⚠️  Этот файл содержит пароль — не коммить его в git!")

    return url


def main():
    # === Загружаем URL и подсовываем как env (чтобы app.config его подхватил) ===
    database_url = load_or_prompt_database_url()
    os.environ["DATABASE_URL"] = database_url

    # Преобразуем postgres:// → postgresql:// (требование SQLAlchemy 2.x)
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
        os.environ["DATABASE_URL"] = database_url

    log.info(f"Connecting to: {_redact_url(database_url)}")

    # === Импорты ПОСЛЕ установки DATABASE_URL ===
    from sqlmodel import Session, create_engine
    from app.services.inn_generator.dump_importer import (
        import_dump,
        resolve_latest_dump_url,
    )

    # === Создаём engine напрямую (без app.db.session чтобы не тянуть весь FastAPI) ===
    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,  # переподключаться если соединение умерло
        connect_args={"connect_timeout": 30},
    )

    # === Проверяем подключение и существование таблиц ===
    log.info("Checking DB connection and schema...")
    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())

        if "self_employed_registry" not in table_names:
            log.error(
                "Таблица self_employed_registry не найдена в БД. "
                "Сначала задеплой Pack 17.2.4 на Railway чтобы init_db создала таблицы."
            )
            sys.exit(1)

        if "registry_import_log" not in table_names:
            log.error(
                "Таблица registry_import_log не найдена. "
                "Сначала задеплой Pack 17.2.4 на Railway."
            )
            sys.exit(1)

        # Текущая статистика
        total = conn.execute(text("SELECT COUNT(*) FROM self_employed_registry")).scalar()
        used = conn.execute(text("SELECT COUNT(*) FROM self_employed_registry WHERE is_used = TRUE")).scalar()
        log.info(f"DB OK. Current state: total={total}, used={used}, available={total - used}")

    # === Резолвим URL свежего дампа ===
    log.info("Resolving latest dump URL from FNS portal...")
    dump_url = resolve_latest_dump_url()
    log.info(f"Dump URL: {dump_url}")

    # === Подтверждение от пользователя ===
    print()
    print("=" * 70)
    print("ГОТОВО К ИМПОРТУ")
    print("=" * 70)
    print(f"Дамп:           {dump_url}")
    print(f"Целевая БД:     {_redact_url(database_url)}")
    print(f"Текущих записей: {total} (use={used})")
    print()
    print("Что произойдёт:")
    print("  1. Скачать ZIP (~735 МБ) — 5-10 минут")
    print("  2. Распаковать XML (~12 ГБ) — нужно место на диске")
    print("  3. Удалить НЕиспользованные записи (used не трогаем)")
    print("  4. Парсить XML и заливать самозанятых в Postgres Railway")
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

    with Session(engine) as session:
        try:
            log_entry = import_dump(
                session=session,
                dump_url=dump_url,
                purge_old=True,
            )
        except Exception as e:
            log.exception(f"Импорт упал: {e}")
            sys.exit(1)

    elapsed = time.time() - started

    # === Результат ===
    print()
    print("=" * 70)
    print("ИМПОРТ ЗАВЕРШЁН")
    print("=" * 70)
    print(f"Status:           {log_entry.status}")
    print(f"Records total:    {log_entry.records_total}")
    print(f"Records imported: {log_entry.records_imported}")
    print(f"Records skipped:  {log_entry.records_skipped}")
    print(f"ZIP size:         {(log_entry.zip_size_bytes or 0) / 1e6:.1f} MB")
    print(f"XML size:         {(log_entry.xml_size_bytes or 0) / 1e9:.2f} GB")
    print(f"Time:             {elapsed / 60:.1f} minutes")
    if log_entry.error_message:
        print(f"Error:            {log_entry.error_message}")

    # Финальная статистика
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM self_employed_registry")).scalar()
        used = conn.execute(text("SELECT COUNT(*) FROM self_employed_registry WHERE is_used = TRUE")).scalar()
        print()
        print(f"DB final: total={total}, used={used}, available={total - used}")


def _redact_url(url: str) -> str:
    """Скрываем пароль в URL для логов."""
    import re
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


if __name__ == "__main__":
    main()
