"""
Pack 26.0.1 — Фикс маппинга ИНН/КПП в CompanyImportDialog.

Проблема: backend возвращает поля с именами `inn` и `kpp` (как в EGRYL/реквизитах),
но в `CompanyResponse` они называются `tax_id_primary` и `tax_id_secondary`.

В CompanyImportDialog.tsx поля передаются в Drawer через setForm({...prev, ...fields}),
поэтому inn/kpp оказываются в форме под чужими именами и не попадают в правильные
input-поля «ИНН» и «КПП».

Решение: перед передачей в Drawer переименовать `inn` → `tax_id_primary`,
                                          `kpp` → `tax_id_secondary`.

Запуск:
    cd D:\\VISA\\visa_kit
    python apply_pack26_0_1.py
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT_CANDIDATES = [Path.cwd(), Path.cwd().parent]
ROOT = None
for c in ROOT_CANDIDATES:
    if (c / "frontend" / "components" / "admin" / "settings" / "CompanyImportDialog.tsx").exists():
        ROOT = c
        break

if ROOT is None:
    print("ERROR: visa_kit root not found.")
    sys.exit(1)

DIALOG = ROOT / "frontend" / "components" / "admin" / "settings" / "CompanyImportDialog.tsx"

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = DIALOG.with_name(DIALOG.name + f".bak_pre_pack26_0_1_{ts}")
shutil.copy2(DIALOG, backup)
print(f"[1/2] Бэкап: {backup.name}")

text = DIALOG.read_text(encoding="utf-8")

# Найти и заменить блок где fields передаются в onSelect.
# В нашем коде это два места:
#   onSelect({ type: "create_new", fields: result.fields });
#   onSelect({ type: "create_new", fields: conflict.fields });
#   onSelect({ type: "update_existing", companyId: conflict.existing_company_id!, fields: conflict.fields });

# Решение: добавить хелпер-функцию mapFieldsToCompany() в начало файла и использовать её.

helper = '''/**
 * Pack 26.0.1 — переименование полей backend-ответа в имена CompanyResponse.
 * Backend возвращает inn/kpp (как в реквизитах), но в схеме они tax_id_primary/secondary.
 */
function mapFieldsToCompany(
  raw: ExtractedCompanyFields["fields"]
): Record<string, string | null | undefined> {
  const { inn, kpp, ...rest } = raw;
  return {
    ...rest,
    tax_id_primary: inn,
    tax_id_secondary: kpp,
  };
}

'''

# Найти место для вставки helper'а — сразу перед компонентом
patches = 0

if "mapFieldsToCompany" in text:
    print(f"[2/2] mapFieldsToCompany уже есть — пропуск helper'а")
else:
    # Вставляем helper после type Action declaration и перед interface Props
    anchor = "interface Props {"
    if anchor in text:
        text = text.replace(anchor, helper + anchor, 1)
        patches += 1
        print(f"[2/2a] Helper mapFieldsToCompany добавлен")
    else:
        print(f"[2/2a] [!] WARN: anchor 'interface Props {{' не найден")

# Заменить 3 вызова onSelect — обернуть fields через mapFieldsToCompany.
# Используем поиск каждого паттерна.
replacements = [
    (
        'onSelect({ type: "create_new", fields: result.fields });',
        'onSelect({ type: "create_new", fields: mapFieldsToCompany(result.fields) as any });',
    ),
    (
        'onSelect({\n                    type: "update_existing",\n                    companyId: conflict.existing_company_id!,\n                    fields: conflict.fields,\n                  })',
        'onSelect({\n                    type: "update_existing",\n                    companyId: conflict.existing_company_id!,\n                    fields: mapFieldsToCompany(conflict.fields) as any,\n                  })',
    ),
    (
        'onSelect({ type: "create_new", fields: conflict.fields })',
        'onSelect({ type: "create_new", fields: mapFieldsToCompany(conflict.fields) as any })',
    ),
]

for old, new in replacements:
    if old in text:
        text = text.replace(old, new, 1)
        patches += 1
    else:
        print(f"[2/2] [!] WARN: одно из вхождений не найдено: '{old[:60]}...'")

DIALOG.write_text(text, encoding="utf-8")

print(f"\n=== Pack 26.0.1 применён ({patches} замен) ===")
print()
print("Дальше:")
print(f"  cd {ROOT}")
print("  git add frontend/components/admin/settings/CompanyImportDialog.tsx")
print("  git status")
print("  git commit -m 'Pack 26.0.1: map inn/kpp to tax_id_primary/secondary on import'")
print("  git push")
print()
print(f"Откат:")
print(f"  Copy-Item -Force '{backup}' '{DIALOG}'")
