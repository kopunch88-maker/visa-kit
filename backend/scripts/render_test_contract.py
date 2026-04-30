"""Test render of contract from real DB data."""
import sys
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlmodel import Session, select

from app.db.session import engine
from app.models import (
    Applicant, Application, ApplicationStatus,
    Company, Position, Representative, SpainAddress,
)
from app.templates_engine import render_contract


OUTPUT_PATH = BACKEND_ROOT.parent / "templates" / "docx" / "_RENDERED_test_contract.docx"


def get_or_create_test_applicant(session):
    existing = session.exec(
        select(Applicant).where(Applicant.passport_number == "C01366076")
    ).first()
    if existing:
        print("[OK] Test Applicant already exists, id=" + str(existing.id))
        return existing

    applicant = Applicant(
        last_name_native="Алиев",
        first_name_native="Джафар",
        middle_name_native="Надирович",
        last_name_latin="ALIYEV",
        first_name_latin="JAFAR",
        birth_date=date(1963, 3, 9),
        birth_place_latin="BAKU",
        nationality="AZE",
        sex="H",
        marital_status="C",
        father_name_latin="NADIR",
        mother_name_latin="ZIVER",
        passport_number="C01366076",
        passport_issue_date=date(2017, 3, 24),
        passport_issuer="МИД Азербайджана",
        inn="230217957801",
        home_address="352919, Краснодарский край, г. Армавир, ул. 11-я Линия, д. 31 кв. 2",
        home_address_line1="352919, Краснодарский край, г. Армавир,",
        home_address_line2="ул. 11-я Линия, д. 31 кв. 2",
        home_country="RUS",
        email="moscu27918@gmail.com",
        phone="+34 627 901 730",
        bank_account="40803840441563809831",
        bank_name="АО «АЛЬФА-БАНК», г. Москва",
        bank_bic="044525593",
        bank_correspondent_account="30101810200000000593",
        education=[
            {
                "institution": "Ростовский государственный строительный университет",
                "graduation_year": 2010,
                "degree": "Инженер",
                "specialty": "Прикладная геодезия",
            }
        ],
        work_history=[],
        languages=["Русский — родной", "Английский — B1"],
    )
    session.add(applicant)
    session.commit()
    session.refresh(applicant)
    print("[OK] Created Applicant: Aliyev, id=" + str(applicant.id))
    return applicant


def get_test_directory_data(session):
    company = session.exec(select(Company).where(Company.short_name == "СК10")).first()
    position = session.exec(
        select(Position).where(Position.title_ru == "инженер-геодезист (камеральщик)")
    ).first()
    representative = session.exec(select(Representative)).first()
    address = session.exec(select(SpainAddress)).first()

    if not all([company, position, representative, address]):
        raise RuntimeError("Database not seeded. Run: python scripts/seed.py")

    return company, position, representative, address


def get_or_create_test_application(session, applicant, company, position, representative, address):
    import secrets

    existing = session.exec(
        select(Application).where(Application.reference == "2026-TEST")
    ).first()
    if existing:
        session.delete(existing)
        session.commit()

    application = Application(
        reference="2026-TEST",
        client_access_token=secrets.token_urlsafe(32),
        status=ApplicationStatus.ASSIGNED,
        applicant_id=applicant.id,
        company_id=company.id,
        position_id=position.id,
        representative_id=representative.id,
        spain_address_id=address.id,
        contract_number="004/09/25",
        contract_sign_date=date(2025, 9, 5),
        contract_sign_city="Ростов-на-Дону",
        contract_end_date=date(2029, 8, 31),
        salary_rub=Decimal("300000"),
    )
    session.add(application)
    session.commit()
    session.refresh(application)
    print("[OK] Created Application 2026-TEST, id=" + str(application.id))
    return application


def main():
    with Session(engine) as session:
        print("=== Preparing data ===")
        applicant = get_or_create_test_applicant(session)
        company, position, representative, address = get_test_directory_data(session)
        print("[OK] Company: " + company.short_name)
        print("[OK] Position: " + position.title_ru)
        print("[OK] Representative: " + representative.first_name + " " + representative.last_name)
        print("[OK] Address: " + address.label)

        application = get_or_create_test_application(
            session, applicant, company, position, representative, address,
        )

        print("")
        print("=== Rendering contract ===")
        try:
            docx_bytes = render_contract(application, session)
        except Exception as e:
            print("[ERROR] " + type(e).__name__ + ": " + str(e))
            import traceback
            traceback.print_exc()
            return 1

        OUTPUT_PATH.write_bytes(docx_bytes)
        print("[OK] Contract saved: " + str(OUTPUT_PATH))
        print("     Size: " + str(len(docx_bytes)) + " bytes")
        print("")
        print("Open the file in Word and check that all {{ variables }} have been replaced.")

    return 0


if __name__ == "__main__":
    sys.exit(main())