"use client";

// Pack 30.0
import { Flame, Briefcase, Calendar } from "lucide-react";
import { ApplicationResponse, STATUS_LABELS } from "@/lib/api";

// Pack 34.3 — режимы сортировки списка
export type SortMode = "default" | "alphabet" | "submission_date";

interface Props {
  applications: ApplicationResponse[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  // Pack 34.3 — режим сортировки. Применяется поверх приоритетных групп
  // огонь/чемодан/обычные (приоритет групп всегда сохраняется).
  sortMode?: SortMode;
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

// Pack 34.3 — форматирование даты подачи: "15.05.2026" или null
function formatSubmissionDate(dateStr?: string): string | null {
  if (!dateStr) return null;
  // Дата приходит в ISO формате "2026-05-15" — преобразуем в "15.05.2026"
  const parts = dateStr.split("T")[0].split("-");
  if (parts.length !== 3) return dateStr;
  return `${parts[2]}.${parts[1]}.${parts[0]}`;
}

// Pack 34.3 — миллисекунды от сегодня до даты (для сортировки "ближайшая выше").
// Прошедшие даты получают Number.POSITIVE_INFINITY чтобы уйти в конец.
// Заявки без даты тоже в конец.
function distanceFromToday(dateStr?: string): number {
  if (!dateStr) return Number.POSITIVE_INFINITY;
  const d = new Date(dateStr).getTime();
  if (Number.isNaN(d)) return Number.POSITIVE_INFINITY;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = d - today.getTime();
  if (diff < 0) return Number.POSITIVE_INFINITY; // прошедшие — в конец
  return diff;
}

// Pack 34.3 — применить sortMode сохраняя приоритет групп urgent/ready/rest.
function applySortMode(
  apps: ApplicationResponse[],
  mode: SortMode,
): ApplicationResponse[] {
  if (mode === "default") return apps;

  const urgent: ApplicationResponse[] = [];
  const ready: ApplicationResponse[] = [];
  const rest: ApplicationResponse[] = [];
  for (const a of apps) {
    if (a.is_urgent) urgent.push(a);
    else if (a.is_ready_for_pickup) ready.push(a);
    else rest.push(a);
  }

  if (mode === "alphabet") {
    const byName = (a: ApplicationResponse, b: ApplicationResponse) =>
      (a.applicant_name_native || a.internal_notes || a.reference || "")
        .toLowerCase()
        .localeCompare(
          (b.applicant_name_native || b.internal_notes || b.reference || "").toLowerCase(),
          "ru",
        );
    urgent.sort(byName);
    ready.sort(byName);
    rest.sort(byName);
  } else if (mode === "submission_date") {
    const byDate = (a: ApplicationResponse, b: ApplicationResponse) =>
      distanceFromToday(a.submission_date) - distanceFromToday(b.submission_date);
    urgent.sort(byDate);
    ready.sort(byDate);
    rest.sort(byDate);
  }

  return [...urgent, ...ready, ...rest];
}

export function ApplicationsList({ applications, selectedId, onSelect, sortMode = "default" }: Props) {
  // Pack 34.3 — пересортировка на клиенте поверх приоритетных групп с бэка
  const sortedApps = applySortMode(applications, sortMode);

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
      {sortedApps.map((app) => {
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
              <div className="text-sm font-semibold text-primary line-clamp-1 flex items-center gap-1.5 min-w-0">
                {/* Pack 30.0 — огонёк у срочных */}
                {app.is_urgent && (
                  <Flame
                    className="w-3.5 h-3.5 flex-shrink-0"
                    style={{ color: "#f97316", fill: "#f97316" }}
                    aria-label="Срочно"
                  />
                )}
                {/* Pack 34.2 — чемодан у заявок «Готово, можно забирать» */}
                {app.is_ready_for_pickup && (
                  <Briefcase
                    className="w-3.5 h-3.5 flex-shrink-0"
                    style={{ color: "#10b981", fill: "rgba(16, 185, 129, 0.15)" }}
                    aria-label="Готово, можно забирать"
                  />
                )}
                <span className="truncate">{displayTitle}</span>
              </div>
              <div className="flex flex-col items-end gap-0.5 whitespace-nowrap">
                <div className="text-xs text-tertiary font-mono">
                  #{app.reference}
                </div>
                {/* Pack 34.3 — дата планируемой подачи */}
                <div
                  className="text-[10px] flex items-center gap-1"
                  style={{
                    color: app.submission_date
                      ? "var(--color-text-tertiary)"
                      : "var(--color-text-tertiary)",
                    opacity: app.submission_date ? 0.85 : 0.45,
                  }}
                  title={app.submission_date ? "Планируемая дата подачи" : "Дата подачи не задана"}
                >
                  <Calendar className="w-3 h-3" />
                  {formatSubmissionDate(app.submission_date) || "не задана"}
                </div>
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
