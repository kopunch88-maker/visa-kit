"use client";

import { useState } from "react";
import { Calendar, Edit2, Loader2, CheckCircle2, AlertCircle, UploadCloud, X } from "lucide-react";
import {
  ApplicationResponse,
  RepresentativeResponse,
  SpainAddressResponse,
  adminUploadTasa,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  representative?: RepresentativeResponse;
  address?: SpainAddressResponse;
  onEdit: () => void;
  /** Pack 71 — родитель перечитывает application после успешной загрузки Tasa */
  onUpdated?: () => void;
  /** Pack 71.2 — родитель перечитывает список «Документы клиента» */
  onDocumentsChanged?: () => void;
}

export function SubmissionCard({ application, representative, address, onEdit, onUpdated, onDocumentsChanged }: Props) {
  const hasData =
    application.submission_date || representative || address || application.tasa_nrc;

  // Pack 71 — drag&drop квитанции Tasa
  const TASA_ACCEPTED_EXT = [".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"];
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [banner, setBanner] = useState<{ kind: "success" | "warning" | "error"; lines: string[] } | null>(null);

  function handleDragEnter(e: React.DragEvent) {
    if (isUploading) return;
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault(); e.stopPropagation();
    setIsDragOver(true);
  }
  function handleDragOver(e: React.DragEvent) {
    if (isUploading) return;
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault(); e.stopPropagation();
  }
  function handleDragLeave(e: React.DragEvent) {
    if (isUploading) return;
    e.preventDefault(); e.stopPropagation();
    if (e.currentTarget === e.target) setIsDragOver(false);
  }
  async function handleDrop(e: React.DragEvent) {
    if (isUploading) return;
    e.preventDefault(); e.stopPropagation();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length === 0) return;
    const file = files[0];
    const dotIdx = file.name.lastIndexOf(".");
    const ext = dotIdx >= 0 ? file.name.slice(dotIdx).toLowerCase() : "";
    if (!TASA_ACCEPTED_EXT.includes(ext)) {
      setBanner({ kind: "error", lines: [`Неподдерживаемый формат: ${ext || file.name}. Поддерживаются: PDF, JPG, PNG, WebP, HEIC.`] });
      return;
    }
    setIsUploading(true);
    setBanner(null);
    try {
      const result = await adminUploadTasa(application.id, file);
      try { onUpdated?.(); } catch {}
      try { onDocumentsChanged?.(); } catch {} // Pack 71.2
      const t = result.tasa_apply;
      const lines: string[] = [];
      let kind: "success" | "warning" | "error" = "success";
      if (!t) {
        kind = "error";
        const err = (result.document as any)?.ocr_error || "не удалось распознать";
        lines.push(`Файл загружен, но распознать не получилось: ${err}.`);
      } else {
        if (t.nrc_set && t.nrc_from_document) {
          lines.push(`NRC ${t.nrc_from_document} сохранён.`);
        } else if (t.nrc_conflict) {
          kind = "warning";
          lines.push(`⚠️ В квитанции NRC ${t.nrc_from_document}, а в карточке уже ${t.nrc_existing}. NRC НЕ перезаписан.`);
        } else if (t.nrc_from_document && !t.nrc_set) {
          lines.push(`NRC ${t.nrc_from_document} уже совпадает с тем, что в карточке.`);
        } else if (!t.nrc_from_document) {
          kind = "warning";
          lines.push(`⚠️ В квитанции не нашёлся NRC. Откройте документ в «Документах клиента» и попробуйте другую страницу PDF.`);
        }
        if (t.name_mismatch) {
          kind = "warning";
          lines.push(`⚠️ Имя в квитанции «${t.document_name}» не совпадает с именем клиента «${t.applicant_name}». Проверьте, ту ли квитанцию загрузили.`);
        }
      }
      setBanner(lines.length ? { kind, lines } : null);
    } catch (e) {
      setBanner({ kind: "error", lines: [(e as Error).message] });
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div
      className="bg-primary rounded-xl border p-4 relative"
      style={{
        borderColor: isDragOver ? "var(--color-accent)" : "var(--color-border-tertiary)",
        borderWidth: isDragOver ? 1.5 : 0.5,
      }}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary flex items-center gap-1.5">
          <Calendar className="w-3.5 h-3.5" />
          Подача
        </h3>
        <button
          onClick={onEdit}
          className="text-xs text-info hover:underline flex items-center gap-1"
          title="Изменить дату подачи, представителя и адрес"
        >
          <Edit2 className="w-3 h-3" />
          Изменить
        </button>
      </div>

      {/* Pack 71 — баннер результата загрузки Tasa */}
      {banner && (
        <div
          className="mb-3 p-2 rounded-md text-xs flex gap-2 items-start"
          style={{
            background:
              banner.kind === "success" ? "var(--color-bg-success)"
                : banner.kind === "warning" ? "var(--color-bg-warning)"
                : "var(--color-bg-danger)",
            color:
              banner.kind === "success" ? "var(--color-text-success)"
                : banner.kind === "warning" ? "var(--color-text-warning)"
                : "var(--color-text-danger)",
            border:
              "0.5px solid " + (banner.kind === "success" ? "var(--color-border-success)"
                : banner.kind === "warning" ? "var(--color-border-warning)"
                : "var(--color-border-danger)"),
          }}
        >
          {banner.kind === "success" ? (
            <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
          ) : (
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          )}
          <div className="flex-1 space-y-1">
            {banner.lines.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
          </div>
          <button onClick={() => setBanner(null)} className="flex-shrink-0 opacity-60 hover:opacity-100" title="Закрыть">
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {!hasData ? (
        <div className="text-sm text-tertiary italic py-4">Не назначена</div>
      ) : (
        <div className="space-y-2">
          <div>
            <div className="text-[11px] text-tertiary">Дата подачи</div>
            <div className="text-sm text-primary">
              {application.submission_date
                ? new Date(application.submission_date).toLocaleDateString("ru")
                : "—"}
              {(application.submission_city || address?.city) && (
                <span className="text-tertiary text-xs ml-2">· {application.submission_city || address?.city}</span>
              )}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-tertiary">Представитель</div>
            <div className="text-sm text-primary">
              {representative?.full_name || "—"}
              {representative?.nie && (
                <span className="text-tertiary text-xs ml-2 font-mono">
                  NIE {representative.nie}
                </span>
              )}
            </div>
          </div>
          {address && (
            <div>
              <div className="text-[11px] text-tertiary">Адрес в Испании</div>
              <div className="text-sm text-primary">{address.label}</div>
            </div>
          )}
          {/* NRC квитанции (Pack 69.1) */}
          <div>
            <div className="text-[11px] text-tertiary">NRC квитанции</div>
            <div className="text-sm text-primary font-mono">{application.tasa_nrc || "—"}</div>
          </div>
        </div>
      )}

      {/* Pack 71 — overlay drop-зоны */}
      {isDragOver && !isUploading && (
        <div
          className="absolute inset-0 rounded-xl flex flex-col items-center justify-center gap-2 pointer-events-none"
          style={{
            background: "color-mix(in srgb, var(--color-accent) 12%, transparent)",
            border: "1.5px dashed var(--color-accent)",
          }}
        >
          <UploadCloud className="w-7 h-7" style={{ color: "var(--color-accent)" }} />
          <div className="text-sm font-medium" style={{ color: "var(--color-accent)" }}>Бросьте квитанцию Tasa сюда</div>
          <div className="text-[11px] text-tertiary">PDF · JPG · PNG · HEIC</div>
        </div>
      )}

      {/* Pack 71 — overlay загрузки/распознавания */}
      {isUploading && (
        <div
          className="absolute inset-0 rounded-xl flex flex-col items-center justify-center gap-2"
          style={{ background: "color-mix(in srgb, var(--color-bg-primary) 88%, transparent)" }}
        >
          <Loader2 className="w-6 h-6 animate-spin" style={{ color: "var(--color-accent)" }} />
          <div className="text-sm font-medium text-primary">Загружаем и распознаём Tasa…</div>
          <div className="text-[11px] text-tertiary">Это занимает 10–30 секунд</div>
        </div>
      )}
    </div>
  );
}
