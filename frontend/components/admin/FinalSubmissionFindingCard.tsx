"use client";

import { useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  Info,
  Check,
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  FileText,
  ExternalLink,
} from "lucide-react";
import {
  FinalSubmissionFinding,
  FINAL_AUDIT_CATEGORY_LABELS,
  acknowledgeFinalSubmissionFinding,
  dismissFinalSubmissionFinding,
} from "@/lib/api";

interface Props {
  finding: FinalSubmissionFinding;
  /** filename → download_url, для отображения affected_documents с открытием */
  docDownloadUrls: Record<string, string | null>;
  /** Колбэк после успешного acknowledge/dismiss — родитель перечитает отчёт */
  onResolved: () => void;
}

const SEVERITY_STYLES = {
  critical: {
    icon: AlertOctagon,
    iconColor: "var(--color-text-danger)",
    bgVar: "var(--color-bg-danger)",
    borderVar: "var(--color-border-secondary)",
    badgeBg: "var(--color-bg-danger)",
    badgeColor: "var(--color-text-danger)",
    label: "Критично",
  },
  warning: {
    icon: AlertTriangle,
    iconColor: "var(--color-text-warning)",
    bgVar: "var(--color-bg-warning)",
    borderVar: "var(--color-border-tertiary)",
    badgeBg: "var(--color-bg-warning)",
    badgeColor: "var(--color-text-warning)",
    label: "Предупреждение",
  },
  info: {
    icon: Info,
    iconColor: "var(--color-text-info)",
    bgVar: "var(--color-bg-info)",
    borderVar: "var(--color-border-tertiary)",
    badgeBg: "var(--color-bg-info)",
    badgeColor: "var(--color-text-info)",
    label: "Замечание",
  },
} as const;

const STATUS_STYLES = {
  open: null,
  acknowledged: {
    icon: CheckCircle2,
    color: "var(--color-text-warning)",
    label: "Учтено · иду исправлять",
  },
  dismissed: {
    icon: XCircle,
    color: "var(--color-text-tertiary)",
    label: "Отклонено как false positive",
  },
} as const;

