"use client";

import { useEffect, useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import {
  CompanyResponse,
  getCompany,
  createCompany,
  updateCompany,
} from "@/lib/api";

interface Props {
  companyId: number | null; // null = создание новой
  onClose: () => void;
  onSaved: () => void;
}

const COUNTRY_OPTIONS = [
  { value: "RUS", label: "Россия" },
  { value: "KAZ", label: "Казахстан" },
  { value: "BLR", label: "Беларусь" },
];

export function CompanyDrawer({ companyId, onClose, onSaved }: Props) {
  const isNew = companyId === null;
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Все поля компании
  const [form, setForm] = useState<Partial<CompanyResponse>>({
    short_name: "",
    full_name_ru: "",
    full_name_es: "",
    country: "RUS",
    tax_id_primary: "",
    tax_id_secondary: "",
    legal_address: "",
    postal_address: "",
    director_full_name_ru: "",
    director_full_name_genitive_ru: "",
    director_short_ru: "",
    director_position_ru: "Генерального директора",
    bank_name: "",
    bank_account: "",
    bank_bic: "",
    bank_correspondent_account: "",
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
        const data = await getCompany(companyId!);
        setForm(data);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [companyId, isNew]);

  function setField<K extends keyof CompanyResponse>(key: K, value: CompanyResponse[K] | string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setError(null);
    const required = {
      "Краткое имя": form.short_name,
      "Полное имя (рус)": form.full_name_ru,
      "Полное имя (исп)": form.full_name_es,
      "ИНН": form.tax_id_primary,
      "Юр. адрес": form.legal_address,
      "ФИО директора (им.п.)": form.director_full_name_ru,
      "ФИО директора (род.п.)": form.director_full_name_genitive_ru,
      "Краткое имя директора": form.director_short_ru,
      "Банк": form.bank_name,
      "Расчётный счёт": form.bank_account,
      "БИК": form.bank_bic,
    };
    const missing = Object.entries(required).filter(([_, v]) => !v).map(([k]) => k);
    if (missing.length > 0) {
      setError(`Заполните поля: ${missing.join(", ")}`);
      return;
    }

    setSaving(true);
    try {
      if (isNew) {
        await createCompany(form);
      } else {
        await updateCompany(companyId!, form);
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
            {isNew ? "Новая компания" : `Компания #${companyId}`}
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
                <Grid>
                  <TextField label="Краткое имя" required value={form.short_name || ""}
                    onChange={(v) => setField("short_name", v)} placeholder="СК10" />
                  <SelectField label="Страна" value={form.country || "RUS"}
                    onChange={(v) => setField("country", v)} options={COUNTRY_OPTIONS} />
                  <TextField label="Полное имя (рус)" required value={form.full_name_ru || ""}
                    onChange={(v) => setField("full_name_ru", v)}
                    placeholder='ООО "Стройкомпания 10"' />
                  <TextField label="Полное имя (исп. транслитерация)" required
                    value={form.full_name_es || ""}
                    onChange={(v) => setField("full_name_es", v)}
                    placeholder="StroyKompaniya 10 LLC" />
                </Grid>
              </Section>

              <Section title="Налоговые ID">
                <Grid>
                  <TextField label="ИНН (или BIN для KZ)" required value={form.tax_id_primary || ""}
                    onChange={(v) => setField("tax_id_primary", v)} placeholder="7715998877" />
                  <TextField label="КПП (только для РФ)" value={form.tax_id_secondary || ""}
                    onChange={(v) => setField("tax_id_secondary", v)} placeholder="771501001" />
                </Grid>
              </Section>

              <Section title="Адреса">
                <TextArea label="Юридический адрес" required value={form.legal_address || ""}
                  onChange={(v) => setField("legal_address", v)}
                  placeholder="125413, г. Москва, ул. Онежская, д. 24" rows={2} />
                <TextArea label="Почтовый адрес (если отличается)"
                  value={form.postal_address || ""}
                  onChange={(v) => setField("postal_address", v)} rows={2} />
              </Section>

              <Section title="Директор (для договоров и других документов)">
                <TextField label="ФИО полное (именительный падеж)" required
                  value={form.director_full_name_ru || ""}
                  onChange={(v) => setField("director_full_name_ru", v)}
                  placeholder="Тараскин Юрий Александрович" />
                <Grid>
                  <TextField label="ФИО (родительный падеж — кого?)" required
                    value={form.director_full_name_genitive_ru || ""}
                    onChange={(v) => setField("director_full_name_genitive_ru", v)}
                    placeholder="Тараскина Юрия Александровича" />
                  <TextField label="Должность (родительный падеж)"
                    value={form.director_position_ru || ""}
                    onChange={(v) => setField("director_position_ru", v)}
                    placeholder="Генерального директора" />
                </Grid>
                <TextField label="Краткое имя для подписи" required
                  value={form.director_short_ru || ""}
                  onChange={(v) => setField("director_short_ru", v)}
                  placeholder="Тараскин Ю.А." />
              </Section>

              <Section title="Банковские реквизиты">
                <TextField label="Название банка" required value={form.bank_name || ""}
                  onChange={(v) => setField("bank_name", v)}
                  placeholder="ПАО Банк ВТБ, г. Санкт-Петербург" />
                <Grid>
                  <TextField label="Расчётный счёт" required value={form.bank_account || ""}
                    onChange={(v) => setField("bank_account", v)}
                    placeholder="40702810500000998877" />
                  <TextField label="БИК" required value={form.bank_bic || ""}
                    onChange={(v) => setField("bank_bic", v)} placeholder="044030704" />
                </Grid>
                <TextField label="Корреспондентский счёт"
                  value={form.bank_correspondent_account || ""}
                  onChange={(v) => setField("bank_correspondent_account", v)}
                  placeholder="30101810200000000704" />
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
// Reusable form components
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

function SelectField({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-secondary mb-1">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
        style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}>
        {options.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
      </select>
    </div>
  );
}
