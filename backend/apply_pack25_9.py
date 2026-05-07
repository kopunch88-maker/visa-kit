"""
Pack 25.9 — гибрид: ручной override даты формирования через application.bank_statement_date.

Что делает:
1. Бэкап bank_statement_generator.py + context.py.
2. Заменяет bank_statement_generator.py.new (period_end = statement_date, без -1).
3. Патч в context.py:
   - Добавляет передачу application.bank_statement_date в generate_default_transactions
     как statement_date_override.
   - Удаляет legacy override через bank_period_start/end (период теперь полностью
     контролируется датой формирования).
4. Patch модели Application — добавить поле bank_statement_date.

Не делает (запускай отдельно):
- Миграция БД: python -m app.scripts.migration_pack25_9
- Frontend: см. инструкцию в конце вывода

Запуск:
    cd D:\\VISA\\visa_kit\\backend
    python apply_pack25_9.py
"""
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GEN_PATH = ROOT / "app" / "services" / "bank_statement_generator.py"
GEN_NEW = ROOT / "bank_statement_generator.py.new"
CTX_PATH = ROOT / "app" / "templates_engine" / "context.py"
MODEL_PATH = ROOT / "app" / "models" / "application.py"

for p in (GEN_PATH, GEN_NEW, CTX_PATH, MODEL_PATH):
    if not p.exists():
        print(f"ERROR: {p} not found.")
        sys.exit(1)


# === 1. Бэкап ===
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
gen_backup = GEN_PATH.with_name(GEN_PATH.name + f".bak_pre_pack25_9_{ts}")
ctx_backup = CTX_PATH.with_name(CTX_PATH.name + f".bak_pre_pack25_9_{ts}")
model_backup = MODEL_PATH.with_name(MODEL_PATH.name + f".bak_pre_pack25_9_{ts}")
shutil.copy2(GEN_PATH, gen_backup)
shutil.copy2(CTX_PATH, ctx_backup)
shutil.copy2(MODEL_PATH, model_backup)
print(f"[1/5] Бэкапы:")
print(f"      {gen_backup.name}")
print(f"      {ctx_backup.name}")
print(f"      {model_backup.name}")


# === 2. Замена generator ===
new_gen_content = GEN_NEW.read_text(encoding="utf-8")
try:
    ast.parse(new_gen_content)
except SyntaxError as e:
    print(f"\n[FAIL] {GEN_NEW.name}: invalid Python: {e}")
    sys.exit(1)
GEN_PATH.write_text(new_gen_content, encoding="utf-8")
print(f"[2/5] bank_statement_generator.py: {len(new_gen_content)} байт")


# === 3. Patch context.py ===
ctx_text = CTX_PATH.read_text(encoding="utf-8")

# 3a. Добавить statement_date_override в вызов
old_call = '''    result = generate_default_transactions(
        submission_date=base_date,
        salary_rub=application.salary_rub,
        contract_number=application.contract_number or "",
        contract_sign_date=application.contract_sign_date,
        company_full_name=company.full_name_ru,
        company_inn=company.tax_id_primary,
        company_bank_account=company.bank_account,
        company_bank_bic=company.bank_bic,
        npd_rate=npd_rate,
        bank_fee=monthly_fee,
        seed=application.id or 0,
        applicant_full_name_ru=_applicant_full_name_ru,
        applicant_phone=_applicant_phone,
    )'''

new_call = '''    result = generate_default_transactions(
        submission_date=base_date,
        salary_rub=application.salary_rub,
        contract_number=application.contract_number or "",
        contract_sign_date=application.contract_sign_date,
        company_full_name=company.full_name_ru,
        company_inn=company.tax_id_primary,
        company_bank_account=company.bank_account,
        company_bank_bic=company.bank_bic,
        npd_rate=npd_rate,
        bank_fee=monthly_fee,
        seed=application.id or 0,
        applicant_full_name_ru=_applicant_full_name_ru,
        applicant_phone=_applicant_phone,
        # Pack 25.9: ручной override даты формирования (если задан в админке)
        statement_date_override=getattr(application, "bank_statement_date", None),
    )'''

if old_call in ctx_text:
    ctx_text = ctx_text.replace(old_call, new_call)
    print(f"[3/5a] context.py: statement_date_override добавлен в вызов")
else:
    print(f"[3/5a] [!] WARN: вызов не найден или уже изменён")


