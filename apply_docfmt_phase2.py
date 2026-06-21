#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 60.1 (Фаза 2) — фронт: три иконки формата на каждой строке документа.
frontend/components/admin/DocumentsGrid.tsx
  - handleDownloadOne(doc, fmt) — ?format=, имя файла под формат (_images.zip для JPG)
  - хелперы _downloadName + компонент FormatButtons (Word серый при kind:"pdf")
  - плитки docx/pdf: <button>(вся плитка-кнопка) → <div> + <FormatButtons/>
Все якоря ASCII (русские строки файла не трогаются → кодировка не мешает).
Идемпотентно, .bak601, CRLF-aware. Синтаксис результата проверен esbuild на этапе сборки.
"""
import os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REL = os.path.join("frontend", "components", "admin", "DocumentsGrid.tsx")
MARKER = "function FormatButtons("

HELPERS = (
'function _downloadName(nativeName: string, fmt: string): string {\n'
'  const base = nativeName.replace(/\\.[^.]+$/, "");\n'
'  if (fmt === "pdf") return base + ".pdf";\n'
'  if (fmt === "docx") return base + ".docx";\n'
'  if (fmt === "jpeg" || fmt === "jpg") return base + "_images.zip";\n'
'  return nativeName;\n'
'}\n'
'\n'
'function FormatButtons({ doc, downloading, onPick }: { doc: DocItem; downloading: boolean; onPick: (fmt: string) => void }) {\n'
'  const wordOk = doc.kind === "docx";\n'
'  const items: { key: string; label: string; ok: boolean }[] = [\n'
'    { key: "docx", label: "Word", ok: wordOk },\n'
'    { key: "pdf", label: "PDF", ok: true },\n'
'    { key: "jpeg", label: "JPG", ok: true },\n'
'  ];\n'
'  return (\n'
'    <div className="flex gap-1 flex-shrink-0">\n'
'      {items.map((it) => (\n'
'        <button\n'
'          key={it.key}\n'
'          type="button"\n'
'          disabled={!it.ok || downloading}\n'
'          onClick={(e) => { e.stopPropagation(); onPick(it.key); }}\n'
'          title={it.ok ? `\u0421\u043a\u0430\u0447\u0430\u0442\u044c: ${it.label}` : "\u041d\u0435\u0442 Word-\u0438\u0441\u0445\u043e\u0434\u043d\u0438\u043a\u0430 \u2014 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0438\u0437\u043d\u0430\u0447\u0430\u043b\u044c\u043d\u043e PDF"}\n'
'          className="px-2 py-1 rounded-md text-xs border transition-colors hover:opacity-80 disabled:cursor-not-allowed flex items-center gap-1"\n'
'          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5, opacity: it.ok ? 1 : 0.4 }}\n'
'        >\n'
'          <Download className="w-3 h-3" />{it.label}\n'
'        </button>\n'
'      ))}\n'
'    </div>\n'
'  );\n'
'}\n'
'\n'
)

PAIRS = [
("sig",
 "  async function handleDownloadOne(doc: DocItem) {",
 '  async function handleDownloadOne(doc: DocItem, fmt: string = "native") {'),
("url",
 "      const res = await fetch(\n"
 "        `${API_BASE_URL}/api/admin/applications/${applicationId}/download-file/${doc.id}`,",
 '      const qs = fmt && fmt !== "native" ? `?format=${fmt}` : "";\n'
 "      const res = await fetch(\n"
 "        `${API_BASE_URL}/api/admin/applications/${applicationId}/download-file/${doc.id}${qs}`,"),
("retry",
 "() => handleDownloadOne(doc))",
 "() => handleDownloadOne(doc, fmt))"),
("dlname",
 "      _triggerBrowserDownload(blob, doc.filename);",
 "      _triggerBrowserDownload(blob, _downloadName(doc.filename, fmt));"),
("helpers",
 "function _triggerBrowserDownload(blob: Blob, filename: string) {",
 HELPERS + "function _triggerBrowserDownload(blob: Blob, filename: string) {"),
("docx-open",
 '            <button key={doc.id} onClick={() => handleDownloadOne(doc)} disabled={isDownloading}\n'
 '              className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left transition-colors hover:opacity-80 disabled:opacity-60 disabled:cursor-wait"\n'
 '              style={{ background: "var(--color-bg-secondary)", border: !seenKeys.has(doc.id) ? "1.5px solid var(--color-accent)" : "1.5px solid transparent" }}>\n'
 '              <NewDot seen={seenKeys.has(doc.id)} onToggle={() => toggleSeen(doc.id)} />',
 '            <div key={doc.id}\n'
 '              className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left"\n'
 '              style={{ background: "var(--color-bg-secondary)", border: !seenKeys.has(doc.id) ? "1.5px solid var(--color-accent)" : "1.5px solid transparent", opacity: isDownloading ? 0.6 : 1 }}>\n'
 '              <NewDot seen={seenKeys.has(doc.id)} onToggle={() => toggleSeen(doc.id)} />'),
("docx-tail",
 '              {isDownloading ? <Loader2 className="w-4 h-4 animate-spin text-tertiary flex-shrink-0" /> : <Download className="w-4 h-4 text-tertiary flex-shrink-0 opacity-50" />}\n'
 '            </button>',
 '              <FormatButtons doc={doc} downloading={isDownloading} onPick={(fmt) => handleDownloadOne(doc, fmt)} />\n'
 '            </div>'),
("pdf-open",
 "              <button key={doc.id} onClick={() => handleDownloadOne(doc)} disabled={isDownloading || tieBlocked}",
 "              <div key={doc.id}"),
("pdf-cls",
 '                className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left transition-colors hover:opacity-80 disabled:opacity-60 disabled:cursor-not-allowed"\n'
 '                style={{ background: "var(--color-bg-secondary)", border: !seenKeys.has(doc.id) ? "1.5px solid var(--color-accent)" : "1.5px solid transparent" }}>',
 '                className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left"\n'
 '                style={{ background: "var(--color-bg-secondary)", border: !seenKeys.has(doc.id) ? "1.5px solid var(--color-accent)" : "1.5px solid transparent", opacity: (isDownloading || tieBlocked) ? 0.6 : 1 }}>'),
("pdf-tail",
 '                {isDownloading ? <Loader2 className="w-4 h-4 animate-spin text-tertiary flex-shrink-0" /> : <Download className="w-4 h-4 text-tertiary flex-shrink-0 opacity-50" />}\n'
 '              </button>',
 '                <FormatButtons doc={doc} downloading={isDownloading || tieBlocked} onPick={(fmt) => handleDownloadOne(doc, fmt)} />\n'
 '              </div>'),
]

def main():
    path = os.path.join(ROOT, REL)
    if not os.path.exists(path): print("!!! не найден:", path); sys.exit(1)
    raw = open(path, "rb").read(); crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")
    if MARKER in norm: print("[SKIP] DocumentsGrid.tsx уже пропатчен (FormatButtons)."); return
    for nm, old, _new in PAIRS:
        c = norm.count(old)
        if c != 1:
            print(f"!!! якорь '{nm}' найден {c} раз (нужно 1). СТОП — файл не тронут.")
            print("    (возможно из-за кодировки/правок — пришли свежий raw-дамп DocumentsGrid.tsx)")
            sys.exit(2)
    new = norm
    for nm, old, repl in PAIRS:
        new = new.replace(old, repl, 1)
    out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
    open(path + ".bak601", "wb").write(raw)
    open(path, "wb").write(out)
    print("OK: DocumentsGrid.tsx пропатчен (.bak601). CRLF:", crlf, "| правок:", len(PAIRS))

if __name__ == "__main__":
    main()
