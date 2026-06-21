#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 60.2 (Фаза 3, фронт) — выбор формата для архива «Скачать всё».
frontend/components/admin/DocumentsGrid.tsx
  - state archiveFormat; <select> Как есть / Всё в PDF / Всё в картинках / Word (где есть)
  - handleDownloadZip: ?format=, имя файла с суффиксом (_pdf/_images/_word)
Все якоря ASCII (применяется ПОСЛЕ Фазы 2). Идемпотентно, .bak602f, CRLF-aware. esbuild-проверено при сборке.
"""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
REL = os.path.join("frontend", "components", "admin", "DocumentsGrid.tsx")
MARKER = "archiveFormat"

PAIRS = [
("state",
 "  const [downloadingZip, setDownloadingZip] = useState(false);",
 "  const [downloadingZip, setDownloadingZip] = useState(false);\n"
 '  const [archiveFormat, setArchiveFormat] = useState<string>("native");  // Pack 60.2'),
("url",
 "      const res = await fetch(\n"
 "        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package`,",
 '      const aqs = archiveFormat && archiveFormat !== "native" ? `?format=${archiveFormat}` : "";\n'
 "      const res = await fetch(\n"
 "        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package${aqs}`,"),
("fname",
 "      _triggerBrowserDownload(blob, `package_${applicationId}.zip`);",
 "      _triggerBrowserDownload(blob, `package_${applicationId}${_pkgSuffix(archiveFormat)}.zip`);"),
("helper",
 "function _triggerBrowserDownload(blob: Blob, filename: string) {",
 'function _pkgSuffix(fmt: string): string {\n'
 '  if (fmt === "pdf") return "_pdf";\n'
 '  if (fmt === "docx") return "_word";\n'
 '  if (fmt === "jpeg" || fmt === "jpg") return "_images";\n'
 '  return "";\n'
 '}\n\n'
 "function _triggerBrowserDownload(blob: Blob, filename: string) {"),
("select",
 '          <button\n'
 '            onClick={handleDownloadZip}\n'
 '            disabled={downloadingZip}\n'
 '            className="px-4 py-1.5 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-1.5"\n'
 '            style={{ background: "var(--color-accent)" }}\n'
 '          >',
 '          <select\n'
 '            value={archiveFormat}\n'
 '            onChange={(e) => setArchiveFormat(e.target.value)}\n'
 '            disabled={downloadingZip}\n'
 '            className="px-2 py-1.5 rounded-md text-sm border text-secondary bg-transparent disabled:opacity-50"\n'
 '            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}\n'
 '            title="\u0424\u043e\u0440\u043c\u0430\u0442 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u043e\u0432 \u0432 \u0430\u0440\u0445\u0438\u0432\u0435"\n'
 '          >\n'
 '            <option value="native">\u041a\u0430\u043a \u0435\u0441\u0442\u044c</option>\n'
 '            <option value="pdf">\u0412\u0441\u0451 \u0432 PDF</option>\n'
 '            <option value="jpeg">\u0412\u0441\u0451 \u0432 \u043a\u0430\u0440\u0442\u0438\u043d\u043a\u0430\u0445</option>\n'
 '            <option value="docx">Word (\u0433\u0434\u0435 \u0435\u0441\u0442\u044c)</option>\n'
 '          </select>\n'
 '          <button\n'
 '            onClick={handleDownloadZip}\n'
 '            disabled={downloadingZip}\n'
 '            className="px-4 py-1.5 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-1.5"\n'
 '            style={{ background: "var(--color-accent)" }}\n'
 '          >'),
]

def main():
    path = os.path.join(ROOT, REL)
    if not os.path.exists(path): print("!!! не найден:", path); sys.exit(1)
    raw = open(path, "rb").read(); crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")
    if MARKER in norm: print("[SKIP] DocumentsGrid.tsx уже пропатчен (archiveFormat)."); return
    if "function _pkgSuffix" not in norm and "FormatButtons" not in norm:
        print("!!! Похоже, Фаза 2 ещё не применена. Сначала apply_docfmt_phase2.py."); sys.exit(4)
    for nm, old, _new in PAIRS:
        c = norm.count(old)
        if c != 1:
            print(f"!!! якорь '{nm}' = {c} (нужно 1). СТОП — файл не тронут.")
            print("    (если из-за правок — пришли свежий raw-дамп DocumentsGrid.tsx)")
            sys.exit(2)
    new = norm
    for nm, old, repl in PAIRS:
        new = new.replace(old, repl, 1)
    open(path + ".bak602f", "wb").write(raw)
    open(path, "wb").write((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print("OK: DocumentsGrid.tsx пропатчен (.bak602f). CRLF:", crlf, "| правок:", len(PAIRS))

if __name__ == "__main__":
    main()
