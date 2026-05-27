"use client";

import { useState, useEffect } from "react";
import { X, Sparkles, Loader2, AlertCircle, Languages } from "lucide-react";
import {
  ApplicationResponse,
  ApplicantResponse,
  CompanyResponse,
  PositionResponse,
  requestRecommendation,
  patchApplication,
  updateCompany,
  getTranslitSuggestion,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  applicant: ApplicantResponse | null;
  companies: CompanyResponse[];
  positions: PositionResponse[];
  onClose: () => void;
  onSaved: () => void;
}

// Pack 26.0: автогенерация номера исходящего письма.
// Формат: {3-значное число}/{2 цифры года}, напр. "544/26".
// Менеджер может перебить руками.
function generateLetterNumber(): string {
  const num = Math.floor(100 + Math.random() * 900); // 100-999
  const yy = String(new Date().getFullYear()).slice(-2);
  return `${num}/${yy}`;
}

function letterDateIso(): string {
  // Pack 26.0.2: дата письма = сегодня минус 3-10 дней (случайно).
  // Менеджер может перебить через date input.
  const daysBack = 3 + Math.floor(Math.random() * 8); // 3..10
  const d = new Date();
  d.setDate(d.getDate() - daysBack);
  return d.toISOString().slice(0, 10);
}


// Pack 28.0: рекомендованная дата окончания договора.
// UGE требует чтобы договор покрывал 3-летний срок ВНЖ.
// Считаем от max(submission_date, today) + 3 года + случайно 3..5 месяцев запаса.
function recommendContractEndDate(submissionDate: string): string {
  const sub = submissionDate ? new Date(submissionDate) : new Date();
  const today = new Date();
  const base = sub > today ? sub : today;

  const d = new Date(base);
  d.setFullYear(d.getFullYear() + 3);
  // Случайно 3-5 месяцев сверху (чтобы все договоры не были в одну дату)
  const extraMonths = 3 + Math.floor(Math.random() * 3); // 3, 4, или 5
  d.setMonth(d.getMonth() + extraMonths);

  return d.toISOString().slice(0, 10);
}

// Минимально допустимая дата окончания = submission_date + 3 года ровно (без запаса).
// Используется для soft warning если менеджер поставил дату меньше.
function minRequiredContractEndDate(submissionDate: string): string {
  if (!submissionDate) return "";
  const sub = new Date(submissionDate);
  sub.setFullYear(sub.getFullYear() + 3);
  return sub.toISOString().slice(0, 10);
}

