"""
Фикс рассинхрона director_full_name_latin. БЕЗОПАСНЫЙ:
  - по умолчанию DRY-RUN (ничего не пишет, только показывает план);
  - перед записью делает JSON-backup старых значений;
  - чинит ТОЛЬКО строки, где latin = ДРУГОЙ человек (другая фамилия) или пусто;
  - стилистические расхождения (та же фамилия, Sergei/Sergey) НЕ трогает,
    если не указан --include-differs.

Кладётся в КОРЕНЬ репо (корень репо). Бьёт по той базе, на которую
настроен backend/.env (DATABASE_URL). Запуск:
    python fix_director_latin.py                     # dry-run
    python fix_director_latin.py --apply             # записать (с backup)
    python fix_director_latin.py --apply --include-differs
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, "backend", ".env"))
except Exception:
    pass

import json
import datetime
from sqlmodel import Session, select

from app.db.session import engine
from app.models import Company
from app.services.transliteration import transliterate_name

APPLY = "--apply" in sys.argv
INCLUDE_DIFFERS = "--include-differs" in sys.argv


def norm(s) -> str:
    return " ".join((s or "").strip().split())


def first_initial(s) -> str:
    s = norm(s)
    return s[0].upper() if s else ""


planned = []
backup = []

with Session(engine) as session:
    for c in session.exec(select(Company)).all():
        ru = norm(getattr(c, "director_full_name_ru", "") or "")
        if not ru:
            continue
        gost = norm(transliterate_name(ru))
        if not gost:
            continue
        lat = norm(getattr(c, "director_full_name_latin", "") or "")

        diff_person = bool(lat) and first_initial(gost) and first_initial(lat) \
            and first_initial(gost) != first_initial(lat)
        empty = not lat
        differs = bool(lat) and lat.lower() != gost.lower() and not diff_person

        if not (empty or diff_person or (INCLUDE_DIFFERS and differs)) or lat == gost:
            continue

        reason = "EMPTY" if empty else ("SUSPECT" if diff_person else "DIFFERS")
        planned.append((c.id, reason, lat, gost))
        backup.append({
            "company_id": c.id,
            "old_director_full_name_latin": getattr(c, "director_full_name_latin", None),
        })
        if APPLY:
            c.director_full_name_latin = gost
            session.add(c)

    if APPLY and planned:
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = f"director_latin_backup_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)
        session.commit()
        print(f"BACKUP -> {path}")

print(f"{'id':>5}  {'reason':<8} {'latin было':<30} -> latin станет")
for pid, reason, old, new in planned:
    print(f"{pid:>5}  {reason:<8} {old:<30} -> {new}")
print(f"\nПод фикс попадает: {len(planned)}")
print("РЕЖИМ:", "APPLY (записано)" if APPLY else "DRY-RUN (не записано)")
if not APPLY:
    print("Применить: python fix_director_latin.py --apply")
