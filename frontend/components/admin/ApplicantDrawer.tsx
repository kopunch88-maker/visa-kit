
"use client";

import { useEffect, useState } from "react";
import { X, Loader2, Sparkles, AlertCircle, Save, User, Wand2, Landmark } from "lucide-react";
import {
  ApplicantResponse,
  updateApplicant,
  transliterateLatToRu,
  BankResponse,
  listBanks,
  generateAccount,
} from "@/lib/api";
import { InnSuggestionModal } from "./InnSuggestionModal";

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

/**
 * Title Case для русского имени — клиентская версия для onBlur.
 */
function toTitleCase(text: string): string {
  if (!text) return "";
  return text
    .trim()
    .toLowerCase()
    .split(/(\s+|-)/)
    .map((p) => (p.match(/[a-zа-яё]/i) ? p.charAt(0).toUpperCase() + p.slice(1) : p))
    .join("");
}

export function ApplicantDrawer({ applicant, onClose, onSaved }: Props) {
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
  // Pack 17.3 — модал генерации ИНН + дата регистрации НПД
  const [innModalOpen, setInnModalOpen] = useState(false);
  const [inn_registration_date, setInnRegistrationDate] = useState(
    applicant.inn_registration_date || ""
  );
  const [inn_kladr_code, setInnKladrCode] = useState(
    applicant.inn_kladr_code || ""
  );

  // Pack 16 — банковские поля
  const [bank_id, setBankId] = useState<number | "">(applicant.bank_id ?? "");
  const [bank_account, setBankAccount] = useState(applicant.bank_account || "");
  const [banks, setBanks] = useState<BankResponse[]>([]);
  const [banksLoading, setBanksLoading] = useState(true);
  const [accountGenerating, setAccountGenerating] = useState(false);

  const [saving, setSaving] = useState(false);
  const [translitLoading, setTranslitLoading] = useState(false);
  const [translitWarning, setTranslitWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fullNameNativeEmpty = !last_name_native?.trim() && !first_name_native?.trim();
  const hasLatin = !!(last_name_latin?.trim() && first_name_latin?.trim());
  const canTransliterate = hasLatin && !translitLoading;

  // Pack 16: загрузить список банков при открытии
  useEffect(() => {
    (async () => {
      try {
        const data = await listBanks();
        setBanks(data);
      } catch (e) {
        // не критично — просто без выбора банка
        console.warn("listBanks failed:", e);
      } finally {
        setBanksLoading(false);
      }
    })();
  }, []);

  async function handleTransliterate() {
    if (!canTransliterate) return;
    setTranslitLoading(true);
    setError(null);
    setTranslitWarning(null);
    try {
      const result = await transliterateLatToRu(
        last_name_latin.trim(),
        first_name_latin.trim(),
        nationality || undefined,
      );
      setLastNameNative(result.last_name_native);
      setFirstNameNative(result.first_name_native);
      setTranslitWarning(result.warning);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setTranslitLoading(false);
    }
  }

  // Pack 16: сгенерировать счёт по выбранному банку
  async function handleGenerateAccount() {
    if (!bank_id) {
      setError("Сначала выберите банк");
      return;
    }
    setAccountGenerating(true);
    setError(null);
    try {
      // Резидент ли клиент: если nationality === "RUS" > резидент (40817), иначе нерезидент (40820)
      const isResident = nationality === "RUS";
      const result = await generateAccount(bank_id as number, isResident);
      setBankAccount(result.account);
    } catch (e) {
      setError(`Не удалось сгенерировать счёт: ${(e as Error).message}`);
    } finally {
      setAccountGenerating(false);
    }
  }

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
      // Pack 16: при выборе банка денормализуем поля bank_name/bic/correspondent_account
      const selectedBank = banks.find((b) => b.id === bank_id);
      const bankFields = selectedBank
        ? {
            bank_id: selectedBank.id,
            bank_name: selectedBank.name,
            bank_bic: selectedBank.bik,
            bank_correspondent_account: selectedBank.correspondent_account,
          }
        : {
            bank_id: null,
          };

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
        inn_registration_date: inn_registration_date || null,
        inn_kladr_code: inn_kladr_code || null,
        // Pack 16
        bank_account: bank_account.trim() || null,
        ...bankFields,
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  }

  return (
    <>
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

          {fullNameNativeEmpty && hasLatin && !translitWarning && (
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
                  Нажмите <b>«? Транслитерировать»</b> ниже — система предложит черновик.
                  После этого проверьте и при необходимости поправьте.
                </div>
              </div>
            </div>
          )}

          {translitWarning && (
            <div
              className="p-3 rounded-md text-sm flex gap-2 items-start"
              style={{
                background: "var(--color-bg-warning)",
                color: "var(--color-text-warning)",
                border: "0.5px solid var(--color-border-warning)",
              }}
            >
              <Wand2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium mb-0.5">Черновик транслитерации</div>
                <div className="text-xs">
                  {translitWarning} Например, <b>YUKSEL</b> может быть «Юксель» или «Юксел» —
                  система не всегда угадывает мягкий знак.
                </div>
              </div>
            </div>
          )}

          {/* ФИО на русском */}
          <Section
            title="ФИО на русском"
            action={
              hasLatin ? (
                <button
                  onClick={handleTransliterate}
                  disabled={!canTransliterate}
                  className="text-xs px-2.5 py-1 rounded-md text-white disabled:opacity-50 transition-colors flex items-center gap-1"
                  style={{ background: "var(--color-accent)" }}
                  title="Сгенерировать черновик с латиницы"
                >
                  {translitLoading ? (
                    <>
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Транслитерация...
                    </>
                  ) : (
                    <>
                      <Wand2 className="w-3 h-3" />
                      Транслитерировать
                    </>
                  )}
                </button>
              ) : null
            }
          >
            <Field label="Фамилия (рус) *" value={last_name_native} onChange={setLastNameNative}
              onBlur={() => setLastNameNative(toTitleCase(last_name_native))}
              placeholder={hasLatin ? `Например: Юксель (от ${last_name_latin})` : "Иванов"} />
            <Field label="Имя (рус) *" value={first_name_native} onChange={setFirstNameNative}
              onBlur={() => setFirstNameNative(toTitleCase(first_name_native))}
              placeholder={hasLatin ? `Например: Ведат (от ${first_name_latin})` : "Сергей"} />
            <Field label="Отчество (если есть)" value={middle_name_native} onChange={setMiddleNameNative}
              onBlur={() => setMiddleNameNative(toTitleCase(middle_name_native))}
              placeholder="Петрович — для русских клиентов" />
          </Section>

          <Section title="ФИО латиницей (как в паспорте)">
            <Field label="Фамилия (latin) *" value={last_name_latin} onChange={setLastNameLatin}
              placeholder="YUKSEL" />
            <Field label="Имя (latin) *" value={first_name_latin} onChange={setFirstNameLatin}
              placeholder="VEDAT" />
          </Section>

          <Section title="Гражданство и пол">
            <FieldSelect label="Гражданство" value={nationality} onChange={setNationality} options={COUNTRY_OPTIONS} />
            <FieldSelect label="Страна жительства" value={home_country} onChange={setHomeCountry} options={COUNTRY_OPTIONS} />
            <FieldSelect label="Пол" value={sex} onChange={setSex} options={SEX_OPTIONS} />
          </Section>

          <Section title="Паспорт">
            <Field label="Номер паспорта" value={passport_number} onChange={setPassportNumber}
              placeholder="U12345678 или 1234 567890" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Дата выдачи" value={passport_issue_date} onChange={setPassportIssueDate}
                placeholder="2020-05-15" type="date" />
              <Field label="Дата рождения" value={birth_date} onChange={setBirthDate}
                placeholder="1972-01-01" type="date" />
            </div>
            <Field label="Кем выдан" value={passport_issuer} onChange={setPassportIssuer}
              placeholder="Ministry of Internal Affairs / ГУ МВД..." />
            <Field label="Место рождения" value={birth_place_latin} onChange={setBirthPlaceLatin}
              placeholder="EDIRNE / MOSCOW" />
          </Section>

          <Section title="Адрес и контакты">
            <Field label="Адрес проживания" value={home_address} onChange={setHomeAddress}
              placeholder="г. Москва, ул. Ленина, д. 10, кв. 5" textarea />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Email" value={email} onChange={setEmail} placeholder="user@example.com" />
              <Field label="Телефон" value={phone} onChange={setPhone} placeholder="+7 999 ..." />
            </div>
            <Field label="ИНН" value={inn} onChange={setInn} placeholder="123456789012"
              actionButton={
                <button
                  type="button"
                  onClick={() => setInnModalOpen(true)}
                  className="text-xs px-2.5 py-1 rounded-md text-white transition-colors flex items-center gap-1 whitespace-nowrap"
                  style={{ background: "var(--color-accent)" }}
                  title="Подобрать ИНН реального самозанятого из реестра ФНС"
                >
                  <Sparkles className="w-3 h-3" />
                  Сгенерировать
                </button>
              }
            />
            {inn_registration_date && (
              <Field
                label="Дата регистрации как самозанятого"
                value={inn_registration_date}
                onChange={setInnRegistrationDate}
                type="date"
              />
            )}
          </Section>

          {/* Pack 16: Банк */}
          <Section
            title="Банк (Pack 16)"
            icon={<Landmark className="w-3.5 h-3.5" />}
          >
            <FieldSelect
              label="Банк"
              value={bank_id === "" ? "" : String(bank_id)}
              onChange={(v) => setBankId(v ? parseInt(v, 10) : "")}
              options={[
                { value: "", label: banksLoading ? "Загрузка..." : "— Не выбран —" },
                ...banks.map((b) => ({
                  value: String(b.id),
                  label: b.short_name || b.name,
                })),
              ]}
            />

            <div>
              <label className="block text-xs text-tertiary mb-1">
                Расчётный счёт (20 цифр)
              </label>
              <div className="flex gap-1.5">
                <input
                  type="text"
                  value={bank_account}
                  onChange={(e) => setBankAccount(e.target.value)}
                  placeholder="40817810810433218196"
                  className="flex-1 px-2 py-1.5 rounded-md text-sm border font-mono"
                  style={{
                    borderColor: "var(--color-border-tertiary)",
                    borderWidth: 0.5,
                    background: "var(--color-bg-primary)",
                    color: "var(--color-text-primary)",
                  }}
                />
                <button
                  type="button"
                  onClick={handleGenerateAccount}
                  disabled={!bank_id || accountGenerating}
                  className="px-2 py-1.5 rounded-md border text-tertiary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1 text-xs"
                  style={{
                    borderColor: "var(--color-border-tertiary)",
                    borderWidth: 0.5,
                  }}
                  title={
                    bank_id
                      ? "Сгенерировать уникальный счёт по правилам ЦБ РФ"
                      : "Сначала выберите банк"
                  }
                >
                  {accountGenerating ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      Сгенерировать
                    </>
                  )}
                </button>
              </div>
              <p className="text-[11px] text-tertiary mt-1">
                {nationality === "RUS"
                  ? "Резидент РФ > префикс 40817 (физлица)"
                  : nationality
                  ? `Нерезидент (${nationality}) > префикс 40820`
                  : "Укажите гражданство для правильного префикса (40817 для РФ / 40820 для остальных)"}
              </p>
            </div>
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
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
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

    {/* Pack 17.3 — модал генерации ИНН */}
    {innModalOpen && (
      <InnSuggestionModal
        applicantId={applicant.id}
        hadAddressBefore={!!(home_address && home_address.trim().length > 5)}
        onClose={() => setInnModalOpen(false)}
        onAccepted={() => {
          // Обновим локальные поля формы по тому, что мог изменить backend.
          // Полные актуальные данные будут получены через onSaved -> родитель
          // обновит applicant и передаст его обратно в Drawer при следующем рендере.
          setInnModalOpen(false);
          onSaved();
        }}
      />
    )}
    </>
  );
}


function Section({
  title, action, children, icon,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div
      className="rounded-md p-4"
      style={{
        background: "var(--color-bg-secondary)",
        border: "0.5px solid var(--color-border-secondary)",
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-tertiary flex items-center gap-1.5">
          {icon}
          {title}
        </div>
        {action}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}


function Field({
  label, value, onChange, onBlur, placeholder, textarea, type, actionButton,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onBlur?: () => void;
  placeholder?: string;
  textarea?: boolean;
  type?: string;
  actionButton?: React.ReactNode;
}) {
  const style = {
    borderColor: "var(--color-border-tertiary)",
    borderWidth: 0.5,
    background: "var(--color-bg-primary)",
    color: "var(--color-text-primary)",
  } as const;

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="block text-xs text-tertiary">{label}</label>
        {actionButton}
      </div>
      {textarea ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
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
          onBlur={onBlur}
          placeholder={placeholder}
          className="w-full px-2 py-1.5 rounded-md text-sm border"
          style={style}
        />
      )}
    </div>
  );
}


function FieldSelect({
  label, value, onChange, options,
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



