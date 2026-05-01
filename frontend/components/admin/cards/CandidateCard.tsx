"use client";

import { User } from "lucide-react";
import { ApplicantResponse, ApplicationResponse } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse | null;
  application: ApplicationResponse;
}

// ISO 3-letter country codes → читаемое русское название
// Топ-30 стран релевантных для DN-визы
const COUNTRY_LABELS: Record<string, string> = {
  RUS: "Россия",
  BLR: "Беларусь",
  UKR: "Украина",
  KAZ: "Казахстан",
  ARM: "Армения",
  AZE: "Азербайджан",
  GEO: "Грузия",
  KGZ: "Кыргызстан",
  TJK: "Таджикистан",
  UZB: "Узбекистан",
  TKM: "Туркменистан",
  MDA: "Молдова",
  TUR: "Турция",
  ISR: "Израиль",
  POL: "Польша",
  DEU: "Германия",
  CZE: "Чехия",
  HUN: "Венгрия",
  SRB: "Сербия",
  MNE: "Черногория",
  HRV: "Хорватия",
  BGR: "Болгария",
  ROU: "Румыния",
  GRC: "Греция",
  CYP: "Кипр",
  ITA: "Италия",
  ESP: "Испания",
  PRT: "Португалия",
  FRA: "Франция",
  NLD: "Нидерланды",
  GBR: "Великобритания",
  USA: "США",
  CAN: "Канада",
  ARE: "ОАЭ",
  THA: "Таиланд",
  IDN: "Индонезия",
};

function formatCountry(code: string | null | undefined): string {
  if (!code) return "—";
  const label = COUNTRY_LABELS[code.toUpperCase()];
  return label ? `${label} (${code})` : code;
}

export function CandidateCard({ applicant, application }: Props) {
  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3 flex items-center gap-1.5">
        <User className="w-3.5 h-3.5" />
        Кандидат
      </h3>

      {!applicant ? (
        <div className="text-sm text-tertiary italic py-4">
          Ожидание данных от клиента
        </div>
      ) : (
        <div className="space-y-2">
          <Field
            label="Паспорт"
            value={
              applicant.passport_number
                ? `${applicant.passport_number}${applicant.nationality ? ` (${applicant.nationality})` : ""}`
                : "—"
            }
          />

          {/* Pack 14b+c: гражданство и страна жительства */}
          <Field
            label="🌍 Гражданство"
            value={formatCountry(applicant.nationality)}
          />
          {applicant.home_country &&
            applicant.home_country !== applicant.nationality && (
              <Field
                label="🏠 Живёт в"
                value={formatCountry(applicant.home_country)}
              />
            )}

          <Field
            label="Родился"
            value={
              applicant.birth_date
                ? `${new Date(applicant.birth_date).toLocaleDateString("ru")}${applicant.birth_place_latin ? `, ${applicant.birth_place_latin}` : ""}`
                : "—"
            }
          />

          {applicant.passport_issue_date && (
            <Field
              label="Паспорт выдан"
              value={`${new Date(applicant.passport_issue_date).toLocaleDateString("ru")}${
                applicant.passport_issuer ? ` · ${applicant.passport_issuer}` : ""
              }`}
            />
          )}
          {applicant.passport_expiry_date && (
            <Field
              label="Паспорт действует до"
              value={new Date(applicant.passport_expiry_date).toLocaleDateString("ru")}
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
