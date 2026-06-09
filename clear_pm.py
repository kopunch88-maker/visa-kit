import os, psycopg2
c = psycopg2.connect(os.environ['DATABASE_URL'])
cur = c.cursor()
cur.execute("""
    UPDATE position SET
        tech_opinion_description_ru = NULL,
        tech_opinion_description_es = NULL,
        tech_opinion_tools_ru = NULL,
        tech_opinion_tools_es = NULL,
        tech_opinion_steps_ru = NULL,
        tech_opinion_steps_es = NULL,
        tech_opinion_grounds_ru = NULL,
        tech_opinion_grounds_es = NULL,
        tech_opinion_contract_clause_ru = NULL,
        tech_opinion_contract_clause_es = NULL,
        international_analog_ru = NULL,
        international_analog_es = NULL
    WHERE id = 7
""")
c.commit()
print(f'Cleared id=7: {cur.rowcount} row(s)')
c.close()
