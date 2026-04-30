"use client";

import { useEffect, useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import {
  RepresentativeResponse,
  getRepresentative,
  createRepresentative,
  updateRepresentative,
} from "@/lib/api";

interface Props {
  representativeId: number | null;
  onClose: () => void;
  onSaved: () => void;
}

export function RepresentativeDrawer({ representativeId, onClose, onSaved }: Props) {
  const isNew = representativeId === null;
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<Partial<RepresentativeResponse>>({
    first_name: "",
    last_name: "",
    nie: "",
    email: "",
    phone: "",
    address_street: "",
    address_number: "",
    address_floor: "",
    address_zip: "",
    address_city: "",
    address_province: "",
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
      try { setForm(await getRepresentative(representativeId!)); }
      catch (e) { setError((e as Error).message); }
      finally { setLoading(false); }
    })();
  }, [representativeId, isNew]);

  function setField<K extends keyof RepresentativeResponse>(key: K, value: any) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setError(null);
    const required = {
      "Имя": form.first_name, "Фамилия": form.last_name, "NIE": form.nie,
      "Email": form.email, "Телефон": form.phone,
      "Улица": form.address_street, "Номер дома": form.address_number,
      "Индекс": form.address_zip, "Город": form.address_city, "Провинция": form.address_province,
    };
    const missing = Object.entries(required).filter(([_, v]) => !v).map(([k]) => k);
    if (missing.length > 0) { setError(`Заполните: ${missing.join(", ")}`); return; }

    setSaving(true);
    try {
      if (isNew) await createRepresentative(form);
      else await updateRepresentative(representativeId!, form);
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
            {isNew ? "Новый представитель" : `Представитель #${representativeId}`}
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
                <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-2">Личные данные</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Field label="Имя (латиница)" required value={form.first_name || ""}
                    onChange={(v) => setField("first_name", v)} placeholder="Anastasia" />
                  <Field label="Фамилия (латиница)" required value={form.last_name || ""}
                    onChange={(v) => setField("last_name", v)} placeholder="Koreneva" />
                  <Field label="NIE / DNI" required value={form.nie || ""}
                    onChange={(v) => setField("nie", v)} placeholder="Z3751311Q" />
                  <Field label="Email" required value={form.email || ""}
                    onChange={(v) => setField("email", v)} placeholder="anastasia@example.com" />
                </div>
                <div className="mt-3">
                  <Field label="Телефон" required value={form.phone || ""}
                    onChange={(v) => setField("phone", v)} placeholder="+34 661 853 441" />
                </div>
              </div>

              <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-2">Адрес в Испании</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Field label="Улица" required value={form.address_street || ""}
                    onChange={(v) => setField("address_street", v)} placeholder="Calle Mayor" />
                  <Field label="Номер дома" required value={form.address_number || ""}
                    onChange={(v) => setField("address_number", v)} placeholder="128" />
                  <Field label="Этаж/квартира" value={form.address_floor || ""}
                    onChange={(v) => setField("address_floor", v)} placeholder="3-2" />
                  <Field label="Индекс" required value={form.address_zip || ""}
                    onChange={(v) => setField("address_zip", v)} placeholder="08008" />
                  <Field label="Город" required value={form.address_city || ""}
                    onChange={(v) => setField("address_city", v)} placeholder="Barcelona" />
                  <Field label="Провинция" required value={form.address_province || ""}
                    onChange={(v) => setField("address_province", v)} placeholder="Barcelona" />
                </div>
              </div>

              <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                <label className="block text-xs font-medium text-secondary mb-1">Внутренние заметки</label>
                <textarea value={form.notes || ""} onChange={(e) => setField("notes", e.target.value)}
                  rows={3} placeholder="Например: предпочтительна для подач в Каталонии"
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
