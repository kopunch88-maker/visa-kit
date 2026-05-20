"use client";

import {
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  Clock,
  DollarSign,
  Cpu,
} from "lucide-react";
import {
  FinalSubmissionAuditReportWithFindings,
  FINAL_AUDIT_VERDICT_LABELS,
} from "@/lib/api";

interface Props {
  report: FinalSubmissionAuditReportWithFindings;
}

const VERDICT_STYLES = {
  PASS: {
    bgVar: "var(--color-bg-success)",
    borderVar: "var(--color-border-success)",
    textVar: "var(--color-text-success)",
    icon: CheckCircle2,
  },
  WARN: {
    bgVar: "var(--color-bg-warning)",
    borderVar: "var(--color-border-secondary)",
    textVar: "var(--color-text-warning)",
    icon: AlertTriangle,
  },
  FAIL: {
    bgVar: "var(--color-bg-danger)",
    borderVar: "var(--color-border-secondary)",
    textVar: "var(--color-text-danger)",
    icon: AlertOctagon,
  },
} as const;

export function FinalSubmissionVerdictBanner({ report }: Props) {
  const v = VERDICT_STYLES[report.verdict];
  const Icon = v.icon;
  const counts = report.summary_counts || {};

  return (
    <div
      className="rounded-lg p-5 mb-4"
      style={{
        background: v.bgVar,
        border: `2px solid ${v.borderVar}`,
      }}
    >
      <div className="flex items-start gap-4">
        <Icon className="w-12 h-12 flex-shrink-0" style={{ color: v.textVar }} />
        <div className="flex-1 min-w-0">
          <div className="text-2xl font-bold" style={{ color: v.textVar }}>
            {FINAL_AUDIT_VERDICT_LABELS[report.verdict]}
          </div>

          {report.inspector_summary && (
            <p
              className="text-sm mt-2 leading-relaxed"
              style={{ color: v.textVar, opacity: 0.9 }}
            >
              {report.inspector_summary}
            </p>
          )}

          {/* Счётчики */}
          <div className="flex items-center gap-4 mt-3 flex-wrap">
            {(counts.critical ?? 0) > 0 && (
              <span
                className="text-xs px-2 py-1 rounded font-medium"
                style={{
                  background: "var(--color-bg-danger)",
                  color: "var(--color-text-danger)",
                }}
              >
                Критично: {counts.critical}
              </span>
            )}
            {(counts.warning ?? 0) > 0 && (
              <span
                className="text-xs px-2 py-1 rounded font-medium"
                style={{
                  background: "var(--color-bg-warning)",
                  color: "var(--color-text-warning)",
                }}
              >
                Предупреждений: {counts.warning}
              </span>
            )}
            {(counts.info ?? 0) > 0 && (
              <span
                className="text-xs px-2 py-1 rounded font-medium"
                style={{
                  background: "var(--color-bg-info)",
                  color: "var(--color-text-info)",
                }}
              >
                Замечаний: {counts.info}
              </span>
            )}
            {(counts.total ?? 0) === 0 && (
              <span
                className="text-xs px-2 py-1 rounded font-medium"
                style={{
                  background: "var(--color-bg-success)",
                  color: "var(--color-text-success)",
                }}
              >
                Замечаний нет
              </span>
            )}
          </div>

          {/* Метаданные */}
          <div
            className="flex items-center gap-4 mt-3 text-xs flex-wrap"
            style={{ color: v.textVar, opacity: 0.7 }}
          >
            {report.duration_ms !== null && (
              <span className="inline-flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {(report.duration_ms / 1000).toFixed(1)} сек
              </span>
            )}
            {report.cost_usd && (
              <span className="inline-flex items-center gap-1">
                <DollarSign className="w-3 h-3" />
                {report.cost_usd}
              </span>
            )}
            {report.model_used && (
              <span className="inline-flex items-center gap-1">
                <Cpu className="w-3 h-3" />
                {report.model_used.replace("anthropic/", "")}
              </span>
            )}
            <span>
              {new Date(report.started_at).toLocaleString("ru-RU")}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
