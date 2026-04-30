"""
Seed скрипт — создаёт справочные данные в БД.

Запуск:
    python scripts/seed.py

Создаёт: 8 компаний с правильными реквизитами, ~9 должностей, представителя,
2 испанских адреса, тестового админа.

Если данные уже есть — пропускает (идемпотентно).
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

from app.db.session import engine, init_db
from app.models import (
    Company, Position, Representative, SpainAddress, User, UserRole,
)


def seed_companies(session: Session):
    """Создаёт 8 компаний с заполненными адресами по 2 строки."""
    companies_data = [
        {
            "short_name": "СК10",
            "full_name_ru": 'Общество с ограниченной ответственностью "Строительная компания СК10"',
            "full_name_es": 'Sociedad de Responsabilidad Limitada "Stroitelnaya Kompaniya SK10"',
            "country": "RUS",
            "tax_id_primary": "6168006148",
            "tax_id_secondary": "616401001",
            "legal_address": "344002, г. Ростов-на-Дону, ул. Московская, зд. 73/29а, ком. 7",
            "legal_address_line1": "344002, г. Ростов-на-Дону,",
            "legal_address_line2": "ул. Московская, зд. 73/29а, ком. 7",
            "postal_address": "344022, г. Ростов-на-Дону, ул. Нижнебульварная 6, БЦ «5 морей»",
            "postal_address_line1": "344022, г. Ростов-на-Дону,",
            "postal_address_line2": "ул. Нижнебульварная 6, БЦ «5 морей»",
            "director_full_name_ru": "Тараскин Юрий Александрович",
            "director_full_name_genitive_ru": "Тараскина Юрия Александровича",
            "director_short_ru": "Тараскин Ю.А.",
            "director_position_ru": "Генерального директора",
            "bank_name": 'Филиал "ЦЕНТРАЛЬНЫЙ" БАНКА ВТБ (ПАО)',
            "bank_account": "40702810206640002909",
            "bank_bic": "044525411",
            "bank_correspondent_account": "30101810145250000411",
        },
        {
            "short_name": "BUKI VEDI",
            "full_name_ru": 'Общество с ограниченной ответственностью "БУКИ ВЕДИ"',
            "full_name_es": 'Sociedad de Responsabilidad Limitada "BUKI VEDI"',
            "country": "RUS",
            "tax_id_primary": "7706796034",
            "tax_id_secondary": "770601001",
            "legal_address": "115035, г. Москва, ул. Большая Ордынка, д. 3",
            "legal_address_line1": "115035, г. Москва,",
            "legal_address_line2": "ул. Большая Ордынка, д. 3",
            "director_full_name_ru": "Ткачев Николай Анатольевич",
            "director_full_name_genitive_ru": "Ткачева Николая Анатольевича",
            "director_short_ru": "Ткачев Н.А.",
            "director_position_ru": "Генерального директора",
            "bank_name": "ПАО Сбербанк, г. Москва",
            "bank_account": "40702810038000123456",
            "bank_bic": "044525225",
            "bank_correspondent_account": "30101810400000000225",
        },
        {
            "short_name": "KING DAVID",
            "full_name_ru": 'Общество с ограниченной ответственностью "КИНГ ДЭВИД"',
            "full_name_es": 'Sociedad de Responsabilidad Limitada "KING DAVID"',
            "country": "RUS",
            "tax_id_primary": "7704123456",
            "tax_id_secondary": "770401001",
            "legal_address": "119019, г. Москва, ул. Арбат, д. 10",
            "legal_address_line1": "119019, г. Москва,",
            "legal_address_line2": "ул. Арбат, д. 10",
            "director_full_name_ru": "Давыдов Александр Сергеевич",
            "director_full_name_genitive_ru": "Давыдова Александра Сергеевича",
            "director_short_ru": "Давыдов А.С.",
            "director_position_ru": "Генерального директора",
            "bank_name": "АО «АЛЬФА-БАНК», г. Москва",
            "bank_account": "40702810700000123456",
            "bank_bic": "044525593",
            "bank_correspondent_account": "30101810200000000593",
        },
        {
            "short_name": "ProTech",
            "full_name_ru": 'Общество с ограниченной ответственностью "ПроТехнологии"',
            "full_name_es": 'Sociedad de Responsabilidad Limitada "ProTechnologies"',
            "country": "RUS",
            "tax_id_primary": "7720987654",
            "tax_id_secondary": "772001001",
            "legal_address": "111250, г. Москва, ул. Красноказарменная, д. 12",
            "legal_address_line1": "111250, г. Москва,",
            "legal_address_line2": "ул. Красноказарменная, д. 12",
            "director_full_name_ru": "Иванов Павел Сергеевич",
            "director_full_name_genitive_ru": "Иванова Павла Сергеевича",
            "director_short_ru": "Иванов П.С.",
            "director_position_ru": "Генерального директора",
            "bank_name": "АО «Тинькофф Банк», г. Москва",
            "bank_account": "40702810010000098765",
            "bank_bic": "044525974",
            "bank_correspondent_account": "30101810145250000974",
        },
        {
            "short_name": "TIKOmpani",
            "full_name_ru": 'Товарищество с ограниченной ответственностью "TIKOmpani"',
            "full_name_es": 'Sociedad de Responsabilidad Limitada "TIKOmpani"',
            "country": "KAZ",
            "tax_id_primary": "600400123456",
            "legal_address": "050000, г. Алматы, ул. Абая, д. 1",
            "legal_address_line1": "050000, г. Алматы,",
            "legal_address_line2": "ул. Абая, д. 1",
            "director_full_name_ru": "Ахметов Бауржан Кайратович",
            "director_full_name_genitive_ru": "Ахметова Бауржана Кайратовича",
            "director_short_ru": "Ахметов Б.К.",
            "director_position_ru": "Директора",
            "bank_name": 'АО "Народный Банк Казахстана", г. Алматы',
            "bank_account": "KZ496010251000123456",
            "bank_bic": "HSBKKZKX",
        },
        {
            "short_name": "MACHINE HEADS",
            "full_name_ru": 'Общество с ограниченной ответственностью "МЭШИН ХЕДС"',
            "full_name_es": 'Sociedad de Responsabilidad Limitada "MACHINE HEADS"',
            "country": "RUS",
            "tax_id_primary": "7733456789",
            "tax_id_secondary": "773301001",
            "legal_address": "125466, г. Москва, ул. Ландышевая, д. 5",
            "legal_address_line1": "125466, г. Москва,",
            "legal_address_line2": "ул. Ландышевая, д. 5",
            "director_full_name_ru": "Соловьёв Дмитрий Александрович",
            "director_full_name_genitive_ru": "Соловьёва Дмитрия Александровича",
            "director_short_ru": "Соловьёв Д.А.",
            "director_position_ru": "Генерального директора",
            "bank_name": "АО «Райффайзенбанк», г. Москва",
            "bank_account": "40702810400000456789",
            "bank_bic": "044525700",
            "bank_correspondent_account": "30101810200000000700",
        },
        {
            "short_name": "KNS GRUPP",
            "full_name_ru": 'Общество с ограниченной ответственностью "КНС ГРУПП"',
            "full_name_es": 'Sociedad de Responsabilidad Limitada "KNS GRUPP"',
            "country": "RUS",
            "tax_id_primary": "7706443322",
            "tax_id_secondary": "770601001",
            "legal_address": "115054, г. Москва, ул. Большая Якиманка, д. 38",
            "legal_address_line1": "115054, г. Москва,",
            "legal_address_line2": "ул. Большая Якиманка, д. 38",
            "director_full_name_ru": "Никитин Сергей Викторович",
            "director_full_name_genitive_ru": "Никитина Сергея Викторовича",
            "director_short_ru": "Никитин С.В.",
            "director_position_ru": "Генерального директора",
            "bank_name": "ПАО Сбербанк, г. Москва",
            "bank_account": "40702810300000334455",
            "bank_bic": "044525225",
            "bank_correspondent_account": "30101810400000000225",
        },
        {
            "short_name": "AVTODOM",
            "full_name_ru": 'Общество с ограниченной ответственностью "АВТОДОМ"',
            "full_name_es": 'Sociedad de Responsabilidad Limitada "AVTODOM"',
            "country": "RUS",
            "tax_id_primary": "7715998877",
            "tax_id_secondary": "771501001",
            "legal_address": "125413, г. Москва, ул. Онежская, д. 24",
            "legal_address_line1": "125413, г. Москва,",
            "legal_address_line2": "ул. Онежская, д. 24",
            "director_full_name_ru": "Беляев Роман Кириллович",
            "director_full_name_genitive_ru": "Беляева Романа Кирилловича",
            "director_short_ru": "Беляев Р.К.",
            "director_position_ru": "Генерального директора",
            "bank_name": "ПАО Банк ВТБ, г. Санкт-Петербург",
            "bank_account": "40702810500000998877",
            "bank_bic": "044030704",
            "bank_correspondent_account": "30101810200000000704",
        },
    ]

    print("📦 Companies:")
    for data in companies_data:
        existing = session.exec(
            select(Company).where(Company.short_name == data["short_name"])
        ).first()
        if existing:
            print(f"  ✓ Company '{data['short_name']}' already exists, skipping")
            continue
        c = Company(**data)
        session.add(c)
        session.flush()
        print(f"  ✓ Created company '{data['short_name']}'")
    session.commit()


def seed_positions(session: Session):
    """Создаёт типовые должности с тегами и описаниями для LLM-рекомендаций."""
    positions_data = [
        {
            "company_short": "СК10",
            "title_ru": "инженер-геодезист (камеральщик)",
            "title_ru_genitive": "инженера-геодезиста (камеральщика)",
            "title_es": "ingeniero topógrafo (gabinete)",
            "duties": [
                "Камеральная обработка результатов измерений",
                "Отрисовка инженерно-топографического плана по облаку точек в автокад (АкадТопоПлан)",
                "Отрисовка инженерно-топографических планов по абрисам/кодам",
                "Отрисовка топографического плана по данным аэрофотосъемки (ортофотоплан)",
                "Обработка и корректировка материалов инженерно-геодезических изысканий, исходя из замечаний экспертизы",
                "Подготовка схемы посадки и выноса в натуру осей здания",
                "Взаимодействие с согласователем: корректировка файла, с учетом проведенных согласований; отслеживание полноты и правильности нанесения подземных инженерных коммуникаций",
                "Подготовка технического отчета по инженерно-геодезическим изысканиям",
                "Подготовка и составление исполнительных схем для сдачи исполнительной документации",
                "Подсчет объёмов работ, сверка объемов проекта с физически выполненными объемами",
                "Составление и ведение реестра, накопительных ведомостей и накопительной схемы выполненных работ",
            ],
            "salary_rub_default": Decimal("300000"),
            "tags": ["геодезия", "топография", "автокад", "инженерное образование", "ИГДИ"],
            "profile_description": "Инженерные специальности с акцентом на геодезию и топографию. Нужен релевантный диплом или 5+ лет опыта.",
        },
        {
            "company_short": "BUKI VEDI",
            "title_ru": "технический переводчик",
            "title_ru_genitive": "технического переводчика",
            "title_es": "traductor técnico",
            "duties": [
                "Письменный перевод технической документации (чертежи, мануалы, протоколы, требования) с английского на русский и обратно",
                "Перевод технических спецификаций и требований для отправки на заводы-изготовители",
                "Перевод деловой переписки и технических заметок",
                "Участие в онлайн и технических совещаниях в качестве переводчика",
                "Ведение глоссария технических терминов для обеспечения консистентности",
                "Унификация терминов, ведение терминологических словарей по отраслям",
            ],
            "salary_rub_default": Decimal("296000"),
            "tags": ["перевод", "английский", "технический", "лингвист"],
            "profile_description": "Переводчики технической документации с английского. Опыт от 3 лет, языковой диплом или сертификат C1+.",
        },
        {
            "company_short": "ProTech",
            "title_ru": "бизнес-аналитик",
            "title_ru_genitive": "бизнес-аналитика",
            "title_es": "analista de negocio",
            "duties": [
                "Анализ бизнес-процессов заказчика",
                "Подготовка технических заданий и спецификаций",
                "Работа с данными в Excel, SQL",
                "Документация требований",
                "Презентация решений стейкхолдерам",
            ],
            "salary_rub_default": Decimal("340000"),
            "tags": ["аналитика", "данные", "Excel", "SQL", "консалтинг"],
            "profile_description": "Аналитики с опытом работы с данными и документацией требований. Знание Excel и SQL обязательно.",
        },
        {
            "company_short": "MACHINE HEADS",
            "title_ru": "Backend developer",
            "title_ru_genitive": "Backend разработчика",
            "title_es": "desarrollador backend",
            "duties": [
                "Разработка серверной части веб-приложений",
                "Проектирование и реализация REST API",
                "Работа с базами данных PostgreSQL/MySQL",
                "Написание тестов и поддержка качества кода",
                "Code review и менторинг младших разработчиков",
            ],
            "salary_rub_default": Decimal("380000"),
            "tags": ["python", "разработка", "API", "backend", "IT"],
            "profile_description": "Backend разработчики на Python (FastAPI/Django) или Node.js. От 3 лет опыта.",
        },
        {
            "company_short": "MACHINE HEADS",
            "title_ru": "Frontend developer",
            "title_ru_genitive": "Frontend разработчика",
            "title_es": "desarrollador frontend",
            "duties": [
                "Разработка пользовательских интерфейсов на React/TypeScript",
                "Интеграция с REST API",
                "Кросс-браузерная вёрстка",
                "Оптимизация производительности",
                "Участие в проектировании UX",
            ],
            "salary_rub_default": Decimal("370000"),
            "tags": ["react", "typescript", "UI", "frontend", "IT"],
            "profile_description": "Frontend разработчики на React. Знание TypeScript обязательно.",
        },
        {
            "company_short": "TIKOmpani",
            "title_ru": "Project manager",
            "title_ru_genitive": "Project manager-а",
            "title_es": "jefe de proyecto",
            "duties": [
                "Планирование и управление проектами разработки",
                "Координация работы команды",
                "Взаимодействие со стейкхолдерами",
                "Управление рисками и бюджетом проекта",
                "Внедрение agile-практик",
            ],
            "salary_rub_default": Decimal("330000"),
            "tags": ["проекты", "agile", "команда", "менеджмент"],
            "profile_description": "Project managers с опытом ведения IT-проектов. Сертификация PMP/Scrum приветствуется.",
        },
        {
            "company_short": "KNS GRUPP",
            "title_ru": "IT-консультант",
            "title_ru_genitive": "IT-консультанта",
            "title_es": "consultor de TI",
            "duties": [
                "Консультирование клиентов по внедрению IT-систем",
                "Анализ существующей инфраструктуры",
                "Подготовка рекомендаций по оптимизации",
                "Участие во внедрении 1С",
                "Обучение персонала клиента",
            ],
            "salary_rub_default": Decimal("320000"),
            "tags": ["консалтинг", "внедрение", "1C", "IT"],
            "profile_description": "IT-консультанты с опытом внедрения корпоративных систем. Знание 1С приветствуется.",
        },
        {
            "company_short": "AVTODOM",
            "title_ru": "Маркетолог",
            "title_ru_genitive": "Маркетолога",
            "title_es": "responsable de marketing",
            "duties": [
                "Разработка и реализация маркетинговых стратегий",
                "Управление рекламными кампаниями",
                "Работа с digital-каналами (SEO, SMM, контекстная реклама)",
                "Анализ эффективности маркетинговых активностей",
                "Подготовка контента для коммуникаций",
            ],
            "salary_rub_default": Decimal("300000"),
            "tags": ["маркетинг", "реклама", "digital", "SEO"],
            "profile_description": "Маркетологи с опытом digital-маркетинга. Знание инструментов (Google Analytics, Яндекс.Метрика) обязательно.",
        },
    ]

    print("💼 Positions:")
    for data in positions_data:
        company_short = data.pop("company_short")
        company = session.exec(
            select(Company).where(Company.short_name == company_short)
        ).first()
        if not company:
            print(f"  ✗ Company '{company_short}' not found, skipping position")
            continue

        existing = session.exec(
            select(Position).where(
                Position.company_id == company.id,
                Position.title_ru == data["title_ru"],
            )
        ).first()
        if existing:
            print(f"  ✓ Position '{data['title_ru']}' for {company_short} already exists")
            continue

        p = Position(company_id=company.id, **data)
        session.add(p)
        session.flush()
        print(f"  ✓ Created position '{data['title_ru']}' for {company_short}")
    session.commit()


def seed_representatives(session: Session):
    print("👤 Representatives:")
    existing = session.exec(
        select(Representative).where(Representative.nie == "Z3751311Q")
    ).first()
    if existing:
        print(f"  ✓ Representative {existing.first_name} {existing.last_name} already exists")
        return

    rep = Representative(
        first_name="ANASTASIIA",
        last_name="KORENEVA",
        nie="Z3751311Q",
        email="mosremstroy@gmail.com",
        phone="+34 627 901 730",
        address_street="CARRER DEL BALMES",
        address_number="128",
        address_floor="3-2",
        address_zip="08008",
        address_city="BARCELONA",
        address_province="BARCELONA",
    )
    session.add(rep)
    session.commit()
    print(f"  ✓ Created representative {rep.first_name} {rep.last_name}")


def seed_spain_addresses(session: Session):
    print("📍 Spain Addresses:")
    addresses_data = [
        {
            "label": "Балмес 128, Барселона",
            "street": "CARRER DEL BALMES",
            "number": "128",
            "floor": "3-2",
            "zip": "08008",
            "city": "BARCELONA",
            "province": "BARCELONA",
            "uge_office": "Cataluña",
        },
        {
            "label": "Кастельо 5, Мадрид",
            "street": "CALLE CASTELLÓ",
            "number": "5",
            "floor": "4-C",
            "zip": "28001",
            "city": "MADRID",
            "province": "MADRID",
            "uge_office": "Madrid",
        },
    ]
    for data in addresses_data:
        existing = session.exec(
            select(SpainAddress).where(SpainAddress.label == data["label"])
        ).first()
        if existing:
            print(f"  ✓ Address '{data['label']}' already exists")
            continue
        a = SpainAddress(**data)
        session.add(a)
        session.flush()
        print(f"  ✓ Created address '{data['label']}'")
    session.commit()


def seed_admin_user(session: Session):
    print("🔑 Admin user:")
    existing = session.exec(
        select(User).where(User.email == "admin@visa-kit.local")
    ).first()
    if existing:
        print(f"  ✓ Admin user already exists")
        return
    u = User(
        email="admin@visa-kit.local",
        full_name="Admin",
        role=UserRole.ADMIN,
    )
    session.add(u)
    session.commit()
    print(f"  ✓ Created admin user 'admin@visa-kit.local'")


def main():
    print("🌱 Seeding database...")
    init_db()
    with Session(engine) as session:
        seed_companies(session)
        seed_positions(session)
        seed_representatives(session)
        seed_spain_addresses(session)
        seed_admin_user(session)
    print("✅ Seed complete!")
    print("Login as: admin@visa-kit.local")


if __name__ == "__main__":
    main()
