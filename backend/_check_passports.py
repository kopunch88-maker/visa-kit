import json
from sqlalchemy import text
from app.db.session import engine

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, passport_number, passport_issue_date, passports "
        "FROM applicant WHERE passports IS NOT NULL ORDER BY id DESC LIMIT 1"
    ))
    for r in rows:
        print("applicant.id =", r[0])
        print("applicant.passport_number =", r[1])
        print("applicant.passport_issue_date =", r[2])
        print("passports JSON:")
        print(json.dumps(r[3], ensure_ascii=False, indent=2))
