"""
End-to-end тест полного workflow через API.

Делает всё за один запуск:
1. Логин менеджера
2. Создание новой заявки
3. Заполнение профиля клиента (через client portal token)
4. Полное распределение (assign-full)
5. Скачивание ZIP-пакета

Запуск:
    python scripts/test_e2e_workflow.py
"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import httpx

BASE_URL = "http://localhost:8000"
OUTPUT_DIR = Path(r"D:\VISA")


def main():
    print("=" * 60)
    print("END-TO-END WORKFLOW TEST")
    print("=" * 60)

    # ============================================================
    # ШАГ 1: Логин
    # ============================================================
    print("\n[1/5] Логин менеджера...")
    resp = httpx.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@visa-kit.local"},
    )
    if resp.status_code != 200:
        print(f"   [ERROR] Status {resp.status_code}: {resp.text}")
        return 1
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"   [OK] Получен JWT токен")

    # ============================================================
    # ШАГ 2: Создание заявки
    # ============================================================
    # ============================================================
    # ШАГ 2: Создание заявки
    # ============================================================
    print("\n[2/5] Создание новой заявки для petrov@example.com...")
    resp = httpx.post(
        f"{BASE_URL}/api/admin/applications",
        headers=headers,
        json={"applicant_email": "petrov@example.com"},
    )
    if resp.status_code != 201:
        print(f"   [ERROR] Status {resp.status_code}: {resp.text}")
        return 1
    app_data = resp.json()
    app_id = app_data["id"]
    reference = app_data["reference"]
    print(f"   [OK] Создана заявка {reference} (id={app_id})")

    # client_access_token не возвращается через API (для безопасности),
    # читаем его напрямую из БД для теста
    BACKEND_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(BACKEND_ROOT))
    from sqlmodel import Session, select
    from app.db.session import engine
    from app.models import Application
    with Session(engine) as session:
        application = session.get(Application, app_id)
        client_token = application.client_access_token
    print(f"        client_access_token: {client_token[:20]}...")

    # ============================================================
    # ШАГ 3: Заполнение профиля клиента (без авторизации, по токену в URL)
    # ============================================================
    print("\n[3/5] Клиент заполняет профиль...")

    # Сначала GET — создаст пустой Applicant и привяжет


    # Теперь PATCH — заполняем данные
    profile_data = {
        "last_name_native": "Петров",
        "first_name_native": "Пётр",
        "middle_name_native": "Петрович",
        "last_name_latin": "PETROV",
        "first_name_latin": "PETR",
        "birth_date": "1985-05-20",
        "birth_place_latin": "MOSCOW",
        "nationality": "RUS",
        "sex": "H",
        "passport_number": "7777888899",
        "home_address": "Москва, ул. Тверская, д. 1, кв. 1",
        "home_country": "RUS",
        "email": "petrov@example.com",
        "phone": "+7 916 555 1234",
    }
    resp = httpx.patch(
        f"{BASE_URL}/api/client/{client_token}/me",
        json=profile_data,
    )
    if resp.status_code != 200:
        print(f"   [ERROR] PATCH /me Status {resp.status_code}: {resp.text}")
        return 1
    print(f"   [OK] Профиль клиента сохранён")

    # ============================================================
    # ШАГ 4: Полное распределение
    # ============================================================
    print("\n[4/5] Менеджер делает полное распределение...")
    assign_data = {
        "company_id": 1,  # СК10
        "position_id": 1,  # инженер-геодезист
        "representative_id": 1,
        "spain_address_id": 1,
        "contract_number": "010/04/26",
        "contract_sign_date": "2026-01-15",
        "contract_sign_city": "Ростов-на-Дону",
        "contract_end_date": "2030-01-14",
        "salary_rub": 350000,
        "submission_date": "2026-05-15",
        "payments_period_months": 3,
        "employer_letter_date": "2026-05-01",
        "employer_letter_number": "550",
    }
    resp = httpx.post(
        f"{BASE_URL}/api/admin/applications/{app_id}/assign-full",
        headers=headers,
        json=assign_data,
    )
    if resp.status_code != 200:
        print(f"   [ERROR] Status {resp.status_code}: {resp.text}")
        return 1
    print(f"   [OK] Заявка распределена: СК10 / инженер-геодезист")

    # ============================================================
    # ШАГ 5: Скачивание пакета документов
    # ============================================================
    print("\n[5/5] Скачивание ZIP-пакета документов...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / f"package_{reference}.zip"

    resp = httpx.post(
        f"{BASE_URL}/api/admin/applications/{app_id}/render-package",
        headers=headers,
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"   [ERROR] Status {resp.status_code}: {resp.text}")
        return 1

    out_file.write_bytes(resp.content)
    size_kb = len(resp.content) / 1024
    print(f"   [OK] Сохранено: {out_file}")
    print(f"        Размер: {size_kb:.1f} KB")

    render_status = resp.headers.get("x-render-status", "")
    if render_status:
        print(f"\n   Статус рендера документов:")
        for entry in render_status.split(","):
            if "=ok" in entry:
                print(f"     ✓ {entry.split('=')[0]}")
            else:
                print(f"     ✗ {entry}")

    # ============================================================
    # ИТОГ
    # ============================================================
    print("\n" + "=" * 60)
    print("ВСЁ ПРОШЛО УСПЕШНО")
    print("=" * 60)
    print(f"\nЗаявка: {reference}")
    print(f"Клиент: Петров П.П.")
    print(f"Компания: СК10")
    print(f"Должность: инженер-геодезист (камеральщик)")
    print(f"\nZIP-пакет: {out_file}")
    print(f"\nОткройте папку:")
    print(f"  explorer.exe \"{OUTPUT_DIR}\"")

    return 0


if __name__ == "__main__":
    sys.exit(main())