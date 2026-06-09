import os, psycopg2
c = psycopg2.connect(os.environ['DATABASE_URL'])
cur = c.cursor()
cur.execute("""
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE tech_opinion_description_ru IS NOT NULL AND LENGTH(tech_opinion_description_ru) > 50) AS filled
    FROM position
""")
total, filled = cur.fetchone()
print(f'Position total: {total}, tech_opinion filled: {filled}, empty: {total - filled}')
c.close()
