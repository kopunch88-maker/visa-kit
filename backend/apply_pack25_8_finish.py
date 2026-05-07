"""
Pack 25.8 finisher — два точечных патча в context.py:

1. Заменить блок statement_date на чтение из bank_data["statement_date"] (Pack 25.8).
2. Добавить applicant_full_name_ru / applicant_phone в вызов generate_default_transactions.

Запуск (из visa_kit/backend/):
    python apply_pack25_8_finish.py
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
backup = CTX_PATH.with_name(CTX_PATH.name + f".bak_pre_pack25_8_finish_{ts}")
shutil.copy2(CTX_PATH, backup)
print(f"[1/3] Бэкап: {backup.name}")

ctx_text = CTX_PATH.read_text(encoding="utf-8")
patches_applied = 0

# === Patch 1: statement_date block ===
old_block_1 = '''    # Дата формирования выписки: period_end + 1 день, иначе submission_date
    statement_date = None
    period_end = bank_data.get("period_end")
    if period_end:
        statement_date = period_end + timedelta(days=1)
    elif application.submission_date:
        statement_date = application.submission_date'''

new_block_1 = '''    # Pack 25.8: дата формирования берётся из генератора (today - random(7..10)).
    # Fallback на старую логику period_end+1, в крайнем случае - submission_date.
    statement_date = bank_data.get("statement_date")
    if not statement_date:
        period_end = bank_data.get("period_end")
        if period_end:
            statement_date = period_end + timedelta(days=1)
        elif application.submission_date:
            statement_date = application.submission_date'''

if old_block_1 in ctx_text:
    ctx_text = ctx_text.replace(old_block_1, new_block_1)
    patches_applied += 1
    print(f"[2/3a] Patch 1 (statement_date block): применён")
else:
    print(f"[2/3a] Patch 1: старый блок не найден — возможно, уже изменён")


# === Patch 2: добавить applicant_full_name_ru / applicant_phone в вызов ===
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
    )'''

# Найдём applicant — нужно понять как он называется в этой функции.
# Видим что в _build_bank_context функция начинается с application/company,
# applicant скорее всего достаётся через application.applicant. Безопасный вариант:
# использовать getattr на случай отсутствия атрибутов.

new_call = '''    # Pack 25.8: applicant нужен для СБП-переводов (имя получателя + телефон РФ)
    _applicant = getattr(application, "applicant", None)
    _applicant_full_name_ru = getattr(_applicant, "full_name_ru", None) if _applicant else None
    _applicant_phone = getattr(_applicant, "phone", None) if _applicant else None

    result = generate_default_transactions(
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

if old_call in ctx_text:
    ctx_text = ctx_text.replace(old_call, new_call)
    patches_applied += 1
    print(f"[2/3b] Patch 2 (generate_default_transactions call): применён")
else:
    print(f"[2/3b] Patch 2: вызов не найден или уже изменён")


CTX_PATH.write_text(ctx_text, encoding="utf-8")

# === Финальная проверка ===
try:
    ast.parse(CTX_PATH.read_text(encoding="utf-8"))
    print(f"[3/3] context.py: синтаксис валиден")
except SyntaxError as e:
    print(f"[FAIL] context.py: {e}")
    print(f"       Откат: Copy-Item -Force '{backup}' '{CTX_PATH}'")
    sys.exit(1)


print(f"\n=== Pack 25.8 finisher: {patches_applied}/2 патчей применено ===\n")

if patches_applied == 2:
    print("Всё готово. Перезапусти backend и тестируй на Vedat.")
    print()
    print("Если применение через application.applicant не работает (атрибут называется")
    print("иначе или подгружается отдельно через session.get(Applicant, ...)) - может быть")
    print("что _applicant_full_name_ru останется None, и СБП будет с 'Получатель'.")
    print("Дай знать - сделаю под твою архитектуру резолва.")
else:
    print("Один или оба патча не применились. Скинь актуальный участок context.py.")

print(f"\nОткат: Copy-Item -Force '{backup}' '{CTX_PATH}'")
