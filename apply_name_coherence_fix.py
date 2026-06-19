#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 59 — когерентность имени заявителя в переводе расчётных листков.

Проблема: в ES-переводе листков имя выходило как решит LLM (SERGEY SERGEYEVICH),
а в формах — паспортное (SERGEI). Причина: листок рендерит ФИО ЗАГЛАВНЫМИ
кириллицей, а SubstitutionDict.apply регистрозависим -> пары имени не матчатся
-> имя романизирует LLM. Плюс отчества нет в парах (на паспорте его нет).

Правки в backend/app/services/translation/name_substitution.py (_build_applicant_subs):
  1) отчество добирается детерминированным GOST (UPPER, как фамилия/имя в паспорте);
  2) к каждой паре добавляется UPPER-вариант (латиница тоже UPPER).

Идемпотентно, .bak59, pre-write py_compile, CRLF-aware (Правило 71).
"""
import os, sys, py_compile, tempfile

REL = os.path.join("backend", "app", "services", "translation", "name_substitution.py")
MARKER = "middle_latin = transliterate_name(middle_native)"

ANCHOR1 = (
    "    # \u041b\u0430\u0442\u0438\u043d\u0441\u043a\u0438\u0435 \u0444\u043e\u0440\u043c\u044b\n"
    "    full_latin_parts = [last_latin, first_latin]"
)
INSERT1 = (
    "    # Pack 59: \u043e\u0442\u0447\u0435\u0441\u0442\u0432\u043e \u043d\u0430 "
    "\u0437\u0430\u0433\u0440\u0430\u043d\u043f\u0430\u0441\u043f\u043e\u0440\u0442\u0435 "
    "\u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 -> middle_name_latin \u043e\u0431\u044b\u0447\u043d\u043e\n"
    "    # \u043f\u0443\u0441\u0442, \u0442\u043e\u0433\u0434\u0430 \u043e\u0442\u0447\u0435\u0441\u0442\u0432\u043e "
    "\u0440\u043e\u043c\u0430\u043d\u0438\u0437\u0438\u0440\u0443\u0435\u0442 LLM (SERGEYEVICH).\n"
    "    # \u0411\u0435\u0440\u0451\u043c \u0434\u0435\u0442\u0435\u0440\u043c\u0438\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 "
    "GOST-\u0442\u0440\u0430\u043d\u0441\u043b\u0438\u0442 (UPPER, \u043a\u0430\u043a \u0432 \u043f\u0430\u0441\u043f\u043e\u0440\u0442\u0435).\n"
    "    if not middle_latin and middle_native:\n"
    "        middle_latin = transliterate_name(middle_native).upper()\n"
    "\n"
    "    # \u041b\u0430\u0442\u0438\u043d\u0441\u043a\u0438\u0435 \u0444\u043e\u0440\u043c\u044b\n"
    "    full_latin_parts = [last_latin, first_latin]"
)

ANCHOR2 = (
    '        pairs.append((f"{first_latin} {last_native[0]}.", f"{first_latin} {last_latin[0]}."))\n'
    "\n"
    "    return pairs"
)
INSERT2 = (
    '        pairs.append((f"{first_latin} {last_native[0]}.", f"{first_latin} {last_latin[0]}."))\n'
    "\n"
    "    # Pack 59: UPPER-\u0432\u0430\u0440\u0438\u0430\u043d\u0442\u044b \u043f\u0430\u0440 \u0438\u043c\u0435\u043d\u0438 "
    "(\u043b\u0438\u0441\u0442\u043a\u0438 \u0440\u0435\u043d\u0434\u0435\u0440\u044f\u0442 \u0424\u0418\u041e \u0417\u0410\u0413\u041b\u0410\u0412\u041d\u042b\u041c\u0418 "
    "\u043a\u0438\u0440\u0438\u043b\u043b\u0438\u0446\u0435\u0439,\n"
    "    # \u0430 apply() \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u043e\u0437\u0430\u0432\u0438\u0441\u0438\u043c). "
    "\u041b\u0430\u0442\u0438\u043d\u0438\u0446\u0430 \u0442\u043e\u0436\u0435 UPPER, \u043a\u0430\u043a \u0432 \u043f\u0430\u0441\u043f\u043e\u0440\u0442\u0435.\n"
    "    upper_pairs: list[tuple[str, str]] = []\n"
    "    for _ru, _lat in pairs:\n"
    "        _ru_up, _lat_up = _ru.upper(), _lat.upper()\n"
    "        if _ru_up != _ru:\n"
    "            upper_pairs.append((_ru_up, _lat_up))\n"
    "    pairs.extend(upper_pairs)\n"
    "\n"
    "    return pairs"
)


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(root, REL)
    if not os.path.exists(path):
        print("!!! \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d:", path); sys.exit(1)

    raw = open(path, "rb").read()
    crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")

    if MARKER in norm:
        print("[SKIP] \u0443\u0436\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u043e (Pack 59)."); return

    for i, anchor in enumerate((ANCHOR1, ANCHOR2), 1):
        c = norm.count(anchor)
        if c != 1:
            print(f"!!! \u044f\u043a\u043e\u0440\u044c {i} \u043d\u0430\u0439\u0434\u0435\u043d {c} \u0440\u0430\u0437 (\u043d\u0443\u0436\u043d\u043e 1). \u0421\u0442\u043e\u043f, \u0444\u0430\u0439\u043b \u043d\u0435 \u0442\u0440\u043e\u043d\u0443\u0442.")
            sys.exit(2)

    new = norm.replace(ANCHOR1, INSERT1, 1).replace(ANCHOR2, INSERT2, 1)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(new); tmp = tf.name
    try:
        py_compile.compile(tmp, doraise=True)
    finally:
        ok = True
        try:
            py_compile.compile(tmp, doraise=True)
        except py_compile.PyCompileError as e:
            ok = False; print("!!! py_compile FAIL \u2014 \u0444\u0430\u0439\u043b \u041d\u0415 \u0442\u0440\u043e\u043d\u0443\u0442:\n", e)
        os.unlink(tmp)
        if not ok:
            sys.exit(3)

    open(path + ".bak59", "wb").write(raw)
    out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
    open(path, "wb").write(out)
    print("OK: name_substitution.py \u043f\u0440\u043e\u043f\u0430\u0442\u0447\u0435\u043d. \u0411\u044d\u043a\u0430\u043f -> name_substitution.py.bak59")
    print("    py_compile: OK; CRLF:", crlf)


if __name__ == "__main__":
    main()
