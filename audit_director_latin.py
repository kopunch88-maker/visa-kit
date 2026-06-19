"""
READ-ONLY аудит рассинхрона director_full_name_ru <-> director_full_name_latin.
Ничего не меняет в БД. Печатает таблицу и пишет CSV рядом.

Кладётся в КОРЕНЬ репо (корень репо). Запуск:
    python audit_director_latin.py
"""
import os
import sys

# --- чтобы работало из корня репо: backend на путь + .env ---
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, "backend", ".env"))
except Exception:
    pass

import csv
from sqlmodel import Session, select

from app.db.session import engine
from app.models import Company
from app.services.transliteration import transliterate_name


def norm(s) -> str:
    return " ".join((s or "").strip().split())


def first_initial(s) -> str:
    s = norm(s)
    return s[0].upper() if s else ""


rows = []
with Session(engine) as session:
    for c in session.exec(select(Company)).all():
        ru = norm(getattr(c, "director_full_name_ru", "") or "")
        if not ru:
            continue
        lat = norm(getattr(c, "director_full_name_latin", "") or "")
        gost = norm(transliterate_name(ru))

        if not lat:
            flag = "EMPTY (на лету уйдёт в GOST — ок)"
        elif lat.lower() == gost.lower():
            flag = "OK"
        elif first_initial(gost) and first_initial(lat) and first_initial(gost) != first_initial(lat):
            flag = ">>> SUSPECT: ДРУГАЯ ФАМИЛИЯ <<<"
        else:
            flag = "DIFFERS (возможно паспортное написание — глазами)"

        name = norm(getattr(c, "short_name", "") or getattr(c, "full_name_ru", "") or "")
        rows.append((c.id, name, ru, lat, gost, flag))

rows.sort(key=lambda r: ("SUSPECT" not in r[5], r[0]))
print(f"{'id':>5}  {'director_ru':<30} {'latin (в БД)':<30} {'GOST(ru)':<30} flag")
for r in rows:
    print(f"{r[0]:>5}  {r[2]:<30} {r[3]:<30} {r[4]:<30} {r[5]}")

with open("director_latin_audit.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["company_id", "company", "director_full_name_ru",
                "director_full_name_latin_db", "gost_translit_of_ru", "flag"])
    w.writerows(rows)

suspects = [r for r in rows if "SUSPECT" in r[5]]
print(f"\nВсего компаний с директором: {len(rows)}")
print(f"SUSPECT (latin — другой человек): {len(suspects)}")
print("CSV: director_latin_audit.csv")
