"use client";

import { useState, useEffect } from "react";
import { X, Sparkles, Loader2, AlertCircle } from "lucide-react";
import {
  ApplicationResponse,
  ApplicantResponse,
  CompanyResponse,
  PositionResponse,
  requestRecommendation,
  patchApplication,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  applicant: ApplicantResponse | null;
  companies: CompanyResponse[];
  positions: PositionResponse[];
  onClose: () => void;
  onSaved: () => void;
}

export function CompanyContractDrawer({
  application, applicant, companies, positions, onClose, onSaved,
}: Props) {
  const [companyId, setCompanyId] = useState<number | "">(application.company_id || "");
  const [positionId, setPositionId] = useState<number | "">(application.position_id || "");
  const [contractNumber, setContractNumber] = useState(application.contract_number || "");
  const [contractDate, setContractDate] = useState(application.contract_sign_date || "");
  const [contractEndDate, setContractEndDate] = useState(application.contract_end_date || "");
  const [contractCity, setContractCity] = useState(application.contract_sign_city || "");
  const [salary, setSalary] = useState<number | "">(application.salary_rub || "");
  const [paymentsMonths, setPaymentsMonths] = useState(application.payments_period_months || 3);

  const [recommendation, setRecommendation] = useState<any>(application.recommendation_snapshot);
  const [loadingRec, setLoadingRec] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const positionsForCompany = companyId ? positions.filter((p) => p.company_id === companyId) : positions;

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

  function applyRecommendation(positionIdRec: number, companyIdRec: number) {
    setCompanyId(companyIdRec);
    handlePositionChange(positionIdRec);
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
      await patchApplication(application.id, {
        company_id: companyId as number,
        position_id: positionId as number,
        contract_number: contractNumber,
        contract_sign_date: contractDate,
        contract_sign_city: contractCity,
        contract_end_date: contractEndDate || undefined,
        salary_rub: salary as number,
        payments_period_months: paymentsMonths,
      });
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
              <DateField label="Дата окончания" value={contractEndDate} onChange={setContractEndDate} />
              <NumberField label="Зарплата ₽/мес" required value={salary} onChange={setSalary} placeholder="300000" />
              <NumberField label="Период оплат (мес)" value={paymentsMonths}
                onChange={(v) => setPaymentsMonths(Number(v) || 3)} placeholder="3" />
            </div>
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

function RecommendationDisplay({ recommendation, companies, positions, onSelect }: any) {
  const items = [recommendation.top_match, ...(recommendation.alternatives || [])].filter(Boolean);
  if (items.length === 0) return <p className="text-xs text-tertiary">Нет результатов</p>;
  return (
    <div className="space-y-1.5 mt-2">
      {items.slice(0, 3).map((item: any, idx: number) => {
        const position = positions.find((p: PositionResponse) => p.id === item.position_id);
        const company = companies.find((c: CompanyResponse) => c.id === position?.company_id);
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
            {position && company && (
              <button onClick={() => onSelect(position.id, company.id)}
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
