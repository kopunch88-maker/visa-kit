"use client";

import { useState, useEffect } from "react";  // Pack 50.41
import { Download, Loader2, Check, RefreshCw } from "lucide-react";
import { API_BASE_URL, getToken } from "@/lib/api";
import { getDocViewState, markDocsSeen, markDocsUnseen } from "@/lib/api"; // Pack 50.41
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
  { id: "employment_contract", filename: "01_Трудовой_договор.docx",        kind: "docx", naimOnly: true },  // Pack 50.10-G swap
  { id: "bank_statement",      filename: "10_Выписка.docx",    kind: "docx" },
  { id: "mi_t",                filename: "11_MI-T.pdf",                                           kind: "pdf"  },
  { id: "designacion",         filename: "12_Designacion_representante.pdf",                      kind: "pdf"  },
  { id: "compromiso",          filename: "13_Compromiso_RETA.pdf",                                kind: "pdf", selfEmployedOnly: true },  // Pack 50.19
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
  { id: "cv",                  filename: "09_Резюме.docx",          kind: "docx" },
  // Pack 50.8-D — Справка 2-НДФЛ (только для EMPLOYMENT)
  { id: "ndfl_2",              filename: "18_2-НДФЛ.docx",                  kind: "docx", naimOnly: true },
  // Pack 50.9-D — Справка СТД-Р (только для EMPLOYMENT)
  { id: "stdr",                filename: "19_СТД-Р.docx",                   kind: "docx", naimOnly: true },
  // Pack 50.10-E — Расчётный листок ×3 за 3 предыдущих месяца (только для EMPLOYMENT)
  { id: "payslip_1",           filename: "20_Расчётный_листок_1.docx",      kind: "docx", naimOnly: true },
  { id: "payslip_2",           filename: "21_Расчётный_листок_2.docx",      kind: "docx", naimOnly: true },
  { id: "payslip_3",           filename: "22_Расчётный_листок_3.docx",      kind: "docx", naimOnly: true },
  { id: "employer_letter_naim", filename: "23_Письмо_работодателя.docx", kind: "docx", naimOnly: true },  // Pack 50.11-C
  { id: "soo", filename: "24_Свидетельство_об_отъезде.docx", kind: "docx", naimOnly: true },  // Pack 50.12-E
  { id: "apostille_sfr", filename: "25_Апостиль_СФР.docx", kind: "docx", naimOnly: true },  // Pack 50.20
];

