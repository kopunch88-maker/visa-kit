#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIX — Карта TIE: сохранение NIE/даты не отображалось.

Баг: в ApplicationDetail обработчик onSaved дровера TIE вызывал onChanged() —
такой функции в компоненте НЕТ (обновление везде идёт через loadAll() + onUpdated()).
После успешного PATCH вызов onChanged() падал → плашка не перечитывала данные,
выглядело как «не сохранилось» (хотя в БД значение записывалось).

Фикс: onChanged() -> loadAll(); onUpdated();  (как у остальных дроверов).

  frontend/components/admin/ApplicationDetail.tsx

Запуск из КОРНЯ репо:  python apply_fix_tie_drawer_save.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
BAK = ".bak_pre_tiefix"


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(1)


def _read(path: Path):
    text = path.read_bytes().decode("utf-8")
    newline = "\r\n" if text.count("\r\n") > 0 else "\n"
    return text.replace("\r\n", "\n"), newline


def _write(path: Path, text_lf: str, newline: str) -> None:
    out = text_lf.replace("\n", newline) if newline == "\r\n" else text_lf
    path.write_bytes(out.encode("utf-8"))


def main() -> None:
    path = REPO / "frontend" / "components" / "admin" / "ApplicationDetail.tsx"
    if not path.exists():
        _fail(f"нет файла {path}")
    text, nl = _read(path)

    old = ("            setShowTieDrawer(false);\n"
           "            onChanged();")
    new = ("            setShowTieDrawer(false);\n"
           "            loadAll();\n"
           "            onUpdated();")

    if old not in text:
        if "setShowTieDrawer(false);\n            loadAll();" in text:
            print("[skip] уже исправлено")
            return
        _fail("якорь не найден: onSaved дровера TIE (setShowTieDrawer(false); onChanged();)")

    if text.count(old) != 1:
        _fail(f"якорь встречается {text.count(old)} раз (нужно 1)")

    bak = path.with_suffix(path.suffix + BAK)
    if not bak.exists():
        bak.write_bytes(path.read_bytes())
        print(f"  backup -> {bak.name}")

    text = text.replace(old, new, 1)
    _write(path, text, nl)
    print("[ok] ApplicationDetail.tsx — TIE onSaved: onChanged() -> loadAll(); onUpdated();")


if __name__ == "__main__":
    main()
