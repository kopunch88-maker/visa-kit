#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 59.3 — код операции _gen_payment_code укорачивается с 17 до 16 символов.

Причина: "\u0421011" + 13 цифр = 17 символов, не влезает в колонку "Код операции"
узкого ЧБ-шаблона (bank_statement_template_v2) -> Word переносит последнюю цифру
на 2-ю строку. Коды C16... и SBP ... (по 16) влезают. Делаем payment-код тоже 16
(12 цифр) -> влезает как остальные.

Правка в backend/app/services/bank_statement_generator.py.
Идемпотентно, .bak593, pre-write py_compile, CRLF-aware (Правило 71).
"""
import os, sys, py_compile, tempfile

REL = os.path.join("backend", "app", "services", "bank_statement_generator.py")
MARKER = "Pack 59.3:"

C = "\u0421"  # кириллическая С
ANCHOR = (
    "    # \u041a\u0438\u0440\u0438\u043b\u043b\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0421 "
    "\u2014 \u043a\u0430\u043a \u0432 \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0445 "
    "\u0432\u044b\u043f\u0438\u0441\u043a\u0430\u0445 \u0410\u043b\u044c\u0444\u044b\n"
    '    return "' + C + '011" + "".join(random.choices(string.digits, k=13))'
)
INSERT = (
    "    # \u041a\u0438\u0440\u0438\u043b\u043b\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0421 "
    "\u2014 \u043a\u0430\u043a \u0432 \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0445 "
    "\u0432\u044b\u043f\u0438\u0441\u043a\u0430\u0445 \u0410\u043b\u044c\u0444\u044b.\n"
    "    # Pack 59.3: 16 \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432 (12 \u0446\u0438\u0444\u0440), "
    "\u0438\u043d\u0430\u0447\u0435 17-\u0441\u0438\u043c\u0432\u043e\u043b\u044c\u043d\u044b\u0439 "
    "\u043a\u043e\u0434 \u043f\u0435\u0440\u0435\u043d\u043e\u0441\u0438\u0442\u0441\u044f\n"
    "    # \u043d\u0430 2-\u044e \u0441\u0442\u0440\u043e\u043a\u0443 \u0432 \u0443\u0437\u043a\u043e\u0439 "
    "\u043a\u043e\u043b\u043e\u043d\u043a\u0435 \u0427\u0411-\u0448\u0430\u0431\u043b\u043e\u043d\u0430.\n"
    '    return "' + C + '011" + "".join(random.choices(string.digits, k=12))'
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
        print("[SKIP] \u0443\u0436\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u043e (Pack 59.3)."); return

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
        ok = False; print("!!! py_compile FAIL:\n", e)
    os.unlink(tmp)
    if not ok:
        sys.exit(3)

    open(path + ".bak593", "wb").write(raw)
    out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
    open(path, "wb").write(out)
    print("OK: _gen_payment_code -> 16 \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432. \u0411\u044d\u043a\u0430\u043f -> bank_statement_generator.py.bak593")
    print("    py_compile: OK; CRLF:", crlf)


if __name__ == "__main__":
    main()
