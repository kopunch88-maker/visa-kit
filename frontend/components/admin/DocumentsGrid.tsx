"use client";

import { useState } from "react";
import { Download, Loader2, Check, RefreshCw } from "lucide-react";
import { API_BASE_URL, getToken } from "@/lib/api";
// Pack 29.4
import { ContractTemplatePickerModal } from "./ContractTemplatePickerModal";

interface Props {
  applicationId: number;
  // Pack 29.4 вЂ” РґР»СЏ РјРѕРґР°Р»РєРё РІС‹Р±РѕСЂР° С€Р°Р±Р»РѕРЅР° РґРѕРіРѕРІРѕСЂР°
  companyId?: number | null;
}

type DocItem = {
  id: string;        // РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РІ URL endpoint
  filename: string;  // С‡С‚Рѕ РїРѕРєР°Р·С‹РІР°РµРј РІ РєР°СЂС‚РѕС‡РєРµ
  kind: "docx" | "pdf";
};

const DOCUMENTS: DocItem[] = [
  { id: "contract",        filename: "01_Р”РѕРіРѕРІРѕСЂ.docx",                          kind: "docx" },
  { id: "act_1",           filename: "02_РђРєС‚_1.docx",                            kind: "docx" },
  { id: "act_2",           filename: "03_РђРєС‚_2.docx",                            kind: "docx" },
  { id: "act_3",           filename: "04_РђРєС‚_3.docx",                            kind: "docx" },
  { id: "invoice_1",       filename: "05_РЎС‡С‘С‚_1.docx",                           kind: "docx" },
  { id: "invoice_2",       filename: "06_РЎС‡С‘С‚_2.docx",                           kind: "docx" },
  { id: "invoice_3",       filename: "07_РЎС‡С‘С‚_3.docx",                           kind: "docx" },
  { id: "employer_letter", filename: "08_РџРёСЃСЊРјРѕ.docx",                           kind: "docx" },
  { id: "cv",              filename: "09_Р РµР·СЋРјРµ.docx",                           kind: "docx" },
  { id: "bank_statement",  filename: "10_Р’С‹РїРёСЃРєР°.docx",                          kind: "docx" },
  // Pack 9 вЂ” РёСЃРїР°РЅСЃРєРёРµ PDF-С„РѕСЂРјС‹
  { id: "mi_t",            filename: "11_MI-T.pdf",                              kind: "pdf"  },
  { id: "designacion",     filename: "12_Designacion_representante.pdf",         kind: "pdf"  },
  { id: "compromiso",      filename: "13_Compromiso_RETA.pdf",                   kind: "pdf"  },
  { id: "declaracion",     filename: "14_Declaracion_antecedentes.pdf",          kind: "pdf"  },
  // Pack 18.3 вЂ” СЃРїСЂР°РІРєР° Рѕ РїРѕСЃС‚Р°РЅРѕРІРєРµ РЅР° СѓС‡С‘С‚ СЃР°РјРѕР·Р°РЅСЏС‚РѕРіРѕ (РљРќР” 1122035)
  { id: "npd_certificate",     filename: "15_РЎРїСЂР°РІРєР°_РќРџР”.docx",                     kind: "docx" },
  // Pack 18.3.3 вЂ” С‚Рѕ Р¶Рµ СЃРѕРґРµСЂР¶Р°РЅРёРµ, РЅРѕ РІ С„РѕСЂРјР°С‚Рµ Р›РљРќ (СЌР»РµРєС‚СЂРѕРЅРЅР°СЏ РїРѕРґРїРёСЃСЊ Р¤РќРЎ РІРЅРёР·Сѓ)
  { id: "npd_certificate_lkn", filename: "15b_РЎРїСЂР°РІРєР°_РќРџР”_Р›РљРќ.docx",                kind: "docx" },
  // Pack 18.9 вЂ” Р°РїРѕСЃС‚РёР»СЊ Рє СЃРїСЂР°РІРєРµ РќРџР”
  { id: "apostille",           filename: "16_РђРїРѕСЃС‚РёР»СЊ.docx",                        kind: "docx" },
];

