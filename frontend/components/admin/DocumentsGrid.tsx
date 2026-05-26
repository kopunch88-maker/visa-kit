"use client";

import { useState } from "react";
import { Download, Loader2, Check, RefreshCw } from "lucide-react";
import { API_BASE_URL, getToken } from "@/lib/api";
// Pack 29.4
import { ContractTemplatePickerModal } from "./ContractTemplatePickerModal";

interface Props {
  applicationId: number;
  // Pack 29.4 — для модалки выбора шаблона при перегенерации
  companyId?: number | null;
  // Pack 50.7-C — для фильтрации naim-карточек
  applicationType?: string | null;
}

type DocItem = {
  id: string;
  filename: string;
  kind: "docx" | "pdf";
  // Pack 50.7-C — карточка видна только для EMPLOYMENT-заявок
  naimOnly?: boolean;
  // Pack 50.1-F3 — карточка видна только для SELF_EMPLOYED-заявок
  selfEmployedOnly?: boolean;
};

const DOCUMENTS: DocItem[] = [
  { id: "contract",            filename: "01_Договор.docx",                        kind: "docx", selfEmployedOnly: true },
  { id: "act_1",               filename: "02_Акт_1.docx",                          kind: "docx", selfEmployedOnly: true },
  { id: "act_2",               filename: "03_Акт_2.docx",                          kind: "docx", selfEmployedOnly: true },
  { id: "act_3",               filename: "04_Акт_3.docx",                          kind: "docx", selfEmployedOnly: true },
  { id: "invoice_1",           filename: "05_Счёт_1.docx",                    kind: "docx", selfEmployedOnly: true },
  { id: "invoice_2",           filename: "06_Счёт_2.docx",                    kind: "docx", selfEmployedOnly: true },
  { id: "invoice_3",           filename: "07_Счёт_3.docx",                    kind: "docx", selfEmployedOnly: true },
  { id: "employer_letter",     filename: "08_Письмо.docx",          kind: "docx", selfEmployedOnly: true },
  { id: "cv",                  filename: "09_Резюме.docx",          kind: "docx" },
  { id: "bank_statement",      filename: "10_Выписка.docx",    kind: "docx" },
  { id: "mi_t",                filename: "11_MI-T.pdf",                                           kind: "pdf"  },
  { id: "designacion",         filename: "12_Designacion_representante.pdf",                      kind: "pdf"  },
  { id: "compromiso",          filename: "13_Compromiso_RETA.pdf",                                kind: "pdf"  },
  { id: "declaracion",         filename: "14_Declaracion_antecedentes.pdf",                       kind: "pdf"  },
  // Pack 36.1 — TIE формы (только если у заявки заполнены NIE и fingerprint_date)
  { id: "mi_tie",              filename: "15_MI-TIE.pdf",                                         kind: "pdf"  },
  { id: "ex17",                filename: "16_EX-17.pdf",                                          kind: "pdf"  },
  { id: "npd_certificate",     filename: "15_Справка_НПД.docx",       kind: "docx", selfEmployedOnly: true },
  { id: "npd_certificate_lkn", filename: "15b_Справка_НПД_ЛКН.docx",   kind: "docx", selfEmployedOnly: true },
  { id: "apostille",           filename: "16_Апостиль.docx",         kind: "docx", selfEmployedOnly: true },
  // Pack 40.0-G — Техническое заключение
  { id: "tech_opinion",        filename: "17_Техническое_заключение.docx", kind: "docx", selfEmployedOnly: true },
  // Pack 50.7-C — Приказ Т-9 о командировке (только для EMPLOYMENT)
  { id: "business_trip_order", filename: "17_Приказ_на_командировку.docx", kind: "docx", naimOnly: true },
  // Pack 50.1-C — Трудовой договор (только для EMPLOYMENT)
  { id: "employment_contract", filename: "01_Трудовой_договор.docx",        kind: "docx", naimOnly: true },
];

