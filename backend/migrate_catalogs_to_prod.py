"""
Перенос справочников из локальной dev.db в production PostgreSQL.

v3: исправлен KeyError на этапе positions (использовать .get вместо [])
v2: исправлены типы SQLite → PostgreSQL (bool 0/1 → False/True)

Использование:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:DATABASE_URL="postgresql://postgres:РЕАЛЬНЫЙ_ПАРОЛЬ@switchyard.proxy.rlwy.net:34408/railway"
    python migrate_catalogs_to_prod.py
    $env:DATABASE_URL=$null
"""
import os
import sys

try:
    from sqlalchemy import create_engine, text, inspect
except ImportError:
    print("ERROR: sqlalchemy не установлен. Активируй .venv:")
    print("  .venv\\Scripts\\Activate.ps1")
    sys.exit(1)


SOURCE_DB_PATH = "dev.db"


def find_table_name(inspector, candidates):
    existing = inspector.get_table_names()
    for name in candidates:
        if name in existing:
            return name
    return None


def read_all_rows(engine, table_name):
    if not table_name:
        return []
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT * FROM {table_name}"))
        rows = [dict(r._mapping) for r in result]
    return rows


def get_columns_info(engine, table_name):
    if not table_name:
        return {}
    inspector = inspect(engine)
    info = {}
    for col in inspector.get_columns(table_name):
        info[col["name"]] = {
            "type": str(col["type"]),
            "nullable": col.get("nullable", True),
        }
    return info


def convert_value_for_postgres(value, col_type_str):
    """SQLite int 0/1 → Postgres bool, остальное без изменений."""
    if value is None:
        return None
    type_upper = col_type_str.upper()
    if "BOOL" in type_upper:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "y")
    return value


