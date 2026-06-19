#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 59.1 — то же, что Pack 59, но для имени ДИРЕКТОРА (_build_director_subs).

Добавляет UPPER-варианты пар директора: если его ФИО где-то рендерится
ЗАГЛАВНЫМИ кириллицей (как ФИО заявителя в расчётных листках), регистрозависимый
SubstitutionDict.apply иначе не сматчит пары и имя романизирует LLM.

Независим от Pack 59 (трогает только _build_director_subs). Идемпотентно,
.bak591, pre-write py_compile, CRLF-aware (Правило 71).
"""
import os, sys, py_compile, tempfile

REL = os.path.join("backend", "app", "services", "translation", "name_substitution.py")
MARKER = "Pack 59.1:"

ANCHOR = (
    "    if short_ru:\n"
    "        pairs.append((short_ru, short_latin))\n"
    "\n"
    "    return pairs"
)
INSERT = (
    "    if short_ru:\n"
    "        pairs.append((short_ru, short_latin))\n"
    "\n"
    "    # Pack 59.1: UPPER-\u0432\u0430\u0440\u0438\u0430\u043d\u0442\u044b \u043f\u0430\u0440 "
    "\u0434\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u0430 (\u0435\u0441\u043b\u0438 \u0424\u0418\u041e "
    "\u0440\u0435\u043d\u0434\u0435\u0440\u0438\u0442\u0441\u044f \u0417\u0410\u0413\u041b\u0410\u0412\u041d\u042b\u041c\u0418\n"
    "    # \u043a\u0438\u0440\u0438\u043b\u043b\u0438\u0446\u0435\u0439 \u2014 \u043a\u0430\u043a \u0432 "
    "\u043b\u0438\u0441\u0442\u043a\u0430\u0445). \u041b\u0430\u0442\u0438\u043d\u0438\u0446\u0430 \u0442\u043e\u0436\u0435 UPPER.\n"
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
        print("[SKIP] \u0443\u0436\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u043e (Pack 59.1)."); return

    c = norm.count(ANCHOR)
    if c != 1:
        print(f"!!! \u044f\u043a\u043e\u0440\u044c \u043d\u0430\u0439\u0434\u0435\u043d {c} \u0440\u0430\u0437 (\u043d\u0443\u0436\u043d\u043e 1). \u0421\u0442\u043e\u043f, \u0444\u0430\u0439\u043b \u043d\u0435 \u0442\u0440\u043e\u043d\u0443\u0442.")
        sys.exit(2)

    new = norm.replace(ANCHOR, INSERT, 1)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(new); tmp = tf.name
    ok = True
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        ok = False; print("!!! py_compile FAIL \u2014 \u0444\u0430\u0439\u043b \u041d\u0415 \u0442\u0440\u043e\u043d\u0443\u0442:\n", e)
    os.unlink(tmp)
    if not ok:
        sys.exit(3)

    open(path + ".bak591", "wb").write(raw)
    out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
    open(path, "wb").write(out)
    print("OK: _build_director_subs \u043f\u0440\u043e\u043f\u0430\u0442\u0447\u0435\u043d. \u0411\u044d\u043a\u0430\u043f -> name_substitution.py.bak591")
    print("    py_compile: OK; CRLF:", crlf)


if __name__ == "__main__":
    main()
