"use client";

import { useState } from "react";
import { CalendarCheck, X, Save, Loader2, AlertCircle } from "lucide-react";
import { ApplicantResponse, updateApplicant } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Pack 56.2 — отдельный дровер «Ситы» (запись на приём).
 * Редактирует cita_* поля applicant'а независимо от дровера кандидата.
 */
export function CitaDrawer({ applicant, onClose, onSaved }: Props) {
  const a = applicant as any;
  const [fillType, setFillType] = useState<string>(a.cita_fill_type || "no_cert");
  const [certOwner, setCertOwner] = useState<string>(a.cita_cert_owner || "");
  const [location, setLocation] = useState<string>(a.cita_location || "");
  const [email, setEmail] = useState<string>(a.cita_email || "");
  const [phone, setPhone] = useState<string>(a.cita_phone || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await updateApplicant(applicant.id, {
        cita_fill_type: fillType || null,
        cita_cert_owner: fillType === "with_cert" ? (certOwner.trim() || null) : null,
        cita_location: location || null,
        cita_email: email.trim() || null,
        cita_phone: phone.trim() || null,
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message || "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md h-full overflow-auto flex flex-col"
        style={{ background: "var(--color-bg-primary)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b sticky top-0 z-10"
          style={{ borderColor: "var(--color-border-tertiary)", borderBottomWidth: 0.5, background: "var(--color-bg-primary)" }}
        >
          <div className="flex items-center gap-2">
            <CalendarCheck className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
            <span className="text-base font-semibold text-primary">Ситы · #{applicant.id}</span>
          </div>
          <button
            onClick={onClose}
            disabled={saving}
            aria-label="Закрыть"
            className="p-1.5 rounded-md hover:bg-secondary transition-colors text-tertiary"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 p-5 space-y-3">
          {error && (
            <div
              className="p-3 rounded-md text-sm flex gap-2 items-start"
              style={{ background: "var(--color-bg-danger)", color: "var(--color-text-danger)", border: "0.5px solid var(--color-border-danger)" }}
            >
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <p className="text-xs text-tertiary">
            Телефон и почта для оформления ситы (запись на приём). На них приходят код и
            подтверждение записи — могут отличаться от контактов клиента.
          </p>

          <DField
            label="Тип заполнения"
            value={fillType}
            onChange={setFillType}
            select
            options={[
              { value: "no_cert", label: "Без сертификата" },
              { value: "with_cert", label: "С сертификатом" },
            ]}
          />

          {fillType === "with_cert" && (
            <DField
              label="Чей сертификат"
              value={certOwner}
              onChange={setCertOwner}
              select
              options={[{ value: "", label: "— сертификаты появятся позже —" }]}
            />
          )}

          <DField
            label="Локация ситы"
            value={location}
            onChange={setLocation}
            select
            options={[
              { value: "", label: "— не выбрана —" },
              { value: "Madrid", label: "Madrid" },
              { value: "Barcelona", label: "Barcelona" },
            ]}
          />

          <DField label="Email (для ситы)" value={email} onChange={setEmail} placeholder="user@example.com" />
          <DField label="Телефон (для ситы)" value={phone} onChange={setPhone} placeholder="+34 ... / +7 ..." />
        </div>

        {/* Footer */}
        <div
          className="px-5 py-4 border-t flex justify-end gap-3 sticky bottom-0"
          style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5, background: "var(--color-bg-primary)" }}
        >
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
          >
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-2"
            style={{ background: "var(--color-accent)" }}
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Сохраняем...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Сохранить
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function DField({
  label, value, onChange, placeholder, options, select,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
  select?: boolean;
}) {
  const style = {
    borderColor: "var(--color-border-tertiary)",
    borderWidth: 0.5,
    background: "var(--color-bg-primary)",
    color: "var(--color-text-primary)",
  } as const;
  return (
    <div>
      <label className="block text-xs text-tertiary mb-1">{label}</label>
      {select ? (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-2 py-1.5 rounded-md text-sm border"
          style={style}
        >
          {(options || []).map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full px-2 py-1.5 rounded-md text-sm border"
          style={style}
        />
      )}
    </div>
  );
}
