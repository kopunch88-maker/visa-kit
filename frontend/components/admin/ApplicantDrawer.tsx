
"use client";

import { useEffect, useState } from "react";
import {
  X, Loader2, Sparkles, AlertCircle, Save, User, Wand2, Landmark,
  CheckCircle2, XCircle, MinusCircle, // Pack 18.5 — статус проверки ИНН через ФНС
  Trash2, Plus, // Pack 19.0.3 — управление записями education
  FileText, RefreshCw, // Pack 25.10 — банковская выписка
} from "lucide-react";
import {
  ApplicantResponse,
  updateApplicant,
  // Pack 35.3 — резолвер русифицированного названия органа выдачи паспорта
  resolvePassportIssuerRu,
  transliterateLatToRu,
  BankResponse,
  listBanks,
  generateAccount,
  regenerateAddress, // Pack 18.8: перегенерация адреса
  regenerateEducation, // Pack 19.0: автогенерация образования
  // Pack 46.0 — диплом для хурадо
  generateDiplomaFields,
  openDiplomaPdf,
  regenerateWorkHistory, // Pack 19.1: автогенерация work_history
  // Pack 25.10 — банковская выписка
  ApplicationResponse,
  patchApplication,
  regenerateBankTransactions,
  // Pack 34.0 — единый список стран (~195) для Гражданство/Страна рождения/Страна жительства
  COUNTRY_OPTIONS as ALL_COUNTRIES,
} from "@/lib/api";
import { InnSuggestionModal } from "./InnSuggestionModal";
// Pack 41.0-D — секция управления passports[]
import { PassportsSection } from "./PassportsSection";
import { RefineInnDateModal } from "./RefineInnDateModal";

interface Props {
  applicant: ApplicantResponse;
  // Pack 25.10 — опционально: если передан, показывается секция «Банковская выписка»
  application?: ApplicationResponse;
  onApplicationSaved?: () => void;
  onClose: () => void;
  onSaved: () => void;
}

const SEX_OPTIONS = [
  { value: "", label: "— Не указано —" },
  { value: "H", label: "Мужской" },
  { value: "M", label: "Женский" },
];

const MARITAL_OPTIONS = [
  { value: "", label: "— Не указано —" },
  { value: "S", label: "Не женат / не замужем" },
  { value: "C", label: "Женат / замужем" },
  { value: "D", label: "Разведён / разведена" },
  { value: "V", label: "Вдовец / вдова" },
];

