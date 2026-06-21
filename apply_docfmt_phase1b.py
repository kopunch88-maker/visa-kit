#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 60.0b (Фаза 1b) — ?format= на РЕАЛЬНОМ эндпоинте скачивания одного документа,
который дёргает фронт: GET /admin/applications/{id}/download-file/{file_id}
(функция download_single_file в applications.py). Модуль doc_convert уже из Фазы 1.

Правки:
  1) сигнатура: + format: str = Query("native", ...)
  2) ветка bank_statement v2: combined PDF по умолчанию; docx → RU-docx; jpeg → растеризация combined PDF
  3) общий возврат: docx/pdf → конвертация через doc_convert

Идемпотентно, .bak60b, pre-write py_compile, CRLF-aware (Правило 71).
"""
import os, sys, py_compile, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
REL = os.path.join("backend", "app", "api", "applications.py")
MARKER = "Pack 60.0"

SIG_OLD = (
    '@router.get("/{app_id}/download-file/{file_id}")\n'
    "async def download_single_file(  # Pack 57.0: def \u2192 async (\u0434\u043b\u044f await _ensure_...)\n"
    "    app_id: int,\n"
    "    file_id: str,\n"
    "    session: Session = Depends(get_session),\n"
    "    _user=Depends(require_manager),\n"
    "):"
)
SIG_NEW = (
    '@router.get("/{app_id}/download-file/{file_id}")\n'
    "async def download_single_file(  # Pack 57.0: def \u2192 async (\u0434\u043b\u044f await _ensure_...)\n"
    "    app_id: int,\n"
    "    file_id: str,\n"
    '    format: str = Query("native", description="native|docx|pdf|jpeg"),  # Pack 60.0\n'
    "    session: Session = Depends(get_session),\n"
    "    _user=Depends(require_manager),\n"
    "):"
)

BANK_OLD = (
    '        filename = "10_\u0412\u044b\u043f\u0438\u0441\u043a\u0430.pdf"\n'
    "        from urllib.parse import quote\n"
    "        safe_name = quote(filename)\n"
    "        return StreamingResponse(\n"
    "            io.BytesIO(content),\n"
    '            media_type="application/pdf",\n'
    "            headers={\"Content-Disposition\": f\"attachment; filename*=UTF-8''{safe_name}\"},\n"
    "        )"
)
BANK_NEW = (
    '        filename = "10_\u0412\u044b\u043f\u0438\u0441\u043a\u0430.pdf"\n'
    '        _bmedia = "application/pdf"\n'
    "        # Pack 60.0 \u2014 \u0444\u043e\u0440\u043c\u0430\u0442 \u0434\u043b\u044f \u0432\u044b\u043f\u0438\u0441\u043a\u0438 v2 (combined PDF \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e)\n"
    '        _bfmt = (format or "native").lower()\n'
    '        if _bfmt == "docx":\n'
    "            content = render_bank_statement(app, session)\n"
    '            filename, _bmedia = "10_\u0412\u044b\u043f\u0438\u0441\u043a\u0430.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"\n'
    '        elif _bfmt in ("jpeg", "jpg", "image", "images"):\n'
    "            from app.services.doc_convert import convert as _convert_doc\n"
    '            content, filename, _bmedia = _convert_doc(content, "pdf", "jpeg", "10_\u0412\u044b\u043f\u0438\u0441\u043a\u0430")\n'
    "        from urllib.parse import quote\n"
    "        safe_name = quote(filename)\n"
    "        return StreamingResponse(\n"
    "            io.BytesIO(content),\n"
    "            media_type=_bmedia,\n"
    "            headers={\"Content-Disposition\": f\"attachment; filename*=UTF-8''{safe_name}\"},\n"
    "        )"
)

GEN_ANCHOR = (
    "    # encode \u0438\u043c\u044f \u0444\u0430\u0439\u043b\u0430 \u0434\u043b\u044f Content-Disposition (\u0440\u0443\u0441\u0441\u043a\u0438\u0435 \u0431\u0443\u043a\u0432\u044b)\n"
    "    from urllib.parse import quote\n"
)
GEN_NEW = (
    "    # Pack 60.0 \u2014 \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0430\u0446\u0438\u044f \u0432 \u0437\u0430\u043f\u0440\u043e\u0448\u0435\u043d\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 (native|docx|pdf|jpeg)\n"
    '    _fmt = (format or "native").lower()\n'
    '    if _fmt not in ("", "native", spec["kind"]):\n'
    "        from app.services.doc_convert import convert as _convert_doc\n"
    "        try:\n"
    '            _base = filename.rsplit(".", 1)[0]\n'
    "            content, filename, media_type = _convert_doc(content, spec[\"kind\"], _fmt, _base)\n"
    "        except ValueError as e:\n"
    "            raise HTTPException(422, str(e))\n"
    "        except RuntimeError as e:\n"
    "            raise HTTPException(500, str(e))\n"
    "\n"
    "    # encode \u0438\u043c\u044f \u0444\u0430\u0439\u043b\u0430 \u0434\u043b\u044f Content-Disposition (\u0440\u0443\u0441\u0441\u043a\u0438\u0435 \u0431\u0443\u043a\u0432\u044b)\n"
    "    from urllib.parse import quote\n"
)


def main():
    path = os.path.join(ROOT, REL)
    if not os.path.exists(path): print("!!! \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d:", path); sys.exit(1)
    raw = open(path, "rb").read(); crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")
    if MARKER in norm: print("[SKIP] applications.py \u0443\u0436\u0435 \u043f\u0440\u043e\u043f\u0430\u0442\u0447\u0435\u043d (Pack 60.0)."); return
    for nm, a in (("sig", SIG_OLD), ("bank", BANK_OLD), ("gen", GEN_ANCHOR)):
        if norm.count(a) != 1:
            print(f"!!! \u044f\u043a\u043e\u0440\u044c {nm} = {norm.count(a)} (\u043d\u0443\u0436\u043d\u043e 1). \u0421\u0442\u043e\u043f."); sys.exit(2)
    new = norm.replace(SIG_OLD, SIG_NEW, 1).replace(BANK_OLD, BANK_NEW, 1).replace(GEN_ANCHOR, GEN_NEW, 1)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(new); tmp = tf.name
    try: py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e: print("!!! py_compile FAIL \u2014 \u043d\u0435 \u0442\u0440\u043e\u043d\u0443\u0442:", e); os.unlink(tmp); sys.exit(3)
    os.unlink(tmp)
    open(path + ".bak60b", "wb").write(raw)
    open(path, "wb").write((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print("OK: download_single_file \u043f\u0440\u043e\u043f\u0430\u0442\u0447\u0435\u043d (.bak60b). CRLF:", crlf)


if __name__ == "__main__":
    main()
