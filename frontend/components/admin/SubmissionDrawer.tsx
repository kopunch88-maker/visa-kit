"use client";

import { useState, useEffect } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import {
  ApplicationResponse,
  RepresentativeResponse,
  SpainAddressResponse,
  patchApplication,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  representatives: RepresentativeResponse[];
  addresses: SpainAddressResponse[];
  onClose: () => void;
  onSaved: () => void;
}

export function SubmissionDrawer({
  application, representatives, addresses, onClose, onSaved,
}: Props) {
  const [representativeId, setRepresentativeId] = useState<number | "">(application.representative_id || "");
  const [spainAddressId, setSpainAddressId] = useState<number | "">(application.spain_address_id || "");
  const [submissionDate, setSubmissionDate] = useState(application.submission_date || "");
  // Pack 9: номер квитанции пошлины (для PDF-форм)
  const [tasaNrc, setTasaNrc] = useState<string>((application as any).tasa_nrc || "");

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  async function handleSave() {
    setSaveError(null);
    if (!representativeId || !spainAddressId) {
      setSaveError("Заполните представителя и адрес");
      return;
    }
    setSaving(true);
    try {
      await patchApplication(application.id, {
        representative_id: representativeId as number,
        spain_address_id: spainAddressId as number,
        submission_date: submissionDate || undefined,
        tasa_nrc: tasaNrc || undefined,
      } as any);
      onSaved();
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-30" onClick={onClose} />
      <div className="fixed right-0 top-0 h-screen w-full sm:w-[500px] bg-primary z-40 shadow-2xl overflow-y-auto"
        style={{ borderLeft: "0.5px solid var(--color-border-tertiary)" }}>
        <div className="sticky top-0 bg-primary border-b px-5 py-4 flex items-center justify-between z-10"
          style={{ borderColor: "var(--color-border-tertiary)", borderBottomWidth: 0.5 }}>
          <h2 className="text-lg font-semibold text-primary">
            Подача · #{application.reference}
          </h2>
          <button onClick={onClose} className="p-1 rounded-md text-tertiary hover:text-primary hover:bg-secondary">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              Представитель в Испании <span className="text-danger">*</span>
            </label>
            <select value={representativeId}
              onChange={(e) => setRepresentativeId(e.target.value ? parseInt(e.target.value, 10) : "")}
              className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
              style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}>
              <option value="">— выберите —</option>
              {representatives.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.full_name || `${r.first_name} ${r.last_name}`}
                  {r.nie ? ` (NIE ${r.nie})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              Адрес в Испании <span className="text-danger">*</span>
            </label>
            <select value={spainAddressId}
              onChange={(e) => setSpainAddressId(e.target.value ? parseInt(e.target.value, 10) : "")}
              className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
              style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}>
              <option value="">— выберите —</option>
              {addresses.map((a) => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              Дата планируемой подачи в UGE
            </label>
            <input type="date" value={submissionDate}
              onChange={(e) => setSubmissionDate(e.target.value)}
              className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
              style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
            <p className="text-xs text-tertiary mt-1">Минимум 90 дней с даты подписания договора</p>
          </div>

          {/* Pack 9 — поле NRC */}
          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              Номер квитанции пошлины (NRC)
            </label>
            <input type="text" value={tasaNrc}
              onChange={(e) => setTasaNrc(e.target.value)}
              placeholder="7900380018790MJSXT1VRT"
              className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary font-mono focus:outline-none focus:ring-2"
              style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
            <p className="text-xs text-tertiary mt-1">
              Уникальный номер от банка после оплаты пошлины 038. Подставится в форму MI-T
            </p>
          </div>

          {saveError && (
            <div className="bg-danger text-danger text-sm p-3 rounded-md flex items-start gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>{saveError}</div>
            </div>
          )}
        </div>

        <div className="sticky bottom-0 bg-primary border-t px-5 py-3 flex justify-end gap-2"
          style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
          <button onClick={onClose}
            className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
            Отмена
          </button>
          <button onClick={handleSave} disabled={saving}
            className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 flex items-center gap-2"
            style={{ background: "var(--color-accent)" }}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Сохранить"}
          </button>
        </div>
      </div>
    </>
  );
}
