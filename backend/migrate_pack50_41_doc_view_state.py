#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pack 50.41 — миграция: таблица document_view_state.

Запускать ОДИН РАЗ из backend/ с активным venv и заданным DATABASE_URL
(как Pack 41.0-M — через app.db.engine, не в git).

Правило 18: без DROP. Правило 20: dump схемы до/после. Идемпотентно (IF NOT EXISTS).
"""
from __future__ import annotations

import sys

from sqlalchemy import text

try:
    from app.db.session import engine
except Exception as e:  # pragma: no cover
    print(f"FAIL: не импортируется app.db.session.engine ({e}). Запускай из backend/ с venv.")
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