export function DocumentsGrid({ applicationId, companyId }: Props) {
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [zipDownloaded, setZipDownloaded] = useState(false);
  const [downloadingDocxZip, setDownloadingDocxZip] = useState(false);
  const [docxZipDownloaded, setDocxZipDownloaded] = useState(false);
  const [downloadingPdfZip, setDownloadingPdfZip] = useState(false);
  const [pdfZipDownloaded, setPdfZipDownloaded] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Pack 29.4 вЂ” СЃРѕСЃС‚РѕСЏРЅРёРµ РјРѕРґР°Р»РєРё РІС‹Р±РѕСЂР° С€Р°Р±Р»РѕРЅР° РїСЂРё 409 NEEDS_CONTRACT_TEMPLATE
  const [pickerState, setPickerState] = useState<{
    isOpen: boolean;
    companyId: number;
    companyShortName: string;
    onSaved: () => void;
  } | null>(null);

  // Pack 29.4 вЂ” РїСЂРѕРІРµСЂРєР° 409 NEEDS_CONTRACT_TEMPLATE
  // Р’РѕР·РІСЂР°С‰Р°РµС‚ true РµСЃР»Рё РѕС‚РєСЂС‹Р»Рё РјРѕРґР°Р»РєСѓ (РЅСѓР¶РЅРѕ РїСЂРµСЂРІР°С‚СЊ РѕР±СЂР°Р±РѕС‚РєСѓ), false РµСЃР»Рё 409 РЅРµ РїСЂРёС€Р»Р°
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
      // Pack 29.4 вЂ” РѕР±СЂР°Р±РѕС‚РєР° 409 NEEDS_CONTRACT_TEMPLATE
      if (await handle409IfNeedsTemplate(res, () => handleDownloadZip())) {
        return;
      }
      if (!res.ok) throw new Error(`РћС€РёР±РєР° ${res.status}: ${await res.text()}`);

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

  async function handleDownloadPdfZip() {
    setDownloadingPdfZip(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package-pdf`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(`РћС€РёР±РєР° ${res.status}: ${await res.text()}`);
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

  async function handleDownloadDocxZip() {
    setDownloadingDocxZip(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package-docx`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(`РћС€РёР±РєР° ${res.status}: ${await res.text()}`);
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

  async function handleDownloadOne(doc: DocItem) {
    setDownloadingId(doc.id);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${applicationId}/download-file/${doc.id}`,
        { method: "GET", headers: { Authorization: `Bearer ${token}` } },
      );
      // Pack 29.4 вЂ” РѕР±СЂР°Р±РѕС‚РєР° 409 NEEDS_CONTRACT_TEMPLATE
      if (await handle409IfNeedsTemplate(res, () => handleDownloadOne(doc))) {
        return;
      }
      if (!res.ok) throw new Error(`РћС€РёР±РєР° ${res.status}: ${await res.text()}`);

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
          Р СѓСЃСЃРєРёРµ С„РѕСЂРјС‹ Word ({DOCUMENTS.filter(d => d.kind === "docx").length})
        </h3>
        <div className="flex items-center gap-2">
          <button onClick={handleDownloadDocxZip} disabled={downloadingDocxZip}
            className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
            {downloadingDocxZip
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Р“РµРЅРµСЂР°С†РёСЏ...</span></>
              : docxZipDownloaded
              ? <><Check className="w-3.5 h-3.5" /><span>РЎРєР°С‡Р°РЅРѕ</span></>
              : <><Download className="w-3.5 h-3.5" /><span>РЎРєР°С‡Р°С‚СЊ ZIP</span></>}
          </button>
          <button
            onClick={handleDownloadZip}
            disabled={downloadingZip}
            className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
            title="РџРµСЂРµРіРµРЅРµСЂРёСЂРѕРІР°С‚СЊ"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${downloadingZip ? "animate-spin" : ""}`} />
            РџРµСЂРµРіРµРЅРµСЂРёСЂРѕРІР°С‚СЊ
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
                Р“РµРЅРµСЂР°С†РёСЏ...
              </>
            ) : zipDownloaded ? (
              <>
                <Check className="w-3.5 h-3.5" />
                РЎРєР°С‡Р°РЅРѕ
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                РЎРєР°С‡Р°С‚СЊ ZIP
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
        {DOCUMENTS.filter(d => d.kind === "docx").map((doc) => {
          const isDownloading = downloadingId === doc.id;
          return (
            <button key={doc.id} onClick={() => handleDownloadOne(doc)} disabled={isDownloading}
              className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left transition-colors hover:opacity-80 disabled:opacity-60 disabled:cursor-wait"
              style={{ background: "var(--color-bg-secondary)" }}>
              <div className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0 text-[10px] font-semibold"
                style={{ background: "var(--color-bg-info)", color: "var(--color-text-info)" }}>DOC</div>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-primary line-clamp-1">{doc.filename}</div>
                <div className="text-xs text-tertiary">{isDownloading ? "РЎРєР°С‡РёРІР°РЅРёРµ..." : "РєР»РёРє РґР»СЏ СЃРєР°С‡РёРІР°РЅРёСЏ"}</div>
              </div>
              {isDownloading ? <Loader2 className="w-4 h-4 animate-spin text-tertiary flex-shrink-0" /> : <Download className="w-4 h-4 text-tertiary flex-shrink-0 opacity-50" />}
            </button>
          );
        })}
      </div>

      <div className="mt-4 border rounded-xl p-4" style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary">
            РСЃРїР°РЅСЃРєРёРµ PDF С„РѕСЂРјС‹ ({DOCUMENTS.filter(d => d.kind === "pdf").length})
          </h3>
          <button onClick={handleDownloadPdfZip} disabled={downloadingPdfZip}
            className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
            {downloadingPdfZip
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Р“РµРЅРµСЂР°С†РёСЏ...</span></>
              : pdfZipDownloaded
              ? <><Check className="w-3.5 h-3.5" /><span>РЎРєР°С‡Р°РЅРѕ</span></>
              : <><Download className="w-3.5 h-3.5" /><span>РЎРєР°С‡Р°С‚СЊ ZIP</span></>}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {DOCUMENTS.filter(d => d.kind === "pdf").map((doc) => {
            const isDownloading = downloadingId === doc.id;
            return (
              <button key={doc.id} onClick={() => handleDownloadOne(doc)} disabled={isDownloading}
                className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left transition-colors hover:opacity-80 disabled:opacity-60 disabled:cursor-wait"
                style={{ background: "var(--color-bg-secondary)" }}>
                <div className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0 text-[10px] font-semibold"
                  style={{ background: "var(--color-bg-danger)", color: "var(--color-text-danger)" }}>PDF</div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-primary line-clamp-1">{doc.filename}</div>
                  <div className="text-xs text-tertiary">{isDownloading ? "РЎРєР°С‡РёРІР°РЅРёРµ..." : "РєР»РёРє РґР»СЏ СЃРєР°С‡РёРІР°РЅРёСЏ"}</div>
                </div>
                {isDownloading ? <Loader2 className="w-4 h-4 animate-spin text-tertiary flex-shrink-0" /> : <Download className="w-4 h-4 text-tertiary flex-shrink-0 opacity-50" />}
              </button>
            );
          })}
        </div>
      </div>

            {/* Pack 29.4 вЂ” РњРѕРґР°Р»РєР° РІС‹Р±РѕСЂР° С€Р°Р±Р»РѕРЅР° РґРѕРіРѕРІРѕСЂР° РїСЂРё 409 */}
      {pickerState && pickerState.isOpen && (
        <ContractTemplatePickerModal
          companyId={pickerState.companyId}
          companyShortName={pickerState.companyShortName}
          onClose={() => setPickerState(null)}
          onSaved={() => {
            const retry = pickerState.onSaved;
            setPickerState(null);
            // РќРµР±РѕР»СЊС€Р°СЏ Р·Р°РґРµСЂР¶РєР° С‡С‚РѕР±С‹ UI Р·Р°РєСЂС‹Р» РјРѕРґР°Р»РєСѓ РїРµСЂРµРґ РїРѕРІС‚РѕСЂРЅРѕР№ РїРѕРїС‹С‚РєРѕР№
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

