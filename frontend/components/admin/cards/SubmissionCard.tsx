"use client";

import { Calendar, Edit2 } from "lucide-react";
import {
  ApplicationResponse,
  RepresentativeResponse,
  SpainAddressResponse,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  representative?: RepresentativeResponse;
  address?: SpainAddressResponse;
  onEdit: () => void;
}

export function SubmissionCard({ application, representative, address, onEdit }: Props) {
  const hasData =
    application.submission_date || representative || address;

  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
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
              {address?.city && (
                <span className="text-tertiary text-xs ml-2">· {address.city}</span>
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
        </div>
      )}
    </div>
  );
}