export function FinalSubmissionFindingCard({
  finding,
  docDownloadUrls,
  onResolved,
}: Props) {
  const [busy, setBusy] = useState<"acknowledge" | "dismiss" | null>(null);

  const s = SEVERITY_STYLES[finding.severity];
  const Icon = s.icon;
  const statusStyle = STATUS_STYLES[finding.status];

  const isResolved = finding.status !== "open";

  async function handleAcknowledge() {
    const note = window.prompt(
      "Заметка (опционально):\nЧто именно идёте исправлять?",
      ""
    );
    // prompt вернёт null если Cancel — отменяем действие
    if (note === null) return;
    setBusy("acknowledge");
    try {
      await acknowledgeFinalSubmissionFinding(finding.id, note || undefined);
      onResolved();
    } catch (e) {
      alert(`Ошибка: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleDismiss() {
    const note = window.prompt(
      "Заметка (опционально):\nПочему это false positive?",
      ""
    );
    if (note === null) return;
    setBusy("dismiss");
    try {
      await dismissFinalSubmissionFinding(finding.id, note || undefined);
      onResolved();
    } catch (e) {
      alert(`Ошибка: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      className="rounded-lg p-4"
      style={{
        background: isResolved ? "var(--color-bg-secondary)" : s.bgVar,
        border: `1px solid ${s.borderVar}`,
        opacity: isResolved ? 0.65 : 1,
      }}
    >
      <div className="flex items-start gap-3">
        <Icon
          className="w-5 h-5 flex-shrink-0 mt-0.5"
          style={{ color: s.iconColor }}
        />

        <div className="flex-1 min-w-0">
          {/* Badges */}
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span
              className="text-xs font-medium px-2 py-0.5 rounded"
              style={{ background: s.badgeBg, color: s.badgeColor }}
            >
              {s.label}
            </span>
            <span
              className="text-xs px-2 py-0.5 rounded"
              style={{
                background: "var(--color-bg-tertiary)",
                color: "var(--color-text-tertiary)",
              }}
            >
              {FINAL_AUDIT_CATEGORY_LABELS[finding.category]}
            </span>
            {statusStyle && (
              <span
                className="text-xs inline-flex items-center gap-1 px-2 py-0.5 rounded"
                style={{ color: statusStyle.color }}
              >
                <statusStyle.icon className="w-3 h-3" />
                {statusStyle.label}
              </span>
            )}
          </div>

          {/* Title */}
          <h3
            className="text-sm font-semibold mb-2"
            style={{ color: "var(--color-text-primary)" }}
          >
            {finding.title}
          </h3>

          {/* Description */}
          {finding.description && (
            <p
              className="text-sm mb-2 leading-relaxed"
              style={{ color: "var(--color-text-secondary)" }}
            >
              {finding.description}
            </p>
          )}

          {/* Recommendation */}
          {finding.recommendation && (
            <div
              className="text-sm mb-2 p-2 rounded"
              style={{
                background: "var(--color-bg-primary)",
                border: "1px solid var(--color-border-tertiary)",
                color: "var(--color-text-primary)",
              }}
            >
              <div
                className="text-xs font-semibold mb-1 uppercase tracking-wide"
                style={{ color: "var(--color-text-tertiary)" }}
              >
                Рекомендация
              </div>
              {finding.recommendation}
            </div>
          )}

          {/* Affected documents */}
          {finding.affected_documents && finding.affected_documents.length > 0 && (
            <div className="mt-2">
              <div
                className="text-xs font-semibold mb-1 uppercase tracking-wide"
                style={{ color: "var(--color-text-tertiary)" }}
              >
                Документы
              </div>
              <div className="flex flex-wrap gap-2">
                {finding.affected_documents.map((ad, i) => {
                  const url = docDownloadUrls[ad.filename];
                  return url ? (
                    <a
                      key={i}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded hover:opacity-80"
                      style={{
                        background: "var(--color-bg-primary)",
                        color: "var(--color-text-info)",
                        border: "1px solid var(--color-border-tertiary)",
                      }}
                    >
                      <FileText className="w-3 h-3" />
                      {ad.filename}
                      {ad.page ? ` · стр.${ad.page}` : ""}
                      <ExternalLink className="w-3 h-3 opacity-50" />
                    </a>
                  ) : (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded"
                      style={{
                        background: "var(--color-bg-primary)",
                        color: "var(--color-text-tertiary)",
                        border: "1px solid var(--color-border-tertiary)",
                      }}
                    >
                      <FileText className="w-3 h-3" />
                      {ad.filename}
                      {ad.page ? ` · стр.${ad.page}` : ""}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* Values found (diff-like) */}
          {finding.values_found && Object.keys(finding.values_found).length > 0 && (
            <div className="mt-2">
              <div
                className="text-xs font-semibold mb-1 uppercase tracking-wide"
                style={{ color: "var(--color-text-tertiary)" }}
              >
                Найденные значения
              </div>
              <div
                className="text-xs rounded p-2 font-mono"
                style={{
                  background: "var(--color-bg-primary)",
                  border: "1px solid var(--color-border-tertiary)",
                }}
              >
                {Object.entries(finding.values_found).map(([key, val]) => (
                  <div key={key} className="mb-0.5">
                    <span style={{ color: "var(--color-text-tertiary)" }}>
                      {key}:
                    </span>{" "}
                    <span style={{ color: "var(--color-text-primary)" }}>
                      {val}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Resolution note */}
          {finding.resolution_note && (
            <div
              className="mt-2 text-xs p-2 rounded italic"
              style={{
                background: "var(--color-bg-tertiary)",
                color: "var(--color-text-secondary)",
              }}
            >
              <strong>Заметка:</strong> {finding.resolution_note}
            </div>
          )}

          {/* Actions */}
          {!isResolved && (
            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={handleAcknowledge}
                disabled={busy !== null}
                className="text-xs px-3 py-1.5 rounded inline-flex items-center gap-1.5 font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
                style={{
                  background: "var(--color-bg-warning)",
                  color: "var(--color-text-warning)",
                }}
                title="Помечаю как «иду исправлять»"
              >
                {busy === "acknowledge" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Check className="w-3.5 h-3.5" />
                )}
                Иду исправлять
              </button>
              <button
                onClick={handleDismiss}
                disabled={busy !== null}
                className="text-xs px-3 py-1.5 rounded inline-flex items-center gap-1.5 font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
                style={{
                  background: "var(--color-bg-tertiary)",
                  color: "var(--color-text-secondary)",
                  border: "1px solid var(--color-border-tertiary)",
                }}
                title="False positive — не критично"
              >
                {busy === "dismiss" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <X className="w-3.5 h-3.5" />
                )}
                False positive
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
