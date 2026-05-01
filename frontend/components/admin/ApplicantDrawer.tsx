"use client";

import { useState } from "react";
import { X, Loader2, Sparkles, AlertCircle, Save, User } from "lucide-react";
import { ApplicantResponse, updateApplicant } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse;
  onClose: () => void;
  onSaved: () => void;
}

const SEX_OPTIONS = [
  { value: "", label: "— Не указано —" },
  { value: "H", label: "Мужской" },
  { value: "M", label: "Женский" },
];

// Самые частые страны для DN-визы (полный список — в CandidateCard)
const COUNTRY_OPTIONS = [
  { value: "", label: "— Не указано —" },
  { value: "RUS", label: "Россия (RUS)" },
  { value: "TUR", label: "Турция (TUR)" },
  { value: "KAZ", label: "Казахстан (KAZ)" },
  { value: "UKR", label: "Украина (UKR)" },
  { value: "BLR", label: "Беларусь (BLR)" },
  { value: "ARM", label: "Армения (ARM)" },
  { value: "AZE", label: "Азербайджан (AZE)" },
  { value: "GEO", label: "Грузия (GEO)" },
  { value: "UZB", label: "Узбекистан (UZB)" },
  { value: "TJK", label: "Таджикистан (TJK)" },
  { value: "KGZ", label: "Кыргызстан (KGZ)" },
  { value: "MDA", label: "Молдова (MDA)" },
  { value: "ISR", label: "Израиль (ISR)" },
  { value: "POL", label: "Польша (POL)" },
  { value: "DEU", label: "Германия (DEU)" },
  { value: "CZE", label: "Чехия (CZE)" },
  { value: "ESP", label: "Испания (ESP)" },
  { value: "ITA", label: "Италия (ITA)" },
  { value: "HUN", label: "Венгрия (HUN)" },
  { value: "PRT", label: "Португалия (PRT)" },
  { value: "GRC", label: "Греция (GRC)" },
  { value: "FRA", label: "Франция (FRA)" },
  { value: "GBR", label: "Великобритания (GBR)" },
  { value: "USA", label: "США (USA)" },
  { value: "CAN", label: "Канада (CAN)" },
  { value: "SRB", label: "Сербия (SRB)" },
  { value: "MNE", label: "Черногория (MNE)" },
  { value: "THA", label: "Таиланд (THA)" },
  { value: "ARE", label: "ОАЭ (ARE)" },
];

