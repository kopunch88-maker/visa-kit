#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 60.0 (Фаза 1) — скачивание документа в выбранном формате.
1) NEW backend/app/services/doc_convert.py (конвертер docx/pdf/jpeg).
2) render_endpoints.py: эндпоинт одного документа получает ?format=native|docx|pdf|jpeg.
3) requirements: + PyMuPDF (растеризация PDF→JPEG).
Идемпотентно, .bak, pre-write py_compile, CRLF-aware (Правило 71).
"""
import os, sys, base64, py_compile, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DOC_CONVERT_B64 = "IyAtKi0gY29kaW5nOiB1dGYtOCAtKi0KIiIiClBhY2sgNjAuMCDigJQg0LrQvtC90LLQtdGA0YLQsNGG0LjRjyDQs9C+0YLQvtCy0L7Qs9C+INC00L7QutGD0LzQtdC90YLQsCDQsiDRhNC+0YDQvNCw0YIg0YHQutCw0YfQuNCy0LDQvdC40Y8uCgrQmNGB0YLQvtGH0L3QuNC6IChkb2N4IHwgcGRmKSDihpIgZG9jeCB8IHBkZiB8IGpwZWcoemlwKS4KICAtIGRvY3jihpJwZGYgIDogTGlicmVPZmZpY2UgKHNvZmZpY2UgLS1oZWFkbGVzcyAtLWNvbnZlcnQtdG8gcGRmKSDigJQg0YPQttC1INC90LAg0YHQtdGA0LLQtdGA0LUgKFBhY2sgNTIpLgogIC0gKuKGkmpwZWcgICAgOiBQREYg0YDQsNGB0YLQtdGA0LjQt9GD0LXRgtGB0Y8g0L/QvtGB0YLRgNCw0L3QuNGH0L3QviDRh9C10YDQtdC3IFB5TXVQREYgKGZpdHopOyDQutCw0LbQtNCw0Y8g0YHRgtGA0LDQvdC40YbQsCA9IEpQRUc7INCy0YHRkSDQsiBaSVAuCiAgLSBwZGbihpJkb2N4ICA6INCd0JUg0L/QvtC00LTQtdGA0LbQuNCy0LDQtdGC0YHRjyAo0YMg0L3QsNGC0LjQstC90YvRhSBQREYg0L3QtdGCIFdvcmQt0LjRgdGF0L7QtNC90LjQutCwKSDihpIgVmFsdWVFcnJvci4KIiIiCmltcG9ydCBpbwppbXBvcnQgb3MKaW1wb3J0IHN1YnByb2Nlc3MKaW1wb3J0IHRlbXBmaWxlCmltcG9ydCB6aXBmaWxlCgpET0NYX01FRElBID0gImFwcGxpY2F0aW9uL3ZuZC5vcGVueG1sZm9ybWF0cy1vZmZpY2Vkb2N1bWVudC53b3JkcHJvY2Vzc2luZ21sLmRvY3VtZW50IgpQREZfTUVESUEgPSAiYXBwbGljYXRpb24vcGRmIgpaSVBfTUVESUEgPSAiYXBwbGljYXRpb24vemlwIgoKCmRlZiBkb2N4X3RvX3BkZihkb2N4X2J5dGVzOiBieXRlcywgdGltZW91dF9zZWM6IGludCA9IDkwKSAtPiBieXRlczoKICAgICIiIkRPQ1gg4oaSIFBERiDRh9C10YDQtdC3IExpYnJlT2ZmaWNlIGhlYWRsZXNzICjRgtC+0YIg0LbQtSDQv9GD0YLRjCwg0YfRgtC+INGDINCy0YvQv9C40YHQutC4LCBQYWNrIDUyKS4iIiIKICAgIHdpdGggdGVtcGZpbGUuVGVtcG9yYXJ5RGlyZWN0b3J5KHByZWZpeD0idmtfY29udl8iKSBhcyB0bXA6CiAgICAgICAgc3JjID0gb3MucGF0aC5qb2luKHRtcCwgImRvYy5kb2N4IikKICAgICAgICB3aXRoIG9wZW4oc3JjLCAid2IiKSBhcyBmOgogICAgICAgICAgICBmLndyaXRlKGRvY3hfYnl0ZXMpCiAgICAgICAgdHJ5OgogICAgICAgICAgICByZXN1bHQgPSBzdWJwcm9jZXNzLnJ1bigKICAgICAgICAgICAgICAgIFsic29mZmljZSIsICItLWhlYWRsZXNzIiwgIi0tY29udmVydC10byIsICJwZGYiLCAiLS1vdXRkaXIiLCB0bXAsIHNyY10sCiAgICAgICAgICAgICAgICBjYXB0dXJlX291dHB1dD1UcnVlLCB0aW1lb3V0PXRpbWVvdXRfc2VjLAogICAgICAgICAgICApCiAgICAgICAgZXhjZXB0IEZpbGVOb3RGb3VuZEVycm9yOgogICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoIkxpYnJlT2ZmaWNlIChzb2ZmaWNlKSDQvdC1INC90LDQudC00LXQvSDQsiBQQVRILiIpCiAgICAgICAgZXhjZXB0IHN1YnByb2Nlc3MuVGltZW91dEV4cGlyZWQ6CiAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcihmIkxpYnJlT2ZmaWNlINC/0YDQtdCy0YvRgdC40Lsge3RpbWVvdXRfc2VjfSDRgdC10Log0L/RgNC4IGRvY3jihpJwZGYuIikKICAgICAgICBpZiByZXN1bHQucmV0dXJuY29kZSAhPSAwOgogICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoIkxpYnJlT2ZmaWNlIGRvY3jihpJwZGY6ICIgKyByZXN1bHQuc3RkZXJyLmRlY29kZSgidXRmLTgiLCAicmVwbGFjZSIpWzo1MDBdKQogICAgICAgIHBkZl9wYXRoID0gb3MucGF0aC5qb2luKHRtcCwgImRvYy5wZGYiKQogICAgICAgIGlmIG5vdCBvcy5wYXRoLmV4aXN0cyhwZGZfcGF0aCk6CiAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcigiUERGINC90LUg0L/QvtGP0LLQuNC70YHRjyDQv9C+0YHQu9C1INC60L7QvdCy0LXRgNGC0LDRhtC40LggZG9jeOKGknBkZi4iKQogICAgICAgIHdpdGggb3BlbihwZGZfcGF0aCwgInJiIikgYXMgZjoKICAgICAgICAgICAgcmV0dXJuIGYucmVhZCgpCgoKZGVmIHBkZl90b19qcGVnX3ppcChwZGZfYnl0ZXM6IGJ5dGVzLCBiYXNlX25hbWU6IHN0ciwgZHBpOiBpbnQgPSAxNzAsIHF1YWxpdHk6IGludCA9IDg1KSAtPiBieXRlczoKICAgICIiIlBERiDihpIgWklQINC/0L7RgdGC0YDQsNC90LjRh9C90YvRhSBKUEVHLiDQmtCw0LbQtNCw0Y8g0YHRgtGA0LDQvdC40YbQsDogPGJhc2VfbmFtZT5f0YHRgtGAMDEuanBnIC4uLiIiIgogICAgaW1wb3J0IGZpdHogICMgUHlNdVBERgogICAgem9vbSA9IGRwaSAvIDcyLjAKICAgIG1hdCA9IGZpdHouTWF0cml4KHpvb20sIHpvb20pCiAgICBvdXQgPSBpby5CeXRlc0lPKCkKICAgIGRvYyA9IGZpdHoub3BlbihzdHJlYW09cGRmX2J5dGVzLCBmaWxldHlwZT0icGRmIikKICAgIHRyeToKICAgICAgICBuID0gZG9jLnBhZ2VfY291bnQKICAgICAgICBwYWQgPSBtYXgoMiwgbGVuKHN0cihuKSkpCiAgICAgICAgd2l0aCB6aXBmaWxlLlppcEZpbGUob3V0LCAidyIsIHppcGZpbGUuWklQX0RFRkxBVEVEKSBhcyB6ZjoKICAgICAgICAgICAgZm9yIGkgaW4gcmFuZ2Uobik6CiAgICAgICAgICAgICAgICBwaXggPSBkb2MubG9hZF9wYWdlKGkpLmdldF9waXhtYXAobWF0cml4PW1hdCkKICAgICAgICAgICAgICAgIGpwZyA9IHBpeC50b2J5dGVzKCJqcGVnIiwganBnX3F1YWxpdHk9cXVhbGl0eSkKICAgICAgICAgICAgICAgIHpmLndyaXRlc3RyKGYie2Jhc2VfbmFtZX1f0YHRgtGAe3N0cihpICsgMSkuemZpbGwocGFkKX0uanBnIiwganBnKQogICAgZmluYWxseToKICAgICAgICBkb2MuY2xvc2UoKQogICAgcmV0dXJuIG91dC5nZXR2YWx1ZSgpCgoKZGVmIGNvbnZlcnQoY29udGVudDogYnl0ZXMsIHNyY19mbXQ6IHN0ciwgdGFyZ2V0X2ZtdDogc3RyLCBiYXNlX25hbWU6IHN0cik6CiAgICAiIiIKICAgINCS0L7Qt9Cy0YDQsNGJ0LDQtdGCIChieXRlcywgZmlsZW5hbWUsIG1lZGlhX3R5cGUpLgogICAgc3JjX2ZtdCAvIHRhcmdldF9mbXQg4oiIIHsnZG9jeCcsJ3BkZicsJ2pwZWcnfSAoKyDRgdC40L3QvtC90LjQvNGLIGpwZy9pbWFnZS9pbWFnZXMpLgogICAgYmFzZV9uYW1lIOKAlCDQsdC10Lcg0YDQsNGB0YjQuNGA0LXQvdC40Y8uCiAgICAiIiIKICAgIHNyY19mbXQgPSAoc3JjX2ZtdCBvciAiIikubG93ZXIoKQogICAgdCA9ICh0YXJnZXRfZm10IG9yICIiKS5sb3dlcigpCiAgICBpZiB0IGluICgianBnIiwgImltYWdlIiwgImltYWdlcyIpOgogICAgICAgIHQgPSAianBlZyIKCiAgICBpZiB0IGluICgiIiwgIm5hdGl2ZSIsIHNyY19mbXQpOgogICAgICAgIG1lZGlhID0gRE9DWF9NRURJQSBpZiBzcmNfZm10ID09ICJkb2N4IiBlbHNlIFBERl9NRURJQQogICAgICAgIHJldHVybiBjb250ZW50LCBmIntiYXNlX25hbWV9LntzcmNfZm10fSIsIG1lZGlhCgogICAgaWYgdCA9PSAicGRmIjoKICAgICAgICBpZiBzcmNfZm10ID09ICJkb2N4IjoKICAgICAgICAgICAgcmV0dXJuIGRvY3hfdG9fcGRmKGNvbnRlbnQpLCBmIntiYXNlX25hbWV9LnBkZiIsIFBERl9NRURJQQogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlBERiDQuNC3INGN0YLQvtCz0L4g0LjRgdGC0L7Rh9C90LjQutCwINC90LXQtNC+0YHRgtGD0L/QtdC9IikKCiAgICBpZiB0ID09ICJkb2N4IjoKICAgICAgICBpZiBzcmNfZm10ID09ICJkb2N4IjoKICAgICAgICAgICAgcmV0dXJuIGNvbnRlbnQsIGYie2Jhc2VfbmFtZX0uZG9jeCIsIERPQ1hfTUVESUEKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJXb3JkINC90LXQtNC+0YHRgtGD0L/QtdC9OiDRgyDQtNC+0LrRg9C80LXQvdGC0LAg0L3QtdGCIFdvcmQt0LjRgdGF0L7QtNC90LjQutCwICjQvtC9INC40LfQvdCw0YfQsNC70YzQvdC+IFBERikiKQoKICAgIGlmIHQgPT0gImpwZWciOgogICAgICAgIHBkZiA9IGNvbnRlbnQgaWYgc3JjX2ZtdCA9PSAicGRmIiBlbHNlIGRvY3hfdG9fcGRmKGNvbnRlbnQpCiAgICAgICAgcmV0dXJuIHBkZl90b19qcGVnX3ppcChwZGYsIGJhc2VfbmFtZSksIGYie2Jhc2VfbmFtZX1faW1hZ2VzLnppcCIsIFpJUF9NRURJQQoKICAgIHJhaXNlIFZhbHVlRXJyb3IoZiLQndC10LjQt9Cy0LXRgdGC0L3Ri9C5INGE0L7RgNC80LDRgjoge3RhcmdldF9mbXR9IikK"

def _norm(p): return os.path.join(ROOT, *p.split("/"))

def write_doc_convert():
    path = _norm("backend/app/services/doc_convert.py")
    data = base64.b64decode(DOC_CONVERT_B64)
    if os.path.exists(path) and open(path, "rb").read() == data:
        print("[SKIP] doc_convert.py уже актуален."); return
    # gate
    with tempfile.NamedTemporaryFile("wb", suffix=".py", delete=False) as tf:
        tf.write(data); tmp = tf.name
    try: py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        print("!!! doc_convert.py не компилируется:", e); sys.exit(3)
    finally: os.unlink(tmp)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)
    print("OK: записан", path.replace(ROOT, "."))

def patch_endpoint():
    path = _norm("backend/app/api/render_endpoints.py")
    raw = open(path, "rb").read(); crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")
    if "Pack 60.0" in norm:
        print("[SKIP] render_endpoints.py уже пропатчен (Pack 60.0)."); return

    sig_old = (
        '@router.post("/{app_id}/render/{document_type}")\n'
        "def render_single_document(\n"
        "    app_id: int,\n"
        "    document_type: str,\n"
        "    session: Session = Depends(get_session),\n"
        "    _user=Depends(require_manager),\n"
        "):"
    )
    sig_new = (
        '@router.post("/{app_id}/render/{document_type}")\n'
        "def render_single_document(\n"
        "    app_id: int,\n"
        "    document_type: str,\n"
        '    format: str = Query("native", description="native|docx|pdf|jpeg"),  # Pack 60.0\n'
        "    session: Session = Depends(get_session),\n"
        "    _user=Depends(require_manager),\n"
        "):"
    )
    conv_anchor = "    import urllib.parse as _urlparse\n"
    conv_block = (
        "    # Pack 60.0 \u2014 \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0430\u0446\u0438\u044f \u0432 \u0437\u0430\u043f\u0440\u043e\u0448\u0435\u043d\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 (native|docx|pdf|jpeg).\n"
        '    _fmt = (format or "native").lower()\n'
        '    if _fmt not in ("", "native"):\n'
        '        _src_fmt = "pdf" if filename.lower().endswith(".pdf") else "docx"\n'
        "        # bank_statement v2 \u043e\u0442\u0434\u0430\u0451\u0442\u0441\u044f PDF, \u043d\u043e \u0438\u043c\u0435\u0435\u0442 DOCX-\u0438\u0441\u0445\u043e\u0434\u043d\u0438\u043a:\n"
        "        # \u0434\u043b\u044f Word/\u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u0439 \u0431\u0435\u0440\u0451\u043c DOCX.\n"
        '        if document_type == "bank_statement" and _src_fmt == "pdf" and _fmt in ("docx", "jpeg", "jpg", "image", "images"):\n'
        "            from app.templates_engine import render_bank_statement\n"
        "            content = render_bank_statement(application, session)\n"
        '            _src_fmt = "docx"\n'
        '            filename = "\u0412\u044b\u043f\u0438\u0441\u043a\u0430_\u043f\u043e_\u0441\u0447\u0435\u0442\u0443.docx"\n'
        "        if _fmt != _src_fmt:\n"
        "            from app.services.doc_convert import convert as _convert_doc\n"
        "            try:\n"
        '                _base = filename.rsplit(".", 1)[0]\n'
        "                content, filename, _media_type_override = _convert_doc(content, _src_fmt, _fmt, _base)\n"
        "            except ValueError as e:\n"
        "                raise HTTPException(422, str(e))\n"
        "            except RuntimeError as e:\n"
        "                raise HTTPException(500, str(e))\n"
        "\n"
        "    import urllib.parse as _urlparse\n"
    )

    for name, a in (("signature", sig_old), ("conv-anchor", conv_anchor)):
        if norm.count(a) != 1:
            print(f"!!! \u044f\u043a\u043e\u0440\u044c {name} \u043d\u0430\u0439\u0434\u0435\u043d {norm.count(a)} \u0440\u0430\u0437 (\u043d\u0443\u0436\u043d\u043e 1). \u0421\u0442\u043e\u043f."); sys.exit(2)

    new = norm.replace(sig_old, sig_new, 1).replace(conv_anchor, conv_block, 1)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(new); tmp = tf.name
    try: py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        print("!!! render_endpoints.py не компилируется \u2014 НЕ тронут:", e); sys.exit(3)
    finally: os.unlink(tmp)
    open(path + ".bak60", "wb").write(raw)
    open(path, "wb").write((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print("OK: render_endpoints.py пропатчен (.bak60). CRLF:", crlf)

def patch_requirements():
    for rel in ("backend/requirements.txt", "requirements.txt"):
        path = _norm(rel)
        if not os.path.exists(path): continue
        txt = open(path, "rb").read().decode("utf-8")
        if "pymupdf" in txt.lower():
            print(f"[SKIP] PyMuPDF уже в {rel}."); return
        sep = "" if txt.endswith("\n") else "\n"
        open(path, "ab").write((sep + "PyMuPDF>=1.24.0  # Pack 60.0 PDF->JPEG\n").encode("utf-8"))
        print(f"OK: PyMuPDF добавлен в {rel}."); return
    print("!!! requirements.txt не найден \u2014 добавь PyMuPDF вручную.")

if __name__ == "__main__":
    write_doc_convert(); patch_endpoint(); patch_requirements()
    print("\nГотово. Не забудь: на сервере уже есть LibreOffice (Pack 52); PyMuPDF поставится при деплое.")
