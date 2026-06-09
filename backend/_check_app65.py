from sqlalchemy import text
from app.db.session import engine

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, applicant_id, business_trip_start_date, business_trip_end_date, "
        "business_trip_order_date, business_trip_order_number, soo_number, soo_date "
        "FROM application WHERE id = 65"
    ))
    cols = ["id","applicant_id","bt_start","bt_end","bt_order_date","bt_order_num","soo_number","soo_date"]
    for r in rows:
        for c, v in zip(cols, r):
            print(f"  {c} = {v}")
