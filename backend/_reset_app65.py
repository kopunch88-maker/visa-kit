from sqlalchemy import text
from app.db.session import engine

APP_ID = 65

with engine.begin() as conn:
    row = conn.execute(text("""
        SELECT business_trip_start_date, business_trip_end_date,
               business_trip_order_date, business_trip_order_number,
               soo_number, soo_date
        FROM application WHERE id = :id
    """), {"id": APP_ID}).mappings().first()

    print("=== ТЕКУЩИЕ значения заявки", APP_ID, "===")
    for k, v in row.items():
        print(f"  {k} = {v}")
