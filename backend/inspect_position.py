# inspect_position.py
import os
from sqlmodel import create_engine, text

e = create_engine(os.environ['DATABASE_URL'])
con = e.connect()

print("=" * 80)
print("SCHEMA position:")
print("=" * 80)
rows = con.execute(text(
    "SELECT column_name, data_type, is_nullable "
    "FROM information_schema.columns "
    "WHERE table_name='position' "
    "ORDER BY ordinal_position"
)).all()
for r in rows:
    print(r)

print()
print("=" * 80)
print("CONTENT id=2 and id=13 (all columns):")
print("=" * 80)
rows = con.execute(text("SELECT * FROM position WHERE id IN (2, 13)")).mappings().all()
for r in rows:
    print(f"\n--- Position id={r['id']} title_ru={r.get('title_ru')!r} ---")
    for k, v in r.items():
        sv = repr(v)
        if len(sv) > 200:
            sv = sv[:200] + f"... [truncated, total len={len(repr(v))}]"
        print(f"  {k}: {sv}")