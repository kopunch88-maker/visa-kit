from app.db.session import engine
from sqlmodel import Session
from app.models import Application
from app.services.work_history_sync import sync_dn_work_record_safe

with Session(engine) as s:
    app = s.get(Application, 52)
    print("Before:")
    for i, wh in enumerate(app.applicant.work_history or []):
        print(f"  [{i}] {wh.get('company')} / {wh.get('period_start')} -> {wh.get('period_end')}")
    print("Sync:", sync_dn_work_record_safe(app, s))
    s.refresh(app.applicant)
    print("After:")
    for i, wh in enumerate(app.applicant.work_history or []):
        print(f"  [{i}] {wh.get('company')} / {wh.get('period_start')} -> {wh.get('period_end')}")