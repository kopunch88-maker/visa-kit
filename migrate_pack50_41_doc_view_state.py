#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pack 50.41 — миграция: таблица document_view_state.

Запускать ОДИН РАЗ из backend/ с активным venv и заданным DATABASE_URL.

Источник подключения (по приоритету):
  1) переменная окружения DATABASE_URL  -> строим СВОЙ engine из неё
     (так исключаем ситуацию, когда app.db.session тащит старый пароль из .env);
  2) если переменной нет — fallback на app.db.session.engine.

Правило 18: без DROP. Правило 20: dump схемы до/после. Идемпотентно (IF NOT EXISTS).
"""
from __future__ import annotations

import os
import re
import sys

from sqlalchemy import text


def _mask(url: str) -> str:
    return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1***\2", url or "")


def _get_engine():
    url = os.environ.get("DATABASE_URL", "").strip().strip('"').strip("'")
    if url:
        # SQLAlchemy 2.x требует схему postgresql:// (а не postgres://)
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        try:
            u = make_url(url)
        except Exception as e:
            print(f"FAIL: не разобрать DATABASE_URL ({e}). Проверь строку из Railway.")
            sys.exit(2)
        # Признаки «задвоенного»/битого URL (частая ошибка вставки):
        #   - в имени БД оказались @ : / (имя базы их не содержит);
        #   - схема встречается дважды;
        #   - после схемы больше одного '@' (хвост host/db приклеен повторно).
        bad_db = bool(u.database) and any(c in u.database for c in "@:/")
        dup_scheme = url.count("://") > 1
        extra_at = url.split("://", 1)[-1].count("@") > 1
        if bad_db or dup_scheme or extra_at:
            print("FAIL: DATABASE_URL задан некорректно — похоже, хост/база приклеены дважды")
            print("      (полный URL вставлен внутрь шаблона). Положи в $env:DATABASE_URL ОДНУ")
            print("      строку из Railway ЦЕЛИКОМ, без обрамляющего текста и без моего хвоста.")
            print(f"      Разобрано: host={u.host} port={u.port} db={u.database!r} user={u.username}")
            print(f"      Маска:     {_mask(url)}")
            sys.exit(2)
        print(f"engine: host={u.host} port={u.port} db={u.database} user={u.username} (пароль скрыт)")
        return create_engine(url, pool_pre_ping=True)
    try:
        from app.db.session import engine
        print(f"engine: из app.db.session (DATABASE_URL не задан в окружении) -> {_mask(str(engine.url))}")
        return engine
    except Exception as e:  # pragma: no cover
        print(f"FAIL: DATABASE_URL не задан и app.db.session.engine не импортируется ({e}).")
        sys.exit(1)


DDL = [
    """
    CREATE TABLE IF NOT EXISTS document_view_state (
        id           BIGSERIAL PRIMARY KEY,
        application_id INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
        doc_key      VARCHAR(120) NOT NULL,
        seen_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
        seen_by      VARCHAR(255) NULL,
        CONSTRAINT uq_document_view_state UNIQUE (application_id, doc_key)
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_document_view_state_app ON document_view_state(application_id);",
]


def _dump_schema(conn):
    rows = conn.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'document_view_state' ORDER BY ordinal_position"
    )).all()
    return [(r[0], r[1]) for r in rows]


def main() -> int:
    engine = _get_engine()
    with engine.begin() as conn:
        before = _dump_schema(conn)
        print("schema BEFORE:", before or "(нет таблицы)")
        for ddl in DDL:
            conn.execute(text(ddl))
        after = _dump_schema(conn)
        cnt = conn.execute(text("SELECT count(*) FROM document_view_state")).scalar()
    print("schema AFTER :", after)
    print(f"PASS: document_view_state готова, строк={cnt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
