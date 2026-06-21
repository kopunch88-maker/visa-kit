#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 60.3 (Фаза 4, ES-перевод) — фронт.
  lib/api.ts                 : downloadTranslationFile / downloadTranslationsZip + format
  TranslationPanel.tsx       : 3 формата на документ (Word/PDF/JPG) + селектор у архива
Идемпотентно, .bak603t, CRLF-aware, esbuild-проверено (TranslationPanel).
"""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))

def _patch(rel, pairs, marker, must_have=None):
    path = os.path.join(ROOT, *rel.split("/"))
    if not os.path.exists(path): print("!!! не найден:", path); sys.exit(1)
    raw = open(path, "rb").read(); crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")
    if marker in norm: print(f"[SKIP] {rel} уже пропатчен ({marker})."); return
    if must_have and must_have not in norm:
        print(f"!!! [{rel}] нет '{must_have}' — проверь порядок фаз."); sys.exit(4)
    for nm, old, _n in pairs:
        c = norm.count(old)
        if c != 1:
            print(f"!!! [{rel}] якорь '{nm}' = {c} (нужно 1). СТОП.")
            print("    (если из-за кодировки — пришли свежий raw-дамп этого файла)")
            sys.exit(2)
    new = norm
    for nm, old, repl in pairs: new = new.replace(old, repl, 1)
    open(path + ".bak603t", "wb").write(raw)
    open(path, "wb").write((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print(f"OK: {rel} пропатчен (.bak603t). CRLF: {crlf} | правок: {len(pairs)}")

API_PAIRS = [
("zip-fn",
 "export async function downloadTranslationsZip(applicationId: number): Promise<Blob> {\n"
 "  const res = await fetch(\n"
 "    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations/zip`,",
 'export async function downloadTranslationsZip(applicationId: number, format: string = "native"): Promise<Blob> {\n'
 '  const _qs = format && format !== "native" ? `?format=${format}` : "";\n'
 "  const res = await fetch(\n"
 "    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations/zip${_qs}`,"),
("one-fn",
 "export async function downloadTranslationFile(\n"
 "  applicationId: number,\n"
 "  kind: TranslationKind,\n"
 "): Promise<Blob> {\n"
 "  const res = await fetch(\n"
 "    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations/${kind}/download`,",
 "export async function downloadTranslationFile(\n"
 "  applicationId: number,\n"
 "  kind: TranslationKind,\n"
 '  format: string = "native",\n'
 "): Promise<Blob> {\n"
 '  const _qs = format && format !== "native" ? `?format=${format}` : "";\n'
 "  const res = await fetch(\n"
 "    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations/${kind}/download${_qs}`,"),
]

HELPERS = (
'function _esName(name: string, fmt: string): string {\n'
'  const base = name.replace(/\\.[^.]+$/, "");\n'
'  if (fmt === "pdf") return base + ".pdf";\n'
'  if (fmt === "jpeg" || fmt === "jpg") return base + "_images.zip";\n'
'  return name;\n'
'}\n'
'function _esPkgSuffix(fmt: string): string {\n'
'  if (fmt === "pdf") return "_pdf";\n'
'  if (fmt === "jpeg" || fmt === "jpg") return "_images";\n'
'  return "";\n'
'}\n'
'function EsFormatButtons({ downloading, onPick }: { downloading: boolean; onPick: (fmt: string) => void }) {\n'
'  const items = [\n'
'    { key: "docx", label: "Word" },\n'
'    { key: "pdf", label: "PDF" },\n'
'    { key: "jpeg", label: "JPG" },\n'
'  ];\n'
'  return (\n'
'    <div className="flex gap-1">\n'
'      {items.map((it) => (\n'
'        <button\n'
'          key={it.key}\n'
'          type="button"\n'
'          disabled={downloading}\n'
'          onClick={() => onPick(it.key)}\n'
'          title={`Скачать: ${it.label}`}\n'
'          className="px-2 py-1 rounded-md text-xs border transition-colors hover:opacity-80 disabled:opacity-50 flex items-center gap-1"\n'
'          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}\n'
'        >\n'
'          <Download className="w-3 h-3" />{it.label}\n'
'        </button>\n'
'      ))}\n'
'    </div>\n'
'  );\n'
'}\n\n'
)

TP_PAIRS = [
("state",
 "  const [downloadingZip, setDownloadingZip] = useState(false);",
 "  const [downloadingZip, setDownloadingZip] = useState(false);\n"
 '  const [archiveFormat, setArchiveFormat] = useState<string>("native");  // Pack 60.3'),
("helpers",
 "function _triggerBrowserDownload(blob: Blob, filename: string) {",
 HELPERS + "function _triggerBrowserDownload(blob: Blob, filename: string) {"),
("one-handler",
 "  async function handleDownloadOne(item: TranslationItem) {\n"
 "    setDownloadingId(item.kind);\n"
 "    setError(null);\n"
 "    try {\n"
 "      const blob = await downloadTranslationFile(applicationId, item.kind);\n"
 "      const filename = item.file_name || TRANSLATION_KIND_INFO[item.kind].es_filename;\n"
 "      _triggerBrowserDownload(blob, filename);",
 '  async function handleDownloadOne(item: TranslationItem, fmt: string = "native") {\n'
 "    setDownloadingId(item.kind);\n"
 "    setError(null);\n"
 "    try {\n"
 "      const blob = await downloadTranslationFile(applicationId, item.kind, fmt);\n"
 "      const baseName = item.file_name || TRANSLATION_KIND_INFO[item.kind].es_filename;\n"
 "      _triggerBrowserDownload(blob, _esName(baseName, fmt));"),
("zip-handler",
 "      const blob = await downloadTranslationsZip(applicationId);\n"
 "      _triggerBrowserDownload(blob, `translations_${applicationId}.zip`);",
 "      const blob = await downloadTranslationsZip(applicationId, archiveFormat);\n"
 "      _triggerBrowserDownload(blob, `translations_${applicationId}${_esPkgSuffix(archiveFormat)}.zip`);"),
("archive-open",
 "              {(summary?.done ?? 0) > 0 && (\n"
 "                <button\n"
 "                  onClick={handleDownloadZip}\n"
 "                  disabled={downloadingZip || busy}",
 "              {(summary?.done ?? 0) > 0 && (\n"
 "                <>\n"
 "                <select value={archiveFormat} onChange={(e) => setArchiveFormat(e.target.value)} disabled={downloadingZip || busy}\n"
 '                  className="px-2 py-1.5 rounded-md text-sm border text-secondary bg-transparent disabled:opacity-50"\n'
 '                  style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }} title="Формат документов в архиве">\n'
 '                  <option value="native">Как есть (Word)</option>\n'
 '                  <option value="pdf">Всё в PDF</option>\n'
 '                  <option value="jpeg">Всё в картинках</option>\n'
 "                </select>\n"
 "                <button\n"
 "                  onClick={handleDownloadZip}\n"
 "                  disabled={downloadingZip || busy}"),
("archive-close",
 "                </button>\n"
 "              )}\n"
 "              <button\n"
 "                onClick={handleRetranslateAll}",
 "                </button>\n"
 "                </>\n"
 "              )}\n"
 "              <button\n"
 "                onClick={handleRetranslateAll}"),
("rowprops",
 "  onDownload: () => void;",
 "  onDownload: (fmt: string) => void;"),
("mapcall",
 "              onDownload={() => handleDownloadOne(item)}",
 "              onDownload={(fmt) => handleDownloadOne(item, fmt)}"),
("row-btn",
 "        {isDone && (\n"
 "          <button\n"
 "            onClick={onDownload}\n"
 "            disabled={isDownloading || busy}\n"
 '            className="p-1.5 rounded hover:bg-primary disabled:opacity-50 transition-colors"\n'
 '            title="Скачать"\n'
 "          >\n"
 "            {isDownloading ? (\n"
 '              <Loader2 className="w-4 h-4 animate-spin text-tertiary" />\n'
 "            ) : (\n"
 '              <Download className="w-4 h-4 text-tertiary" />\n'
 "            )}\n"
 "          </button>\n"
 "        )}",
 "        {isDone && (\n"
 "          <EsFormatButtons downloading={isDownloading || busy} onPick={onDownload} />\n"
 "        )}"),
]

if __name__ == "__main__":
    _patch("frontend/lib/api.ts", API_PAIRS, "applicationId: number, format: string")
    _patch("frontend/components/admin/TranslationPanel.tsx", TP_PAIRS, "archiveFormat")
    print("\nГотово (Фаза 4c). Перевод: 3 формата на документ + формат архива.")
