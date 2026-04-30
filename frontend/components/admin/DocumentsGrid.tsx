"use client";

import { useState } from "react";
import { Download, Loader2, Check, RefreshCw } from "lucide-react";
import { API_BASE_URL, getToken } from "@/lib/api";

interface Props {
  applicationId: number;
}

type DocItem = {
  id: string;        // используется в URL endpoint
  filename: string;  // что показываем в карточке
  kind: "docx" | "pdf";
};

const DOCUMENTS: DocItem[] = [
  { id: "contract",        filename: "01_Договор.docx",                          kind: "docx" },
  { id: "act_1",           filename: "02_Акт_1.docx",                            kind: "docx" },
  { id: "act_2",           filename: "03_Акт_2.docx",                            kind: "docx" },
  { id: "act_3",           filename: "04_Акт_3.docx",                            kind: "docx" },
  { id: "invoice_1",       filename: "05_Счёт_1.docx",                           kind: "docx" },
  { id: "invoice_2",       filename: "06_Счёт_2.docx",                           kind: "docx" },
  { id: "invoice_3",       filename: "07_Счёт_3.docx",                           kind: "docx" },
  { id: "employer_letter", filename: "08_Письмо.docx",                           kind: "docx" },
  { id: "cv",              filename: "09_Резюме.docx",                           kind: "docx" },
  { id: "bank_statement",  filename: "10_Выписка.docx",                          kind: "docx" },
  // Pack 9 — испанские PDF-формы
  { id: "mi_t",            filename: "11_MI-T.pdf",                              kind: "pdf"  },
  { id: "designacion",     filename: "12_Designacion_representante.pdf",         kind: "pdf"  },
  { id: "compromiso",      filename: "13_Compromiso_RETA.pdf",                   kind: "pdf"  },
  { id: "declaracion",     filename: "14_Declaracion_antecedentes.pdf",          kind: "pdf"  },
];

export function DocumentsGrid({ applicationId }: Props) {
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [zipDownloaded, setZipDownloaded] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDownloadZip() {
    setDownloadingZip(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);

      const blob = await res.blob();
      _triggerBrowserDownload(blob, `package_${applicationId}.zip`);

      setZipDownloaded(true);
      setTimeout(() => setZipDownloaded(false), 3000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloadingZip(false);
    }
  }

  async function handleDownloadOne(doc: DocItem) {
    setDownloadingId(doc.id);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${applicationId}/download-file/${doc.id}`,
        { method: "GET", headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);

      const blob = await res.blob();
      _triggerBrowserDownload(blob, doc.filename);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary">
          Документы пакета ({DOCUMENTS.length})
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownloadZip}
            disabled={downloadingZip}
            className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
            title="Перегенерировать"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${downloadingZip ? "animate-spin" : ""}`} />
            Перегенерировать
          </button>
          <button
            onClick={handleDownloadZip}
            disabled={downloadingZip}
            className="px-4 py-1.5 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{ background: "var(--color-accent)" }}
          >
            {downloadingZip ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Генерация...
              </>
            ) : zipDownloaded ? (
              <>
                <Check className="w-3.5 h-3.5" />
                Скачано
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                Скачать ZIP
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 bg-danger text-danger text-sm p-3 rounded-md">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {DOCUMENTS.map((doc) => {
          const isDownloading = downloadingId === doc.id;
          const isPdf = doc.kind === "pdf";
          return (
            <button
              key={doc.id}
              onClick={() => handleDownloadOne(doc)}
              disabled={isDownloading}
              className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left transition-colors hover:opacity-80 disabled:opacity-60 disabled:cursor-wait"
              style={{ background: "var(--color-bg-secondary)" }}
              title={`Скачать ${doc.filename}`}
            >
              <div
                className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0 text-[10px] font-semibold"
                style={
                  isPdf
                    ? {
                        background: "var(--color-bg-danger)",
                        color: "var(--color-text-danger)",
                      }
                    : {
                        background: "var(--color-bg-info)",
                        color: "var(--color-text-info)",
                      }
                }
              >
                {isPdf ? "PDF" : "DOC"}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-primary line-clamp-1">{doc.filename}</div>
                <div className="text-xs text-tertiary">
                  {isDownloading ? "Скачивание..." : "клик для скачивания"}
                </div>
              </div>
              {isDownloading ? (
                <Loader2 className="w-4 h-4 animate-spin text-tertiary flex-shrink-0" />
              ) : (
                <Download className="w-4 h-4 text-tertiary flex-shrink-0 opacity-50" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function _triggerBrowserDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
