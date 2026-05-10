"""
Pack 25.10 finisher — пробрасывает application в ApplicantDrawer.

Запуск:
    cd D:\\VISA\\visa_kit
    python apply_pack25_10_finish.py
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT_CANDIDATES = [Path.cwd() / "frontend", Path.cwd().parent / "frontend", Path.cwd()]
FRONTEND = None
for c in ROOT_CANDIDATES:
    if (c / "components" / "admin" / "ApplicationDetail.tsx").exists():
        FRONTEND = c
        break

if FRONTEND is None:
    print("ERROR: frontend/ не найден. Запускай из visa_kit/")
    sys.exit(1)

DETAIL = FRONTEND / "components" / "admin" / "ApplicationDetail.tsx"

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = DETAIL.with_name(DETAIL.name + f".bak_pre_pack25_10_finish_{ts}")
shutil.copy2(DETAIL, backup)
print(f"[1/2] Бэкап: {backup.name}")

text = DETAIL.read_text(encoding="utf-8")

old = '''        <ApplicantDrawer
          applicant={applicant}
          onClose={() => setShowApplicantDrawer(false)}
          onSaved={() => {
            setShowApplicantDrawer(false);
            loadAll();'''

new = '''        <ApplicantDrawer
          applicant={applicant}
          application={application}
          onApplicationSaved={loadAll}
          onClose={() => setShowApplicantDrawer(false)}
          onSaved={() => {
            setShowApplicantDrawer(false);
            loadAll();'''

if old in text:
    text = text.replace(old, new)
    DETAIL.write_text(text, encoding="utf-8")
    print(f"[2/2] ApplicationDetail.tsx: application + onApplicationSaved прокинуты")
else:
    print(f"[2/2] [!] WARN: блок не найден. Возможно отступы другие.")
    print(f"        Открой ApplicationDetail.tsx около L359 и добавь руками:")
    print(f"          application={{application}}")
    print(f"          onApplicationSaved={{loadAll}}")
    sys.exit(1)

print("\n=== Pack 25.10 finisher применён ===")
print("\nТеперь пуш:")
print("  cd D:\\VISA\\visa_kit")
print("  git add frontend/lib/api.ts frontend/components/admin/ApplicantDrawer.tsx frontend/components/admin/ApplicationDetail.tsx")
print("  git status   # ← убедись что только эти 3 файла")
print("  git commit -m 'Pack 25.10: bank statement date picker + regenerate button in ApplicantDrawer'")
print("  git push")
print(f"\nОткат:")
print(f"  Copy-Item -Force '{backup}' '{DETAIL}'")
