"use client";

import { User } from "lucide-react";
import { ApplicantResponse, ApplicationResponse } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse | null;
  application: ApplicationResponse;
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
