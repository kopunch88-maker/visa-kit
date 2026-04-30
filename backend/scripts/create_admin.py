"""
Скрипт создания пользователей админки.

Использование:
    cd backend
    .venv\\Scripts\\Activate.ps1  (Windows) / source .venv/bin/activate (Linux)
    python scripts/create_admin.py
"""

import getpass
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sqlmodel import Session, select
from app.db.session import engine
from app.models import User
from app.api.auth import hash_password


def main():
    print("=" * 60)
    print("Создание пользователя админки visa-kit")
    print("=" * 60)

    email = input("Email: ").strip().lower()
    if not email or "@" not in email:
        print("[ERROR] Некорректный email")
        sys.exit(1)

    full_name = input("ФИО (обязательно): ").strip()
    if not full_name:
        print("[ERROR] ФИО обязательно")
        sys.exit(1)

    role = input("Роль (admin/manager/readonly) [manager]: ").strip().lower()
    if not role:
        role = "manager"
    if role not in ("admin", "manager", "readonly"):
        print(f"[ERROR] Неверная роль: {role}")
        sys.exit(1)

    while True:
        password = getpass.getpass("Пароль (минимум 8 символов): ")
        if len(password) < 8:
            print("[ERROR] Пароль слишком короткий")
            continue
        confirm = getpass.getpass("Повторите пароль: ")
        if password != confirm:
            print("[ERROR] Пароли не совпадают, попробуйте ещё раз")
            continue
        break

    password_hashed = hash_password(password)

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == email)).first()

        if existing:
            print(f"\n[WARNING] Пользователь {email} уже существует")
            confirm_update = input("Обновить пароль и имя? (y/n): ").strip().lower()
            if confirm_update != "y":
                print("Отменено")
                sys.exit(0)
            existing.password_hash = password_hashed
            existing.full_name = full_name
            existing.role = role
            existing.is_active = True
            session.add(existing)
            session.commit()
            print(f"\n[OK] Пользователь обновлён: {email}")
        else:
            user = User(
                email=email,
                full_name=full_name,
                role=role,
                is_active=True,
                password_hash=password_hashed,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            print(f"\n[OK] Пользователь создан: id={user.id}, email={user.email}, role={user.role}")

    print("\nГотово. Можно логиниться через UI: http://localhost:3000/admin/login")


if __name__ == "__main__":
    main()
