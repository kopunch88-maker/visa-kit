"""
Pack 14a/b/c — миграция PG enum applicantdocumenttype (FIX версия).

История:
- Первая версия скрипта по ошибке добавила lowercase значения в enum.
- Реальные значения которые использует backend — UPPERCASE
  (SQLAlchemy маппит Python Enum.NAME, а не .value).
- Эта версия добавляет правильные uppercase значения
  для Pack 14a/b: PASSPORT_NATIONAL, RESIDENCE_CARD, CRIMINAL_RECORD, EGRYL_EXTRACT.
- Lowercase дубликаты которые добавила первая версия — оставляем
  (PostgreSQL не позволяет удалять enum values без сложных манипуляций,
  они просто будут unused).

Использование:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:DATABASE_URL="postgresql://postgres:ПАРОЛЬ@switchyard.proxy.rlwy.net:34408/railway"
    python migrate_pack14_enum.py
    $env:DATABASE_URL=$null
"""
import os
import sys

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("ERROR: sqlalchemy не установлен. Активируй .venv.")
    sys.exit(1)


# UPPERCASE значения которые backend РЕАЛЬНО использует
# (SQLAlchemy default behaviour: Python Enum.NAME → PG enum value)
EXPECTED_UPPERCASE_VALUES = [
    "PASSPORT_INTERNAL_MAIN",
    "PASSPORT_INTERNAL_ADDRESS",
    "PASSPORT_FOREIGN",
    "DIPLOMA_MAIN",
    "DIPLOMA_APOSTILLE",
    "PASSPORT_NATIONAL",     # Pack 14a — НОВЫЙ
    "RESIDENCE_CARD",         # Pack 14a — НОВЫЙ
    "CRIMINAL_RECORD",        # Pack 14a — НОВЫЙ
    "EGRYL_EXTRACT",          # Pack 14b — НОВЫЙ
    "OTHER",
]


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: переменная окружения DATABASE_URL не установлена")
        sys.exit(1)

    if "ПАРОЛЬ" in db_url:
        print("ERROR: не заменён плейсхолдер на реальный пароль")
        sys.exit(1)

    print("[1/4] Подключаюсь к production...")
    print(f"      Хост: {db_url.split('@')[-1] if '@' in db_url else '?'}")

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"ERROR: не могу подключиться: {e}")
        sys.exit(1)

    print("[2/4] Анализирую тип applicantdocumenttype...")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = 'applicantdocumenttype'
            ORDER BY e.enumsortorder
        """))
        existing_values = [r[0] for r in result.fetchall()]

    if not existing_values:
        print("❌ Тип applicantdocumenttype не найден в БД")
        sys.exit(1)

    print(f"      Сейчас в enum: {len(existing_values)} значений")
    for v in existing_values:
        marker = "✓" if v in EXPECTED_UPPERCASE_VALUES else "?"
        print(f"        {marker} {v}")

    # Что нужно добавить (только uppercase)
    missing_uppercase = [v for v in EXPECTED_UPPERCASE_VALUES if v not in existing_values]

    print()
    print(f"[3/4] Анализ:")
    print(f"      Нужно добавить uppercase значения: {len(missing_uppercase)}")
    for v in missing_uppercase:
        print(f"        + {v}")

    if not missing_uppercase:
        print()
        print("✅ Все uppercase значения уже на месте — миграция не нужна!")
        print()
        print("Если backend всё ещё кидает 500 — попробуй сделать пустой commit чтобы")
        print("Railway перезапустил процесс (psycopg2 кеширует enum):")
        print("  cd D:\\VISA\\visa_kit")
        print("  git commit --allow-empty -m 'trigger restart'")
        print("  git push")
        return

    print()
    answer = input(f"Добавить {len(missing_uppercase)} значений? (yes/no): ").strip().lower()
    if answer != "yes":
        print("Отменено.")
        return

    print()
    print("[4/4] Выполняю...")

    # ALTER TYPE ADD VALUE требует AUTOCOMMIT в PG < 12, безопасен везде
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for value in missing_uppercase:
            try:
                conn.execute(text(f"ALTER TYPE applicantdocumenttype ADD VALUE IF NOT EXISTS '{value}'"))
                print(f"  + добавлено: {value}")
            except Exception as e:
                print(f"  ❌ ошибка для {value}: {e}")

    print()
    print("✅ Миграция завершена!")
    print()
    print("ВАЖНО: перезапусти backend на Railway чтобы драйвер perezagruzил enum:")
    print("  cd D:\\VISA\\visa_kit")
    print("  git commit --allow-empty -m 'restart for enum migration'")
    print("  git push")
    print()
    print("Через 1-2 минуты Railway перезапустится → попробуй импорт пакета снова.")
    print()
    print("Затем удали этот скрипт:")
    print("  Remove-Item migrate_pack14_enum.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано.")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
