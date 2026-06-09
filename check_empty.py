import os, psycopg2
c = psycopg2.connect(os.environ['DATABASE_URL'])
cur = c.cursor()
cur.execute("""
    SELECT id, title_ru, primary_specialty_id
    FROM position
    WHERE tech_opinion_description_ru IS NULL OR LENGTH(tech_opinion_description_ru) <= 50
    ORDER BY id
""")
print('Empty positions:')
for r in cur.fetchall():
    print(f'  id={r[0]:3d}  spec_id={r[1] if r[1] is None else r[2]}  {r[1]}')
c.close()
