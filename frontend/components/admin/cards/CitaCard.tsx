"use client";

import { useState } from "react";
import { CalendarCheck, Edit2, Play, Square, Loader2 } from "lucide-react";
import { ApplicantResponse, ApplicationResponse, updateApplicant } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse;
  application: ApplicationResponse;
  onEdit: () => void;
  onChanged: () => void;
}

/**
 * Pack 56.1 — карточка "СИТЫ" (запись на приём).
 * Тип заполнения, локация (Madrid/Barcelona), контакты для оформления ситы.
 * Данные на applicant (cita_*); редактируются в ApplicantDrawer (секция «Ситы»).
 */
export function CitaCard({ applicant, application, onEdit, onChanged }: Props) {
  const a = applicant as any;
  const fillType: string = a.cita_fill_type || "no_cert";
  const certOwner: string = a.cita_cert_owner || "";
  const location: string = a.cita_location || "";
  const email: string = a.cita_email || "";
  const phone: string = a.cita_phone || "";

  // Pack 56.4 — отлов сит
  const nie: string = (application as any).nie || "";
  const catching: boolean = Boolean(a.cita_catching);
  const approved = application.status === "approved";
  const allFilled = Boolean(location && email && phone && nie);
  const canStart = approved && allFilled && !catching;
  // Pack 56.6 — статус/результат отлова (пишет воркер)
  const citaStatus: string = a.cita_status || "";
  const citaStatusAt: string = a.cita_status_at || "";
  const citaOffice: string = a.cita_office || "";
  const citaAppt: string = a.cita_appointment_at || "";
  const citaNote: string = a.cita_result_note || "";
  const STATUS_RU: Record<string, string> = {
    running: "ловим",
    slot_found: "слот найден",
    office_picked: "офис выбран",
    booked: "забронировано",
    other_offices: "слоты в других офисах",
    error: "ошибка",
  };
  const statusLabel = STATUS_RU[citaStatus] || citaStatus;
  const [busy, setBusy] = useState(false);
  const [catchErr, setCatchErr] = useState<string | null>(null);

  async function toggleCatch(on: boolean) {
    setBusy(true);
    setCatchErr(null);
    try {
      await updateApplicant(applicant.id, { cita_catching: on });
      onChanged();
    } catch (e) {
      setCatchErr((e as Error).message || "Ошибка");
    } finally {
      setBusy(false);
    }
  }

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

      {/* Pack 56.4 — отлов сит (заглушка): работает из общей карточки клиента */}
      <div className="mt-3 pt-3" style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}>
        <div className="flex items-center gap-2 mb-2">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ background: catching ? "#22c55e" : "var(--color-border-secondary)" }}
          />
          <span className="text-xs text-tertiary">
            {catching ? "Ловля ситы запущена" : "Ловля остановлена"}
          </span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => toggleCatch(true)}
            disabled={!canStart || busy}
            title={
              catching
                ? "Отлов уже запущен"
                : !approved
                ? "Доступно только при статусе «Одобрена»"
                : !allFilled
                ? "Заполните все поля ситы: локация, email, телефон, N.I.E"
                : "Начать ловить ситу"
            }
            className="flex-1 px-3 py-1.5 rounded-md text-xs font-medium text-white disabled:opacity-40 flex items-center justify-center gap-1.5"
            style={{ background: "var(--color-accent)" }}
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Начать ловить ситу
          </button>
          <button
            onClick={() => toggleCatch(false)}
            disabled={!catching || busy}
            title={catching ? "Остановить отлов" : "Отлов не запущен"}
            className="flex-1 px-3 py-1.5 rounded-md text-xs font-medium border disabled:opacity-40 flex items-center justify-center gap-1.5 text-secondary hover:bg-secondary"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
          >
            <Square className="w-3.5 h-3.5" />
            Остановить
          </button>
        </div>
        {citaStatus && (
          <div className="mt-2 text-xs text-secondary space-y-0.5">
            <div>
              Статус ловли: <span className="text-primary">{statusLabel}</span>
              {citaStatusAt ? <span className="text-tertiary"> · {citaStatusAt}</span> : null}
            </div>
            {citaOffice && <div>Офис: {citaOffice}</div>}
            {citaAppt && <div>Время ситы: {citaAppt}</div>}
            {citaNote && <div className="text-tertiary">{citaNote}</div>}
          </div>
        )}
        {catchErr && <div className="text-xs text-danger mt-2">{catchErr}</div>}
      </div>
    </div>
  );
}
