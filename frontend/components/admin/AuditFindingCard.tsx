"use client";

import { useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  Info,
  Check,
  X,
  Edit3,
  Loader2,
  CheckCircle2,
  XCircle,
  Wrench,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  AuditFinding,
  AUDIT_CATEGORY_LABELS,
  acceptAuditFinding,
  dismissAuditFinding,
} from "@/lib/api";
import { AuditManualFixDialog } from "./AuditManualFixDialog";

interface Props {
  finding: AuditFinding;
  /** Колбэк после успешного действия — родитель перечитает отчёт */
  onResolved: () => void;
}

const SEVERITY_STYLES = {
  critical: {
    border: "border-red-300",
    bg: "bg-red-50",
    iconColor: "text-red-600",
    icon: AlertOctagon,
    badgeBg: "bg-red-100",
    badgeText: "text-red-800",
    label: "Критично",
  },
  warning: {
    border: "border-amber-300",
    bg: "bg-amber-50",
    iconColor: "text-amber-600",
    icon: AlertTriangle,
    badgeBg: "bg-amber-100",
    badgeText: "text-amber-800",
    label: "Предупреждение",
  },
  info: {
    border: "border-blue-200",
    bg: "bg-blue-50",
    iconColor: "text-blue-500",
    icon: Info,
    badgeBg: "bg-blue-100",
    badgeText: "text-blue-700",
    label: "Замечание",
  },
} as const;

const STATUS_STYLES = {
  open: null,
  accepted: {
    icon: CheckCircle2,
    color: "text-green-600",
    label: "Принято",
  },
  dismissed: {
    icon: XCircle,
    color: "text-gray-500",
    label: "Отклонено",
  },
  manually_fixed: {
    icon: Wrench,
    color: "text-violet-600",
    label: "Исправлено вручную",
  },
} as const;