// Pack 34.0 — локальный COUNTRY_OPTIONS теперь генерится из ALL_COUNTRIES
// (полный мир ISO 3166-1 из @/lib/api). Префикс «— Не указано —» сохранён.
// Формат label «Страна (ISO3)» — привычный для менеджеров.
const COUNTRY_OPTIONS = [
  { value: "", label: "— Не указано —" },
  ...ALL_COUNTRIES.map((c) => ({ value: c.value, label: `${c.label} (${c.value})` })),
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

export function ApplicantDrawer({ applicant, application, onApplicationSaved, onClose, onSaved }: Props) {
  const [last_name_native, setLastNameNative] = useState(applicant.last_name_native || "");
  const [first_name_native, setFirstNameNative] = useState(applicant.first_name_native || "");
  const [middle_name_native, setMiddleNameNative] = useState(applicant.middle_name_native || "");
  // Pack 50.7-D — ФИО в винительном падеже для Приказа Т-9 (найм)
  const [full_name_accusative, setFullNameAccusative] = useState((applicant as any).full_name_accusative || "");
  const [last_name_latin, setLastNameLatin] = useState(applicant.last_name_latin || "");
  const [first_name_latin, setFirstNameLatin] = useState(applicant.first_name_latin || "");
  const [sex, setSex] = useState(applicant.sex || "");
  const [marital_status, setMaritalStatus] = useState(applicant.marital_status || "");
  const [nationality, setNationality] = useState(applicant.nationality || "");
  const [home_country, setHomeCountry] = useState(applicant.home_country || "");
  const [home_address, setHomeAddress] = useState(applicant.home_address || "");
// Pack 41.0-D — мультипаспорт: passports[] + passport_id_for_ru_docs
  const [passports, setPassports] = useState(
    Array.isArray((applicant as any).passports) ? (applicant as any).passports : []
  );
  const [passportIdForRuDocs, setPassportIdForRuDocs] = useState(
    (applicant as any).passport_id_for_ru_docs || null
  );
 
  const [birth_date, setBirthDate] = useState(applicant.birth_date || "");
  const [birth_place_latin, setBirthPlaceLatin] = useState(applicant.birth_place_latin || "");
  // Pack 18.10 — страна рождения (отдельно от гражданства)
  const [birth_country, setBirthCountry] = useState(applicant.birth_country || "");
  // Поля для анкеты MI-T (Nombre del padre / Nombre de la madre)
  const [father_name_latin, setFatherNameLatin] = useState(applicant.father_name_latin || "");
  const [mother_name_latin, setMotherNameLatin] = useState(applicant.mother_name_latin || "");
  const [email, setEmail] = useState(applicant.email || "");
  const [phone, setPhone] = useState(applicant.phone || "");
  const [inn, setInn] = useState(applicant.inn || "");
  // Pack 17.3 — модал генерации ИНН + дата регистрации НПД
  const [innModalOpen, setInnModalOpen] = useState(false);
  // Pack 28.5: модал уточнения реальной даты регистрации НПД
  const [refineModalOpen, setRefineModalOpen] = useState(false);
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

  // Pack 18.8: перегенерация адреса
  const [addressRegenerating, setAddressRegenerating] = useState(false);

  // Pack 25.10 — банковская выписка
  const [bankStatementDate, setBankStatementDate] = useState<string>(
    (application as any)?.bank_statement_date || ""
  );
  const [bankRegenerating, setBankRegenerating] = useState(false);
  const hasOverride = !!(application as any)?.bank_transactions_override;

  // Pack 18.9: подписант апостиля (опционально, если пусто — backend подставит дефолт Байрамова)
  const [apostille_signer_short, setApostilleSignerShort] = useState(
    applicant.apostille_signer_short || "",
  );
  const [apostille_signer_signature, setApostilleSignerSignature] = useState(
    applicant.apostille_signer_signature || "",
  );
  const [apostille_signer_position, setApostilleSignerPosition] = useState(
    applicant.apostille_signer_position || "",
  );

  // Pack 19.0 — образование (List[EducationRecord]) и состояние регенерации
  const [education, setEducation] = useState<
    Array<{ institution: string; graduation_year: number; degree: string; specialty: string }>
  >((applicant.education as any) || []);
  const [educationRegenerating, setEducationRegenerating] = useState(false);
  const [educationFallbackUsed, setEducationFallbackUsed] = useState(false);
  // Pack 46.0 — состояния для генерации диплома (по индексу записи)
  const [diplomaGenerating, setDiplomaGenerating] = useState<number | null>(null);
  const [diplomaOpening, setDiplomaOpening] = useState<number | null>(null);
  const [diplomaError, setDiplomaError] = useState<string | null>(null);

  // Pack 46.0 — handler генерации полей диплома через LLM
  async function handleGenerateDiplomaFields(i: number) {
    const edu = education[i];
    if (!edu.institution || !edu.specialty || !edu.graduation_year) {
      setDiplomaError(
        "Сначала заполни ВУЗ, специальность и год выпуска"
      );
      return;
    }
    // Проверка непустоты — confirm если поля уже заполнены
    const hasFilled =
      !!(edu as any).diploma_number ||
      !!(edu as any).registration_number ||
      !!(edu as any).protocol_number ||
      !!(edu as any).issue_date;
    if (hasFilled) {
      const ok = window.confirm(
        "Поля диплома (номер, регистрационный, дата, подписанты) будут перезаписаны генерацией из LLM. Продолжить?"
      );
      if (!ok) return;
    }
    setDiplomaError(null);
    setDiplomaGenerating(i);
    try {
      const result = await generateDiplomaFields(applicant.id, i);
      const next = [...education];
      next[i] = { ...next[i], ...result };
      setEducation(next);

      // Pack 46.0 / fix1 — автосохранение в БД, чтобы кнопка 📄 Скачать диплом
      // сразу работала на актуальных данных (без ожидания клика «Сохранить»).
      try {
        await updateApplicant(applicant.id, { education: next });
        onSaved();
      } catch (saveErr) {
        setDiplomaError(
          "Поля сгенерированы, но не удалось сохранить в БД: " +
            ((saveErr as Error).message || "ошибка PATCH") +
            ". Нажми «Сохранить» вручную перед скачиванием PDF."
        );
      }
    } catch (e) {
      setDiplomaError(
        "Не удалось сгенерировать: " +
          ((e as Error).message || "ошибка LLM")
      );
    } finally {
      setDiplomaGenerating(null);
    }
  }

  // Pack 46.0 — handler открытия PDF диплома
  async function handleOpenDiplomaPdf(i: number) {
    setDiplomaError(null);
    setDiplomaOpening(i);
    try {
      await openDiplomaPdf(applicant.id, i);
    } catch (e) {
      setDiplomaError(
        "Не удалось открыть PDF: " + ((e as Error).message || "ошибка")
      );
    } finally {
      setDiplomaOpening(null);
    }
  }
  // Pack 19.1 — работа (List[WorkRecord]) с генератором + editable полями.
  // period_start/period_end — свободные строки ("Сентябрь 2022", "по настоящее время").
  const [workHistory, setWorkHistory] = useState<
    Array<{ period_start: string; period_end: string; company: string; position: string; duties: string[] }>
  >((applicant.work_history as any) || []);
  const [workHistoryRegenerating, setWorkHistoryRegenerating] = useState(false);
  const [workHistoryFallbackUsed, setWorkHistoryFallbackUsed] = useState(false);

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

  // Pack 18.8: сгенерировать новый адрес в том же городе куда привязан ИНН.
  // Бэк по умолчанию использует applicant.inn_kladr_code — поэтому кнопка
  // disabled пока ИНН не выдан (или старый формат до Pack 18.6).
  async function handleRegenerateAddress() {
    if (!inn_kladr_code) {
      setError(
        "Сначала сгенерируйте ИНН — без него неизвестно для какого города делать адрес.",
      );
      return;
    }
    setAddressRegenerating(true);
    setError(null);
    try {
      const result = await regenerateAddress(applicant.id);
      setHomeAddress(result.home_address);
    } catch (e) {
      setError(`Не удалось перегенерировать адрес: ${(e as Error).message}`);
    } finally {
      setAddressRegenerating(false);
    }
  }

  // Pack 19.0: автогенерация вуза + специальности + года выпуска по
  // региону клиента и должности из work_history. Если уже что-то есть —
  // перезаписывает (UI запрашивает подтверждение через native confirm()).
  async function handleRegenerateEducation() {
    if (education.length > 0) {
      const ok = window.confirm(
        "У клиента уже заполнено образование. Перегенерировать (старая запись будет удалена)?",
      );
      if (!ok) return;
    }
    setEducationRegenerating(true);
    setError(null);
    try {
      const result = await regenerateEducation(applicant.id);
      // Записываем в state — реальная запись в БД произойдёт при «Сохранить»
      setEducation([
        {
          institution: result.institution,
          graduation_year: result.graduation_year,
          degree: result.degree,
          specialty: result.specialty,
        },
      ]);
      setEducationFallbackUsed(result.fallback_used);
    } catch (e) {
      setError(`Не удалось подобрать вуз: ${(e as Error).message}`);
    } finally {
      setEducationRegenerating(false);
    }
  }

  // Pack 19.1: автогенерация work_history (1-3 записи: компании + должности + даты).
  // Если уже что-то есть — перезаписывает (UI запрашивает подтверждение).
  async function handleRegenerateWorkHistory() {
    if (workHistory.length > 0) {
      const ok = window.confirm(
        "У клиента уже заполнен опыт работы. Перегенерировать (старые записи будут удалены)?",
      );
      if (!ok) return;
    }
    setWorkHistoryRegenerating(true);
    setError(null);
    try {
      const result = await regenerateWorkHistory(applicant.id);
      // Записываем в state — реальная запись в БД произойдёт при «Сохранить»
      setWorkHistory(
        result.records.map((r) => ({
          period_start: r.period_start,
          period_end: r.period_end,
          company: r.company,
          position: r.position,
          duties: r.duties,
        })),
      );
      setWorkHistoryFallbackUsed(result.fallback_used);
    } catch (e) {
      setError(`Не удалось подобрать опыт работы: ${(e as Error).message}`);
    } finally {
      setWorkHistoryRegenerating(false);
    }
  }

  // Pack 25.10 — кнопка ✨ Auto: today - 8 дней (середина диапазона 7..10)
  function handleAutoStatementDate() {
    const d = new Date();
    d.setDate(d.getDate() - 8);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    setBankStatementDate(`${yyyy}-${mm}-${dd}`);
  }

  // Pack 25.10 — перегенерировать банковскую выписку.
  // 1. Если есть существующий override — confirm.
  // 2. PATCH application с новой bank_statement_date (или null чтобы сбросить).
  // 3. POST bank-transactions/generate.
  async function handleRegenerateBankStatement() {
    if (!application) return;
    if (hasOverride) {
      const ok = window.confirm(
        "У этой заявки уже есть сохранённая выписка. " +
        "Все ручные правки транзакций будут потеряны. Продолжить?"
      );
      if (!ok) return;
    }
    setBankRegenerating(true);
    setError(null);
    try {
      // Сохраняем дату формирования (или null если поле пустое)
      const currentDate = (application as any).bank_statement_date || null;
      const newDate = bankStatementDate || null;
      if (currentDate !== newDate) {
        await patchApplication(application.id, {
          bank_statement_date: newDate,
        } as any);
      }
      // Перегенерируем транзакции
      await regenerateBankTransactions(application.id);
      // Сообщаем родителю что application изменился
      if (onApplicationSaved) onApplicationSaved();
    } catch (e) {
      setError(`Не удалось перегенерировать выписку: ${(e as Error).message}`);
    } finally {
      setBankRegenerating(false);
    }
  }

  // Pack 35.3 — кнопка генерации рядом с «Кем выдан (рус., для договора)»
  

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
        // Pack 50.7-D — винительный падеж для Т-9
        full_name_accusative: full_name_accusative.trim() || null,
        sex,
        marital_status,
        nationality,
        home_country,
        home_address: home_address.trim(),
        // Pack 41.0-D — passports[] вместо 5 скалярных полей
        passports: passports,
        passport_id_for_ru_docs: passportIdForRuDocs,
        birth_date,
        birth_place_latin: birth_place_latin.trim(),
        birth_country: birth_country || null,  // Pack 18.10
        // Имена родителей для анкеты MI-T (Nombre del padre / Nombre de la madre)
        father_name_latin: father_name_latin.trim() || null,
        mother_name_latin: mother_name_latin.trim() || null,
        email: email.trim(),
        phone: phone.trim(),
        inn: inn.trim(),
        inn_registration_date: inn_registration_date || null,
        inn_kladr_code: inn_kladr_code || null,
        // Pack 16
        bank_account: bank_account.trim() || null,
        ...bankFields,
        // Pack 18.9 — подписант апостиля (пустое = null = бэкенд подставит дефолт)
        apostille_signer_short: apostille_signer_short.trim() || null,
        apostille_signer_signature: apostille_signer_signature.trim() || null,
        apostille_signer_position: apostille_signer_position.trim() || null,
        // Pack 19.0 — образование (передаём только если что-то есть)
        education: education.length > 0 ? education : undefined,
        // Pack 19.1 — опыт работы (передаём только если что-то есть)
        work_history: workHistory.length > 0 ? workHistory : undefined,
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
            {/* Pack 50.7-D — винительный падеж ФИО для Приказа Т-9 (найм). Заполняется вручную. */}
            <Field
              label="ФИО в винительном падеже (для Т-9)"
              value={full_name_accusative}
              onChange={setFullNameAccusative}
              placeholder="Например: Орлова Ивана Андреевича"
            />
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
            <FieldSelect label="Семейное положение" value={marital_status} onChange={setMaritalStatus} options={MARITAL_OPTIONS} />
          </Section>

          {/* Pack 41.0-D — мультипаспортная секция */}
          <PassportsSection
            passports={passports}
            setPassports={setPassports}
            passportIdForRuDocs={passportIdForRuDocs}
            setPassportIdForRuDocs={setPassportIdForRuDocs}
            nationality={nationality}
          />

          <Section title="Место и дата рождения">
            <Field label="Дата рождения" value={birth_date} onChange={setBirthDate}
              placeholder="1972-01-01" type="date" />
            <Field label="Место рождения" value={birth_place_latin} onChange={setBirthPlaceLatin}
              placeholder="EDIRNE / MOSCOW" />
            {/* Pack 18.10 — страна рождения (для Pais в MI-T, отдельно от гражданства) */}
            <FieldSelect label="Страна рождения" value={birth_country} onChange={setBirthCountry}
              options={COUNTRY_OPTIONS} />
          </Section>

          {/* Сведения о родителях — для анкеты MI-T (Nombre del padre / Nombre de la madre) */}
          <Section title="Сведения о родителях">
            <p className="text-xs text-tertiary mb-3">
              Имена родителей нужны для испанской анкеты MI-T (поля Nombre del padre /
              Nombre de la madre). Заполняются латиницей как в свидетельстве о рождении.
            </p>
            <Field
              label="Имя отца (латиницей)"
              value={father_name_latin}
              onChange={setFatherNameLatin}
              placeholder="ALIYEV NADIR"
            />
            <Field
              label="Имя матери (латиницей)"
              value={mother_name_latin}
              onChange={setMotherNameLatin}
              placeholder="ALIYEVA LEYLA"
            />
          </Section>

          <Section title="Адрес и контакты">
            <Field
              label="Адрес проживания"
              value={home_address}
              onChange={setHomeAddress}
              placeholder="г. Москва, ул. Ленина, д. 10, кв. 5"
              textarea
              actionButton={
                /* Pack 18.8: перегенерация случайного адреса в том же городе.
                   Disabled пока ИНН не выдан (нет inn_kladr_code) — без него
                   бэк не знает для какого города делать адрес. */
                <button
                  type="button"
                  onClick={handleRegenerateAddress}
                  disabled={!inn_kladr_code || addressRegenerating}
                  className="text-xs px-2.5 py-1 rounded-md text-white disabled:opacity-40 transition-colors flex items-center gap-1 whitespace-nowrap"
                  style={{ background: "var(--color-accent)" }}
                  title={
                    inn_kladr_code
                      ? "Сгенерировать другой случайный адрес в том же городе"
                      : "Сначала сгенерируйте ИНН — без него неизвестно для какого города делать адрес"
                  }
                >
                  {addressRegenerating ? (
                    <>
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Генерация...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3 h-3" />
                      Сгенерировать
                    </>
                  )}
                </button>
              }
            />
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
            {/* Pack 18.5 — статус проверки ИНН через ФНС API */}
            <NpdCheckBadge
              status={applicant.npd_check_status ?? null}
              lastCheckAt={applicant.npd_last_check_at ?? null}
              hasInn={!!inn.trim()}
            />
            {inn_registration_date && (
              <Field
                label="Дата регистрации как самозанятого"
                value={inn_registration_date}
                onChange={setInnRegistrationDate}
                type="date"
              />
            )}
            {/* Pack 28.5: бэйдж реальная/ориентировочная + кнопка уточнения */}
            {applicant.inn && applicant.inn_source && (
              <div className="flex items-center gap-2 mt-2 text-xs flex-wrap">
                {applicant.inn_source === "npd_pool_real" ? (
                  <span
                    className="px-2 py-0.5 rounded inline-flex items-center gap-1"
                    style={{
                      background: "var(--color-bg-success)",
                      color: "var(--color-text-success)",
                      border: "0.5px solid var(--color-border-success)",
                    }}
                  >
                    ✓ Реальная дата (из ФНС)
                  </span>
                ) : applicant.inn_source === "npd_pool_synthetic" ? (
                  <>
                    <span
                      className="px-2 py-0.5 rounded inline-flex items-center gap-1"
                      style={{
                        background: "var(--color-bg-warning)",
                        color: "var(--color-text-warning)",
                        border: "0.5px solid var(--color-border-warning)",
                      }}
                    >
                      ⚠ Ориентировочная дата
                    </span>
                    <button
                      type="button"
                      onClick={() => setRefineModalOpen(true)}
                      className="px-2 py-0.5 rounded text-xs hover:bg-secondary transition-colors"
                      style={{
                        border: "0.5px solid var(--color-border-tertiary)",
                        color: "var(--color-text-primary)",
                      }}
                      title="Запустит бинпоиск через ФНС API (~7 минут)"
                    >
                      Уточнить точную дату
                    </button>
                  </>
                ) : null}
              </div>
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

          {/* Pack 25.10 — Банковская выписка (показывается только если передан application) */}
          {application && (
            <Section
              title="Банковская выписка"
              icon={<FileText className="w-3.5 h-3.5" />}
            >
              <p className="text-xs text-tertiary mb-3">
                Дата формирования выписки. По умолчанию (если поле пустое) генератор
                ставит дату <strong>сегодня минус 7-10 дней</strong> — реалистично для подачи
                на визу. При желании можно задать конкретную дату.
              </p>

              <Field
                label="Дата формирования"
                value={bankStatementDate}
                onChange={setBankStatementDate}
                type="date"
                actionButton={
                  <button
                    type="button"
                    onClick={handleAutoStatementDate}
                    className="text-xs px-2.5 py-1 rounded-md text-white transition-colors flex items-center gap-1 whitespace-nowrap"
                    style={{ background: "var(--color-accent)" }}
                    title="Подставить сегодня минус 8 дней"
                  >
                    <Sparkles className="w-3 h-3" />
                    Auto
                  </button>
                }
              />
              <p className="text-[11px] text-tertiary mt-1">
                Период выписки = 3 месяца до этой даты, включая её.
                Например: 27.04.2026 → выписка 27.01.2026 — 27.04.2026.
              </p>

              <div className="pt-2">
                <button
                  type="button"
                  onClick={handleRegenerateBankStatement}
                  disabled={bankRegenerating}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm w-full justify-center"
                  style={{
                    background: "var(--color-bg-secondary)",
                    border: "1px solid var(--color-border-tertiary)",
                    color: "var(--color-text-primary)",
                  }}
                >
                  {bankRegenerating ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Перегенерируем...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      {hasOverride ? "Перегенерировать выписку" : "Сгенерировать выписку"}
                    </>
                  )}
                </button>
                <p className="text-[11px] text-tertiary mt-2">
                  {hasOverride
                    ? "⚠ Существующие транзакции будут перезаписаны"
                    : "Создаст черновик транзакций по текущим настройкам"}
                </p>
              </div>
            </Section>
          )}

          {/* Pack 18.9 — подписант апостиля (опционально, по умолчанию Байрамов Н.А.) */}
          <Section title="Апостиль">
            <p className="text-xs text-tertiary mb-3">
              Поля для апостиля к справке НПД. Если оставить пустыми — будет использован
              подписант по умолчанию: <strong>Байрамов Н.А.</strong>, заместитель начальника
              отдела международной правовой помощи и предоставления апостиля Главного управления
              Министерства юстиции РФ по Москве.
            </p>
            <Field
              label="ФИО для таблицы (Фамилия И.О.)"
              value={apostille_signer_short}
              onChange={setApostilleSignerShort}
              placeholder="Байрамов Н.А."
            />
            <Field
              label="ФИО для подписи (И.О. Фамилия)"
              value={apostille_signer_signature}
              onChange={setApostilleSignerSignature}
              placeholder="Н.А. Байрамов"
            />
            <Field
              label="Должность"
              value={apostille_signer_position}
              onChange={setApostilleSignerPosition}
              placeholder="Заместитель начальника отдела международной правовой помощи..."
              textarea
            />
          </Section>

          {/* Pack 19.0 — Образование с кнопкой ? автогенерации */}
          <Section title="Образование">
            <p className="text-xs text-tertiary mb-3">
              Если клиент не указал ВУЗ — кнопка ? подберёт вуз по региону
              и должности. Все поля можно редактировать вручную.
            </p>

            {education.length === 0 && (
              <div
                className="text-xs italic mb-3"
                style={{ color: "var(--color-text-tertiary)" }}
              >
                Образование не заполнено.
              </div>
            )}

            {education.map((edu, i) => (
              <div
                key={i}
                className="rounded-md p-3 mb-3 space-y-2"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border-tertiary)",
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className="text-xs font-semibold uppercase tracking-wide"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    Запись #{i + 1}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setEducation(education.filter((_, idx) => idx !== i));
                    }}
                    className="p-1 rounded hover:bg-red-50"
                    title="Удалить запись"
                  >
                    <Trash2 size={14} style={{ color: "#dc2626" }} />
                  </button>
                </div>

                <div>
                  <label
                    className="text-xs block mb-1"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    Название вуза (полное, для CV)
                  </label>
                  <textarea
                    value={edu.institution}
                    onChange={(e) => {
                      const next = [...education];
                      next[i] = { ...next[i], institution: e.target.value };
                      setEducation(next);
                    }}
                    rows={3}
                    className="w-full px-2 py-1 rounded text-sm"
                    style={{
                      background: "var(--color-bg-primary)",
                      border: "1px solid var(--color-border-tertiary)",
                      color: "var(--color-text-primary)",
                    }}
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label
                      className="text-xs block mb-1"
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      Степень
                    </label>
                    <select
                      value={edu.degree}
                      onChange={(e) => {
                        const next = [...education];
                        next[i] = { ...next[i], degree: e.target.value };
                        setEducation(next);
                      }}
                      className="w-full px-2 py-1 rounded text-sm"
                      style={{
                        background: "var(--color-bg-primary)",
                        border: "1px solid var(--color-border-tertiary)",
                        color: "var(--color-text-primary)",
                      }}
                    >
                      {/* Pack 34.1 — расширенный список степеней/квалификаций.
                          «Инженер» — фактическая квалификация в большинстве
                          российских инженерных дипломов (~80% по словам Кости).
                          «Кандидат наук» — для PhD из OCR. */}
                      <option value="Инженер">Инженер</option>
                      <option value="Специалист">Специалист</option>
                      <option value="Бакалавр">Бакалавр</option>
                      <option value="Магистр">Магистр</option>
                      <option value="Кандидат наук">Кандидат наук</option>
                      <option value="Среднее специальное">Среднее специальное</option>
                    </select>
                  </div>
                  <div>
                    <label
                      className="text-xs block mb-1"
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      Год выпуска
                    </label>
                    <input
                      type="number"
                      value={edu.graduation_year || ""}
                      min={1950}
                      max={2025}
                      onChange={(e) => {
                        const next = [...education];
                        next[i] = {
                          ...next[i],
                          graduation_year: parseInt(e.target.value) || 0,
                        };
                        setEducation(next);
                      }}
                      className="w-full px-2 py-1 rounded text-sm"
                      style={{
                        background: "var(--color-bg-primary)",
                        border: "1px solid var(--color-border-tertiary)",
                        color: "var(--color-text-primary)",
                      }}
                    />
                  </div>
                </div>

                <div>
                  <label
                    className="text-xs block mb-1"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    Специальность (код ОКСО + название)
                  </label>
                  <input
                    type="text"
                    value={edu.specialty}
                    onChange={(e) => {
                      const next = [...education];
                      next[i] = { ...next[i], specialty: e.target.value };
                      setEducation(next);
                    }}
                    placeholder="08.03.01 Строительство"
                    className="w-full px-2 py-1 rounded text-sm"
                    style={{
                      background: "var(--color-bg-primary)",
                      border: "1px solid var(--color-border-tertiary)",
                      color: "var(--color-text-primary)",
                    }}
                  />
                </div>

                {/* ===================================================== */}
                {/* Pack 46.0 — поля для диплома для хурадо               */}
                {/* ===================================================== */}
                <div
                  className="mt-3 pt-3"
                  style={{
                    borderTop: "1px solid var(--color-border-tertiary)",
                  }}
                >
                  <div
                    className="text-xs font-semibold mb-2"
                    style={{ color: "var(--color-text-secondary)" }}
                  >
                    📄 Диплом для хурадо
                  </div>

                  <div className="grid grid-cols-2 gap-2 mb-2">
                    <div>
                      <label
                        className="text-xs block mb-1"
                        style={{ color: "var(--color-text-tertiary)" }}
                      >
                        Номер бланка
                      </label>
                      <input
                        type="text"
                        value={(edu as any).diploma_number || ""}
                        onChange={(e) => {
                          const next = [...education];
                          next[i] = { ...next[i], diploma_number: e.target.value } as any;
                          setEducation(next);
                        }}
                        placeholder="107724  0170246"
                        className="w-full px-2 py-1 rounded text-sm"
                        style={{
                          background: "var(--color-bg-primary)",
                          border: "1px solid var(--color-border-tertiary)",
                          color: "var(--color-text-primary)",
                        }}
                      />
                    </div>
                    <div>
                      <label
                        className="text-xs block mb-1"
                        style={{ color: "var(--color-text-tertiary)" }}
                      >
                        Регистрационный номер
                      </label>
                      <input
                        type="text"
                        value={(edu as any).registration_number || ""}
                        onChange={(e) => {
                          const next = [...education];
                          next[i] = { ...next[i], registration_number: e.target.value } as any;
                          setEducation(next);
                        }}
                        placeholder="2.10.3-13.1/423"
                        className="w-full px-2 py-1 rounded text-sm"
                        style={{
                          background: "var(--color-bg-primary)",
                          border: "1px solid var(--color-border-tertiary)",
                          color: "var(--color-text-primary)",
                        }}
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2 mb-2">
                    <div>
                      <label
                        className="text-xs block mb-1"
                        style={{ color: "var(--color-text-tertiary)" }}
                      >
                        № протокола
                      </label>
                      <input
                        type="text"
                        value={(edu as any).protocol_number || ""}
                        onChange={(e) => {
                          const next = [...education];
                          next[i] = { ...next[i], protocol_number: e.target.value } as any;
                          setEducation(next);
                        }}
                        placeholder="1"
                        className="w-full px-2 py-1 rounded text-sm"
                        style={{
                          background: "var(--color-bg-primary)",
                          border: "1px solid var(--color-border-tertiary)",
                          color: "var(--color-text-primary)",
                        }}
                      />
                    </div>
                    <div>
                      <label
                        className="text-xs block mb-1"
                        style={{ color: "var(--color-text-tertiary)" }}
                      >
                        Дата протокола
                      </label>
                      <input
                        type="date"
                        value={(edu as any).protocol_date || ""}
                        onChange={(e) => {
                          const next = [...education];
                          next[i] = { ...next[i], protocol_date: e.target.value } as any;
                          setEducation(next);
                        }}
                        className="w-full px-2 py-1 rounded text-sm"
                        style={{
                          background: "var(--color-bg-primary)",
                          border: "1px solid var(--color-border-tertiary)",
                          color: "var(--color-text-primary)",
                        }}
                      />
                    </div>
                    <div>
                      <label
                        className="text-xs block mb-1"
                        style={{ color: "var(--color-text-tertiary)" }}
                      >
                        Дата выдачи
                      </label>
                      <input
                        type="date"
                        value={(edu as any).issue_date || ""}
                        onChange={(e) => {
                          const next = [...education];
                          next[i] = { ...next[i], issue_date: e.target.value } as any;
                          setEducation(next);
                        }}
                        className="w-full px-2 py-1 rounded text-sm"
                        style={{
                          background: "var(--color-bg-primary)",
                          border: "1px solid var(--color-border-tertiary)",
                          color: "var(--color-text-primary)",
                        }}
                      />
                    </div>
                  </div>

                  <div className="mb-2">
                    <label
                      className="text-xs block mb-1"
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      Подписанты (по одному на строку, формат «Фамилия И.О.»)
                    </label>
                    <textarea
                      value={
                        ((edu as any).signers || [])
                          .map((s: any) => (typeof s === "string" ? s : s?.name || ""))
                          .filter(Boolean)
                          .join("\n")
                      }
                      onChange={(e) => {
                        const next = [...education];
                        const lines = e.target.value
                          .split("\n")
                          .map((s) => s.trim())
                          .filter(Boolean);
                        next[i] = {
                          ...next[i],
                          signers: lines.map((name) => ({ name, position: null })),
                        } as any;
                        setEducation(next);
                      }}
                      rows={2}
                      placeholder="Афанасьев А.П.&#10;Радаев В.В."
                      className="w-full px-2 py-1 rounded text-sm"
                      style={{
                        background: "var(--color-bg-primary)",
                        border: "1px solid var(--color-border-tertiary)",
                        color: "var(--color-text-primary)",
                      }}
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Pack 46.0 — кнопка LLM-генерации 6 полей */}
                    <button
                      type="button"
                      onClick={() => handleGenerateDiplomaFields(i)}
                      disabled={
                        diplomaGenerating === i ||
                        !edu.institution ||
                        !edu.specialty ||
                        !edu.graduation_year
                      }
                      title={
                        !edu.institution || !edu.specialty || !edu.graduation_year
                          ? "Сначала заполни ВУЗ, специальность и год выпуска"
                          : "Сгенерировать номер бланка, регистрационный, протокол, даты и подписантов через LLM"
                      }
                      className="text-xs flex items-center gap-1 px-2.5 py-1.5 rounded text-primary border hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
                      style={{
                        borderColor: "var(--color-border-tertiary)",
                      }}
                    >
                      {diplomaGenerating === i ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Генерация...
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5" />
                          Сгенерировать
                        </>
                      )}
                    </button>

                    {/* Pack 46.0 — кнопка открытия PDF */}
                    <button
                      type="button"
                      onClick={() => handleOpenDiplomaPdf(i)}
                      disabled={
                        diplomaOpening === i ||
                        !(edu as any).diploma_number ||
                        !(edu as any).registration_number ||
                        !(edu as any).issue_date
                      }
                      title={
                        !(edu as any).diploma_number ||
                        !(edu as any).registration_number ||
                        !(edu as any).issue_date
                          ? "Сначала заполни поля диплома (или сгенерируй)"
                          : "Открыть PDF диплома в новой вкладке"
                      }
                      className="text-xs flex items-center gap-1 px-2.5 py-1.5 rounded text-primary border hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
                      style={{
                        borderColor: "var(--color-border-tertiary)",
                      }}
                    >
                      {diplomaOpening === i ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Открытие...
                        </>
                      ) : (
                        <>
                          📄 Скачать диплом
                        </>
                      )}
                    </button>
                  </div>

                  {diplomaError && (
                    <div
                      className="text-xs mt-2 px-2 py-1 rounded"
                      style={{
                        background: "rgba(220, 38, 38, 0.1)",
                        color: "#b91c1c",
                        border: "1px solid rgba(220, 38, 38, 0.3)",
                      }}
                    >
                      {diplomaError}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {educationFallbackUsed && education.length > 0 && (
              <div
                className="text-xs mb-3 px-3 py-2 rounded-md"
                style={{
                  background: "rgba(234, 179, 8, 0.1)",
                  color: "#b45309",
                  border: "1px solid rgba(234, 179, 8, 0.3)",
                }}
              >
                ? В регионе клиента не нашлось подходящих вузов — подобрали
                из Москвы. Можно нажать ? ещё раз для другого варианта.
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleRegenerateEducation}
                disabled={educationRegenerating}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border-tertiary)",
                  color: "var(--color-text-primary)",
                }}
              >
                {educationRegenerating ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Sparkles size={14} />
                )}
                {education.length > 0 ? "Подобрать другой вуз" : "Подобрать вуз"}
              </button>

              <button
                type="button"
                onClick={() => {
                  setEducation([
                    ...education,
                    {
                      institution: "",
                      graduation_year: new Date().getFullYear() - 10,
                      degree: "Бакалавр",
                      specialty: "",
                    },
                  ]);
                }}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border-tertiary)",
                  color: "var(--color-text-primary)",
                }}
              >
                <Plus size={14} />
                Добавить вручную
              </button>
            </div>
          </Section>

          {/* Pack 19.1 — Опыт работы с кнопкой ✨ автогенерации */}
          <Section title="Опыт работы">
            <p className="text-xs text-tertiary mb-3">
              Если клиент не указал опыт работы — кнопка ✨ подберёт 1-3
              правдоподобные записи (компании + должности + даты) по региону
              и специальности. Минимум 3.5 года в последней работе для DN-визы.
              Все поля можно редактировать вручную.
            </p>

            {workHistory.length === 0 && (
              <div
                className="text-xs italic mb-3"
                style={{ color: "var(--color-text-tertiary)" }}
              >
                Опыт работы не заполнен.
              </div>
            )}

            {workHistory.map((wh, i) => (
              <div
                key={i}
                className="rounded-md p-3 mb-3 space-y-2"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border-tertiary)",
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className="text-xs font-semibold uppercase tracking-wide"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    Запись #{i + 1}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setWorkHistory(workHistory.filter((_, idx) => idx !== i));
                    }}
                    className="p-1 rounded hover:bg-red-50"
                    title="Удалить запись"
                  >
                    <Trash2 size={14} style={{ color: "#dc2626" }} />
                  </button>
                </div>

                <div>
                  <label
                    className="text-xs block mb-1"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    Компания (полное название, для CV)
                  </label>
                  <textarea
                    value={wh.company}
                    onChange={(e) => {
                      const next = [...workHistory];
                      next[i] = { ...next[i], company: e.target.value };
                      setWorkHistory(next);
                    }}
                    rows={2}
                    className="w-full px-2 py-1 rounded text-sm"
                    style={{
                      background: "var(--color-bg-primary)",
                      border: "1px solid var(--color-border-tertiary)",
                      color: "var(--color-text-primary)",
                    }}
                  />
                </div>

                <div>
                  <label
                    className="text-xs block mb-1"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    Должность
                  </label>
                  <input
                    type="text"
                    value={wh.position}
                    onChange={(e) => {
                      const next = [...workHistory];
                      next[i] = { ...next[i], position: e.target.value };
                      setWorkHistory(next);
                    }}
                    placeholder="Главный инженер проекта"
                    className="w-full px-2 py-1 rounded text-sm"
                    style={{
                      background: "var(--color-bg-primary)",
                      border: "1px solid var(--color-border-tertiary)",
                      color: "var(--color-text-primary)",
                    }}
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label
                      className="text-xs block mb-1"
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      Начало (period_start)
                    </label>
                    <input
                      type="text"
                      value={wh.period_start}
                      onChange={(e) => {
                        const next = [...workHistory];
                        next[i] = { ...next[i], period_start: e.target.value };
                        setWorkHistory(next);
                      }}
                      placeholder="Сентябрь 2022"
                      className="w-full px-2 py-1 rounded text-sm"
                      style={{
                        background: "var(--color-bg-primary)",
                        border: "1px solid var(--color-border-tertiary)",
                        color: "var(--color-text-primary)",
                      }}
                    />
                  </div>
                  <div>
                    <label
                      className="text-xs block mb-1"
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      Окончание (period_end)
                    </label>
                    <input
                      type="text"
                      value={wh.period_end}
                      onChange={(e) => {
                        const next = [...workHistory];
                        next[i] = { ...next[i], period_end: e.target.value };
                        setWorkHistory(next);
                      }}
                      placeholder="по настоящее время"
                      className="w-full px-2 py-1 rounded text-sm"
                      style={{
                        background: "var(--color-bg-primary)",
                        border: "1px solid var(--color-border-tertiary)",
                        color: "var(--color-text-primary)",
                      }}
                    />
                  </div>
                </div>

                {/* Pack 19.1b: duties редактируемы */}
                <div>
                  <label
                    className="text-xs block mb-1"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    Обязанности ({(wh.duties || []).length})
                  </label>
                  {(wh.duties || []).map((duty, di) => (
                    <div key={di} className="flex gap-1 mb-1">
                      <textarea
                        value={duty}
                        onChange={(e) => {
                          const next = [...workHistory];
                          const duties = [...(next[i].duties || [])];
                          duties[di] = e.target.value;
                          next[i] = { ...next[i], duties };
                          setWorkHistory(next);
                        }}
                        rows={2}
                        className="w-full px-2 py-1 rounded text-xs"
                        style={{
                          background: "var(--color-bg-primary)",
                          border: "1px solid var(--color-border-tertiary)",
                          color: "var(--color-text-primary)",
                          resize: "vertical",
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const next = [...workHistory];
                          const duties = (next[i].duties || []).filter((_, idx) => idx !== di);
                          next[i] = { ...next[i], duties };
                          setWorkHistory(next);
                        }}
                        className="p-1 rounded hover:bg-red-50 self-start mt-0.5"
                        title="Удалить"
                      >
                        <Trash2 size={12} style={{ color: "#dc2626" }} />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      const next = [...workHistory];
                      next[i] = { ...next[i], duties: [...(next[i].duties || []), ""] };
                      setWorkHistory(next);
                    }}
                    className="text-xs px-2 py-1 rounded mt-1"
                    style={{
                      background: "var(--color-bg-secondary)",
                      border: "1px solid var(--color-border-tertiary)",
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    + Добавить обязанность
                  </button>
                </div>
              </div>
            ))}

            {workHistoryFallbackUsed && workHistory.length > 0 && (
              <div
                className="text-xs mb-3 px-3 py-2 rounded-md"
                style={{
                  background: "rgba(234, 179, 8, 0.1)",
                  color: "#b45309",
                  border: "1px solid rgba(234, 179, 8, 0.3)",
                }}
              >
                ⚠ В регионе клиента не нашлось подходящих компаний — подобрали
                из Москвы. Можно нажать ✨ ещё раз для другого варианта.
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleRegenerateWorkHistory}
                disabled={workHistoryRegenerating}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border-tertiary)",
                  color: "var(--color-text-primary)",
                }}
              >
                {workHistoryRegenerating ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Sparkles size={14} />
                )}
                {workHistory.length > 0 ? "Подобрать другой опыт" : "Подобрать опыт работы"}
              </button>

              <button
                type="button"
                onClick={() => {
                  setWorkHistory([
                    ...workHistory,
                    {
                      period_start: "",
                      period_end: "",
                      company: "",
                      position: "",
                      duties: [],
                    },
                  ]);
                }}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border-tertiary)",
                  color: "var(--color-text-primary)",
                }}
              >
                <Plus size={14} />
                Добавить вручную
              </button>
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

      {/* Pack 28.5: модал уточнения даты регистрации НПД */}
      {refineModalOpen && applicant.inn && (
        <RefineInnDateModal
          applicantId={applicant.id}
          applicantName={[applicant.last_name_native, applicant.first_name_native].filter(Boolean).join(" ") || applicant.last_name_latin || `Applicant ${applicant.id}`}
          inn={applicant.inn}
          onClose={() => setRefineModalOpen(false)}
          onSuccess={(newDate) => {
            setInnRegistrationDate(newDate);
            setRefineModalOpen(false);
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




// Pack 18.5 — значок статуса проверки ИНН через ФНС API
//
// Показывает рядом с полем ИНН результат живой проверки на statusnpd.nalog.ru:
//   verified    > ?? «Проверен ФНС DD.MM.YYYY» (зелёный, последняя успешная проверка)
//   invalid     > ?? «Не действителен (ФНС подтвердил отзыв статуса НПД)» (красный)
//   not_checked > ? «Не проверен» (серый, ИНН выдан до Pack 18.2 или ФНС недоступен был)
//   no_inn / null > ничего не рендерим (значок не нужен пока ИНН пуст)
//
// Источник статуса — backend `_compute_npd_check_status()` на основе
// self_employed_registry.is_invalid + last_npd_check_at.
function NpdCheckBadge({
  status,
  lastCheckAt,
  hasInn,
}: {
  status: "no_inn" | "verified" | "invalid" | "not_checked" | null;
  lastCheckAt: string | null | undefined;
  hasInn: boolean;
}) {
  // Если ИНН пустой или backend сказал no_inn — значок не показываем вообще.
  if (!hasInn || status === "no_inn" || status == null) return null;

  const formatDate = (iso: string | null | undefined): string => {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      const dd = String(d.getDate()).padStart(2, "0");
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const yyyy = d.getFullYear();
      return `${dd}.${mm}.${yyyy}`;
    } catch {
      return "";
    }
  };

  let icon: React.ReactNode;
  let text: string;
  let bg: string;
  let color: string;
  let border: string;
  let title: string;

  if (status === "verified") {
    icon = <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />;
    const dateStr = formatDate(lastCheckAt);
    text = dateStr ? `Проверен ФНС ${dateStr}` : "Проверен ФНС";
    bg = "var(--color-bg-success, var(--color-bg-info))";
    color = "var(--color-text-success, var(--color-text-info))";
    border = "var(--color-border-success, var(--color-border-info))";
    title = "ИНН подтверждён через ФНС API на statusnpd.nalog.ru — самозанятый активен";
  } else if (status === "invalid") {
    icon = <XCircle className="w-3.5 h-3.5 flex-shrink-0" />;
    text = "Не действителен (ФНС подтвердил отзыв)";
    bg = "var(--color-bg-danger)";
    color = "var(--color-text-danger)";
    border = "var(--color-border-danger)";
    title = "ФНС вернул status=False — статус НПД отозван. Подберите другой ИНН через ?";
  } else {
    // not_checked
    icon = <MinusCircle className="w-3.5 h-3.5 flex-shrink-0" />;
    text = "Не проверен";
    bg = "var(--color-bg-secondary)";
    color = "var(--color-text-tertiary)";
    border = "var(--color-border-tertiary)";
    title =
      "ИНН не проверялся через ФНС API (выдан до Pack 18.2 или ФНС был недоступен в момент выдачи). " +
      "Можно перевыдать через ? для свежей проверки.";
  }

  return (
    <div
      className="px-2.5 py-1.5 rounded-md text-xs flex items-center gap-1.5"
      style={{
        background: bg,
        color: color,
        border: `0.5px solid ${border}`,
      }}
      title={title}
    >
      {icon}
      <span>{text}</span>
    </div>
  );
}