"""
Pack 25.12 — DIPLOMA_MAIN всегда замещает applicant.education.

Раньше (by design): _auto_apply_ocr_to_applicant обновлял education ТОЛЬКО если оно
было пусто (`if not existing_edu`). Это защищало ручные правки менеджера, но мешало
случаю когда у клиента уже стояла сгенерированная "легенда" (Pack 19.0 ✨), а потом
загружался реальный диплом — диплом игнорировался.

Решение: реальный документ важнее легенды. DIPLOMA_MAIN всегда замещает education.

Файлы:
- backend/app/api/client_documents_admin.py (для админских загрузок)
- backend/app/api/client_portal.py (для самозагрузок клиента через клиентский кабинет)
- backend/app/api/import_package.py (для bulk import — оставляем как есть, там менеджер
  явно нажал "import" и legend ещё не сгенерирован)

Запуск:
    cd D:\\VISA\\visa_kit\\backend
    python apply_pack25_12.py
"""
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADMIN_PATH = ROOT / "app" / "api" / "client_documents_admin.py"
PORTAL_PATH = ROOT / "app" / "api" / "client_portal.py"

for p in (ADMIN_PATH, PORTAL_PATH):
    if not p.exists():
        print(f"ERROR: {p} not found.")
        sys.exit(1)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
admin_backup = ADMIN_PATH.with_name(ADMIN_PATH.name + f".bak_pre_pack25_12_{ts}")
portal_backup = PORTAL_PATH.with_name(PORTAL_PATH.name + f".bak_pre_pack25_12_{ts}")
shutil.copy2(ADMIN_PATH, admin_backup)
shutil.copy2(PORTAL_PATH, portal_backup)
print(f"[1/3] Бэкапы:")
print(f"      {admin_backup.name}")
print(f"      {portal_backup.name}")

patches = 0

# === 2. Patch client_documents_admin.py ===
admin_text = ADMIN_PATH.read_text(encoding="utf-8")

old_admin = '''        # Education
        edu_record = _build_education_from_diploma(session, application_id)
        if edu_record:
            existing_edu = (existing.education if existing else []) or []
            if not existing_edu:
                update_data["education"] = [edu_record]'''

new_admin = '''        # Education — Pack 25.12: DIPLOMA_MAIN всегда замещает education
        # (реальный документ важнее легенды Pack 19.0)
        edu_record = _build_education_from_diploma(session, application_id)
        if edu_record:
            update_data["education"] = [edu_record]'''

if old_admin in admin_text:
    admin_text = admin_text.replace(old_admin, new_admin)
    ADMIN_PATH.write_text(admin_text, encoding="utf-8")
    patches += 1
    print(f"[2/3] client_documents_admin.py: education replace применён")
else:
    print(f"[2/3] [!] WARN: блок не найден в client_documents_admin.py")


# === 3. Patch client_portal.py ===
# В client_portal есть ДВА места применения education (auto + manual apply).
# Оба должны замещать. Покажем содержимое чтобы понять.
portal_text = PORTAL_PATH.read_text(encoding="utf-8")

# Ищем все варианты
import re
# Найдём паттерн похожий на existing_edu logic
patterns_tried = [
    # Variant 1
    '''        if edu_record:
            existing_edu = (applicant.education if applicant else []) or []
            if not existing_edu:
                update_data["education"] = [edu_record]''',
    # Variant 2
    '''            if not existing_edu:
                update_data["education"] = [edu_record]''',
]

# Точное содержимое не знаем — поэтому используем regex для поиска
pattern = re.compile(
    r'(if edu_record:\s*\n'
    r'(?:[ \t]+[^\n]*\n)*?'  # любые отступленные строки
    r'[ \t]+if not existing_edu:\s*\n'
    r'[ \t]+update_data\["education"\]\s*=\s*\[edu_record\])',
    re.MULTILINE
)

matches = pattern.findall(portal_text)
print(f"[3/3] client_portal.py: найдено {len(matches)} мест с 'if not existing_edu'")

if matches:
    for m in matches:
        # Заменим всё что между `if edu_record:` и `update_data[...] = [edu_record]`
        # на простую безусловную форму
        replacement = '''if edu_record:
            update_data["education"] = [edu_record]'''
        portal_text = portal_text.replace(m, replacement)
        patches += 1
    PORTAL_PATH.write_text(portal_text, encoding="utf-8")
    print(f"      Заменено {len(matches)} мест → education всегда замещается")
else:
    print(f"      [!] WARN: паттерн не найден. Возможно отступы или структура другая.")
    print(f"      Проверь руками client_portal.py около строк 666 и 750:")
    print(f"        edu_record = _build_education_from_diploma(docs)")
    print(f"      Замени блок 'if not existing_edu' на безусловное присваивание.")


# === Финальная проверка синтаксиса ===
errors = []
for p in (ADMIN_PATH, PORTAL_PATH):
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errors.append(f"{p.name}: {e}")

if errors:
    print(f"\n[FAIL] синтаксические ошибки:")
    for e in errors:
        print(f"  - {e}")
    print(f"\nОткат:")
    print(f"  Copy-Item -Force '{admin_backup}' '{ADMIN_PATH}'")
    print(f"  Copy-Item -Force '{portal_backup}' '{PORTAL_PATH}'")
    sys.exit(1)

print(f"\n[OK] оба файла валидны")
print(f"\n=== Pack 25.12 применён ({patches} патчей) ===\n")
print("Дальше:")
print("  cd D:\\VISA\\visa_kit")
print("  git add backend/app/api/client_documents_admin.py backend/app/api/client_portal.py")
print("  git status   # проверить что только эти файлы")
print("  git commit -m 'Pack 25.12: DIPLOMA_MAIN always replaces applicant.education'")
print("  git push")
print()
print("После Railway-деплоя — тест:")
print("  1. У клиента стоит легенда (Pack 19.0 ✨)")
print("  2. Загружаешь диплом → OCR_DONE → auto-apply")
print("  3. applicant.education должен СТАТЬ из диплома (не остаться легендой)")
print()
print(f"Откат:")
print(f"  Copy-Item -Force '{admin_backup}' '{ADMIN_PATH}'")
print(f"  Copy-Item -Force '{portal_backup}' '{PORTAL_PATH}'")