export function AuditFindingCard({ finding, onResolved }: Props) {
  const [busy, setBusy] = useState<"accept" | "dismiss" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showManualFix, setShowManualFix] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const sev = SEVERITY_STYLES[finding.severity];
  const SevIcon = sev.icon;

  const isResolved = finding.status !== "open";
  const resolved = isResolved ? STATUS_STYLES[finding.status] : null;

  async function handleAccept() {
    if (!finding.can_auto_apply) return;
    setBusy("accept");
    setError(null);
    try {
      await acceptAuditFinding(finding.id);
      onResolved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function handleDismiss() {
    const note = window.prompt("Причина отклонения (необязательно):", "");
    if (note === null) return; // отмена в браузерном диалоге
    setBusy("dismiss");
    setError(null);
    try {
      await dismissAuditFinding(finding.id, note || undefined);
      onResolved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  // Resolved карточка — компактная, без кнопок
  if (isResolved && resolved) {
    const ResolvedIcon = resolved.icon;
    return (
      <div className="border border-gray-200 bg-gray-50 rounded-lg p-3 opacity-70">
        <div className="flex items-start gap-3">
          <ResolvedIcon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${resolved.color}`} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={`text-xs font-medium ${resolved.color}`}>
                {resolved.label}
              </span>
              <span className="text-xs text-gray-400">
                · {AUDIT_CATEGORY_LABELS[finding.category]}
              </span>
            </div>
            <p className="text-sm text-gray-700 line-through">{finding.title}</p>
            {finding.resolution_note && (
              <p className="text-xs text-gray-500 mt-1 italic">
                {finding.resolution_note}
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Активная карточка с кнопками
  return (
    <>
      <div className={`border ${sev.border} ${sev.bg} rounded-lg p-4`}>
        <div className="flex items-start gap-3">
          <SevIcon className={`w-6 h-6 mt-0.5 flex-shrink-0 ${sev.iconColor}`} />
          <div className="flex-1 min-w-0">
            {/* Бейджи */}
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${sev.badgeBg} ${sev.badgeText}`}
              >
                {sev.label}
              </span>
              <span className="text-xs text-gray-600 font-medium">
                {AUDIT_CATEGORY_LABELS[finding.category]}
              </span>
              {finding.field_path && (
                <code className="text-xs text-gray-500 bg-white px-1.5 py-0.5 rounded border border-gray-200 font-mono">
                  {finding.field_path}
                </code>
              )}
            </div>

            {/* Заголовок */}
            <h3 className="text-sm font-semibold text-gray-900 mb-1">{finding.title}</h3>

            {/* Описание (раскрывающееся) */}
            {(finding.description || finding.evidence) && (
              <>
                <button
                  onClick={() => setExpanded((e) => !e)}
                  className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 mb-2"
                >
                  {expanded ? (
                    <>
                      <ChevronUp className="w-3 h-3" /> Скрыть детали
                    </>
                  ) : (
                    <>
                      <ChevronDown className="w-3 h-3" /> Показать детали
                    </>
                  )}
                </button>
                {expanded && (
                  <div className="mb-3 space-y-2 text-xs text-gray-700">
                    {finding.description && (
                      <p className="whitespace-pre-wrap">{finding.description}</p>
                    )}
                    {finding.evidence && (
                      <div className="bg-white border border-gray-200 rounded p-2">
                        <p className="text-gray-500 font-medium mb-1">Обоснование:</p>
                        <p className="whitespace-pre-wrap text-gray-700 font-mono text-[11px]">
                          {finding.evidence}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}

            {/* Diff текущее → предлагаемое */}
            {(finding.current_value || finding.suggested_value) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
                {finding.current_value !== null && (
                  <div>
                    <div className="text-xs text-gray-500 mb-0.5">Сейчас:</div>
                    <div className="px-2 py-1 bg-white border border-red-200 rounded text-xs font-mono break-all text-red-900">
                      {String(finding.current_value) || "(пусто)"}
                    </div>
                  </div>
                )}
                {finding.suggested_value !== null && (
                  <div>
                    <div className="text-xs text-gray-500 mb-0.5">Предлагается:</div>
                    <div className="px-2 py-1 bg-white border border-green-300 rounded text-xs font-mono break-all text-green-900">
                      {String(finding.suggested_value)}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Ошибка действия */}
            {error && (
              <div className="bg-red-100 border border-red-300 text-red-900 text-xs px-2 py-1.5 rounded mb-2">
                {error}
              </div>
            )}

            {/* Кнопки */}
            <div className="flex items-center gap-2 flex-wrap">
              {finding.can_auto_apply && (
                <button
                  onClick={handleAccept}
                  disabled={busy !== null}
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white text-xs font-medium rounded hover:bg-green-700 disabled:opacity-50"
                  title="Применить предложение ИИ автоматически"
                >
                  {busy === "accept" ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Check className="w-3.5 h-3.5" />
                  )}
                  Принять
                </button>
              )}

              <button
                onClick={() => setShowManualFix(true)}
                disabled={busy !== null}
                className="inline-flex items-center gap-1 px-3 py-1.5 bg-violet-600 text-white text-xs font-medium rounded hover:bg-violet-700 disabled:opacity-50"
                title="Ввести значение вручную"
              >
                <Edit3 className="w-3.5 h-3.5" /> Изменить
              </button>

              <button
                onClick={handleDismiss}
                disabled={busy !== null}
                className="inline-flex items-center gap-1 px-3 py-1.5 bg-white border border-gray-300 text-gray-700 text-xs font-medium rounded hover:bg-gray-50 disabled:opacity-50"
                title="Закрыть замечание без изменений"
              >
                {busy === "dismiss" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <X className="w-3.5 h-3.5" />
                )}
                Отклонить
              </button>

              {!finding.can_auto_apply && finding.fix_action === null && (
                <span className="text-[11px] text-gray-500 italic ml-1">
                  ИИ не предложил автофикс — используйте «Изменить» или «Отклонить»
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {showManualFix && (
        <AuditManualFixDialog
          finding={finding}
          onClose={() => setShowManualFix(false)}
          onApplied={() => {
            setShowManualFix(false);
            onResolved();
          }}
        />
      )}
    </>
  );
}
