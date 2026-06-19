"""
Apply-скрипт: вставляет anti-stale guard в _build_director_subs
(backend/app/services/translation/name_substitution.py).
Идемпотентный, с .bak бэкапом и py_compile-проверкой.

Кладётся в КОРЕНЬ репо (корень репо). Запуск:
    python apply_guard_director_latin.py
"""
import os
import py_compile

_ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(_ROOT, "backend", "app", "services",
                      "translation", "name_substitution.py")

OLD = (
    '    full_latin = _safe(getattr(company, "director_full_name_latin", None))\n'
    '    if not full_latin:\n'
    '        full_latin = _gost_director_full(full_ru)\n'
)

NEW = (
    '    full_latin = _safe(getattr(company, "director_full_name_latin", None))\n'
    '\n'
    '    # Anti-stale guard (инцидент "Морозов -> Nikitin"): если latin-поле\n'
    '    # указывает на ДРУГОГО человека (фамилия не совпадает с транслитом ru) —\n'
    '    # не доверяем ему, транслитерируем ru на лету. Иначе подпись в ES молча\n'
    '    # подменяется. См. _gost_director_full ниже.\n'
    '    gost_latin = _gost_director_full(full_ru)\n'
    '    if full_latin and gost_latin:\n'
    '        ru_init = gost_latin.split()[0][:1].upper() if gost_latin.split() else ""\n'
    '        lat_init = full_latin.split()[0][:1].upper() if full_latin.split() else ""\n'
    '        if ru_init and lat_init and ru_init != lat_init:\n'
    '            log.warning(\n'
    '                "[name_sub] Company %s: director_full_name_latin (%r) ne sovpadaet "\n'
    '                "po familii s director_full_name_ru (%r) — ignoriruyu latin, beru GOST. "\n'
    '                "Proverte kartochku kompanii.",\n'
    '                getattr(company, "id", "?"), full_latin, full_ru,\n'
    '            )\n'
    '            full_latin = ""\n'
    '\n'
    '    if not full_latin:\n'
    '        full_latin = gost_latin\n'
)

MARKER = "Anti-stale guard"

if not os.path.exists(TARGET):
    raise SystemExit(f"Не найден файл: {TARGET}")

data = open(TARGET, "rb").read().decode("utf-8")
eol = "\r\n" if "\r\n" in data else "\n"
norm = data.replace("\r\n", "\n")

if MARKER in norm:
    print("Уже пропатчено (guard на месте) — пропускаю.")
elif OLD not in norm:
    raise SystemExit(
        "Старый блок не найден (другой отступ/уже изменён). "
        "Патчить вручную в _build_director_subs."
    )
else:
    with open(TARGET + ".bak", "wb") as f:
        f.write(data.encode("utf-8"))
    out = norm.replace(OLD, NEW, 1).replace("\n", eol)
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))
    py_compile.compile(TARGET, doraise=True)
    print(f"OK: guard вставлен. Бэкап: {TARGET}.bak")
    print("py_compile: OK")
