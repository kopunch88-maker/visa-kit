"use client";

import { useEffect, useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import {
  BankResponse,
  getBank,
  createBank,
  updateBank,
} from "@/lib/api";

interface Props {
  bankId: number | null; // null = создание новой
  onClose: () => void;
  onSaved: () => void;
}

export function BankDrawer({ bankId, onClose, onSaved }: Props) {
  const isNew = bankId === null;
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<Partial<BankResponse>>({
    name: "",
    short_name: "",
    bik: "",
    inn: "",
    kpp: "",
    correspondent_account: "",
    swift: "",
    address: "",
    phone: "",
    email: "",
    website: "",
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
      try {
        const data = await getBank(bankId!);
        setForm(data);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [bankId, isNew]);

  function setField<K extends keyof BankResponse>(key: K, value: BankResponse[K] | string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setError(null);
    const required = {
      "Название": form.name,
      "БИК": form.bik,
      "ИНН": form.inn,
      "Корр. счёт": form.correspondent_account,
    };
    const missing = Object.entries(required).filter(([_, v]) => !v).map(([k]) => k);
    if (missing.length > 0) {
      setError(`Заполните поля: ${missing.join(", ")}`);
      return;
    }

    // БИК должен быть 9 цифр
    if (form.bik && !/^\d{9}$/.test(form.bik)) {
      setError("БИК должен состоять ровно из 9 цифр");
      return;
    }

    setSaving(true);
    try {
      if (isNew) {
        await createBank(form);
      } else {
        await updateBank(bankId!, form);
      }
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-30" onClick={onClose} />
      <div className="fixed right-0 top-0 h-screen w-full sm:w-[700px] bg-primary z-40 shadow-2xl overflow-y-auto"
        style={{ borderLeft: "0.5px solid var(--color-border-tertiary)" }}>
        <div className="sticky top-0 bg-primary border-b px-5 py-4 flex items-center justify-between z-10"
          style={{ borderColor: "var(--color-border-tertiary)", borderBottomWidth: 0.5 }}>
          <h2 className="text-lg font-semibold text-primary">
            {isNew ? "Новый банк" : `Банк #${bankId}`}
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
            <div className="px-5 py-4 space-y-5">
              <Section title="Идентификация">
                <TextField label="Полное название" required value={form.name || ""}
                  onChange={(v) => setField("name", v)} placeholder="АО «АЛЬФА-БАНК»" />
                <TextField label="Краткое название" value={form.short_name || ""}
                  onChange={(v) => setField("short_name", v)} placeholder="Альфа-Банк" />
              </Section>

              <Section title="Реквизиты">
                <Grid>
                  <TextField label="БИК (9 цифр)" required value={form.bik || ""}
                    onChange={(v) => setField("bik", v)} placeholder="044525593" />
                  <TextField label="ИНН" required value={form.inn || ""}
                    onChange={(v) => setField("inn", v)} placeholder="7728168971" />
                  <TextField label="КПП" value={form.kpp || ""}
                    onChange={(v) => setField("kpp", v)} placeholder="770801001" />
                  <TextField label="SWIFT/BIC" value={form.swift || ""}
                    onChange={(v) => setField("swift", v)} placeholder="ALFARUMM" />
                </Grid>
                <TextField label="Корреспондентский счёт" required value={form.correspondent_account || ""}
                  onChange={(v) => setField("correspondent_account", v)}
                  placeholder="30101810200000000593" />
              </Section>

              <Section title="Контакты">
                <TextArea label="Адрес" value={form.address || ""}
                  onChange={(v) => setField("address", v)}
                  placeholder="ул. Каланчёвская, 27, Москва, 107078" rows={2} />
                <Grid>
                  <TextField label="Телефон" value={form.phone || ""}
                    onChange={(v) => setField("phone", v)} placeholder="+7 495 620 91 91" />
                  <TextField label="Email" value={form.email || ""}
                    onChange={(v) => setField("email", v)} placeholder="mail@alfabank.ru" />
                </Grid>
                <TextField label="Сайт" value={form.website || ""}
                  onChange={(v) => setField("website", v)} placeholder="alfabank.ru" />
              </Section>

              <Section title="Внутренние заметки">
                <TextArea label="Заметки (видны только команде)" value={form.notes || ""}
                  onChange={(v) => setField("notes", v)} rows={3} />
              </Section>

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

// =====================================================================
// Reusable form components (same as CompanyDrawer)
// =====================================================================

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-2">{title}</h4>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{children}</div>;
}

function TextField({ label, required, value, onChange, placeholder }: {
  label: string; required?: boolean; value: string;
  onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-secondary mb-1">
        {label} {required && <span className="text-danger">*</span>}
      </label>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
        style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
    </div>
  );
}

function TextArea({ label, required, value, onChange, placeholder, rows }: {
  label: string; required?: boolean; value: string;
  onChange: (v: string) => void; placeholder?: string; rows?: number;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-secondary mb-1">
        {label} {required && <span className="text-danger">*</span>}
      </label>
      <textarea value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder} rows={rows || 3}
        className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2 resize-y"
        style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
    </div>
  );
}
