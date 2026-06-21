#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 59.4 — инициалы в подписи романизируются LLM (GOST «IU» вместо паспортного «Y»).

Причина: _initials_native / _nbsp_initials рендерят НЕРАЗРЫВНЫЙ пробел (U+00A0)
между фамилией и инициалом («Кот\u00a0Ю.А.»), а пары в name_substitution строятся
ОБЫЧНЫМ пробелом («Кот Ю.А.»). NBSP != обычный пробел -> пара не матчится ->
инициалы переводит LLM по GOST. Фамилия ловится одиночной парой, отсюда «KOT IU.A.».

Фикс: в _build_applicant_subs и _build_director_subs добавляем NBSP-варианты КАЖДОЙ
пары (как Pack 59 добавил UPPER-варианты). Латиница тоже с NBSP — Word не разрывает.

Идемпотентно, .bak594, pre-write py_compile, CRLF-aware (Правило 71).
"""
import os, sys, py_compile, tempfile

REL = os.path.join("backend", "app", "services", "translation", "name_substitution.py")
MARKER = "Pack 59.4:"

NBSP_BLOCK = (
    "    # Pack 59.4: \u043f\u043e\u0434\u043f\u0438\u0441\u044c/\u0438\u043d\u0438\u0446\u0438\u0430\u043b\u044b "
    "\u0440\u0435\u043d\u0434\u0435\u0440\u044f\u0442\u0441\u044f \u0441 \u041d\u0415\u0420\u0410\u0417\u0420\u042b\u0412\u041d\u042b\u041c "
    "\u043f\u0440\u043e\u0431\u0435\u043b\u043e\u043c (U+00A0: _initials_native /\n"
    "    # _nbsp_initials), \u0430 \u043f\u0430\u0440\u044b \u0432\u044b\u0448\u0435 \u2014 \u0441 \u043e\u0431\u044b\u0447\u043d\u044b\u043c. "
    "\u0411\u0435\u0437 NBSP-\u0432\u0430\u0440\u0438\u0430\u043d\u0442\u043e\u0432 \u00ab\u041a\u043e\u0442 \u042e.\u0410.\u00bb \u043d\u0435 \u043c\u0430\u0442\u0447\u0438\u0442\n"
    "    # \u00ab\u041a\u043e\u0442<NBSP>\u042e.\u0410.\u00bb \u2192 \u0438\u043d\u0438\u0446\u0438\u0430\u043b\u044b \u0440\u043e\u043c\u0430\u043d\u0438\u0437\u0438\u0440\u0443\u0435\u0442 LLM "
    "(GOST \u00abIU\u00bb \u0432\u043c\u0435\u0441\u0442\u043e \u043f\u0430\u0441\u043f\u043e\u0440\u0442\u043d\u043e\u0433\u043e \u00abY\u00bb).\n"
    "    _NBSP = \"\\u00a0\"\n"
    "    nbsp_pairs: list[tuple[str, str]] = []\n"
    "    for _ru, _lat in pairs:\n"
    "        if \" \" in _ru:\n"
    "            nbsp_pairs.append((_ru.replace(\" \", _NBSP), _lat.replace(\" \", _NBSP)))\n"
    "    pairs.extend(nbsp_pairs)\n"
    "\n"
)

# якоря — уникальные комментарии UPPER-блоков (Pack 59 / 59.1)
ANCHOR_APP = (
    "    # Pack 59: UPPER-\u0432\u0430\u0440\u0438\u0430\u043d\u0442\u044b \u043f\u0430\u0440 \u0438\u043c\u0435\u043d\u0438 "
    "(\u043b\u0438\u0441\u0442\u043a\u0438 \u0440\u0435\u043d\u0434\u0435\u0440\u044f\u0442 \u0424\u0418\u041e \u0417\u0410\u0413\u041b\u0410\u0412\u041d\u042b\u041c\u0418 "
    "\u043a\u0438\u0440\u0438\u043b\u043b\u0438\u0446\u0435\u0439,"
)
ANCHOR_DIR = (
    "    # Pack 59.1: UPPER-\u0432\u0430\u0440\u0438\u0430\u043d\u0442\u044b \u043f\u0430\u0440 "
    "\u0434\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u0430 (\u0435\u0441\u043b\u0438 \u0424\u0418\u041e \u0440\u0435\u043d\u0434\u0435\u0440\u0438\u0442\u0441\u044f \u0417\u0410\u0413\u041b\u0410\u0412\u041d\u042b\u041c\u0418"
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
        print("[SKIP] \u0443\u0436\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u043e (Pack 59.4)."); return

    for nm, anchor in (("applicant", ANCHOR_APP), ("director", ANCHOR_DIR)):
        if norm.count(anchor) != 1:
            print(f"!!! \u044f\u043a\u043e\u0440\u044c {nm} \u043d\u0430\u0439\u0434\u0435\u043d {norm.count(anchor)} \u0440\u0430\u0437 (\u043d\u0443\u0436\u043d\u043e 1). \u0421\u0442\u043e\u043f.")
            sys.exit(2)

    new = norm.replace(ANCHOR_APP, NBSP_BLOCK + ANCHOR_APP, 1)
    new = new.replace(ANCHOR_DIR, NBSP_BLOCK + ANCHOR_DIR, 1)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(new); tmp = tf.name
    ok = True
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        ok = False; print("!!! py_compile FAIL:\n", e)
    os.unlink(tmp)
    if not ok:
        sys.exit(3)

    open(path + ".bak594", "wb").write(raw)
    out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
    open(path, "wb").write(out)
    print("OK: NBSP-\u0432\u0430\u0440\u0438\u0430\u043d\u0442\u044b \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u044b (\u0437\u0430\u044f\u0432\u0438\u0442\u0435\u043b\u044c + \u0434\u0438\u0440\u0435\u043a\u0442\u043e\u0440). \u0411\u044d\u043a\u0430\u043f -> name_substitution.py.bak594")
    print("    py_compile: OK; CRLF:", crlf)


if __name__ == "__main__":
    main()