export function DocumentsGrid({ applicationId, companyId, applicationType }: Props) {
  // Pack 50.7-C + 50.1-F3 — фильтр карточек по типу заявки.
  // naimOnly: видна только при EMPLOYMENT. selfEmployedOnly: скрыта при EMPLOYMENT.
  const visibleDocs = DOCUMENTS.filter((d) => {
    if (d.naimOnly && applicationType !== "EMPLOYMENT") return false;
    if (d.selfEmployedOnly && applicationType === "EMPLOYMENT") return false;
    return true;
  });
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [zipDownloaded, setZipDownloaded] = useState(false);
  const [downloadingDocxZip, setDownloadingDocxZip] = useState(false);
  const [docxZipDownloaded, setDocxZipDownloaded] = useState(false);
  const [downloadingPdfZip, setDownloadingPdfZip] = useState(false);
  const [pdfZipDownloaded, setPdfZipDownloaded] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Pack 29.4 тАФ ╤Б╨╛╤Б╤В╨╛╤П╨╜╨╕╨╡ ╨╝╨╛╨┤╨░╨╗╨║╨╕ ╨▓╤Л╨▒╨╛╤А╨░ ╤И╨░╨▒╨╗╨╛╨╜╨░ ╨┐╤А╨╕ 409 NEEDS_CONTRACT_TEMPLATE
  const [pickerState, setPickerState] = useState<{
    isOpen: boolean;
    companyId: number;
    companyShortName: string;
    onSaved: () => void;
  } | null>(null);

  // Pack 29.4 тАФ ╨┐╤А╨╛╨▓╨╡╤А╨║╨░ 409 NEEDS_CONTRACT_TEMPLATE
  // ╨Т╨╛╨╖╨▓╤А╨░╤Й╨░╨╡╤В true ╨╡╤Б╨╗╨╕ ╨╛╤В╨║╤А╤Л╨╗╨╕ ╨╝╨╛╨┤╨░╨╗╨║╤Г (╨╜╤Г╨╢╨╜╨╛ ╨┐╤А╨╡╤А╨▓╨░╤В╤М ╨╛╨▒╤А╨░╨▒╨╛╤В╨║╤Г), false ╨╡╤Б╨╗╨╕ 409 ╨╜╨╡ ╨┐╤А╨╕╤И╨╗╨░
  async function handle409IfNeedsTemplate(res: Response, retryFn: () => void): Promise<boolean> {
    if (res.status !== 409) return false;
    let detail: any;
    try {
      const json = await res.json();
      detail = json.detail;
    } catch {
      return false;
    }
    if (!detail || detail.code !== "NEEDS_CONTRACT_TEMPLATE") return false;
    setPickerState({
      isOpen: true,
      companyId: detail.company_id,
      companyShortName: detail.company_short_name || `id=${detail.company_id}`,
      onSaved: retryFn,
    });
    return true;
  }

  async function handleDownloadZip() {
    setDownloadingZip(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      // Pack 29.4 тАФ ╨╛╨▒╤А╨░╨▒╨╛╤В╨║╨░ 409 NEEDS_CONTRACT_TEMPLATE
      if (await handle409IfNeedsTemplate(res, () => handleDownloadZip())) {
        return;
      }
      if (!res.ok) throw new Error(`╨Ю╤И╨╕╨▒╨║╨░ ${res.status}: ${await res.text()}`);

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

  async function handleDownloadDocxZip() {
    setDownloadingDocxZip(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package-docx`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);
      const blob = await res.blob();
      _triggerBrowserDownload(blob, `docx_package_${applicationId}.zip`);
      setDocxZipDownloaded(true);
      setTimeout(() => setDocxZipDownloaded(false), 3000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloadingDocxZip(false);
    }
  }

  async function handleDownloadPdfZip() {
    setDownloadingPdfZip(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package-pdf`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);
      const blob = await res.blob();
      _triggerBrowserDownload(blob, `pdf_forms_${applicationId}.zip`);
      setPdfZipDownloaded(true);
      setTimeout(() => setPdfZipDownloaded(false), 3000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloadingPdfZip(false);
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
      // Pack 29.4 тАФ ╨╛╨▒╤А╨░╨▒╨╛╤В╨║╨░ 409 NEEDS_CONTRACT_TEMPLATE
      if (await handle409IfNeedsTemplate(res, () => handleDownloadOne(doc))) {
        return;
      }
      if (!res.ok) throw new Error(`╨Ю╤И╨╕╨▒╨║╨░ ${res.status}: ${await res.text()}`);

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
      <div className="flex items-center justify-end mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownloadZip}
            disabled={downloadingZip}
            className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
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
                Скачать всё
              </>
            )}
          </button>
        </div>
      </div>
      <div className="border rounded-xl p-4" style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary">
          Русские формы Word ({visibleDocs.filter(d => d.kind === "docx").length})
        </h3>
        <button onClick={handleDownloadDocxZip} disabled={downloadingDocxZip}
          className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
          {downloadingDocxZip
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Генерация...</span></>
            : docxZipDownloaded
            ? <><Check className="w-3.5 h-3.5" /><span>Скачано</span></>
            : <><Download className="w-3.5 h-3.5" /><span>Скачать ZIP</span></>}
        </button>
      </div>

      {error && (
        <div className="mb-3 bg-danger text-danger text-sm p-3 rounded-md">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {visibleDocs.filter(d => d.kind === "docx").map((doc) => {
          const isDownloading = downloadingId === doc.id;
          return (
            <button key={doc.id} onClick={() => handleDownloadOne(doc)} disabled={isDownloading}
              className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left transition-colors hover:opacity-80 disabled:opacity-60 disabled:cursor-wait"
              style={{ background: "var(--color-bg-secondary)" }}>
              <div className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0 text-[10px] font-semibold"
                style={{ background: "var(--color-bg-info)", color: "var(--color-text-info)" }}>DOC</div>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-primary line-clamp-1">{doc.filename}</div>
                <div className="text-xs text-tertiary">{isDownloading ? "Скачивание..." : "клик для скачивания"}</div>
              </div>
              {isDownloading ? <Loader2 className="w-4 h-4 animate-spin text-tertiary flex-shrink-0" /> : <Download className="w-4 h-4 text-tertiary flex-shrink-0 opacity-50" />}
            </button>
          );
        })}
      </div>
      </div>
      <div className="mt-4 border rounded-xl p-4" style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary">
            Испанские PDF формы ({visibleDocs.filter(d => d.kind === "pdf").length})
          </h3>
          <button onClick={handleDownloadPdfZip} disabled={downloadingPdfZip}
            className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
            {downloadingPdfZip
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Генерация...</span></>
              : pdfZipDownloaded
              ? <><Check className="w-3.5 h-3.5" /><span>Скачано</span></>
              : <><Download className="w-3.5 h-3.5" /><span>Скачать ZIP</span></>}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {visibleDocs.filter(d => d.kind === "pdf").map((doc) => {
            const isDownloading = downloadingId === doc.id;
            return (
              <button key={doc.id} onClick={() => handleDownloadOne(doc)} disabled={isDownloading}
                className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left transition-colors hover:opacity-80 disabled:opacity-60 disabled:cursor-wait"
                style={{ background: "var(--color-bg-secondary)" }}>
                <div className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0 text-[10px] font-semibold"
                  style={{ background: "var(--color-bg-danger)", color: "var(--color-text-danger)" }}>PDF</div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-primary line-clamp-1">{doc.filename}</div>
                  <div className="text-xs text-tertiary">{isDownloading ? "Скачивание..." : "клик для скачивания"}</div>
                </div>
                {isDownloading ? <Loader2 className="w-4 h-4 animate-spin text-tertiary flex-shrink-0" /> : <Download className="w-4 h-4 text-tertiary flex-shrink-0 opacity-50" />}
              </button>
            );
          })}
        </div>
      </div>

            {/* Pack 29.4 тАФ ╨Ь╨╛╨┤╨░╨╗╨║╨░ ╨▓╤Л╨▒╨╛╤А╨░ ╤И╨░╨▒╨╗╨╛╨╜╨░ Перегенерировать▓╨╛╤А╨░ ╨┐╤А╨╕ 409 */}
      {pickerState && pickerState.isOpen && (
        <ContractTemplatePickerModal
          companyId={pickerState.companyId}
          companyShortName={pickerState.companyShortName}
          onClose={() => setPickerState(null)}
          onSaved={() => {
            const retry = pickerState.onSaved;
            setPickerState(null);
            // ╨Э╨╡╨▒╨╛╨╗╤М╤И╨░╤П ╨╖╨░╨┤╨╡╤А╨╢╨║╨░ ╤З╤В╨╛╨▒╤Л UI ╨╖╨░╨║╤А╤Л╨╗ ╨╝╨╛╨┤╨░╨╗╨║╤Г ╨┐╨╡╤А╨╡╨┤ ╨┐╨╛╨▓╤В╨╛╤А╨╜╨╛╨╣ ╨┐╨╛╨┐╤Л╤В╨║╨╛╨╣
            setTimeout(() => retry(), 100);
          }}
        />
      )}
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
