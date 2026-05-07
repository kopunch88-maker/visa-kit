"""
Pack 25.9.1 — фикс имени клиента в СБП-переводах.

Проблема: applicant.full_name_ru не существует в модели/БД.
Реальные поля: last_name_native, first_name_native, middle_name_native.
Из-за этого в СБП-переводах всегда срабатывал fallback "Получатель".

Фикс: собираем full_name_ru из first_name_native + last_name_native.
"""
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CTX_PATH = ROOT / "app" / "templates_engine" / "context.py"

if not CTX_PATH.exists():
    print(f"ERROR: {CTX_PATH} not found.")
    sys.exit(1)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = CTX_PATH.with_name(CTX_PATH.name + f".bak_pre_pack25_9_1_{ts}")
shutil.copy2(CTX_PATH, backup)
print(f"[1/2] Бэкап: {backup.name}")

ctx_text = CTX_PATH.read_text(encoding="utf-8")

# Старый блок с неправильным резолвом
old_block = '''    # Pack 25.8: applicant нужен для СБП-переводов (имя получателя + телефон РФ)
    _applicant = getattr(application, "applicant", None)
    _applicant_full_name_ru = getattr(_applicant, "full_name_ru", None) if _applicant else None
    _applicant_phone = getattr(_applicant, "phone", None) if _applicant else None'''

# Новый — собираем имя из реальных полей модели
new_block = '''    # Pack 25.9.1: applicant нужен для СБП-переводов (имя получателя + телефон РФ).
    # Реальные поля: first_name_native + last_name_native (full_name_ru НЕ существует).
    _applicant = getattr(application, "applicant", None)
    _applicant_full_name_ru = None
    _applicant_phone = None
    if _applicant is not None:
        _first = getattr(_applicant, "first_name_native", None) or ""
        _last = getattr(_applicant, "last_name_native", None) or ""
        _full = f"{_first} {_last}".strip()
        _applicant_full_name_ru = _full or None
        _applicant_phone = getattr(_applicant, "phone", None)'''

if old_block in ctx_text:
    ctx_text = ctx_text.replace(old_block, new_block)
    CTX_PATH.write_text(ctx_text, encoding="utf-8")
    print(f"[2/2] context.py: applicant name resolution исправлен")
else:
    print(f"[2/2] [!] WARN: старый блок не найден — возможно, уже изменён")
    print(f"        Открой context.py около строк 928-931 и проверь руками")
    sys.exit(1)

# Проверка синтаксиса
try:
    ast.parse(CTX_PATH.read_text(encoding="utf-8"))
    print("\n[OK] context.py: синтаксис валиден")
except SyntaxError as e:
    print(f"\n[FAIL] {e}")
    print(f"Откат: Copy-Item -Force '{backup}' '{CTX_PATH}'")
    sys.exit(1)

print("\n=== Pack 25.9.1 применён ===\n")
print("Дальше:")
print("  git add app/templates_engine/context.py")
print("  git commit -m 'Pack 25.9.1: fix applicant name in SBP transfers (use first/last_name_native)'")
print("  git push")
print("  → Railway деплой → проверка пакета на Vedat")
print()
print("Должно стать: 'Перевод по СБП. Получатель: Ведат Ю.'")
print()
print(f"Откат: Copy-Item -Force '{backup}' '{CTX_PATH}'")
