import os, psycopg2
c = psycopg2.connect(os.environ['DATABASE_URL'])
cur = c.cursor()
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name='specialty'
    ORDER BY ordinal_position
""")
print('specialty columns:')
for name, dtype in cur.fetchall():
    print(f'  {name}: {dtype}')
c.close()
