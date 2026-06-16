"use client";

import { CalendarCheck, Edit2 } from "lucide-react";
import { ApplicantResponse } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse;
  onEdit: () => void;
}

/**
 * Pack 56.1 — карточка "СИТЫ" (запись на приём).
 * Тип заполнения, локация (Madrid/Barcelona), контакты для оформления ситы.
 * Данные на applicant (cita_*); редактируются в ApplicantDrawer (секция «Ситы»).
 */
export function CitaCard({ applicant, onEdit }: Props) {
  const a = applicant as any;
  const fillType: string = a.cita_fill_type || "no_cert";
  const certOwner: string = a.cita_cert_owner || "";
  const location: string = a.cita_location || "";
  const email: string = a.cita_email || "";
  const phone: string = a.cita_phone || "";

  const fillTypeLabel = fillType === "with_cert" ? "С сертификатом" : "Без сертификата";
  const hasData = Boolean(location || email || phone || a.cita_fill_type);

  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
    >
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary flex items-center gap-1.5">
          <CalendarCheck className="w-3.5 h-3.5" />
          Ситы
        </h3>
        <button
          onClick={onEdit}
          className="text-xs text-info hover:underline flex items-center gap-1"
          title="Изменить данные ситы"
        >
          <Edit2 className="w-3 h-3" />
          Изменить
        </button>
      </div>

      {!hasData ? (
        <div className="text-sm text-tertiary italic py-4">
          Не заполнены
          <div className="text-xs text-tertiary mt-1 not-italic">
            Тип заполнения, локация и контакты для записи на приём
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <div>
            <div className="text-[11px] text-tertiary">Тип заполнения</div>
            <div className="text-sm text-primary">{fillTypeLabel}</div>
          </div>
          {fillType === "with_cert" && (
            <div>
              <div className="text-[11px] text-tertiary">Чей сертификат</div>
              <div className="text-sm text-primary">{certOwner || "— не выбран —"}</div>
            </div>
          )}
          <div>
            <div className="text-[11px] text-tertiary">Локация</div>
            <div className="text-sm text-primary">{location || "—"}</div>
          </div>
          <div>
            <div className="text-[11px] text-tertiary">Email</div>
            <div className="text-sm text-primary">{email || "—"}</div>
          </div>
          <div>
            <div className="text-[11px] text-tertiary">Телефон</div>
            <div className="text-sm text-primary">{phone || "—"}</div>
          </div>
        </div>
      )}
    </div>
  );
}
