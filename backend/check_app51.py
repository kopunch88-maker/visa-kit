# Сохрани в backend\sync_app51.py
from app.db.session import engine
from sqlmodel import Session
from app.models import Application
from app.services.work_history_sync import sync_dn_work_record_safe

with Session(engine) as s:
    app = s.get(Application, 51)
    print(f"Before sync:")
    for i, wh in enumerate(app.applicant.work_history or []):
        print(f"  [{i}] {wh.get('company')} / {wh.get('period_start')} -> {wh.get('period_end')}")
    
    result = sync_dn_work_record_safe(app, s)
    print(f"\nSync result: {result}")
    
    s.refresh(app)
    s.refresh(app.applicant)
    print(f"\nAfter sync:")
    for i, wh in enumerate(app.applicant.work_history or []):
        print(f"  [{i}] {wh.get('company')} / {wh.get('period_start')} -> {wh.get('period_end')}")