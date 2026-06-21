#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 60.3 (Фаза 4, DocumentsGrid) — выбор формата для архивов
«Русские формы Word» (docx-пакет) и «Испанские формы» (pdf-формы).
Требует Фазы 2+3 (есть _pkgSuffix). Идемпотентно, .bak603d, CRLF-aware, esbuild-проверено.
"""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
REL = os.path.join("frontend", "components", "admin", "DocumentsGrid.tsx")
MARKER = "docxArchiveFormat"

PAIRS = [
("state",
 "  const [pdfZipDownloaded, setPdfZipDownloaded] = useState(false);",
 "  const [pdfZipDownloaded, setPdfZipDownloaded] = useState(false);\n"
 '  const [docxArchiveFormat, setDocxArchiveFormat] = useState<string>("native");  // Pack 60.3\n'
 '  const [pdfArchiveFormat, setPdfArchiveFormat] = useState<string>("native");  // Pack 60.3'),

("docx-url",
 "      const res = await fetch(\n"
 "        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package-docx`,",
 '      const dqs = docxArchiveFormat && docxArchiveFormat !== "native" ? `?format=${docxArchiveFormat}` : "";\n'
 "      const res = await fetch(\n"
 "        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package-docx${dqs}`,"),
("docx-fname",
 "      _triggerBrowserDownload(blob, `docx_package_${applicationId}.zip`);",
 "      _triggerBrowserDownload(blob, `docx_package_${applicationId}${_pkgSuffix(docxArchiveFormat)}.zip`);"),

("pdf-url",
 "      const res = await fetch(\n"
 "        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package-pdf`,",
 '      const pqs = pdfArchiveFormat && pdfArchiveFormat !== "native" ? `?format=${pdfArchiveFormat}` : "";\n'
 "      const res = await fetch(\n"
 "        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package-pdf${pqs}`,"),
("pdf-fname",
 "      _triggerBrowserDownload(blob, `pdf_forms_${applicationId}.zip`);",
 "      _triggerBrowserDownload(blob, `pdf_forms_${applicationId}${_pkgSuffix(pdfArchiveFormat)}.zip`);"),

("docx-btn",
 '        <button onClick={handleDownloadDocxZip} disabled={downloadingDocxZip}\n'
 '          className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"\n'
 '          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>',
 '        <div className="flex items-center gap-2">\n'
 '        <select value={docxArchiveFormat} onChange={(e) => setDocxArchiveFormat(e.target.value)} disabled={downloadingDocxZip}\n'
 '          className="px-2 py-1.5 rounded-md text-sm border text-secondary bg-transparent disabled:opacity-50"\n'
 '          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }} title="Формат документов в архиве">\n'
 '          <option value="native">Как есть</option>\n'
 '          <option value="pdf">Всё в PDF</option>\n'
 '          <option value="jpeg">Всё в картинках</option>\n'
 '        </select>\n'
 '        <button onClick={handleDownloadDocxZip} disabled={downloadingDocxZip}\n'
 '          className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"\n'
 '          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>'),
("docx-btn-close",
 '            : <><Download className="w-3.5 h-3.5" /><span>Скачать ZIP</span></>}\n'
 '        </button>\n'
 '      </div>',
 '            : <><Download className="w-3.5 h-3.5" /><span>Скачать ZIP</span></>}\n'
 '        </button>\n'
 '        </div>\n'
 '      </div>'),

("pdf-btn",
 '          <button onClick={handleDownloadPdfZip} disabled={downloadingPdfZip}\n'
 '            className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"\n'
 '            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>',
 '          <div className="flex items-center gap-2">\n'
 '          <select value={pdfArchiveFormat} onChange={(e) => setPdfArchiveFormat(e.target.value)} disabled={downloadingPdfZip}\n'
 '            className="px-2 py-1.5 rounded-md text-sm border text-secondary bg-transparent disabled:opacity-50"\n'
 '            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }} title="Формат форм в архиве">\n'
 '            <option value="native">Как есть</option>\n'
 '            <option value="jpeg">В картинках</option>\n'
 '          </select>\n'
 '          <button onClick={handleDownloadPdfZip} disabled={downloadingPdfZip}\n'
 '            className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"\n'
 '            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>'),
("pdf-btn-close",
 '              : <><Download className="w-3.5 h-3.5" /><span>Скачать ZIP</span></>}\n'
 '          </button>\n'
 '        </div>',
 '              : <><Download className="w-3.5 h-3.5" /><span>Скачать ZIP</span></>}\n'
 '          </button>\n'
 '          </div>\n'
 '        </div>'),
]

def main():
    path = os.path.join(ROOT, REL)
    if not os.path.exists(path): print("!!! не найден:", path); sys.exit(1)
    raw = open(path, "rb").read(); crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")
    if MARKER in norm: print("[SKIP] DocumentsGrid.tsx уже пропатчен (docxArchiveFormat)."); return
    if "_pkgSuffix" not in norm:
        print("!!! Нет _pkgSuffix — сначала Фаза 3 (apply_docfmt_phase3_front.py)."); sys.exit(4)
    for nm, old, _n in PAIRS:
        c = norm.count(old)
        if c != 1:
            print(f"!!! якорь '{nm}' = {c} (нужно 1). СТОП — файл не тронут.")
            print("    (если из-за кодировки — пришли свежий raw-дамп DocumentsGrid.tsx)")
            sys.exit(2)
    new = norm
    for nm, old, repl in PAIRS: new = new.replace(old, repl, 1)
    open(path + ".bak603d", "wb").write(raw)
    open(path, "wb").write((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print("OK: DocumentsGrid.tsx пропатчен (.bak603d). CRLF:", crlf, "| правок:", len(PAIRS))

if __name__ == "__main__":
    main()
