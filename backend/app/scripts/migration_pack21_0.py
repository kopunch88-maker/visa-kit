"""
Pack 21.0 — Seed для Representative и SpainAddress.

ЦЕЛИ:
1. Удалить мусорные тестовые записи (id=1 в обеих таблицах)
2. Создать 5 представителей-испанцев (доверенные лица для нотариальных доверенностей)
3. Создать 11 адресов в Барселоне (пул для клиентов — куда они регистрируются)

ВАЖНО:
- representative.address_* — это ЛИЧНЫЙ адрес представителя (где он сам живёт)
- spain_address.* — это адрес ДЛЯ КЛИЕНТА (куда applicant регистрируется,
  попадает в MIT, Declaration Responsable, Designacion de representante)

КАК ПРИМЕНИТЬ:
    $env:DATABASE_URL = "..."
    $env:PYTHONIOENCODING = "utf-8"
    cd D:\\VISA\\visa_kit\\backend
    python -m app.scripts.migration_pack21_0

Идемпотентно — проверяет наличие записей перед INSERT/UPDATE.
"""

from sqlalchemy import text
from app.db.session import engine


# ============================================================================
# DATA
# ============================================================================

REPRESENTATIVES = [
    {
        "first_name": "ANNA",
        "last_name": "TELEPNEVA",
        "nie": "Z3314769Z",
        "email": "Moscu27918@gmail.com",
        "phone": "+34 661 853 441",
        "address_street": "Carrer de Valencia",
        "address_number": "178",
        "address_floor": "5-1",
        "address_zip": "08011",
        "address_city": "Barcelona",
        "address_province": "Barcelona",
        "is_active": True,
    },
    {
        "first_name": "NIKOLA",
        "last_name": "BUGARIN",
        "nie": "Z4052281P",
        "email": "Moscu27918@gmail.com",
        "phone": "+34 627 901 720",
        "address_street": "Carrer de la Creu Coberta",
        "address_number": "58",
        "address_floor": "1-2",
        "address_zip": "08014",
        "address_city": "Barcelona",
        "address_province": "Barcelona",
        "is_active": True,
    },
    {
        "first_name": "IVAN",
        "last_name": "DMITREV",
        "nie": "Z393149S",
        "email": "Ivan.dmitref66@gmail.com",
        "phone": "+34 607 887 71",
        "address_street": "Carrer de Verdi",
        "address_number": "72",
        "address_floor": "3-2",
        "address_zip": "08012",
        "address_city": "Barcelona",
        "address_province": "Barcelona",
        "is_active": True,
    },
    {
        "first_name": "TATIANA",
        "last_name": "ORLOVA",
        "nie": "Z2063956X",
        "email": "Mosremstroy@gmail.com",
        "phone": "+34 627 901 730",
        "address_street": "Carrer de Padila",
        "address_number": "375",
        "address_floor": "2-2",
        "address_zip": "08025",
        "address_city": "Barcelona",
        "address_province": "Barcelona",
        "is_active": True,
    },
    {
        "first_name": "ANASTASIIA",
        "last_name": "KORENEVA",
        "nie": "Z3751311Q",
        "email": "Mosremstroy@gmail.com",
        "phone": "+34 627 901 730",
        "address_street": "Carrer de Padila",
        "address_number": "375",
        "address_floor": "2-2",
        "address_zip": "08025",
        "address_city": "Barcelona",
        "address_province": "Barcelona",
        "is_active": True,
    },
]


