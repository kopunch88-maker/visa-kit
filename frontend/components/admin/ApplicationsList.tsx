"use client";

import { ApplicationResponse, STATUS_LABELS } from "@/lib/api";

interface Props {
  applications: ApplicationResponse[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  draft: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
  awaiting_data: { bg: "var(--color-bg-warning)", text: "var(--color-text-warning)" },
  ready_to_assign: { bg: "var(--color-bg-info)", text: "var(--color-text-info)" },
  assigned: { bg: "var(--color-bg-info)", text: "var(--color-text-info)" },
  drafts_generated: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  at_translator: { bg: "var(--color-bg-info)", text: "var(--color-text-info)" },
  awaiting_scans: { bg: "var(--color-bg-warning)", text: "var(--color-text-warning)" },
  awaiting_digital_sign: { bg: "var(--color-bg-warning)", text: "var(--color-text-warning)" },
  submitted: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  approved: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  rejected: { bg: "var(--color-bg-danger)", text: "var(--color-text-danger)" },
  needs_followup: { bg: "var(--color-bg-warning)", text: "var(--color-text-warning)" },
  hold: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
  cancelled: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
};

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  if (hours < 24) return `${hours} ч назад`;
  if (days === 1) return "вчера";
  if (days < 7) return `${days} дн назад`;
  if (days < 30) return `${Math.floor(days / 7)} нед назад`;
  return `${Math.floor(days / 30)} мес назад`;
}

export function ApplicationsList({ applications, selectedId, onSelect }: Props) {
  if (applications.length === 0) {
    return (
      <div
        className="bg-primary rounded-xl border p-8 text-center text-tertiary text-sm"
        style={{
          borderColor: "var(--color-border-tertiary)",
          borderWidth: 0.5,
        }}
      >
        По заданным фильтрам ничего не найдено
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 max-h-[calc(100vh-220px)] overflow-y-auto">
      {applications.map((app) => {
        const isSelected = app.id === selectedId;
        const statusLabel = STATUS_LABELS[app.status] || app.status;
        const colors = STATUS_COLORS[app.status] || STATUS_COLORS.draft;

        // Приоритет отображения:
        // 1. ФИО клиента (если заполнена анкета)
        // 2. Внутренняя заметка менеджера
        // 3. Просто номер заявки
        const hasApplicant =
          app.applicant_name_native && app.applicant_name_native.trim() !== "";
        const hasNotes =
          app.internal_notes && app.internal_notes.trim() !== "";

        const displayTitle = hasApplicant
          ? app.applicant_name_native
          : hasNotes
          ? app.internal_notes
          : `Заявка ${app.reference}`;

        // Подзаголовок:
        // - если есть имя — показываем латиницу (если есть)
        // - если нет имени, но есть заметка — ничего не показываем (заметка уже сверху)
        const subtitle =
          hasApplicant && app.applicant_name_latin
            ? app.applicant_name_latin
            : null;

        return (
          <button
            key={app.id}
            onClick={() => onSelect(app.id)}
            className={`text-left bg-primary rounded-xl border p-3 transition-all hover:shadow-sm ${
              isSelected ? "ring-2" : ""
            }`}
            style={{
              borderColor: isSelected
                ? "var(--color-accent)"
                : "var(--color-border-tertiary)",
              borderWidth: isSelected ? 1 : 0.5,
              ...(isSelected
                ? ({ "--tw-ring-color": "var(--color-accent)" } as React.CSSProperties)
                : {}),
            }}
          >
            <div className="flex items-start justify-between gap-2 mb-1">
              <div className="text-sm font-semibold text-primary line-clamp-1">
                {displayTitle}
              </div>
              <div className="text-xs text-tertiary font-mono whitespace-nowrap">
                #{app.reference}
              </div>
            </div>

            {subtitle && (
              <div className="text-xs text-tertiary uppercase tracking-wide line-clamp-1 mb-1.5">
                {subtitle}
              </div>
            )}

            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="inline-block px-2 py-0.5 rounded text-xs font-medium"
                style={{ background: colors.bg, color: colors.text }}
              >
                {statusLabel}
              </span>
              <span className="text-xs text-tertiary">
                {formatRelativeTime(app.created_at)}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
