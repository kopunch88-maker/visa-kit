"""
Pack 25.11 — обратный фикс period_end.

В Pack 25.8 было: period_end = statement_date - 1 день
В Pack 25.9 переделали на: period_end = statement_date
Команда сказала: правильно как в 25.8 (выписка за период минус 1 день от даты выдачи).

Возвращаем 25.8-логику, но с актуальными комментариями.

Запуск:
    cd D:\\VISA\\visa_kit\\backend
    python apply_pack25_11.py
"""
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GEN_PATH = ROOT / "app" / "services" / "bank_statement_generator.py"

if not GEN_PATH.exists():
    print(f"ERROR: {GEN_PATH} not found.")
    sys.exit(1)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = GEN_PATH.with_name(GEN_PATH.name + f".bak_pre_pack25_11_{ts}")
shutil.copy2(GEN_PATH, backup)
print(f"[1/2] Бэкап: {backup.name}")

text = GEN_PATH.read_text(encoding="utf-8")

old_block = '''    # Pack 25.9: period_end = statement_date (включая день формирования).
    # Реальные банки: «выписка с 27.01 по 27.04, дата формирования 27.04».
    period_end = statement_date
    period_start = (statement_date - relativedelta(months=period_months))'''

new_block = '''    # Pack 25.11: period_end = statement_date - 1 день (как реально делают банки).
    # Пример: дата формирования 06.05 → период 06.02..05.05 (3 мес минус 1 день).
    period_end = statement_date - timedelta(days=1)
    period_start = (statement_date - relativedelta(months=period_months))'''

if old_block in text:
    text = text.replace(old_block, new_block)
    GEN_PATH.write_text(text, encoding="utf-8")
    print(f"[2/2] period_end изменён на statement_date - 1 день")
else:
    print(f"[2/2] [!] WARN: блок Pack 25.9 period_end не найден.")
    print(f"        Возможно файл уже изменён. Проверь руками около строки с 'period_end ='")
    sys.exit(1)

# Sanity
try:
    ast.parse(GEN_PATH.read_text(encoding="utf-8"))
    print("\n[OK] синтаксис валиден")
except SyntaxError as e:
    print(f"\n[FAIL] {e}")
    print(f"Откат: Copy-Item -Force '{backup}' '{GEN_PATH}'")
    sys.exit(1)

print("\n=== Pack 25.11 применён ===\n")
print("Дальше:")
print("  1. Сбрось override у заявок (там сохранены старые данные с period_end=statement_date):")
print('     python -c "from sqlalchemy import text; from app.db.session import engine; conn = engine.connect(); r = conn.execute(text(\\"UPDATE application SET bank_transactions_override = NULL\\")); conn.commit(); print(f\\"cleared {r.rowcount}\\"); conn.close()"')
print()
print("  2. Пуш:")
print("     git add app/services/bank_statement_generator.py")
print("     git commit -m 'Pack 25.11: period_end = statement_date - 1 day (банковская конвенция)'")
print("     git push")
print()
print("  3. После Railway-деплоя нажми в админке у Vedat «Перегенерировать выписку».")
print("     Должно быть: дата формирования = today-7..10, период = -3мес от даты до даты-1.")
print()
print(f"Откат: Copy-Item -Force '{backup}' '{GEN_PATH}'")
