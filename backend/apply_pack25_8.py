"""
Pack 25.8 — починка банковской выписки.

Что делает:
1. Копирует bank_statement_generator.py.new -> app/services/bank_statement_generator.py
2. Точечно правит app/templates_engine/context.py:
   - statement_date теперь берётся из bank_data (Pack 25.8), а не считается как period_end+1
3. Подсказывает, как добавить applicant_full_name_ru/phone в вызов generate_default_transactions

Структура файлов перед запуском:
    visa_kit/backend/
        apply_pack25_8.py                              <- этот файл
        bank_statement_generator.py.new                <- новый генератор (положи рядом)
        app/services/bank_statement_generator.py       <- будет заменён
        app/templates_engine/context.py                <- будет пропатчен

Запуск (из visa_kit/backend/):
    python apply_pack25_8.py
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

if not GEN_NEW.exists():
    print(f"ERROR: {GEN_NEW} not found.")
    print("       Положи bank_statement_generator.py.new в backend/ рядом с apply_pack25_8.py")
    sys.exit(1)
if not GEN_PATH.exists():
    print(f"ERROR: {GEN_PATH} not found. Запускай из visa_kit/backend/")
    sys.exit(1)
if not CTX_PATH.exists():
    print(f"ERROR: {CTX_PATH} not found.")
    sys.exit(1)


# === 1. Бэкап ===
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
gen_backup = GEN_PATH.with_name(GEN_PATH.name + f".bak_pre_pack25_8_{ts}")
ctx_backup = CTX_PATH.with_name(CTX_PATH.name + f".bak_pre_pack25_8_{ts}")
shutil.copy2(GEN_PATH, gen_backup)
shutil.copy2(CTX_PATH, ctx_backup)
print(f"[1/4] Бэкапы:")
print(f"      {gen_backup.name}")
print(f"      {ctx_backup.name}")


# === 2. Замена generator ===
new_gen_content = GEN_NEW.read_text(encoding="utf-8")
try:
    ast.parse(new_gen_content)
except SyntaxError as e:
    print(f"\n[FAIL] {GEN_NEW.name}: invalid Python syntax: {e}")
    sys.exit(1)
GEN_PATH.write_text(new_gen_content, encoding="utf-8")
print(f"[2/4] bank_statement_generator.py: {len(new_gen_content)} байт записано")


# === 3. Патч context.py ===
ctx_text = CTX_PATH.read_text(encoding="utf-8")

old_block = '''    # Дата формирования выписки: period_end + 1 день, иначе submission_date
    statement_date = None
    period_end = bank_data.get("period_end")
    if period_end:
        statement_date = period_end + timedelta(days=1)
    else:
        statement_date = application.submission_date'''

new_block = '''    # Pack 25.8: дата формирования берётся из генератора (today - random(7..10)).
    # Fallback на старую логику period_end+1, в крайнем случае - submission_date.
    statement_date = bank_data.get("statement_date")
    if not statement_date:
        period_end = bank_data.get("period_end")
        if period_end:
            statement_date = period_end + timedelta(days=1)
        else:
            statement_date = application.submission_date'''

if old_block in ctx_text:
    ctx_text = ctx_text.replace(old_block, new_block)
    print(f"[3/4] context.py: фикс statement_date применён")
else:
    print(f"[3/4] [!] WARNING: старый блок statement_date не найден.")
    print(f"      Возможно, уже изменён. Проверь руками около строки 847.")


if "result = generate_default_transactions(" in ctx_text:
    if "applicant_full_name_ru=" not in ctx_text:
        print(f"\n[!] ВНИМАНИЕ: generate_default_transactions вызывается без applicant_full_name_ru.")
        print(f"    Открой context.py, найди 'result = generate_default_transactions(' и добавь:")
        print(f"        applicant_full_name_ru=applicant.full_name_ru,")
        print(f"        applicant_phone=applicant.phone,")
        print(f"    в список аргументов. БЕЗ ЭТОГО СБП-переводы будут с 'Получатель' вместо имени.")

CTX_PATH.write_text(ctx_text, encoding="utf-8")
print(f"[4/4] context.py сохранён")


# === Финальная проверка ===
try:
    ast.parse(CTX_PATH.read_text(encoding="utf-8"))
    print("\n[OK] context.py: синтаксис валиден")
except SyntaxError as e:
    print(f"\n[FAIL] context.py: {e}")
    sys.exit(1)
try:
    ast.parse(GEN_PATH.read_text(encoding="utf-8"))
    print("[OK] bank_statement_generator.py: синтаксис валиден")
except SyntaxError as e:
    print(f"[FAIL] bank_statement_generator.py: {e}")
    sys.exit(1)


print("\n=== Pack 25.8 применён успешно ===\n")
print("Следующие шаги:")
print("  1. (если ВНИМАНИЕ выше): добавь applicant_full_name_ru/phone в вызов")
print("  2. Перезапусти backend локально")
print("  3. Сгенерируй пакет для тестовой заявки (Vedat)")
print("  4. Открой 10_Выписка.docx в Microsoft Word (Правило 25!)")
print("  5. Проверь:")
print("     - Дата формирования = сегодня минус 7-10 дней")
print("     - Период = 3 месяца, заканчивается за день до даты формирования")
print("     - НИ ОДНОЙ транзакции после period_end")
print("     - СБП-переводы себе с РФ-номером")
print("     - Подписки (Яндекс Плюс, Литрес, IVI и т.п.)")
print("     - Суммы расходов с копейками")
print("  6. Если всё ок:")
print("     git add app/services/bank_statement_generator.py app/templates_engine/context.py")
print("     git commit -m 'Pack 25.8: bank statement period fix + СБП + подписки + копейки'")
print("     git push\n")
print("Откат:")
print(f"  Copy-Item -Force '{gen_backup}' '{GEN_PATH}'")
print(f"  Copy-Item -Force '{ctx_backup}' '{CTX_PATH}'")