SPAIN_ADDRESSES = [
    # 11 адресов из списка Кости — пул для клиентов
    {
        "street": "Carrer de Balmes",
        "number": "45",
        "floor": "3 2",
        "zip": "08007",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Balmes 45, Barcelona",
    },
    {
        "street": "Carrer de la Princesa",
        "number": "21",
        "floor": "2 1",
        "zip": "08003",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Princesa 21, Barcelona",
    },
    {
        "street": "Carrer Gran de Gràcia",
        "number": "120",
        "floor": "1 3",
        "zip": "08012",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Gran de Gràcia 120, Barcelona",
    },
    {
        "street": "Carrer de Joaquín Costa",
        "number": "58",
        "floor": "4 1",
        "zip": "08001",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Joaquín Costa 58, Barcelona",
    },
    {
        "street": "Carrer de Pere IV",
        "number": "310",
        "floor": "2 2",
        "zip": "08020",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Pere IV 310, Barcelona",
    },
    {
        "street": "Carrer de Bac de Roda",
        "number": "65",
        "floor": "5 4",
        "zip": "08019",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Bac de Roda 65, Barcelona",
    },
    {
        "street": "Carrer de Llull",
        "number": "185",
        "floor": "5 2",
        "zip": "08005",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Llull 185, Barcelona",
    },
    {
        "street": "Carrer de Josep Pla",
        "number": "150",
        "floor": "7 1",
        "zip": "08019",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Josep Pla 150, Barcelona",
    },
    {
        "street": "Carrer de Tajo",
        "number": "45",
        "floor": "2 1",
        "zip": "08032",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Tajo 45, Barcelona",
    },
    {
        "street": "Carrer de Sants",
        "number": "214",
        "floor": "3 2",
        "zip": "08028",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Sants 214, Barcelona",
    },
    {
        "street": "Carrer de Fabra i Puig",
        "number": "380",
        "floor": "4 2",
        "zip": "08031",
        "city": "Barcelona",
        "province": "Barcelona",
        "uge_office": "Cataluña",
        "label": "Fabra i Puig 380, Barcelona",
    },
]


# ============================================================================
# MIGRATION
# ============================================================================

