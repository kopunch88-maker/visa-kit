"use client";

import { User, Pencil } from "lucide-react";
import { ApplicantResponse, ApplicationResponse } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse | null;
  application: ApplicationResponse;
  onEdit?: () => void;
}

// ISO 3166-1 alpha-3 → русское название (топ-страны для DN-визы и СНГ)
const COUNTRY_LABELS: Record<string, string> = {
  RUS: "Россия",
  UKR: "Украина",
  BLR: "Беларусь",
  KAZ: "Казахстан",
  AZE: "Азербайджан",
  ARM: "Армения",
  GEO: "Грузия",
  TJK: "Таджикистан",
  UZB: "Узбекистан",
  KGZ: "Кыргызстан",
  TKM: "Туркменистан",
  MDA: "Молдова",
  TUR: "Турция",
  ISR: "Израиль",
  POL: "Польша",
  DEU: "Германия",
  CZE: "Чехия",
  ESP: "Испания",
  ITA: "Италия",
  HUN: "Венгрия",
  PRT: "Португалия",
  GRC: "Греция",
  FRA: "Франция",
  GBR: "Великобритания",
  USA: "США",
  CAN: "Канада",
  SRB: "Сербия",
  MNE: "Черногория",
  THA: "Таиланд",
  ARE: "ОАЭ",
};

function formatCountry(code: string | null | undefined): string {
  if (!code) return "—";
  const upper = code.toUpperCase();
  return COUNTRY_LABELS[upper] || upper;
}

export function CandidateCard({ applicant, application, onEdit }: Props) {
  // Pack 14 — подсказка для иностранцев у которых пустое русское ФИО
  const needsRussianName =
    applicant &&
    (!applicant.last_name_native?.trim() || !applicant.first_name_native?.trim()) &&
    applicant.last_name_latin &&
    applicant.first_name_latin;

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
        {applicant && onEdit && (
          <button
            onClick={onEdit}
            className="text-xs px-2 py-1 rounded-md hover:bg-secondary transition-colors flex items-center gap-1"
            style={{ color: "var(--color-text-info)" }}
            title="Редактировать данные кандидата"
          >
            <Pencil className="w-3 h-3" />
            Изменить
          </button>
        )}
      </div>

      {!applicant ? (
        <div className="text-sm text-tertiary italic py-4">
          Ожидание данных от клиента
        </div>
      ) : (
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

          <Field
            label="Паспорт"
            value={
              applicant.passport_number
                ? `${applicant.passport_number} (${applicant.nationality || "?"})`
                : "—"
            }
          />
          <Field
            label="Родился"
            value={
              applicant.birth_date
                ? `${new Date(applicant.birth_date).toLocaleDateString("ru")}${applicant.birth_place_latin ? `, ${applicant.birth_place_latin}` : ""}`
                : "—"
            }
          />

          {applicant.nationality && (
            <Field
              label="Гражданство"
              value={`${formatCountry(applicant.nationality)} (${applicant.nationality})`}
            />
          )}
          {applicant.home_country && (
            <Field
              label="Живёт в"
              value={`${formatCountry(applicant.home_country)} (${applicant.home_country})`}
            />
          )}
          {applicant.home_address && (
            <Field label="Адрес" value={applicant.home_address} />
          )}

          <Field
            label="Контакты"
            value={
              applicant.email || applicant.phone
                ? `${applicant.email || ""}${applicant.phone ? ` · ${applicant.phone}` : ""}`
                : "—"
            }
          />
          {applicant.inn && <Field label="ИНН" value={applicant.inn} />}
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-tertiary">{label}</div>
      <div className="text-sm text-primary break-words">{value}</div>
    </div>
  );
}
