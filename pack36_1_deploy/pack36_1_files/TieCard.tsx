"use client";

import { useState } from "react";
import { CreditCard, Edit2, Download, Loader2, Check } from "lucide-react";
import { ApplicationResponse, API_BASE_URL, getToken } from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onEdit: () => void;
}

/**
 * Pack 36.1 — карточка "КАРТА TIE".
 * Показывает NIE + дату отпечатков, рядом с SubmissionCard в сетке.
 * Под полями — две кнопки скачать MI-TIE и EX-17 (только если NIE+date заполнены).
 */
export function TieCard({ application, onEdit }: Props) {
  const hasData = Boolean(application.nie && application.fingerprint_date);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadedIds, setDownloadedIds] = useState<Set<string>>(new Set());

  async function handleDownload(fileId: "mi_tie" | "ex17", filename: string) {
    setDownloadingId(fileId);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/admin/applications/${application.id}/download-file/${fileId}`,
        { headers: { Authorization: `Bearer ${getToken()}` } }
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setDownloadedIds(prev => new Set([...prev, fileId]));
    } catch (e) {
      alert(`Ошибка скачивания: ${(e as Error).message}`);
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
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary flex items-center gap-1.5">
          <CreditCard className="w-3.5 h-3.5" />
          Карта TIE
        </h3>
        <button
          onClick={onEdit}
          className="text-xs text-info hover:underline flex items-center gap-1"
          title="Изменить NIE и дату отпечатков"
        >
          <Edit2 className="w-3 h-3" />
          Изменить
        </button>
      </div>

      {!hasData ? (
        <div className="text-sm text-tertiary italic py-4">
          Не назначены
          <div className="text-xs text-tertiary mt-1 not-italic">
            Заполняется после одобрения MI-T и получения NIE от полиции
          </div>
        </div>
      ) : (
        <>
          <div className="space-y-2 mb-3">
            <div>
              <div className="text-[11px] text-tertiary">N.I.E</div>
              <div className="text-sm text-primary font-mono">{application.nie}</div>
            </div>
            <div>
              <div className="text-[11px] text-tertiary">Дата отпечатков</div>
              <div className="text-sm text-primary">
                {application.fingerprint_date
                  ? new Date(application.fingerprint_date).toLocaleDateString("ru")
                  : "—"}
              </div>
            </div>
          </div>

          {/* Кнопки скачать */}
          <div className="flex gap-2 pt-2 border-t" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
            <button
              onClick={() => handleDownload("mi_tie", "15_MI-TIE.pdf")}
              disabled={downloadingId !== null}
              className="flex-1 px-3 py-1.5 text-xs rounded-md border text-secondary hover:bg-secondary disabled:opacity-50 flex items-center justify-center gap-1.5"
              style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
              title="Скачать форму MI-TIE (Movilidad Internacional)"
            >
              {downloadingId === "mi_tie" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : downloadedIds.has("mi_tie") ? (
                <Check className="w-3.5 h-3.5 text-success" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              MI-TIE
            </button>
            <button
              onClick={() => handleDownload("ex17", "16_EX-17.pdf")}
              disabled={downloadingId !== null}
              className="flex-1 px-3 py-1.5 text-xs rounded-md border text-secondary hover:bg-secondary disabled:opacity-50 flex items-center justify-center gap-1.5"
              style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
              title="Скачать форму EX-17 (универсальная МВД)"
            >
              {downloadingId === "ex17" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : downloadedIds.has("ex17") ? (
                <Check className="w-3.5 h-3.5 text-success" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              EX-17
            </button>
          </div>
        </>
      )}
    </div>
  );
}
