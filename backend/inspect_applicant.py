import os
os.environ['DATABASE_URL'] = 'postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway'
from sqlmodel import create_engine, Session, select
from app.models import Applicant

engine = create_engine(os.environ['DATABASE_URL'])
with Session(engine) as session:
    # Найду Ибрахима с bank_id=4 (ТБанк)
    rows = session.exec(
        select(Applicant).where(Applicant.bank_id == 4)
    ).all()
    print(f'Applicant с ТБанком: {len(rows)}')
    for a in rows[:3]:
        print(f"\n=== id={a.id} ===")
        for col in a.__table__.columns:
            val = getattr(a, col.name, None)
            if val is not None and val != "" and col.name != "id":
                preview = str(val)[:80]
                print(f"  {col.name:35s} = {preview!r}")
