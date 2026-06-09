# inspect_director.py
import os
from sqlmodel import create_engine, text

e = create_engine(os.environ['DATABASE_URL'])
con = e.connect()

# 1. Какие столбцы директора есть в company
print("=" * 80)
print("SCHEMA company — все director_* колонки:")
print("=" * 80)
rows = con.execute(text(
    "SELECT column_name, data_type FROM information_schema.columns "
    "WHERE table_name='company' AND column_name LIKE 'director%' "
    "ORDER BY ordinal_position"
)).all()
for r in rows:
    print(r)

# 2. Все director-поля у Кайтукти и Агаларова
print()
print("=" * 80)
print("РЕНКОНС vs АГАЛАРОВ — director_* поля:")
print("=" * 80)
director_cols = [r[0] for r in rows]
cols_sql = ", ".join(["id", "name"] + director_cols)
rows = con.execute(text(
    f"SELECT {cols_sql} FROM company "
    "WHERE name ILIKE '%РЕНКОНС%' OR name ILIKE '%АГАЛАРОВ%'"
)).mappings().all()
for r in rows:
    print(f"\n--- Company id={r['id']} name={r['name']!r} ---")
    for k, v in r.items():
        if k in ('id', 'name'):
            continue
        print(f"  {k}: {v!r}")