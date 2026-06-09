from sqlalchemy import text
from app.db.session import engine

APP_ID = 65

with engine.begin() as conn:
    before = conn.execute(text(
        "SELECT soo_number, soo_date FROM application WHERE id = :id"
    ), {"id": APP_ID}).mappings().first()
    print("ДО :", dict(before))

    conn.execute(text(
        "UPDATE application SET soo_number = NULL, soo_date = NULL WHERE id = :id"
    ), {"id": APP_ID})

    after = conn.execute(text(
        "SELECT soo_number, soo_date FROM application WHERE id = :id"
    ), {"id": APP_ID}).mappings().first()
    print("ПОСЛЕ:", dict(after))

print("Готово. soo_number и soo_date обнулены — пересчитаются при следующей генерации СОО.")
