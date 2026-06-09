# inspect_director_data.py
import os
from sqlmodel import create_engine, text

e = create_engine(os.environ['DATABASE_URL'])
con = e.connect()

print("=" * 80)
print("Все director_* поля у РЕНКОНС и АГАЛАРОВ:")
print("=" * 80)
rows = con.execute(text(
    "SELECT id, short_name, full_name_ru, "
    "director_full_name_ru, director_full_name_genitive_ru, "
    "director_short_ru, director_position_ru, director_full_name_latin "
    "FROM company "
    "WHERE short_name ILIKE '%РЕНКОНС%' OR short_name ILIKE '%АГАЛАРОВ%' "
    "   OR full_name_ru ILIKE '%РЕНКОНС%' OR full_name_ru ILIKE '%АГАЛАРОВ%'"
)).mappings().all()
for r in rows:
    print(f"\n--- Company id={r['id']} short_name={r['short_name']!r} ---")
    for k, v in r.items():
        if k in ('id', 'short_name'):
            continue
        print(f"  {k}: {v!r}")