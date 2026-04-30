"use client";

import { useEffect, useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import {
  SpainAddressResponse,
  getSpainAddress,
  createSpainAddress,
  updateSpainAddress,
} from "@/lib/api";

interface Props {
  addressId: number | null;
  onClose: () => void;
  onSaved: () => void;
}

const UGE_OPTIONS = [
  { value: "Cataluña", label: "Cataluña (Барселона и др.)" },
  { value: "Madrid", label: "Madrid" },
  { value: "Andalucía", label: "Andalucía (Севилья, Малага и др.)" },
  { value: "Valencia", label: "Valencia" },
  { value: "Galicia", label: "Galicia" },
  { value: "Otros", label: "Другая провинция" },
];

export function SpainAddressDrawer({ addressId, onClose, onSaved }: Props) {
  const isNew = addressId === null;
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<Partial<SpainAddressResponse>>({
    street: "",
    number: "",
    floor: "",
    zip: "",
    city: "",
    province: "",
    uge_office: "Cataluña",
    label: "",
    notes: "",
  });

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    if (isNew) return;
    (async () => {
      try { setForm(await getSpainAddress(addressId!)); }
      catch (e) { setError((e as Error).message); }
      finally { setLoading(false); }
    })();
  }, [addressId, isNew]);

  function setField<K extends keyof SpainAddressResponse>(key: K, value: any) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setError(null);
    const required = {
      "Метка": form.label, "Улица": form.street, "Номер": form.number,
      "Индекс": form.zip, "Город": form.city, "Провинция": form.province,
      "UGE": form.uge_office,
    };
    const missing = Object.entries(required).filter(([_, v]) => !v).map(([k]) => k);
    if (missing.length > 0) { setError(`Заполните: ${missing.join(", ")}`); return; }

    setSaving(true);
    try {
      if (isNew) await createSpainAddress(form);
      else await updateSpainAddress(addressId!, form);
      onSaved();
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-30" onClick={onClose} />
      <div className="fixed right-0 top-0 h-screen w-full sm:w-[600px] bg-primary z-40 shadow-2xl overflow-y-auto"
        style={{ borderLeft: "0.5px solid var(--color-border-tertiary)" }}>
        <div className="sticky top-0 bg-primary border-b px-5 py-4 flex items-center justify-between z-10"
          style={{ borderColor: "var(--color-border-tertiary)", borderBottomWidth: 0.5 }}>
          <h2 className="text-lg font-semibold text-primary">
            {isNew ? "Новый адрес" : `Адрес #${addressId}`}
          </h2>
          <button onClick={onClose} className="p-1 rounded-md text-tertiary hover:text-primary hover:bg-secondary">
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
          </div>
        ) : (
          <>
            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Метка для пикера <span className="text-danger">*</span>
                </label>
                <input type="text" value={form.label || ""}
                  onChange={(e) => setField("label", e.target.value)}
                  placeholder="Балмес, Барселона (квартира)"
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
                <p className="text-xs text-tertiary mt-1">Короткое имя как менеджер увидит в списке выбора</p>
              </div>

              <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-2">Адрес</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Field label="Улица" required value={form.street || ""}
                    onChange={(v) => setField("street", v)} placeholder="Carrer del Balmes" />
                  <Field label="Номер дома" required value={form.number || ""}
                    onChange={(v) => setField("number", v)} placeholder="128" />
                  <Field label="Этаж/квартира" value={form.floor || ""}
                    onChange={(v) => setField("floor", v)} placeholder="3-2" />
                  <Field label="Индекс" required value={form.zip || ""}
                    onChange={(v) => setField("zip", v)} placeholder="08008" />
                  <Field label="Город" required value={form.city || ""}
                    onChange={(v) => setField("city", v)} placeholder="Barcelona" />
                  <Field label="Провинция" required value={form.province || ""}
                    onChange={(v) => setField("province", v)} placeholder="Barcelona" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  UGE / Регион подачи <span className="text-danger">*</span>
                </label>
                <select value={form.uge_office || ""}
                  onChange={(e) => setField("uge_office", e.target.value)}
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}>
                  {UGE_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
              </div>

              <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                <label className="block text-xs font-medium text-secondary mb-1">Внутренние заметки</label>
                <textarea value={form.notes || ""} onChange={(e) => setField("notes", e.target.value)}
                  rows={3} placeholder="Например: арендована до 2027, адрес представителя Анны"
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
              </div>

              {error && (
                <div className="bg-danger text-danger text-sm p-3 rounded-md flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>{error}</div>
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
          </>
        )}
      </div>
    </>
  );
}

function Field({ label, required, value, onChange, placeholder }: {
  label: string; required?: boolean; value: string;
  onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-secondary mb-1">
        {label} {required && <span className="text-danger">*</span>}
      </label>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
        style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
    </div>
  );
}