export function CompanyContractDrawer({
  application, applicant, companies, positions, onClose, onSaved,
}: Props) {
  const [companyId, setCompanyId] = useState<number | "">(application.company_id || "");
  // Pack 50.7-D — ОКПО для шапки Приказа Т-9
  const [companyOkpo, setCompanyOkpo] = useState("");
  // Pack 50.8-D — ОКТМО + телефон компании для §1 справки 2-НДФЛ
  const [companyOktmo, setCompanyOktmo] = useState("");
  const [companyPhone, setCompanyPhone] = useState("");

  // Pack 50.7-D — поля для Приказа Т-9 о командировке (отображаются только при EMPLOYMENT)
  const isNaim = (application as any).application_type === "EMPLOYMENT";
  const [btOrderNumber, setBtOrderNumber] = useState((application as any).business_trip_order_number || "");
  const [btOrderDate, setBtOrderDate] = useState((application as any).business_trip_order_date || "");
  const [btStartDate, setBtStartDate] = useState((application as any).business_trip_start_date || "");
  const [btEndDate, setBtEndDate] = useState((application as any).business_trip_end_date || "");
  const [btPurposeOverride, setBtPurposeOverride] = useState((application as any).business_trip_purpose_override || "");
  const [btDurationWords, setBtDurationWords] = useState((application as any).business_trip_duration_words || "");
  const [btDurationUnit, setBtDurationUnit] = useState((application as any).business_trip_duration_unit || "");
  const [btPlaceShort, setBtPlaceShort] = useState<boolean>((application as any).business_trip_place_short || false);
  const [empTabNumber, setEmpTabNumber] = useState((application as any).employee_tab_number || "");
  // Pack 50.8-D — Справка 2-НДФЛ (только для EMPLOYMENT)
  const [ndfl2Year, setNdfl2Year] = useState<number | "">((application as any).ndfl_2_year || "");
  const [ndfl2PeriodFrom, setNdfl2PeriodFrom] = useState<number | "">((application as any).ndfl_2_period_from || "");
  const [ndfl2PeriodTo, setNdfl2PeriodTo] = useState<number | "">((application as any).ndfl_2_period_to || "");
  const [ndfl2IssueDate, setNdfl2IssueDate] = useState<string>((application as any).ndfl_2_issue_date || "");
  const [positionId, setPositionId] = useState<number | "">(application.position_id || "");
  const [contractNumber, setContractNumber] = useState(application.contract_number || "");
  const [contractDate, setContractDate] = useState(application.contract_sign_date || "");
  const [contractEndDate, setContractEndDate] = useState(() => {
    // Pack 28.0: автозаполнение даты окончания договора.
    // Если поле пустое — рекомендуем submission+3y+3..5мес.
    // Если поле задано но меньше submission+3y — тоже перезаписываем (мягкая коррекция).
    const existing = application.contract_end_date || "";
    const submission = application.submission_date || "";
    const minRequired = minRequiredContractEndDate(submission);
    if (!existing) {
      return recommendContractEndDate(submission);
    }
    if (minRequired && existing < minRequired) {
      return recommendContractEndDate(submission);
    }
    return existing;
  });
  const [contractCity, setContractCity] = useState(application.contract_sign_city || "");
  const [salary, setSalary] = useState<number | "">(application.salary_rub || "");
  const [paymentsMonths, setPaymentsMonths] = useState(application.payments_period_months || 3);

  // Pack 26.0 — поля для письма от компании (Исх. №, дата)
  const [letterNumber, setLetterNumber] = useState(
    application.employer_letter_number || generateLetterNumber()
  );
  const [letterDate, setLetterDate] = useState(
    application.employer_letter_date || letterDateIso()
  );

  const [recommendation, setRecommendation] = useState<any>(application.recommendation_snapshot);
  const [loadingRec, setLoadingRec] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Pack 15.1 — поля компании для качественного перевода
  const selectedCompany = companies.find((c) => c.id === companyId);
  const [companyFullNameEs, setCompanyFullNameEs] = useState("");
  const [directorFullNameLatin, setDirectorFullNameLatin] = useState("");
  const [translitLoading, setTranslitLoading] = useState<"name" | "director" | null>(null);
  const [companyFieldsDirty, setCompanyFieldsDirty] = useState(false);

  // Когда меняется выбор компании — подгружаем её текущие поля
  useEffect(() => {
    if (selectedCompany) {
      setCompanyFullNameEs(selectedCompany.full_name_es || "");
      setDirectorFullNameLatin(selectedCompany.director_full_name_latin || "");
      // Pack 50.7-D — синхронизация ОКПО с выбранной компанией
      setCompanyOkpo((selectedCompany as any).okpo || "");
      // Pack 50.8-D — синхронизация ОКТМО/телефона
      setCompanyOktmo((selectedCompany as any).oktmo || "");
      setCompanyPhone((selectedCompany as any).phone || "");
      setCompanyFieldsDirty(false);
    } else {
      setCompanyFullNameEs("");
      setDirectorFullNameLatin("");
      setCompanyOkpo("");
    }
  }, [companyId, selectedCompany?.id]);

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  // Pack 27.1: после отвязки Position от Company (Pack 20.0) фильтр по company_id невалиден.
  // Position больше не имеет поля company_id — показываем все активные должности.
  const positionsForCompany = positions;

  function handlePositionChange(newPositionId: number | "") {
    setPositionId(newPositionId);
    if (newPositionId && !salary) {
      const pos = positions.find((p) => p.id === newPositionId);
      if (pos?.salary_rub_default) setSalary(pos.salary_rub_default);
    }
  }

  async function handleRequestRecommendation() {
    if (!applicant) { setRecError("Клиент ещё не заполнил анкету"); return; }
    setLoadingRec(true); setRecError(null);
    try {
      const result = await requestRecommendation(application.id);
      setRecommendation(result);
    } catch (e) { setRecError((e as Error).message); }
    finally { setLoadingRec(false); }
  }

  function applyRecommendation(positionIdRec: number) {
    // Pack 27.1: больше не подменяем company (Position не привязан к Company начиная с Pack 20.0).
    // Компанию менеджер выбирает отдельно — рекомендация только про должность.
    handlePositionChange(positionIdRec);
  }

  // Pack 15.1: авто-транслит через backend
  async function handleTranslitName() {
    if (!selectedCompany?.full_name_ru) return;
    setTranslitLoading("name");
    try {
      const r = await getTranslitSuggestion(selectedCompany.full_name_ru, "company_name");
      setCompanyFullNameEs(r.suggestion);
      setCompanyFieldsDirty(true);
    } catch (e) {
      alert(`Не удалось получить транслит: ${(e as Error).message}`);
    } finally {
      setTranslitLoading(null);
    }
  }

  async function handleTranslitDirector() {
    if (!selectedCompany?.director_full_name_ru) return;
    setTranslitLoading("director");
    try {
      const r = await getTranslitSuggestion(selectedCompany.director_full_name_ru, "director_name");
      setDirectorFullNameLatin(r.suggestion);
      setCompanyFieldsDirty(true);
    } catch (e) {
      alert(`Не удалось получить транслит: ${(e as Error).message}`);
    } finally {
      setTranslitLoading(null);
    }
  }

  async function handleSave() {
    setSaveError(null);
    const required = {
      Компания: companyId, Должность: positionId,
      "Номер договора": contractNumber, "Дата договора": contractDate,
      "Город подписания": contractCity, Зарплата: salary,
    };
    const missing = Object.entries(required).filter(([_, v]) => !v).map(([k]) => k);
    if (missing.length > 0) { setSaveError(`Заполните поля: ${missing.join(", ")}`); return; }

    setSaving(true);
    try {
      // Pack 15.1: если поля компании менялись — сохраняем компанию
      if (companyFieldsDirty && companyId && selectedCompany) {
        const updates: any = {};
        if (companyFullNameEs !== (selectedCompany.full_name_es || "")) {
          updates.full_name_es = companyFullNameEs;
        }
        if (directorFullNameLatin !== (selectedCompany.director_full_name_latin || "")) {
          updates.director_full_name_latin = directorFullNameLatin || null;
        }
        // Pack 50.7-D — ОКПО для Т-9
        if (companyOkpo !== ((selectedCompany as any).okpo || "")) {
          updates.okpo = companyOkpo.trim() || null;
        }
        // Pack 50.8-D — ОКТМО + телефон для 2-НДФЛ
        if (companyOktmo !== ((selectedCompany as any).oktmo || "")) {
          updates.oktmo = companyOktmo.trim() || null;
        }
        if (companyPhone !== ((selectedCompany as any).phone || "")) {
          updates.phone = companyPhone.trim() || null;
        }
        if (Object.keys(updates).length > 0) {
          await updateCompany(companyId as number, updates);
        }
      }

      await patchApplication(application.id, {
        company_id: companyId as number,
        position_id: positionId as number,
        contract_number: contractNumber,
        contract_sign_date: contractDate,
        contract_sign_city: contractCity,
        contract_end_date: contractEndDate || undefined,
        salary_rub: salary as number,
        payments_period_months: paymentsMonths,
        // Pack 26.0 — поля письма
        employer_letter_number: letterNumber || undefined,
        employer_letter_date: letterDate || undefined,
        // Pack 50.7-D — поля Приказа Т-9 (отправляются всегда; для SELF_EMPLOYED останутся NULL т.к. не редактировались)
        business_trip_order_number: btOrderNumber.trim() || undefined,
        business_trip_order_date: btOrderDate || undefined,
        business_trip_start_date: btStartDate || undefined,
        business_trip_end_date: btEndDate || undefined,
        business_trip_purpose_override: btPurposeOverride.trim() || undefined,
        business_trip_duration_words: btDurationWords.trim() || undefined,
        business_trip_duration_unit: btDurationUnit || undefined,
        business_trip_place_short: btPlaceShort,
        employee_tab_number: empTabNumber.trim() || undefined,
        // Pack 50.8-D — поля Справки 2-НДФЛ (только для EMPLOYMENT; для SELF_EMPLOYED null)
        ndfl_2_year: ndfl2Year === "" ? null : Number(ndfl2Year),
        ndfl_2_period_from: ndfl2PeriodFrom === "" ? null : Number(ndfl2PeriodFrom),
        ndfl_2_period_to: ndfl2PeriodTo === "" ? null : Number(ndfl2PeriodTo),
        ndfl_2_issue_date: ndfl2IssueDate || null,
      } as any);
      onSaved();
    } catch (e) { setSaveError((e as Error).message); }
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
            Компания и договор · #{application.reference}
          </h2>
          <button onClick={onClose} className="p-1 rounded-md text-tertiary hover:text-primary hover:bg-secondary">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          <div className="rounded-md p-3 border" style={{
            background: "var(--color-bg-info)",
            borderColor: "var(--color-border-info)",
            borderWidth: 0.5,
          }}>
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <h4 className="text-sm font-semibold text-info flex items-center gap-1.5">
                <Sparkles className="w-4 h-4" />
                Рекомендация Claude
              </h4>
              {!recommendation && (
                <button onClick={handleRequestRecommendation} disabled={loadingRec || !applicant}
                  className="text-xs px-3 py-1 rounded-md font-medium text-white disabled:opacity-50 flex items-center gap-1.5"
                  style={{ background: "var(--color-accent)" }}>
                  {loadingRec ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Получить"}
                </button>
              )}
            </div>
            {recError && <div className="text-xs text-danger mb-1">{recError}</div>}
            {!recommendation && !loadingRec && (
              <p className="text-xs text-info">Claude предложит должность на основе опыта клиента</p>
            )}
            {recommendation && (
              <RecommendationDisplay recommendation={recommendation} companies={companies}
                positions={positions} onSelect={applyRecommendation} />
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <SelectField label="Компания" required value={companyId}
              onChange={(v) => { setCompanyId(v); setPositionId(""); }}
              options={companies.map((c) => ({ value: c.id, label: c.short_name }))} />
            <SelectField label="Должность" required value={positionId}
              onChange={handlePositionChange}
              options={positionsForCompany.map((p) => ({ value: p.id, label: p.title_ru }))}
              disabled={!companyId} />
          </div>

          <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-2">Договор</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <TextField label="Номер договора" required value={contractNumber}
                onChange={setContractNumber} placeholder="004/09/25" />
              <DateField label="Дата подписания" required value={contractDate} onChange={setContractDate} />
              <TextField label="Город подписания" required value={contractCity}
                onChange={setContractCity} placeholder="Москва" />
              <div>
                <DateField label="Дата окончания" value={contractEndDate} onChange={setContractEndDate} />
                {(() => {
                  // Pack 28.0: soft warning если дата окончания < submission+3 года.
                  // ВНЖ выдаётся на 3 года, договор должен покрывать весь срок.
                  const minRequired = minRequiredContractEndDate(application.submission_date || "");
                  if (!minRequired || !contractEndDate) return null;
                  if (contractEndDate >= minRequired) return null;
                  const minRequiredFormatted = new Date(minRequired).toLocaleDateString("ru");
                  return (
                    <div
                      className="mt-1 p-2 rounded text-xs flex items-start gap-1.5"
                      style={{
                        background: "var(--color-bg-warning)",
                        color: "var(--color-text-warning)",
                      }}
                    >
                      <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                      <span>
                        Договор покрывает менее 3 лет от даты подачи. Рекомендуется ≥ {minRequiredFormatted} —
                        ВНЖ выдаётся на 3 года, UGE может зацепиться.
                      </span>
                    </div>
                  );
                })()}
              </div>
              <NumberField label="Зарплата ₽/мес" required value={salary} onChange={setSalary} placeholder="300000" />
              <NumberField label="Период оплат (мес)" value={paymentsMonths}
                onChange={(v) => setPaymentsMonths(Number(v) || 3)} placeholder="3" />
            </div>
          </div>

          {/* Pack 26.0 — реквизиты письма от компании */}
          <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-1">
              Письмо от компании
            </h4>
            <p className="text-[11px] text-tertiary mb-3">
              Исходящий номер и дата письма. Подставляются в шапку «08_Письмо.docx». Авто-сгенерированы — можно перебить.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-secondary mb-1">Исх. №</label>
                <div className="flex gap-1.5">
                  <input type="text" value={letterNumber}
                    onChange={(e) => setLetterNumber(e.target.value)}
                    placeholder="544/26"
                    className="flex-1 px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
                  <button type="button" onClick={() => setLetterNumber(generateLetterNumber())}
                    className="px-2 py-1.5 rounded-md border text-tertiary hover:bg-secondary transition-colors flex items-center"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                    title="Сгенерировать новый номер">
                    <Sparkles className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <DateField label="Дата письма" value={letterDate} onChange={setLetterDate} />
            </div>
          </div>

          {/* Pack 15.1 — поля для качественного испанского перевода */}
          {selectedCompany && (
            <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-1 flex items-center gap-1.5">
                <Languages className="w-3.5 h-3.5" />
                Поля компании для перевода
              </h4>
              <p className="text-[11px] text-tertiary mb-3">
                Используются Pack 15 при переводе на испанский. Кнопка ✨ — авто-транслит по ГОСТ как черновик, можно подправить.
              </p>
              <div className="space-y-3">
                <TranslitField
                  label="Название компании на испанском"
                  ru={selectedCompany.full_name_ru}
                  value={companyFullNameEs}
                  onChange={(v) => { setCompanyFullNameEs(v); setCompanyFieldsDirty(true); }}
                  onTranslit={handleTranslitName}
                  loading={translitLoading === "name"}
                  placeholder='напр. «Sociedad Limitada "INZHGEOSERVIS"»'
                />
                <TranslitField
                  label="ФИО директора на латинице"
                  ru={selectedCompany.director_full_name_ru}
                  value={directorFullNameLatin}
                  onChange={(v) => { setDirectorFullNameLatin(v); setCompanyFieldsDirty(true); }}
                  onTranslit={handleTranslitDirector}
                  loading={translitLoading === "director"}
                  placeholder='напр. "Tarakin Yury Aleksandrovich"'
                />
                {/* Pack 50.7-D — ОКПО (8 цифр) для шапки Приказа Т-9 */}
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">
                    ОКПО <span className="text-tertiary font-normal">(для Т-9 при найме)</span>
                  </label>
                  <input
                    type="text"
                    value={companyOkpo}
                    onChange={(e) => { setCompanyOkpo(e.target.value); setCompanyFieldsDirty(true); }}
                    placeholder="например 01465988 (8 цифр)"
                    maxLength={8}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                {/* Pack 50.8-D — ОКТМО (8 или 11 цифр) для шапки Справки 2-НДФЛ */}
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">
                    ОКТМО <span className="text-tertiary font-normal">(для 2-НДФЛ при найме)</span>
                  </label>
                  <input
                    type="text"
                    value={companyOktmo}
                    onChange={(e) => { setCompanyOktmo(e.target.value); setCompanyFieldsDirty(true); }}
                    placeholder="например 45901000000 (8 или 11 цифр)"
                    maxLength={11}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                {/* Pack 50.8-D — Телефон компании для шапки Справки 2-НДФЛ */}
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">
                    Телефон компании <span className="text-tertiary font-normal">(для 2-НДФЛ при найме)</span>
                  </label>
                  <input
                    type="text"
                    value={companyPhone}
                    onChange={(e) => { setCompanyPhone(e.target.value); setCompanyFieldsDirty(true); }}
                    placeholder="например +74954104579"
                    maxLength={32}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
              </div>
              {companyFieldsDirty && (
                <p className="text-[11px] text-info mt-2">
                  Изменения применятся ко всей компании при сохранении
                </p>
              )}
            </div>
          )}

          {/* Pack 50.7-D — Секция Командировка (Т-9). Только для EMPLOYMENT. */}
          {isNaim && (
            <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-1">
                💼 Командировка (Приказ Т-9)
              </h4>
              <p className="text-[11px] text-tertiary mb-3">
                Поля для шаблона «17_Приказ_на_командировку.docx». Большинство auto если оставить пустыми:
                номер генерится по компании, даты — из договора + 30 дней / +3 года, срок — из дат прописью.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">№ приказа Т-9</label>
                  <input
                    type="text"
                    value={btOrderNumber}
                    onChange={(e) => setBtOrderNumber(e.target.value)}
                    placeholder="auto, напр. 37/к"
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Дата приказа</label>
                  <input
                    type="date"
                    value={btOrderDate}
                    onChange={(e) => setBtOrderDate(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                  <p className="text-[10px] text-tertiary mt-0.5">пусто = дата договора</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Начало командировки</label>
                  <input
                    type="date"
                    value={btStartDate}
                    onChange={(e) => setBtStartDate(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                  <p className="text-[10px] text-tertiary mt-0.5">пусто = подача + 30 дней</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Конец командировки</label>
                  <input
                    type="date"
                    value={btEndDate}
                    onChange={(e) => setBtEndDate(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                  <p className="text-[10px] text-tertiary mt-0.5">пусто = начало + 3 года</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Срок словами (override)</label>
                  <input
                    type="text"
                    value={btDurationWords}
                    onChange={(e) => setBtDurationWords(e.target.value)}
                    placeholder="auto, напр. Сорок шесть"
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Единица срока (override)</label>
                  <select
                    value={btDurationUnit}
                    onChange={(e) => setBtDurationUnit(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  >
                    <option value="">auto (по датам)</option>
                    <option value="days">дни</option>
                    <option value="months">месяцы</option>
                    <option value="years">годы</option>
                  </select>
                </div>
              </div>

              <div className="mt-3">
                <label className="block text-xs font-medium text-secondary mb-1">
                  Цель командировки (override)
                </label>
                <textarea
                  value={btPurposeOverride}
                  onChange={(e) => setBtPurposeOverride(e.target.value)}
                  placeholder="auto, берётся из Position.business_trip_purpose"
                  rows={3}
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                />
                <p className="text-[10px] text-tertiary mt-0.5">
                  Пусто = берётся из настроек должности. Заполни если для этой заявки нужна особая формулировка.
                </p>
              </div>

              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Табельный номер</label>
                  <input
                    type="text"
                    value={empTabNumber}
                    onChange={(e) => setEmpTabNumber(e.target.value)}
                    placeholder="напр. 159"
                    maxLength={16}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                <div className="flex items-end">
                  <label className="flex items-center gap-2 text-xs text-secondary cursor-pointer">
                    <input
                      type="checkbox"
                      checked={btPlaceShort}
                      onChange={(e) => setBtPlaceShort(e.target.checked)}
                      className="rounded"
                    />
                    Короткий формат адреса (только страна и город)
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* Pack 50.8-D — Секция Справка 2-НДФЛ. Только для EMPLOYMENT. */}
          {isNaim && (
            <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
              <div className="flex items-center justify-between mb-1">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-tertiary">
                  📊 Справка 2-НДФЛ (КНД 1175018)
                </h4>
                <button
                  type="button"
                  onClick={() => {
                    // ✨ Авторасчёт: год = текущий, период 1..последний полный месяц,
                    // дата формирования = 1-е число месяца после period_to
                    const today = new Date();
                    let y = today.getFullYear();
                    let pFrom = 1;
                    let pTo: number;
                    if (today.getMonth() === 0) {
                      // январь — берём декабрь предыдущего года
                      y -= 1;
                      pTo = 12;
                    } else {
                      pTo = today.getMonth();  // getMonth() = 0..11, нужен (текущий - 1) → 0..11 → 1..12 после +1
                      // т.е. если сейчас май (getMonth()=4), pTo = 4 → апрель — последний полный месяц
                    }
                    setNdfl2Year(y);
                    setNdfl2PeriodFrom(pFrom);
                    setNdfl2PeriodTo(pTo);
                    // issue_date = 1 число месяца после pTo
                    const issue = pTo === 12
                      ? new Date(y + 1, 0, 1)
                      : new Date(y, pTo, 1);  // pTo (1..11) → pTo (как индекс месяца следующего) — потому что getMonth() 0-индекс
                    setNdfl2IssueDate(issue.toISOString().slice(0, 10));
                  }}
                  className="text-[11px] px-2 py-1 rounded-md border text-secondary hover:bg-secondary flex items-center gap-1"
                  style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
                  title="Рассчитать автоматически: год = текущий, период с января по последний полный месяц, дата формирования = 1 число следующего"
                >
                  <Sparkles className="w-3 h-3" />
                  Рассчитать авто
                </button>
              </div>
              <p className="text-[11px] text-tertiary mb-3">
                Поля для шаблона «18_2-НДФЛ.docx». Если оставить пустыми — на бэкенде вычислятся дефолты
                (год = текущий, период 1..последний полный месяц, дата = 1 число следующего).
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Год</label>
                  <input
                    type="number"
                    value={ndfl2Year}
                    onChange={(e) => setNdfl2Year(e.target.value === "" ? "" : Number(e.target.value))}
                    placeholder="2026"
                    min={2020}
                    max={2099}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Период с (месяц)</label>
                  <input
                    type="number"
                    value={ndfl2PeriodFrom}
                    onChange={(e) => setNdfl2PeriodFrom(e.target.value === "" ? "" : Number(e.target.value))}
                    placeholder="1"
                    min={1}
                    max={12}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Период по (месяц)</label>
                  <input
                    type="number"
                    value={ndfl2PeriodTo}
                    onChange={(e) => setNdfl2PeriodTo(e.target.value === "" ? "" : Number(e.target.value))}
                    placeholder="5"
                    min={1}
                    max={12}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Дата формирования</label>
                  <input
                    type="date"
                    value={ndfl2IssueDate}
                    onChange={(e) => setNdfl2IssueDate(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
              </div>
            </div>
          )}

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

function RecommendationDisplay({ recommendation, companies, positions, onSelect }: any) {
  const items = [recommendation.top_match, ...(recommendation.alternatives || [])].filter(Boolean);
  if (items.length === 0) return <p className="text-xs text-tertiary">Нет результатов</p>;
  return (
    <div className="space-y-1.5 mt-2">
      {items.slice(0, 3).map((item: any, idx: number) => {
        const position = positions.find((p: PositionResponse) => p.id === item.position_id);
        // Pack 27.1: position.company_id больше не существует (Pack 20.0).
        // Компанию для строки-рекомендации не показываем — она выбирается отдельно сверху.
        const company = null as CompanyResponse | null;
        return (
          <div key={idx} className="bg-primary rounded-md p-2 border flex items-center justify-between gap-2"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-primary line-clamp-1">
                {item.position_title || position?.title_ru || "—"}
              </div>
              <div className="text-[10px] text-tertiary">
                {company?.short_name || "—"}
                {item.score !== undefined && ` · ${Math.round(item.score * 100)}%`}
              </div>
            </div>
            {position && (
              <button onClick={() => onSelect(position.id)}
                className="text-[10px] px-2 py-1 rounded text-white whitespace-nowrap"
                style={{ background: "var(--color-accent)" }}>
                Выбрать
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function SelectField({ label, required, value, onChange, options, disabled }: any) {
  return (
    <div>
      <label className="block text-xs font-medium text-secondary mb-1">
        {label} {required && <span className="text-danger">*</span>}
      </label>
      <select value={value} onChange={(e) => onChange(e.target.value ? parseInt(e.target.value, 10) : "")}
        disabled={disabled}
        className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary disabled:opacity-50 focus:outline-none focus:ring-2"
        style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}>
        <option value="">— выберите —</option>
        {options.map((opt: any) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
      </select>
    </div>
  );
}

function TextField({ label, required, value, onChange, placeholder }: any) {
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

function DateField({ label, required, value, onChange }: any) {
  return (
    <div>
      <label className="block text-xs font-medium text-secondary mb-1">
        {label} {required && <span className="text-danger">*</span>}
      </label>
      <input type="date" value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
        style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
    </div>
  );
}

function NumberField({ label, required, value, onChange, placeholder }: any) {
  return (
    <div>
      <label className="block text-xs font-medium text-secondary mb-1">
        {label} {required && <span className="text-danger">*</span>}
      </label>
      <input type="number" value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
        placeholder={placeholder}
        className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
        style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
    </div>
  );
}

// Pack 15.1
function TranslitField({ label, ru, value, onChange, onTranslit, loading, placeholder }: {
  label: string;
  ru?: string;
  value: string;
  onChange: (v: string) => void;
  onTranslit: () => void;
  loading: boolean;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-secondary mb-1">{label}</label>
      {ru && (
        <div className="text-[11px] text-tertiary mb-1 truncate" title={ru}>
          из русского: {ru}
        </div>
      )}
      <div className="flex gap-1.5">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
          style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
        />
        <button
          type="button"
          onClick={onTranslit}
          disabled={loading || !ru}
          className="px-2 py-1.5 rounded-md border text-tertiary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1"
          style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
          title="Авто-транслит по ГОСТ (черновик)"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
}
