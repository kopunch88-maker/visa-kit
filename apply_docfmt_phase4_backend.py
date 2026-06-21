#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 60.3 (Фаза 4, бэкенд) — ?format= на остальных архивах и ES-переводе.
  render_endpoints.py : render_package_docx / render_package_pdf
  translations.py     : + Query; download_translations_zip / download_single_translation
Требует doc_convert с convert_package_zip + convert (Фазы 1 и 3).
Идемпотентно, .bak603, pre-write py_compile, CRLF-aware.
"""
import os, sys, py_compile, tempfile
ROOT = os.path.dirname(os.path.abspath(__file__))

def _patch(rel, pairs, marker):
    path = os.path.join(ROOT, *rel.split("/"))
    if not os.path.exists(path): print("!!! не найден:", path); sys.exit(1)
    raw = open(path, "rb").read(); crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")
    if marker in norm: print(f"[SKIP] {rel} уже пропатчен ({marker})."); return
    for nm, old, _n in pairs:
        if norm.count(old) != 1:
            print(f"!!! [{rel}] якорь '{nm}' = {norm.count(old)} (нужно 1). Стоп."); sys.exit(2)
    new = norm
    for nm, old, repl in pairs: new = new.replace(old, repl, 1)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(new); tmp = tf.name
    try: py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e: print(f"!!! [{rel}] py_compile FAIL — не тронут:", e); os.unlink(tmp); sys.exit(3)
    os.unlink(tmp)
    open(path + ".bak603", "wb").write(raw)
    open(path, "wb").write((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print(f"OK: {rel} пропатчен (.bak603). CRLF: {crlf}")

CONV = (
    '    _pfmt = (format or "native").lower()\n'
    '    if _pfmt not in ("", "native"):\n'
    "        from app.services.doc_convert import convert_package_zip\n"
    "        try:\n"
    "            zip_bytes = convert_package_zip(zip_bytes, _pfmt)\n"
    "        except Exception as e:\n"
    "            raise HTTPException(500, f\"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0430\u0440\u0445\u0438\u0432 \u0432 {_pfmt}: {type(e).__name__}: {e}\")\n"
)

RE_PAIRS = [
("docx-sig",
 '@router.post("/{app_id}/render-package-docx")\n'
 "async def render_package_docx(  # Pack 57.2: def \u2192 async (\u0434\u043b\u044f await _ensure_...)\n"
 "    app_id: int,\n"
 "    db: Session = Depends(get_session),",
 '@router.post("/{app_id}/render-package-docx")\n'
 "async def render_package_docx(  # Pack 57.2: def \u2192 async (\u0434\u043b\u044f await _ensure_...)\n"
 "    app_id: int,\n"
 '    format: str = Query("native", description="native|docx|pdf|jpeg"),  # Pack 60.3\n'
 "    db: Session = Depends(get_session),"),
("docx-ret",
 '    download_name = f"docx_package_{application.reference}.zip"',
 CONV + '    download_name = f"docx_package_{application.reference}.zip"'),
("pdf-sig",
 '@router.post("/{app_id}/render-package-pdf")\n'
 "def render_package_pdf(\n"
 "    app_id: int,\n"
 "    db: Session = Depends(get_session),",
 '@router.post("/{app_id}/render-package-pdf")\n'
 "def render_package_pdf(\n"
 "    app_id: int,\n"
 '    format: str = Query("native", description="native|jpeg"),  # Pack 60.3\n'
 "    db: Session = Depends(get_session),"),
("pdf-ret",
 '    download_name = f"pdf_forms_{application.reference}.zip"',
 CONV + '    download_name = f"pdf_forms_{application.reference}.zip"'),
]

TR_PAIRS = [
("import",
 "from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException",
 "from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query"),
("zip-sig",
 '@router.get("/{app_id}/translations/zip")\n'
 "def download_translations_zip(\n"
 "    app_id: int,\n"
 "    session: Session = Depends(get_session),\n"
 "):",
 '@router.get("/{app_id}/translations/zip")\n'
 "def download_translations_zip(\n"
 "    app_id: int,\n"
 '    format: str = Query("native", description="native|docx|pdf|jpeg"),  # Pack 60.3\n'
 "    session: Session = Depends(get_session),\n"
 "):"),
("zip-conv",
 "    zip_buffer.seek(0)\n"
 '    download_name = f"translations_{application.reference}.zip"',
 "    zip_buffer.seek(0)\n"
 '    _pfmt = (format or "native").lower()\n'
 '    if _pfmt not in ("", "native"):\n'
 "        from app.services.doc_convert import convert_package_zip\n"
 "        try:\n"
 "            zip_buffer = io.BytesIO(convert_package_zip(zip_buffer.getvalue(), _pfmt))\n"
 "        except Exception as e:\n"
 "            raise HTTPException(500, f\"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0430\u0440\u0445\u0438\u0432 \u0432 {_pfmt}: {type(e).__name__}: {e}\")\n"
 '    download_name = f"translations_{application.reference}.zip"'),
("one-sig",
 '@router.get("/{app_id}/translations/{kind}/download")\n'
 "def download_single_translation(\n"
 "    app_id: int,\n"
 "    kind: TranslationKind,\n"
 "    session: Session = Depends(get_session),\n"
 "):",
 '@router.get("/{app_id}/translations/{kind}/download")\n'
 "def download_single_translation(\n"
 "    app_id: int,\n"
 "    kind: TranslationKind,\n"
 '    format: str = Query("native", description="native|docx|pdf|jpeg"),  # Pack 60.3\n'
 "    session: Session = Depends(get_session),\n"
 "):"),
("one-ret",
 "    return StreamingResponse(\n"
 "        io.BytesIO(content),\n"
 '        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",\n'
 "        headers={\n"
 "            \"Content-Disposition\": f'attachment; filename=\"{tr.file_name}\"',\n"
 "        },\n"
 "    )",
 '    _media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"\n'
 "    _fname = tr.file_name\n"
 '    _fmt = (format or "native").lower()\n'
 '    if _fmt not in ("", "native", "docx"):\n'
 "        from app.services.doc_convert import convert as _convert_doc\n"
 "        try:\n"
 '            _base = (tr.file_name or "translation.docx").rsplit(".", 1)[0]\n'
 '            content, _fname, _media = _convert_doc(content, "docx", _fmt, _base)\n'
 "        except ValueError as e:\n"
 "            raise HTTPException(422, str(e))\n"
 "        except RuntimeError as e:\n"
 "            raise HTTPException(500, str(e))\n"
 "\n"
 "    return StreamingResponse(\n"
 "        io.BytesIO(content),\n"
 "        media_type=_media,\n"
 "        headers={\n"
 "            \"Content-Disposition\": f'attachment; filename=\"{_fname}\"',\n"
 "        },\n"
 "    )"),
]

if __name__ == "__main__":
    _patch("backend/app/api/render_endpoints.py", RE_PAIRS, "Pack 60.3")
    _patch("backend/app/api/translations.py", TR_PAIRS, "Pack 60.3")
    print("\nГотово (бэкенд Фазы 4). Требует doc_convert из Фаз 1+3.")
