"""
Тестовый скрипт — скачивает пакет через API и сохраняет на диск.

Использует существующее тестовое приложение 2026-TEST. Сначала логинится,
получает токен, потом вызывает /render-package и сохраняет ZIP.

Запуск:
    python scripts/test_download_package.py
"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = BACKEND_ROOT.parent / "templates" / "docx" / "_DOWNLOADED_test_package.zip"


def main():
    base_url = "http://localhost:8000"

    # 1. Логинимся
    print("1. Login...")
    resp = httpx.post(
        f"{base_url}/api/auth/login",
        json={"email": "admin@visa-kit.local"},
    )
    if resp.status_code != 200:
        print(f"[ERROR] Login failed: {resp.status_code} {resp.text}")
        return 1
    token = resp.json()["access_token"]
    print("   [OK] Got token")

    # 2. Находим application 2026-TEST
    print("2. Finding test application...")
    resp = httpx.get(
        f"{base_url}/api/admin/applications",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        print(f"[ERROR] List failed: {resp.status_code} {resp.text}")
        return 1
    apps = resp.json()
    test_app = next((a for a in apps if a.get("reference") == "2026-TEST"), None)
    if not test_app:
        print("[ERROR] No test application 2026-TEST. Run scripts/render_test_full_package.py first.")
        return 1
    app_id = test_app["id"]
    print(f"   [OK] Test application id={app_id}")

    # 3. Скачиваем пакет
    print("3. Rendering package...")
    resp = httpx.post(
        f"{base_url}/api/admin/applications/{app_id}/render-package",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"[ERROR] Render failed: {resp.status_code}")
        print(f"        Body: {resp.text}")
        return 1

    OUTPUT_PATH.write_bytes(resp.content)
    print(f"   [OK] ZIP saved: {OUTPUT_PATH}")
    print(f"        Size: {len(resp.content):,} bytes")

    status = resp.headers.get("x-render-status", "")
    if status:
        print(f"   Render status:")
        for entry in status.split(","):
            print(f"     {entry}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