def upsert_representative(conn, rep: dict) -> tuple[int, str]:
    """INSERT или UPDATE Representative по NIE (уникальный ключ)."""
    existing = conn.execute(
        text("SELECT id FROM representative WHERE nie = :nie"),
        {"nie": rep["nie"]},
    ).fetchone()

    if existing:
        rep_id = existing[0]
        conn.execute(
            text("""
                UPDATE representative SET
                    first_name = :first_name,
                    last_name = :last_name,
                    email = :email,
                    phone = :phone,
                    address_street = :address_street,
                    address_number = :address_number,
                    address_floor = :address_floor,
                    address_zip = :address_zip,
                    address_city = :address_city,
                    address_province = :address_province,
                    is_active = :is_active,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {**rep, "id": rep_id},
        )
        return rep_id, "UPDATED"
    else:
        result = conn.execute(
            text("""
                INSERT INTO representative (
                    first_name, last_name, nie, email, phone,
                    address_street, address_number, address_floor,
                    address_zip, address_city, address_province,
                    is_active, created_at, updated_at
                ) VALUES (
                    :first_name, :last_name, :nie, :email, :phone,
                    :address_street, :address_number, :address_floor,
                    :address_zip, :address_city, :address_province,
                    :is_active, NOW(), NOW()
                )
                RETURNING id
            """),
            rep,
        )
        return result.scalar(), "INSERTED"


def upsert_spain_address(conn, addr: dict) -> tuple[int, str]:
    """INSERT или UPDATE SpainAddress по (street, number, zip)."""
    existing = conn.execute(
        text("""
            SELECT id FROM spain_address
            WHERE street = :street AND number = :number AND zip = :zip
        """),
        {"street": addr["street"], "number": addr["number"], "zip": addr["zip"]},
    ).fetchone()

    if existing:
        addr_id = existing[0]
        conn.execute(
            text("""
                UPDATE spain_address SET
                    floor = :floor,
                    city = :city,
                    province = :province,
                    uge_office = :uge_office,
                    label = :label,
                    is_active = TRUE,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {**addr, "id": addr_id},
        )
        return addr_id, "UPDATED"
    else:
        result = conn.execute(
            text("""
                INSERT INTO spain_address (
                    street, number, floor, zip, city, province,
                    uge_office, label,
                    is_active, created_at, updated_at
                ) VALUES (
                    :street, :number, :floor, :zip, :city, :province,
                    :uge_office, :label,
                    TRUE, NOW(), NOW()
                )
                RETURNING id
            """),
            addr,
        )
        return result.scalar(), "INSERTED"


def main():
    print("[Pack 21.0] start: seed Representatives + SpainAddresses")

    with engine.begin() as conn:
        # ====================================================================
        # 1. Удалить мусорные id=1 в обеих таблицах
        # ====================================================================
        print("\n[Pack 21.0] === STEP 1: cleanup junk id=1 ===")

        # representative id=1 (zxczxc, Королев)
        # Проверяем что нет привязок к application
        n_apps_repr1 = conn.execute(
            text("SELECT COUNT(*) FROM application WHERE representative_id = 1")
        ).scalar()
        if n_apps_repr1 == 0:
            existing = conn.execute(
                text("SELECT id, last_name FROM representative WHERE id = 1")
            ).fetchone()
            if existing:
                conn.execute(text("DELETE FROM representative WHERE id = 1"))
                print(f"    DELETED representative id=1 '{existing[1]}'")
        else:
            print(f"    SKIP: representative id=1 has {n_apps_repr1} applications, cannot delete")

        # spain_address id=1 (zxczxc)
        n_apps_addr1 = conn.execute(
            text("SELECT COUNT(*) FROM application WHERE spain_address_id = 1")
        ).scalar()
        if n_apps_addr1 == 0:
            existing = conn.execute(
                text("SELECT id, label FROM spain_address WHERE id = 1")
            ).fetchone()
            if existing:
                conn.execute(text("DELETE FROM spain_address WHERE id = 1"))
                print(f"    DELETED spain_address id=1 '{existing[1]}'")
        else:
            print(f"    SKIP: spain_address id=1 has {n_apps_addr1} applications, cannot delete")

        # ====================================================================
        # 2. Создать представителей
        # ====================================================================
        print("\n[Pack 21.0] === STEP 2: seed representatives ===")
        for rep in REPRESENTATIVES:
            rep_id, action = upsert_representative(conn, rep)
            print(f"    {action} representative id={rep_id} "
                  f"{rep['first_name']} {rep['last_name']} ({rep['nie']}) "
                  f"@ {rep['address_street']} {rep['address_number']}")

        # ====================================================================
        # 3. Создать адреса в Барселоне
        # ====================================================================
        print("\n[Pack 21.0] === STEP 3: seed Barcelona addresses ===")
        for addr in SPAIN_ADDRESSES:
            addr_id, action = upsert_spain_address(conn, addr)
            print(f"    {action} spain_address id={addr_id} '{addr['label']}'")

        # ====================================================================
        # 4. Финальная картина
        # ====================================================================
        print("\n[Pack 21.0] === FINAL ===")

        n_repr_total = conn.execute(text("SELECT COUNT(*) FROM representative")).scalar()
        n_repr_active = conn.execute(text("SELECT COUNT(*) FROM representative WHERE is_active = TRUE")).scalar()
        print(f"    representative: total={n_repr_total}, active={n_repr_active}")

        n_addr_total = conn.execute(text("SELECT COUNT(*) FROM spain_address")).scalar()
        n_addr_active = conn.execute(text("SELECT COUNT(*) FROM spain_address WHERE is_active = TRUE")).scalar()
        print(f"    spain_address: total={n_addr_total}, active={n_addr_active}")

        print("\n    Active representatives:")
        rows = conn.execute(text("""
            SELECT id, last_name, first_name, nie,
                   address_street, address_number, address_zip
            FROM representative WHERE is_active = TRUE ORDER BY last_name
        """)).fetchall()
        for r in rows:
            print(f"      id={r[0]:>2}  {r[1]:<12} {r[2]:<12}  {r[3]:<10}  "
                  f"{r[4]} {r[5]}, {r[6]}")

        print("\n    Active spain addresses:")
        rows = conn.execute(text("""
            SELECT id, label, street, number, zip, uge_office
            FROM spain_address WHERE is_active = TRUE ORDER BY id
        """)).fetchall()
        for r in rows:
            print(f"      id={r[0]:>2}  {r[1]:<35}  {r[2]} {r[3]}, {r[4]}  ({r[5]})")

    print("\n[Pack 21.0] ✅ DONE")


if __name__ == "__main__":
    main()