# 3b. Убрать legacy override через bank_period_start/end
# (период теперь полностью контролируется через bank_statement_date)
old_legacy = '''    if application.bank_period_start:
        result["period_start"] = application.bank_period_start
    if application.bank_period_end:
        result["period_end"] = application.bank_period_end'''

new_legacy = '''    # Pack 25.9: legacy bank_period_start/end больше не override-ят период.
    # Период теперь определяется через application.bank_statement_date (см. вызов выше).
    # if application.bank_period_start:
    #     result["period_start"] = application.bank_period_start
    # if application.bank_period_end:
    #     result["period_end"] = application.bank_period_end'''

if old_legacy in ctx_text:
    ctx_text = ctx_text.replace(old_legacy, new_legacy)
    print(f"[3/5b] context.py: legacy bank_period_start/end закомментирован")
else:
    print(f"[3/5b] [!] WARN: legacy блок не найден")

CTX_PATH.write_text(ctx_text, encoding="utf-8")


# === 4. Patch модели Application — добавить bank_statement_date ===
model_text = MODEL_PATH.read_text(encoding="utf-8")

# Ищем строку с bank_period_start и добавляем bank_statement_date перед ней
old_model = '    bank_period_start: Optional[date] = None'
new_model = '''    # Pack 25.9: ручной override даты формирования банковской выписки.
    # Если NULL — генератор берёт today - random(7..10).
    # Если задано — генератор использует эту дату как statement_date,
    # период считается как [statement_date - 3мес, statement_date].
    bank_statement_date: Optional[date] = None
    bank_period_start: Optional[date] = None'''

if "bank_statement_date" in model_text:
    print(f"[4/5] модель Application: bank_statement_date уже есть — пропускаем")
elif old_model in model_text:
    model_text = model_text.replace(old_model, new_model)
    MODEL_PATH.write_text(model_text, encoding="utf-8")
    print(f"[4/5] модель Application: bank_statement_date добавлен")
else:
    print(f"[4/5] [!] WARN: место для bank_statement_date не найдено. Проверь модель руками.")


# === 5. Финальная проверка синтаксиса ===
errors = []
for path in (GEN_PATH, CTX_PATH, MODEL_PATH):
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errors.append(f"{path.name}: {e}")

if errors:
    print(f"\n[FAIL] Синтаксические ошибки:")
    for e in errors:
        print(f"  - {e}")
    print(f"\nОткат:")
    print(f"  Copy-Item -Force '{gen_backup}' '{GEN_PATH}'")
    print(f"  Copy-Item -Force '{ctx_backup}' '{CTX_PATH}'")
    print(f"  Copy-Item -Force '{model_backup}' '{MODEL_PATH}'")
    sys.exit(1)

print(f"[5/5] Синтаксис всех 3 файлов: OK")


print("\n=== Pack 25.9 backend применён ===\n")
print("СЛЕДУЮЩИЕ ШАГИ:")
print()
print("1. Применить миграцию БД:")
print('   $env:DATABASE_URL = "postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"')
print('   $env:PYTHONIOENCODING = "utf-8"')
print("   python -m app.scripts.migration_pack25_9")
print()
print("2. Сбросить старые bank_period_start/end у Vedat (legacy данные мешают):")
print('   $env:DATABASE_URL = "postgresql://..."')
print('   psql $env:DATABASE_URL -c "UPDATE application SET bank_period_start = NULL, bank_period_end = NULL WHERE bank_period_start IS NOT NULL;"')
print("   (или через админку)")
print()
print("3. Перезапусти backend, протестируй на Vedat — должно показать:")
print("   - дата формирования: today - 7..10 дней")
print("   - период: 3 месяца до даты формирования (включая её)")
print()
print("4. Frontend (отдельно): добавить date-picker bank_statement_date в Drawer заявки.")
print("   Поиск файла Drawer:")
print('   Get-ChildItem -Recurse -Path "D:\\VISA\\visa_kit" -Include "*.tsx" |')
print('     Select-String -Pattern "bank_period_start|bank_period_end" -List |')
print('     ForEach-Object { $_.Path }')
print("   Скинь мне путь — выкачу tsx-патч.")
print()
print(f"Откат:")
print(f"  Copy-Item -Force '{gen_backup}' '{GEN_PATH}'")
print(f"  Copy-Item -Force '{ctx_backup}' '{CTX_PATH}'")
print(f"  Copy-Item -Force '{model_backup}' '{MODEL_PATH}'")
