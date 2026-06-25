#!/usr/bin/env python3
"""
Pack 66: устранение артефактов кириллицы в скобках в duties Position.

Проблема: в CV видны такие фрагменты как
  "elaboración de listas de incidencias (Issue-листов)"
где русское слово «листов» вылезло в испанский текст. Причина —
в исходных duties (которые рендерятся в CV напрямую) часть текста
смешанная: латиница + кириллица в скобках-пояснениях.

Фикс: regex ищет любые скобки с кириллической буквой внутри
и удаляет их целиком (вместе с предшествующим пробелом).
Скобки без кириллицы (AR, KR, OViK), (BEP — BIM Execution Plan)
остаются нетронутыми.

Сканирует duties и profile_description у ВСЕХ Position. Дополнительно
если в таблице есть поле duties_es / profile_description_es — чистит
и их.

Идемпотентно: после первого прогона regex ничего не находит → NO-OP.
Транзакция атомарна.

Использование:
    $env:DATABASE_URL = "postgresql://..."
    python apply_pack66_cyrillic_in_parens.py
    python apply_pack66_cyrillic_in_parens.py --dry-run  # без UPDATE
"""
import argparse
import json
import os
import re
import sys


# Скобки с любой кириллической буквой внутри. Жадно по содержимому
# (внутри скобок нет других скобок). Захватываем ВЕДУЩИЙ whitespace
# чтобы убрать "слово (...) другое" → "слово другое" без двойного пробела.
CYRILLIC_PARENS_RE = re.compile(r"\s*\([^)]*[а-яА-ЯёЁ][^)]*\)")

# Нормализация двойных пробелов и пробела перед запятой/точкой после чистки.
DOUBLE_SPACE_RE = re.compile(r" {2,}")
SPACE_BEFORE_PUNCT_RE = re.compile(r" ([,.;:])")


def clean_text(text):
    """Очистка текста от скобок с кириллицей + нормализация пробелов.
    Возвращает (new_text, changed: bool)."""
    if not isinstance(text, str):
        return text, False
    new = CYRILLIC_PARENS_RE.sub("", text)
    new = DOUBLE_SPACE_RE.sub(" ", new)
    new = SPACE_BEFORE_PUNCT_RE.sub(r"\1", new)
    new = new.strip()
    return new, new != text


def process_jsonb_array(value):
    """Обработка JSONB-массива строк. Возвращает (new_list, changes_list).
    changes_list: [(idx, old, new), ...]"""
    if not isinstance(value, list):
        return value, []
    new_list = []
    changes = []
    for idx, item in enumerate(value):
        new_item, changed = clean_text(item)
        new_list.append(new_item)
        if changed:
            changes.append((idx, item, new_item))
    return new_list, changes


def get_existing_columns(cur, table, candidates):
    """Возвращает подмножество candidates, реально существующих в таблице."""
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = ANY(%s)
        """,
        (table, candidates),
    )
    return {r["column_name"] for r in cur.fetchall()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Только показать diff, без UPDATE")
    args = parser.parse_args()

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("ERROR: psycopg2 не установлен. pip install psycopg2-binary")
        return 1

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL не задан в env")
        return 1

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # ── Определить какие колонки на самом деле есть ──
        candidate_cols = [
            "duties", "duties_es",
            "profile_description", "profile_description_es",
        ]
        existing = get_existing_columns(cur, "position", candidate_cols)
        print(f"[Pack 66] Найденные колонки в position: {sorted(existing)}")

        # ── Загрузить все Position с этими колонками ──
        cols_sql = ", ".join(["id", "title_ru"] + sorted(existing))
        cur.execute(f"SELECT {cols_sql} FROM position ORDER BY id")
        rows = cur.fetchall()
        print(f"[Pack 66] Сканирую {len(rows)} Position...")

        updates = []
        for row in rows:
            pos_id = row["id"]
            title = row["title_ru"]
            patch = {}
            display_changes = []

            for col in existing:
                value = row.get(col)
                if value is None:
                    continue
                if col in ("duties", "duties_es"):
                    # JSONB array of strings
                    new_value, col_changes = process_jsonb_array(value)
                    if col_changes:
                        patch[col] = new_value
                        for idx, old, new in col_changes:
                            display_changes.append(
                                (f"{col}[{idx}]", old, new)
                            )
                elif col in ("profile_description", "profile_description_es"):
                    # plain text
                    new_value, changed = clean_text(value)
                    if changed:
                        patch[col] = new_value
                        display_changes.append((col, value, new_value))

            if patch:
                updates.append({
                    "id": pos_id,
                    "title": title,
                    "patch": patch,
                    "display_changes": display_changes,
                })

        if not updates:
            print("\n[Pack 66] ✓ Ничего не найдено — все Position уже чистые (NO-OP)")
            print("[Pack 66] (миграция идемпотентна — повторный прогон ничего не делает)")
            conn.rollback()
            return 0

        # ── Показать diff ──
        total_changes = sum(len(u["display_changes"]) for u in updates)
        print(f"\n[Pack 66] Будет затронуто Position: {len(updates)}")
        print(f"[Pack 66] Всего фрагментов для очистки: {total_changes}")
        for u in updates:
            print(f"\n  ── id={u['id']}  {u['title']!r} ──")
            for field, old, new in u["display_changes"]:
                # сокращаем длинные строки для читаемости diff'а
                old_show = old if len(old) <= 200 else old[:197] + "..."
                new_show = new if len(new) <= 200 else new[:197] + "..."
                print(f"    {field}:")
                print(f"      ДО:    {old_show}")
                print(f"      ПОСЛЕ: {new_show}")

        if args.dry_run:
            print("\n[Pack 66] --dry-run: UPDATE не применяется")
            conn.rollback()
            return 0

        # ── Применить UPDATE ──
        for u in updates:
            set_parts = []
            params = []
            for col, new_value in u["patch"].items():
                if col in ("duties", "duties_es"):
                    set_parts.append(f"{col} = %s::jsonb")
                    params.append(json.dumps(new_value, ensure_ascii=False))
                else:
                    set_parts.append(f"{col} = %s")
                    params.append(new_value)
            params.append(u["id"])
            sql = f"UPDATE position SET {', '.join(set_parts)} WHERE id = %s"
            cur.execute(sql, params)

        conn.commit()
        print(f"\n[Pack 66] ✅ DONE — обновлено {len(updates)} Position, "
              f"{total_changes} фрагментов очищено")
        return 0

    except Exception as e:
        conn.rollback()
        print(f"[Pack 66] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