export function ApplicantDrawer({ applicant, onClose, onSaved }: Props) {
  // Все поля локально хранятся как строки (для управляемых input'ов)
  const [last_name_native, setLastNameNative] = useState(applicant.last_name_native || "");
  const [first_name_native, setFirstNameNative] = useState(applicant.first_name_native || "");
  const [middle_name_native, setMiddleNameNative] = useState(applicant.middle_name_native || "");
  const [last_name_latin, setLastNameLatin] = useState(applicant.last_name_latin || "");
  const [first_name_latin, setFirstNameLatin] = useState(applicant.first_name_latin || "");
  const [sex, setSex] = useState(applicant.sex || "");
  const [nationality, setNationality] = useState(applicant.nationality || "");
  const [home_country, setHomeCountry] = useState(applicant.home_country || "");
  const [home_address, setHomeAddress] = useState(applicant.home_address || "");
  const [passport_number, setPassportNumber] = useState(applicant.passport_number || "");
  const [passport_issue_date, setPassportIssueDate] = useState(applicant.passport_issue_date || "");
  const [passport_issuer, setPassportIssuer] = useState(applicant.passport_issuer || "");
  const [birth_date, setBirthDate] = useState(applicant.birth_date || "");
  const [birth_place_latin, setBirthPlaceLatin] = useState(applicant.birth_place_latin || "");
  const [email, setEmail] = useState(applicant.email || "");
  const [phone, setPhone] = useState(applicant.phone || "");
  const [inn, setInn] = useState(applicant.inn || "");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Латинская версия для подсказки если рус ещё не вписан
  const fullNameNativeEmpty = !last_name_native?.trim() && !first_name_native?.trim();
  const hasLatin = !!(last_name_latin?.trim() && first_name_latin?.trim());

  async function handleSave() {
    setError(null);
    if (!last_name_native?.trim() || !first_name_native?.trim()) {
      setError("Фамилия и Имя на русском обязательны (хотя бы транслитом).");
      return;
    }
    if (!last_name_latin?.trim() || !first_name_latin?.trim()) {
      setError("Фамилия и Имя на латинице обязательны (как в паспорте).");
      return;
    }

    setSaving(true);
    try {
      await updateApplicant(applicant.id, {
        last_name_native: last_name_native.trim(),
        first_name_native: first_name_native.trim(),
        middle_name_native: middle_name_native.trim(),
        last_name_latin: last_name_latin.trim(),
        first_name_latin: first_name_latin.trim(),
        sex,
        nationality,
        home_country,
        home_address: home_address.trim(),
        passport_number: passport_number.trim(),
        passport_issue_date,
        passport_issuer: passport_issuer.trim(),
        birth_date,
        birth_place_latin: birth_place_latin.trim(),
        email: email.trim(),
        phone: phone.trim(),
        inn: inn.trim(),
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
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
        className="w-full max-w-xl h-full overflow-auto flex flex-col"
        style={{ background: "var(--color-bg-primary)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b sticky top-0 z-10"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderBottomWidth: 0.5,
            background: "var(--color-bg-primary)",
          }}
        >
          <div className="flex items-center gap-2">
            <User className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
            <span className="text-base font-semibold text-primary">
              Редактирование кандидата
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors text-tertiary"
            disabled={saving}
            aria-label="Закрыть"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 p-5 space-y-5">
          {error && (
            <div
              className="p-3 rounded-md text-sm flex gap-2 items-start"
              style={{
                background: "var(--color-bg-danger)",
                color: "var(--color-text-danger)",
                border: "0.5px solid var(--color-border-danger)",
              }}
            >
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Подсказка для иностранцев */}
          {fullNameNativeEmpty && hasLatin && (
            <div
              className="p-3 rounded-md text-sm flex gap-2 items-start"
              style={{
                background: "var(--color-bg-info)",
                color: "var(--color-text-info)",
                border: "0.5px solid var(--color-border-info)",
              }}
            >
              <Sparkles className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium mb-0.5">
                  У клиента не заполнены ФИО на русском
                </div>
                <div className="text-xs">
                  Впишите русскую транслитерацию имени из паспорта
                  (<b>{last_name_latin} {first_name_latin}</b>) — это нужно для договора и других русских документов.
                </div>
              </div>
            </div>
          )}

          {/* ФИО на русском */}
          <Section title="ФИО на русском">
            <Field
              label="Фамилия (рус) *"
              value={last_name_native}
              onChange={setLastNameNative}
              placeholder={hasLatin ? `Например: Юксель (от ${last_name_latin})` : "Иванов"}
            />
            <Field
              label="Имя (рус) *"
              value={first_name_native}
              onChange={setFirstNameNative}
              placeholder={hasLatin ? `Например: Ведат (от ${first_name_latin})` : "Сергей"}
            />
            <Field
              label="Отчество (если есть)"
              value={middle_name_native}
              onChange={setMiddleNameNative}
              placeholder="Петрович — для русских клиентов"
            />
          </Section>

          {/* Латиница */}
          <Section title="ФИО латиницей (как в паспорте)">
            <Field
              label="Фамилия (latin) *"
              value={last_name_latin}
              onChange={setLastNameLatin}
              placeholder="YUKSEL"
            />
            <Field
              label="Имя (latin) *"
              value={first_name_latin}
              onChange={setFirstNameLatin}
              placeholder="VEDAT"
            />
          </Section>

          {/* Гражданство и пол */}
          <Section title="Гражданство и пол">
            <FieldSelect
              label="Гражданство"
              value={nationality}
              onChange={setNationality}
              options={COUNTRY_OPTIONS}
            />
            <FieldSelect
              label="Страна жительства"
              value={home_country}
              onChange={setHomeCountry}
              options={COUNTRY_OPTIONS}
            />
            <FieldSelect
              label="Пол"
              value={sex}
              onChange={setSex}
              options={SEX_OPTIONS}
            />
          </Section>

          {/* Паспорт */}
          <Section title="Паспорт">
            <Field
              label="Номер паспорта"
              value={passport_number}
              onChange={setPassportNumber}
              placeholder="U12345678 или 1234 567890"
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field
                label="Дата выдачи"
                value={passport_issue_date}
                onChange={setPassportIssueDate}
                placeholder="2020-05-15"
                type="date"
              />
              <Field
                label="Дата рождения"
                value={birth_date}
                onChange={setBirthDate}
                placeholder="1972-01-01"
                type="date"
              />
            </div>
            <Field
              label="Кем выдан"
              value={passport_issuer}
              onChange={setPassportIssuer}
              placeholder="Ministry of Internal Affairs / ГУ МВД..."
            />
            <Field
              label="Место рождения"
              value={birth_place_latin}
              onChange={setBirthPlaceLatin}
              placeholder="EDIRNE / MOSCOW"
            />
          </Section>

          {/* Адрес и контакты */}
          <Section title="Адрес и контакты">
            <Field
              label="Адрес проживания"
              value={home_address}
              onChange={setHomeAddress}
              placeholder="г. Москва, ул. Ленина, д. 10, кв. 5"
              textarea
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field
                label="Email"
                value={email}
                onChange={setEmail}
                placeholder="user@example.com"
              />
              <Field
                label="Телефон"
                value={phone}
                onChange={setPhone}
                placeholder="+7 999 ..."
              />
            </div>
            <Field
              label="ИНН"
              value={inn}
              onChange={setInn}
              placeholder="123456789012"
            />
          </Section>
        </div>

        {/* Footer */}
        <div
          className="px-5 py-4 border-t flex justify-end gap-3 sticky bottom-0"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderTopWidth: 0.5,
            background: "var(--color-bg-primary)",
          }}
        >
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
            disabled={saving}
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


function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-md p-4"
      style={{
        background: "var(--color-bg-secondary)",
        border: "0.5px solid var(--color-border-secondary)",
      }}
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
        {title}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}


function Field({
  label,
  value,
  onChange,
  placeholder,
  textarea,
  type,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  textarea?: boolean;
  type?: string;
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
      {textarea ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={2}
          className="w-full px-2 py-1.5 rounded-md text-sm border"
          style={style}
        />
      ) : (
        <input
          type={type || "text"}
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


function FieldSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div>
      <label className="block text-xs text-tertiary mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1.5 rounded-md text-sm border"
        style={{
          borderColor: "var(--color-border-tertiary)",
          borderWidth: 0.5,
          background: "var(--color-bg-primary)",
          color: "var(--color-text-primary)",
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
