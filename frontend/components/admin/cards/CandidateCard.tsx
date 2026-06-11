"use client";

import { User, Pencil, Loader2 } from "lucide-react";
import { ApplicantResponse, ApplicationResponse, COUNTRY_OPTIONS } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse | null;
  application: ApplicationResponse;
  onEdit?: () => void;
  // Pack 32.0 — спиннер пока родитель создаёт пустого applicant'а на бэке
  editLoading?: boolean;
}

// Pack 36.3 — полный справочник стран из COUNTRY_OPTIONS (~195 стран, вкл. XKX->Косово).
// Раньше тут был усечённый локальный список -> карточка показывала сырой ISO-код
// для редких гражданств. Источник один с дропдауном Гражданство/Страна.
const COUNTRY_LABELS: Record<string, string> = Object.fromEntries(
  COUNTRY_OPTIONS.map((o) => [o.value, o.label])
);

function formatCountry(code: string | null | undefined): string {
  if (!code) return "—";
  const upper = code.toUpperCase();
  return COUNTRY_LABELS[upper] || upper;
}

// Pack 32.0 — определяет, является ли запись "только что созданным placeholder'ом"
// (имена «—»). Нужно чтобы не считать иностранцем у которого пустые русские
// ФИО (там реальная latin есть).
function isPlaceholder(applicant: ApplicantResponse | null): boolean {
  if (!applicant) return false;
  const ln = (applicant.last_name_native || "").trim();
  const fn = (applicant.first_name_native || "").trim();
  return ln === "—" && fn === "—";
}

export function CandidateCard({ applicant, application, onEdit, editLoading }: Props) {
  // Pack 14 — подсказка для иностранцев у которых пустое русское ФИО.
  // Pack 32.0: для свежесозданного placeholder'а подсказка не нужна.
  const needsRussianName =
    applicant &&
    !isPlaceholder(applicant) &&
    (!applicant.last_name_native?.trim() || !applicant.first_name_native?.trim()) &&
    applicant.last_name_latin &&
    applicant.first_name_latin &&
    applicant.last_name_latin !== "—" &&
    applicant.first_name_latin !== "—";

  // Pack 32.0 — показываем поля карточки даже когда applicant=null или
  // placeholder, просто с прочерками. Это даёт менеджеру визуальную
  // согласованность и пустую структуру для редактирования.
  const placeholder = !applicant || isPlaceholder(applicant);

  // Удобные геттеры с прочерками вместо пустых значений.
  const passportValue = (() => {
    if (!applicant || !applicant.passport_number) return "—";
    return `${applicant.passport_number} (${applicant.nationality || "?"})`;
  })();

  const birthValue = (() => {
    if (!applicant || !applicant.birth_date) return "—";
    const d = new Date(applicant.birth_date).toLocaleDateString("ru");
    return applicant.birth_place_latin
      ? `${d}, ${applicant.birth_place_latin}`
      : d;
  })();

  const contactsValue = (() => {
    if (!applicant) return "—";
    if (!applicant.email && !applicant.phone) return "—";
    return `${applicant.email || ""}${applicant.phone ? ` · ${applicant.phone}` : ""}`;
  })();

  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary flex items-center gap-1.5">
          <User className="w-3.5 h-3.5" />
          Кандидат
        </h3>
        {/* Pack 32.0 — кнопка «Изменить» показывается ВСЕГДА если onEdit задан,
            даже когда applicant ещё не создан. Родитель сам решает что делать
            (создать пустого + открыть Drawer, либо просто открыть). */}
        {onEdit && (
          <button
            onClick={onEdit}
            disabled={editLoading}
            className="text-xs px-2 py-1 rounded-md hover:bg-secondary transition-colors flex items-center gap-1 disabled:opacity-50 disabled:cursor-wait"
            style={{ color: "var(--color-text-info)" }}
            title="Редактировать данные кандидата"
          >
            {editLoading ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Pencil className="w-3 h-3" />
            )}
            Изменить
          </button>
        )}
      </div>

      <div className="space-y-2">
        {/* Pack 14 — предупреждение если у иностранца нет русского имени */}
        {needsRussianName && (
          <div
            className="mb-2 p-2 rounded text-xs flex gap-1.5 items-start"
            style={{
              background: "var(--color-bg-warning)",
              color: "var(--color-text-warning)",
              border: "0.5px solid var(--color-border-warning)",
            }}
          >
            <Pencil className="w-3 h-3 flex-shrink-0 mt-0.5" />
            <div>
              В договоре будет латиница. Нажмите <b>«Изменить»</b> и впишите русские ФИО.
            </div>
          </div>
        )}

        <Field label="Паспорт" value={passportValue} muted={placeholder} />
        <Field label="Родился" value={birthValue} muted={placeholder} />

        {applicant && applicant.nationality ? (
          <Field
            label="Гражданство"
            value={`${formatCountry(applicant.nationality)} (${applicant.nationality})`}
          />
        ) : (
          <Field label="Гражданство" value="—" muted={placeholder} />
        )}
        {applicant && applicant.home_country ? (
          <Field
            label="Живёт в"
            value={`${formatCountry(applicant.home_country)} (${applicant.home_country})`}
          />
        ) : (
          <Field label="Живёт в" value="—" muted={placeholder} />
        )}
        {applicant && applicant.home_address ? (
          <Field label="Адрес" value={applicant.home_address} />
        ) : (
          <Field label="Адрес" value="—" muted={placeholder} />
        )}

        <Field label="Контакты" value={contactsValue} muted={placeholder} />
        {applicant && applicant.inn ? (
          <Field label="ИНН" value={applicant.inn} />
        ) : (
          <Field label="ИНН" value="—" muted={placeholder} />
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  muted,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div>
      <div className="text-[11px] text-tertiary">{label}</div>
      <div
        className={
          muted ? "text-sm text-tertiary break-words" : "text-sm text-primary break-words"
        }
      >
        {value}
      </div>
    </div>
  );
}
