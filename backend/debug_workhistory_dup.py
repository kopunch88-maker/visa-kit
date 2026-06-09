"""Pack 37.x debug — поиск задвоенных work_history записей."""
from app.db.session import engine
from sqlmodel import Session, select
from app.models import Application, Applicant, Company

with Session(engine) as s:
    apps = s.exec(
        select(Application)
        .where(Application.applicant_id.is_not(None))
        .where(Application.company_id.is_not(None))
    ).all()

    for app in apps:
        applicant = app.applicant
        if not applicant or not applicant.work_history:
            continue
        company = s.get(Company, app.company_id) if app.company_id else None
        company_name = (company.full_name_ru if company else "?")

        # Считаем сколько записей с этим company_name
        wh = applicant.work_history
        same_company_count = 0
        for w in wh:
            if isinstance(w, dict):
                c = (w.get("company") or "").strip()
                if c == company_name.strip():
                    same_company_count += 1

        if same_company_count > 1:
            print(f"\n=== app={app.id}  applicant={applicant.last_name_native} {applicant.first_name_native} ===")
            print(f"DN-company: {company_name}")
            print(f"Duplicate count: {same_company_count}")
            for i, w in enumerate(wh):
                if isinstance(w, dict):
                    mark = " <-- DN match" if w.get("company", "").strip() == company_name.strip() else ""
                    print(f"  [{i}] '{w.get('company')}' / {w.get('period_start')} -> {w.get('period_end')}{mark}")