export function DocumentsGrid({ applicationId, companyId, applicationType }: Props) {
  // Pack 52: bank_statement — для v2-заявок (bank_template_legacy_v1=false) карточка
  // отрисуется как «10_Выписка.pdf» с PDF-иконкой; backend тоже отдаёт PDF.
  // Тянем флаг с бэка асинхронно. До получения ответа считаем legacy (DOCX) —
  // на v2-заявке после fetch перерисуется в PDF.
  const [bankIsV2, setBankIsV2] = useState<boolean>(false);
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/admin/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.bank_template_legacy_v1 === false) {
          setBankIsV2(true);
        }
      })
      .catch(() => {});
  }, [applicationId]);

  // Pack 50.7-C + 50.1-F3 — фильтр карточек по типу заявки.
  // naimOnly: видна только при EMPLOYMENT. selfEmployedOnly: скрыта при EMPLOYMENT.
  const visibleDocs = DOCUMENTS.filter((d) => {
    if (d.naimOnly && applicationType !== "EMPLOYMENT") return false;
    if (d.selfEmployedOnly && applicationType === "EMPLOYMENT") return false;
    return true;
  }).map((d) => {
    // Pack 52: bank_statement для v2 → отрисуется как PDF
    if (d.id === "bank_statement" && bankIsV2) {
      return { ...d, filename: "10_Выписка.pdf", kind: "pdf" as const };
    }
    return d;
  });
  // Pack 50.41 — состояние «просмотрено» (общее на команду)
  const [seenKeys, setSeenKeys] = useState<Set<string>>(new Set());
  useEffect(() => {
    getDocViewState(applicationId).then((ks) => setSeenKeys(new Set(ks))).catch(() => {});
  }, [applicationId]);
  function _applySeen(keys: string[]) {
    setSeenKeys((prev) => { const n = new Set(prev); keys.forEach((k) => n.add(k)); return n; });
    markDocsSeen(applicationId, keys).catch(() => {});
  }
  function _applyUnseen(keys: string[]) {
    setSeenKeys((prev) => { const n = new Set(prev); keys.forEach((k) => n.delete(k)); return n; });
    markDocsUnseen(applicationId, keys).catch(() => {});
  }
  function toggleSeen(id: string) {
    if (seenKeys.has(id)) _applyUnseen([id]); else _applySeen([id]);
  }
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [zipDownloaded, setZipDownloaded] = useState(false);
  const [downloadingDocxZip, setDownloadingDocxZip] = useState(false);
  const [docxZipDownloaded, setDocxZipDownloaded] = useState(false);
  const [downloadingPdfZip, setDownloadingPdfZip] = useState(false);
  const [pdfZipDownloaded, setPdfZipDownloaded] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Pack 29.4 + 50.1-G — состояние модалки выбора шаблона при 409.
  // kind: "contract" — самозанятый, "employment" — трудовой договор.
  const [pickerState, setPickerState] = useState<{
    isOpen: boolean;
    companyId: number;
    companyShortName: string;
    onSaved: () => void;
    kind: "contract" | "employment";
  } | null>(null);

  // Pack 29.4 + 50.1-G — обработка 409 для обоих кодов:
  //   NEEDS_CONTRACT_TEMPLATE (самозанятый)
  //   NEEDS_EMPLOYMENT_CONTRACT_TEMPLATE (трудовой)
  // Возвращает true если открыли модалку (нужно прервать обработку), false иначе.
  async function handle409IfNeedsTemplate(res: Response, retryFn: () => void): Promise<boolean> {
    if (res.status !== 409) return false;
    let detail: any;
    try {
      const json = await res.json();
      detail = json.detail;
    } catch {
      return false;
    }
    if (!detail) return false;
    let kind: "contract" | "employment" | null = null;
    if (detail.code === "NEEDS_CONTRACT_TEMPLATE") kind = "contract";
    else if (detail.code === "NEEDS_EMPLOYMENT_CONTRACT_TEMPLATE") kind = "employment";
    if (!kind) return false;
    setPickerState({
      isOpen: true,
      companyId: detail.company_id,
      companyShortName: detail.company_short_name || `id=${detail.company_id}`,
      onSaved: retryFn,
      kind,
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
      _applySeen(visibleDocs.map((d) => d.id)); // Pack 50.41

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
      _applySeen(visibleDocs.filter((d) => d.kind === "docx").map((d) => d.id)); // Pack 50.41
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
      _applySeen(visibleDocs.filter((d) => d.kind === "pdf").map((d) => d.id)); // Pack 50.41
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
      _applySeen([doc.id]); // Pack 50.41
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
              style={{ background: "var(--color-bg-secondary)", border: !seenKeys.has(doc.id) ? "1.5px solid var(--color-accent)" : "1.5px solid transparent" }}>
              <NewDot seen={seenKeys.has(doc.id)} onToggle={() => toggleSeen(doc.id)} />
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
                style={{ background: "var(--color-bg-secondary)", border: !seenKeys.has(doc.id) ? "1.5px solid var(--color-accent)" : "1.5px solid transparent" }}>
                <NewDot seen={seenKeys.has(doc.id)} onToggle={() => toggleSeen(doc.id)} />
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
          kind={pickerState.kind}
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

function NewDot({ seen, onToggle }: { seen: boolean; onToggle: () => void }) {
  return (
    <span
      role="button"
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggle(); }}
      title={seen ? "Просмотрен — клик вернёт «новый»" : "Новый — клик пометит просмотренным"}
      className="flex-shrink-0 w-2.5 h-2.5 rounded-full cursor-pointer self-center"
      style={{
        background: seen ? "transparent" : "var(--color-accent)",
        border: seen ? "1.5px solid var(--color-border-tertiary)" : "1.5px solid var(--color-accent)",
      }}
    />
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
