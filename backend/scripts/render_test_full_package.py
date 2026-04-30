"""
Тестовый рендер всего пакета документов из реальных данных в БД.

Создаёт тестовую заявку Алиева (если ещё нет), рендерит все 9 документов:
- Договор
- 3 акта
- 3 счёта
- Письмо от компании (с EUR-эквивалентом по курсу ЦБ)
- CV

Запуск:
    cd D:\\VISA\\visa_kit\\backend
    python scripts\\render_test_full_package.py
"""
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
from app.templates_engine import (
    render_contract, render_act, render_invoice,
    render_employer_letter, render_cv,
)


OUTPUT_DIR = BACKEND_ROOT.parent / "templates" / "docx"


def get_or_create_test_applicant(session):
    existing = session.exec(
        select(Applicant).where(Applicant.passport_number == "C01366076")
    ).first()
    if existing:
        # Обновим work_history на случай если в БД была неполная версия
        existing.work_history = _make_work_history()
        existing.education = _make_education()
        existing.languages = ["Русский — родной", "Английский B1"]
        session.add(existing)
        session.commit()
        session.refresh(existing)
        print("[OK] Test Applicant exists, id=" + str(existing.id))
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
        education=_make_education(),
        work_history=_make_work_history(),
        languages=["Русский — родной", "Английский B1"],
    )
    session.add(applicant)
    session.commit()
    session.refresh(applicant)
    print("[OK] Created Applicant: Aliyev, id=" + str(applicant.id))
    return applicant


def _make_education():
    return [
        {
            "institution": "Государственное образовательное учреждение высшего профессионального образования «Ростовский государственный строительный университет»",
            "graduation_year": 2010,
            "degree": "Инженер",
            "specialty": "Прикладная геодезия",
        }
    ]


def _make_work_history():
    """5 мест работы из реального CV Алиева."""
    return [
        {
            "period_start": "Сентябрь 2025",
            "period_end": "по настоящее время",
            "company": "ООО «Строительная компания «СК10»",
            "position": "Инженер-геодезист (камеральщик)",
            "duties": [
                "Камеральная обработка результатов измерений",
                "Отрисовка инженерно-топографического плана по облаку точек в автокад (АкадТопоПлан)",
                "Отрисовка инженерно-топографических планов по абрисам/кодам",
                "Отрисовка топографического плана по данным аэрофотосъемки (ортофотоплан)",
                "Подготовка технического отчета по инженерно-геодезическим изысканиям",
                "Подсчет объёмов работ, сверка объемов проекта с физически выполненными объемами",
            ],
        },
        {
            "period_start": "Март 2022",
            "period_end": "Август 2025",
            "company": "ООО «ИНЖГЕОСЕРВИС»",
            "position": "геодезист-камеральщик",
            "duties": [
                "Обработка и анализ геодезических данных",
                "Создание картографического материала с использованием специализированного ПО",
                "Построение трехмерных моделей рельефа местности",
                "Выпуск Технического отчета по ИГДИ",
            ],
        },
        {
            "period_start": "Январь 2019",
            "period_end": "Октябрь 2021",
            "company": "Advanced Geo Solutions, Ltd.",
            "position": "геодезист-камеральщик",
            "duties": [
                "Работа с проектной документацией",
                "Выполнение камеральных работ по созданию исполнительных чертежей",
                "Черчение теплосетей (план+профиль+стыки+узлы+СОДК)",
            ],
        },
        {
            "period_start": "Январь 2015",
            "period_end": "Декабрь 2018",
            "company": "Project Terra LLC",
            "position": "Инженер-геодезист",
            "duties": [
                "Работа на строительных площадках по геодезическому сопровождению строительства",
                "Проведение инструментального контроля за соблюдением геометрических параметров",
                "Выполнение исполнительных съемок по законченным работам",
            ],
        },
        {
            "period_start": "Февраль 2013",
            "period_end": "Декабрь 2014",
            "company": "Construction Expertise",
            "position": "Инженер-геодезист",
            "duties": [
                "Проектирование и прокладка магистральных газовых труб и коммуникаций",
                "Сопровождение строительных работ для объектов железнодорожных путей",
                "Топографическая съемка строительных объектов",
            ],
        },
    ]


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
        # Параметры для актов/счетов
        submission_date=date(2026, 4, 28),
        payments_period_months=3,
        # Письмо от компании
        employer_letter_number="544",
        employer_letter_date=date(2026, 4, 17),
    )
    session.add(application)
    session.commit()
    session.refresh(application)
    print("[OK] Created Application 2026-TEST, id=" + str(application.id))
    return application


def render_one(name, fn, *args):
    """Вспомогательная — рендерит один документ, ловит ошибки."""
    try:
        out_bytes = fn(*args)
        out_path = OUTPUT_DIR / f"_RENDERED_test_{name}.docx"
        out_path.write_bytes(out_bytes)
        print(f"  [OK] {name}: {len(out_bytes)} bytes")
        return True
    except Exception as e:
        print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


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
        print("=== Rendering full package ===")

        # Договор
        render_one("contract", render_contract, application, session)

        # Акты и счета (3 штуки каждого)
        for n in (1, 2, 3):
            render_one(f"act_{n}", render_act, application, session, n)
            render_one(f"invoice_{n}", render_invoice, application, session, n)

        # Письмо от компании
        render_one("employer_letter", render_employer_letter, application, session)

        # CV
        render_one("cv", render_cv, application, session)

        print("")
        print(f"All rendered files are in: {OUTPUT_DIR}")
        print("Open files starting with _RENDERED_test_ in Word and check.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
