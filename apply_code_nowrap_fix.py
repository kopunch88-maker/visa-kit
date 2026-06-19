#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 59.2 — коды операций с пробелом (SBP …, RECUR …, MOSH 19…) переносятся
на 2-ю строку в узкой колонке ЧБ-шаблона выписки (bank_statement_template_v2).

Причина: Word переносит на пробеле. Сплошные коды (C16…, С011…) не страдают.
Фикс: при заполнении __TX_CODE__ заменяем обычный пробел на НЕРАЗРЫВНЫЙ (\\u00A0)
— визуально тот же пробел, но разрыва строки в коде больше не будет. Чинит и
уже существующие выписки (правка на стороне рендера), и любой узкий шаблон.

Правка в backend/app/templates_engine/docx_renderer.py (_fill_tx_row).
Идемпотентно, .bak592, pre-write py_compile, CRLF-aware (Правило 71).
"""
import os, sys, py_compile, tempfile

REL = os.path.join("backend", "app", "templates_engine", "docx_renderer.py")
MARKER = "Pack 59.2:"

ANCHOR = '        "__TX_CODE__": tx.get("code", ""),'
INSERT = (
    "        # Pack 59.2: \u043f\u0440\u043e\u0431\u0435\u043b \u0432 \u043a\u043e\u0434\u0430\u0445 "
    "(SBP \u2026, RECUR \u2026, MOSH 19\u2026) -> \u043d\u0435\u0440\u0430\u0437\u0440\u044b\u0432\u043d\u044b\u0439,\n"
    "        # \u0438\u043d\u0430\u0447\u0435 \u043d\u0430 \u0443\u0437\u043a\u043e\u0439 \u043a\u043e\u043b\u043e\u043d\u043a\u0435 "
    "\u0427\u0411-\u0448\u0430\u0431\u043b\u043e\u043d\u0430 (v2) Word \u043f\u0435\u0440\u0435\u043d\u043e\u0441\u0438\u0442 "
    "\u0446\u0438\u0444\u0440\u044b \u043d\u0430 2-\u044e \u0441\u0442\u0440\u043e\u043a\u0443.\n"
    '        "__TX_CODE__": (tx.get("code", "") or "").replace(" ", "\\u00a0"),'
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
        print("[SKIP] \u0443\u0436\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u043e (Pack 59.2)."); return

    c = norm.count(ANCHOR)
    if c != 1:
        print(f"!!! \u044f\u043a\u043e\u0440\u044c \u043d\u0430\u0439\u0434\u0435\u043d {c} \u0440\u0430\u0437 (\u043d\u0443\u0436\u043d\u043e 1). \u0421\u0442\u043e\u043f.")
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

    open(path + ".bak592", "wb").write(raw)
    out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
    open(path, "wb").write(out)
    print("OK: docx_renderer.py \u043f\u0440\u043e\u043f\u0430\u0442\u0447\u0435\u043d. \u0411\u044d\u043a\u0430\u043f -> docx_renderer.py.bak592")
    print("    py_compile: OK; CRLF:", crlf)


if __name__ == "__main__":
    main()