def clean_row_for_dst(row, dst_columns_info, drop_id=True):
    """
    Подготавливает row для INSERT:
    - убирает 'id' (генерируется автоматически)
    - оставляет только колонки которые есть в production
    - конвертирует bool 0/1 → True/False
    """
    cleaned = {}
    for k, v in row.items():
        if drop_id and k == "id":
            continue
        if k not in dst_columns_info:
            continue
        col_type = dst_columns_info[k]["type"]
        cleaned[k] = convert_value_for_postgres(v, col_type)
    return cleaned


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: переменная окружения DATABASE_URL не установлена")
        sys.exit(1)

    if "ПАРОЛЬ" in db_url or "PASSWORD" in db_url:
        print("ERROR: похоже ты не заменил плейсхолдер на реальный пароль")
        sys.exit(1)

    if not os.path.exists(SOURCE_DB_PATH):
        print(f"ERROR: локальная БД {SOURCE_DB_PATH} не найдена")
        print(f"Запусти из папки D:\\VISA\\visa_kit\\backend")
        sys.exit(1)

    print("[1/5] Подключаюсь к локальной dev.db...")
    src_engine = create_engine(f"sqlite:///{SOURCE_DB_PATH}")

    print("[2/5] Подключаюсь к production...")
    print(f"      Хост: {db_url.split('@')[-1] if '@' in db_url else '?'}")
    try:
        dst_engine = create_engine(db_url)
        with dst_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"ERROR: не могу подключиться к production: {e}")
        sys.exit(1)

    print("[3/5] Ищу таблицы...")
    src_inspector = inspect(src_engine)
    dst_inspector = inspect(dst_engine)

    table_candidates = {
        "company": ["company", "companies"],
        "position": ["position", "positions"],
        "representative": ["representative", "representatives"],
        "spain_address": ["spain_address", "spainaddress", "spainaddresses", "spain_addresses"],
    }

    tables_src = {}
    tables_dst = {}
    for logical_name, candidates in table_candidates.items():
        tables_src[logical_name] = find_table_name(src_inspector, candidates)
        tables_dst[logical_name] = find_table_name(dst_inspector, candidates)

    print()
    print("Найдено таблиц:")
    for logical_name in table_candidates:
        src = tables_src[logical_name] or "❌ нет"
        dst = tables_dst[logical_name] or "❌ нет"
        print(f"  {logical_name:20} src={src:30} dst={dst}")
    print()

    print("[4/5] Анализирую что нужно перенести...")
    print()

    src_data = {}
    plan = {}

    for logical_name in table_candidates:
        src_table = tables_src[logical_name]
        dst_table = tables_dst[logical_name]

        if not src_table or not dst_table:
            continue

        src_rows = read_all_rows(src_engine, src_table)
        dst_rows = read_all_rows(dst_engine, dst_table)
        # Сохраняем КОПИИ src_rows для разных целей — чтобы pop не портил
        src_data[logical_name] = [dict(r) for r in src_rows]

        if logical_name == "company":
            existing = {r["short_name"] for r in dst_rows if r.get("short_name")}
            to_migrate = [r for r in src_rows if r.get("short_name") and r["short_name"] not in existing]
        elif logical_name == "representative":
            existing = {r["nie"] for r in dst_rows if r.get("nie")}
            to_migrate = [r for r in src_rows if r.get("nie") and r["nie"] not in existing]
        elif logical_name == "position":
            to_migrate = src_rows
        elif logical_name == "spain_address":
            existing = {
                (r.get("street", ""), r.get("number", ""), r.get("city", ""))
                for r in dst_rows
            }
            to_migrate = [
                r for r in src_rows
                if (r.get("street", ""), r.get("number", ""), r.get("city", "")) not in existing
            ]
        else:
            to_migrate = src_rows

        plan[logical_name] = {
            "src_total": len(src_rows),
            "dst_existing": len(dst_rows),
            "to_migrate": len(to_migrate),
            "rows": to_migrate,
            "src_table": src_table,
            "dst_table": dst_table,
        }

        print(f"  {logical_name}:")
        print(f"    в локальной БД:    {len(src_rows)}")
        print(f"    уже в production:  {len(dst_rows)}")
        print(f"    будет добавлено:   {len(to_migrate)}")

    print()

    if "company" in plan and plan["company"]["to_migrate"]:
        print("Компании к переносу:")
        for c in plan["company"]["rows"]:
            print(f"  - [{c.get('short_name')}] {(c.get('full_name_ru') or '')[:60]}")
        print()

    if "representative" in plan and plan["representative"]["to_migrate"]:
        print("Представители к переносу:")
        for r in plan["representative"]["rows"]:
            name = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
            print(f"  - [{r.get('nie')}] {name}")
        print()

    total = sum(p["to_migrate"] for p in plan.values())
    if total == 0:
        print("✅ Всё уже синхронизировано — переносить нечего.")
        return

    print(f"[5/5] Готов перенести всего: {total} записей")
    print()
    answer = input("Продолжить? (введи 'yes' для подтверждения): ").strip().lower()
    if answer != "yes":
        print("Отменено.")
        return

    print()
    print("Выполняю перенос...")
    print()

    # === 5.1. Companies ===
    if "company" in plan and plan["company"]["to_migrate"]:
        dst_table = plan["company"]["dst_table"]
        dst_cols_info = get_columns_info(dst_engine, dst_table)

        with dst_engine.begin() as conn:
            for row in plan["company"]["rows"]:
                old_id = row.get("id")
                clean = clean_row_for_dst(row, dst_cols_info)
                col_names = ", ".join(clean.keys())
                placeholders = ", ".join(f":{k}" for k in clean.keys())
                stmt = text(
                    f"INSERT INTO {dst_table} ({col_names}) VALUES ({placeholders}) RETURNING id"
                )
                result = conn.execute(stmt, clean)
                new_id = result.scalar()
                print(f"  + Компания: {clean.get('short_name')} (id {old_id} → {new_id})")

    # === 5.2. Positions ===
    # Ключевой момент: используем src_data["company"] (полные ОРИГИНАЛЬНЫЕ строки с id),
    # а не plan["company"]["rows"] (которые могли быть модифицированы)
    if "position" in plan and plan["position"]["src_total"] > 0:
        dst_table = plan["position"]["dst_table"]
        dst_cols_info = get_columns_info(dst_engine, dst_table)

        # Маппинг старого company_id → short_name (из локальной БД)
        src_companies = src_data.get("company", [])
        old_id_to_short = {
            c.get("id"): c.get("short_name")
            for c in src_companies
            if c.get("id") is not None and c.get("short_name")
        }

        # Маппинг short_name → новый id (читаем production свежий)
        dst_company_table = plan["company"]["dst_table"] if "company" in plan else None
        if dst_company_table:
            dst_companies_now = read_all_rows(dst_engine, dst_company_table)
            short_to_new_id = {
                c["short_name"]: c["id"]
                for c in dst_companies_now
                if c.get("short_name")
            }
        else:
            short_to_new_id = {}

        existing_dst = read_all_rows(dst_engine, dst_table)
        existing_keys = {(r.get("company_id"), r.get("title_ru")) for r in existing_dst}

        with dst_engine.begin() as conn:
            for row in plan["position"]["rows"]:
                old_company_id = row.get("company_id")
                short = old_id_to_short.get(old_company_id)
                if not short:
                    print(f"  ⚠ Должность '{row.get('title_ru')}': не нашёл компанию по old_id={old_company_id}, пропускаю")
                    continue
                new_company_id = short_to_new_id.get(short)
                if not new_company_id:
                    print(f"  ⚠ Должность '{row.get('title_ru')}': компания '{short}' не в production, пропускаю")
                    continue

                if (new_company_id, row.get("title_ru")) in existing_keys:
                    print(f"  ⏭  Должность '{row.get('title_ru')}' для '{short}' уже есть, пропускаю")
                    continue

                # Подменяем company_id перед очисткой
                row_modified = dict(row)
                row_modified["company_id"] = new_company_id

                clean = clean_row_for_dst(row_modified, dst_cols_info)
                col_names = ", ".join(clean.keys())
                placeholders = ", ".join(f":{k}" for k in clean.keys())
                stmt = text(f"INSERT INTO {dst_table} ({col_names}) VALUES ({placeholders})")
                conn.execute(stmt, clean)
                existing_keys.add((new_company_id, row.get("title_ru")))
                print(f"  + Должность: {row.get('title_ru')} → {short}")

    # === 5.3. Representatives ===
    if "representative" in plan and plan["representative"]["to_migrate"]:
        dst_table = plan["representative"]["dst_table"]
        dst_cols_info = get_columns_info(dst_engine, dst_table)

        with dst_engine.begin() as conn:
            for row in plan["representative"]["rows"]:
                clean = clean_row_for_dst(row, dst_cols_info)
                col_names = ", ".join(clean.keys())
                placeholders = ", ".join(f":{k}" for k in clean.keys())
                stmt = text(f"INSERT INTO {dst_table} ({col_names}) VALUES ({placeholders})")
                conn.execute(stmt, clean)
                print(f"  + Представитель: {clean.get('nie')} {clean.get('first_name', '')} {clean.get('last_name', '')}")

    # === 5.4. Spain addresses ===
    if "spain_address" in plan and plan["spain_address"]["to_migrate"]:
        dst_table = plan["spain_address"]["dst_table"]
        dst_cols_info = get_columns_info(dst_engine, dst_table)

        with dst_engine.begin() as conn:
            for row in plan["spain_address"]["rows"]:
                clean = clean_row_for_dst(row, dst_cols_info)
                col_names = ", ".join(clean.keys())
                placeholders = ", ".join(f":{k}" for k in clean.keys())
                stmt = text(f"INSERT INTO {dst_table} ({col_names}) VALUES ({placeholders})")
                conn.execute(stmt, clean)
                print(f"  + Адрес: {clean.get('street', '')} {clean.get('number', '')}, {clean.get('city', '')}")

    print()
    print("✅ Перенос завершён успешно!")
    print()
    print("Проверь в админке: https://visa-kit.vercel.app/admin/settings/companies")
    print()
    print("Затем удали этот скрипт:")
    print("  Remove-Item migrate_catalogs_to_prod.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)