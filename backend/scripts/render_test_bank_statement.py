"""Тестовый рендер банковской выписки (для проверки плана Б)."""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlmodel import Session, select

from app.db.session import engine
from app.models import Application
from app.templates_engine import render_bank_statement


OUTPUT_PATH = BACKEND_ROOT.parent / "templates" / "docx" / "_RENDERED_test_bank_statement.docx"


def main():
    with Session(engine) as session:
        # Берём первое приложение Алиева (должна быть готовая 2026-TEST или 2026-0003)
        application = session.exec(
            select(Application).order_by(Application.id.desc())
        ).first()
        if not application:
            print("[ERROR] No applications in DB. Run scripts/test_e2e_workflow.py first.")
            return 1

        print(f"Rendering bank statement for application {application.reference}")
        print(f"  ID: {application.id}")
        print(f"  Submission date: {application.submission_date}")
        print(f"  Salary: {application.salary_rub}")

        try:
            content = render_bank_statement(application, session)
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return 1

        OUTPUT_PATH.write_bytes(content)
        print(f"[OK] Saved: {OUTPUT_PATH}")
        print(f"     Size: {len(content):,} bytes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
