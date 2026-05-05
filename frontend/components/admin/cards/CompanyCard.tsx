"use client";

import { Building2, Edit2, CheckCircle2, AlertTriangle, XCircle, Landmark } from "lucide-react";
import { CompanyResponse, PositionResponse, ApplicationResponse } from "@/lib/api";

interface Props {
  company?: CompanyResponse;
  position?: PositionResponse;
  application: ApplicationResponse;
  onEdit: () => void;
}

// Pack 29.2 — константы для проверок
const UGE_MIN_SALARY_EUR = 2762; // Минимум для DN-визы (200% испанского SMI 2026 + запас)
const RUB_PER_EUR = 95;          // Примерный курс для конвертации (поправить если сильно изменится)
const REQUIRED_CONTRACT_DAYS = 90; // UGE требует ≥90 дней между подписанием и подачей
const REQUIRED_VISA_YEARS = 3;     // ВНЖ выдаётся на 3 года — договор должен покрывать

type CheckStatus = "ok" | "warn" | "error" | "neutral";

interface CheckResult {
  status: CheckStatus;
  message: string;
}

function daysSince(dateStr?: string): number | null {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  const now = new Date();
  return Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
}

function daysBetween(fromIso?: string, toIso?: string): number | null {
  if (!fromIso || !toIso) return null;
  const a = new Date(fromIso);
  const b = new Date(toIso);
  return Math.floor((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
}

function formatRub(amount?: number | null): string {
  if (!amount) return "—";
  return new Intl.NumberFormat("ru-RU").format(amount) + " ₽/мес";
}

function rubToEur(rub?: number | null): number {
  if (!rub) return 0;
  return Math.round(rub / RUB_PER_EUR);
}

function formatDuration(days: number | null): string {
  if (days === null) return "";
  if (days < 0) return `просрочен на ${Math.abs(days)} дн.`;
  const years = Math.floor(days / 365);
  const months = Math.floor((days % 365) / 30);
  if (years > 0 && months > 0) return `~${years} г ${months} мес`;
  if (years > 0) return `~${years} г`;
  if (months > 0) return `~${months} мес`;
  return `${days} дн.`;
}

// =============================================================================
// Проверки бизнес-правил (Pack 29.2)
// =============================================================================

function checkContractAge(application: ApplicationResponse): CheckResult {
  // Договор должен быть подписан минимум за 90 дней до подачи
  const days = daysBetween(application.contract_sign_date, application.submission_date);
  if (days === null) {
    return { status: "neutral", message: "Не заполнены даты договора и/или подачи" };
  }
  if (days >= REQUIRED_CONTRACT_DAYS) {
    return { status: "ok", message: `Договор подписан за ${days} дней до подачи (требуется ≥${REQUIRED_CONTRACT_DAYS})` };
  }
  if (days >= 60) {
    return { status: "warn", message: `До подачи всего ${days} дней — UGE требует минимум ${REQUIRED_CONTRACT_DAYS}` };
  }
  return { status: "error", message: `До подачи всего ${days} дней — это меньше требуемых ${REQUIRED_CONTRACT_DAYS}` };
}

function checkContractCoverage(application: ApplicationResponse): CheckResult {
  // Договор должен покрывать 3-летний срок ВНЖ от даты подачи
  if (!application.contract_end_date || !application.submission_date) {
    return { status: "neutral", message: "Не заполнены даты окончания договора и/или подачи" };
  }
  const submission = new Date(application.submission_date);
  const required = new Date(submission);
  required.setFullYear(required.getFullYear() + REQUIRED_VISA_YEARS);
  const requiredWarn = new Date(submission);
  requiredWarn.setMonth(requiredWarn.getMonth() + REQUIRED_VISA_YEARS * 12 - 6); // -6 месяцев warn-зона

  const end = new Date(application.contract_end_date);
  const requiredFmt = required.toLocaleDateString("ru");

  if (end >= required) {
    const remaining = daysBetween(application.submission_date, application.contract_end_date);
    return {
      status: "ok",
      message: `Договор покрывает ${formatDuration(remaining)} от даты подачи (нужно ≥3 года)`,
    };
  }
  if (end >= requiredWarn) {
    return {
      status: "warn",
      message: `Договор почти покрывает 3 года, но не до конца — рекомендуется ≥${requiredFmt}`,
    };
  }
  return {
    status: "error",
    message: `Договор покрывает менее 2.5 лет — рекомендуется ≥${requiredFmt}`,
  };
}

function checkSalary(application: ApplicationResponse): CheckResult {
  const rub = application.salary_rub;
  if (!rub) {
    return { status: "neutral", message: "Зарплата не указана" };
  }
  const eur = rubToEur(rub);
  if (eur >= UGE_MIN_SALARY_EUR) {
    return {
      status: "ok",
      message: `~${eur}€/мес ≥ ${UGE_MIN_SALARY_EUR}€ (минимум UGE для DN-визы)`,
    };
  }
  if (eur >= UGE_MIN_SALARY_EUR * 0.9) {
    return {
      status: "warn",
      message: `~${eur}€/мес — близко к минимуму ${UGE_MIN_SALARY_EUR}€, риск отказа`,
    };
  }
  return {
    status: "error",
    message: `~${eur}€/мес — ниже минимума ${UGE_MIN_SALARY_EUR}€ для DN-визы`,
  };
}

function checkCompanyComplete(company?: CompanyResponse): CheckResult {
  if (!company) {
    return { status: "neutral", message: "Компания не выбрана" };
  }
  // Critical fields
  const critical = {
    "ИНН": company.tax_id_primary,
    "Юр. адрес": company.legal_address,
    "ФИО директора": company.director_full_name_ru,
    "Банк": company.bank_name,
    "Расчётный счёт": company.bank_account,
    "БИК": company.bank_bic,
  };
  const missingCritical = Object.entries(critical)
    .filter(([, v]) => !v || (typeof v === "string" && !v.trim()))
    .map(([k]) => k);

  if (missingCritical.length === 0) {
    return { status: "ok", message: "Все ключевые реквизиты заполнены" };
  }
  if (missingCritical.length <= 2) {
    return { status: "warn", message: `Не хватает: ${missingCritical.join(", ")}` };
  }
  return { status: "error", message: `Не хватает критичных полей: ${missingCritical.join(", ")}` };
}

// =============================================================================
// Иконка статуса
// =============================================================================

function StatusIcon({ check }: { check: CheckResult }) {
  if (check.status === "ok") {
    return (
      <span title={check.message} className="inline-flex">
        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--color-text-success)" }} />
      </span>
    );
  }
  if (check.status === "warn") {
    return (
      <span title={check.message} className="inline-flex">
        <AlertTriangle className="w-3.5 h-3.5" style={{ color: "var(--color-text-warning)" }} />
      </span>
    );
  }
  if (check.status === "error") {
    return (
      <span title={check.message} className="inline-flex">
        <XCircle className="w-3.5 h-3.5" style={{ color: "var(--color-text-danger)" }} />
      </span>
    );
  }
  return null; // neutral — иконку не показываем
}

// =============================================================================
// Main
// =============================================================================

export function CompanyCard({ company, position, application, onEdit }: Props) {
  const days = daysSince(application.contract_sign_date);
  const inn = company?.tax_id_primary;

  // Pack 29.2 — все 4 проверки
  const contractAgeCheck = checkContractAge(application);
  const contractCoverageCheck = checkContractCoverage(application);
  const salaryCheck = checkSalary(application);
  const companyCheck = checkCompanyComplete(company);

  // Расчёты для UI
  const contractEndDays = application.contract_end_date
    ? daysBetween(new Date().toISOString().slice(0, 10), application.contract_end_date)
    : null;

  // Сжатое имя банка (Альфа, ВТБ, Сбер...) — берём короткую часть до первой запятой/тире
  const bankShortName = company?.bank_name
    ? company.bank_name.split(/[,\-—]/)[0].trim()
    : null;

  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary flex items-center gap-1.5">
          <Building2 className="w-3.5 h-3.5" />
          Компания и договор
        </h3>
        <button
          onClick={onEdit}
          className="text-xs text-info hover:underline flex items-center gap-1"
          title="Изменить компанию и договор"
        >
          <Edit2 className="w-3 h-3" />
          Изменить
        </button>
      </div>

      {!company ? (
        <div className="text-sm text-tertiary italic py-4">Не распределена</div>
      ) : (
        <div className="space-y-2">
          {/* Заказчик + статус полноты реквизитов */}
          <div>
            <div className="text-[11px] text-tertiary flex items-center gap-1">
              Заказчик
              <StatusIcon check={companyCheck} />
            </div>
            <div className="text-sm text-primary">
              {company.short_name}
              {inn && (
                <span className="text-tertiary text-xs ml-2 font-mono">ИНН {inn}</span>
              )}
            </div>
          </div>

          {/* Должность */}
          <div>
            <div className="text-[11px] text-tertiary">Должность</div>
            <div className="text-sm text-primary">{position?.title_ru || "—"}</div>
          </div>

          {/* Pack 29.2 — Банк (новое поле) */}
          {bankShortName && (
            <div>
              <div className="text-[11px] text-tertiary flex items-center gap-1">
                <Landmark className="w-3 h-3" />
                Банк
              </div>
              <div className="text-sm text-primary">
                {bankShortName}
                {company.bank_bic && (
                  <span className="text-tertiary text-xs ml-2 font-mono">
                    БИК {company.bank_bic}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Договор — даты, зарплата */}
          {(application.contract_sign_date || application.contract_end_date || application.salary_rub) && (
            <div
              className="border-t pt-2 mt-2"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderTopWidth: 0.5,
              }}
            >
              {/* Дата подписания */}
              {application.contract_sign_date && (
                <div className="mb-1.5">
                  <div className="text-[11px] text-tertiary flex items-center gap-1">
                    Договор подписан
                    <StatusIcon check={contractAgeCheck} />
                  </div>
                  <div className="text-sm text-primary">
                    {new Date(application.contract_sign_date).toLocaleDateString("ru")}
                    {days !== null && (
                      <span className="text-tertiary text-xs ml-2">
                        ({days} дн. назад)
                      </span>
                    )}
                    {application.contract_number && (
                      <span className="text-tertiary text-xs ml-2 font-mono">
                        №{application.contract_number}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Pack 29.2 — Дата окончания (новое поле) */}
              {application.contract_end_date && (
                <div className="mb-1.5">
                  <div className="text-[11px] text-tertiary flex items-center gap-1">
                    Договор до
                    <StatusIcon check={contractCoverageCheck} />
                  </div>
                  <div className="text-sm text-primary">
                    {new Date(application.contract_end_date).toLocaleDateString("ru")}
                    {contractEndDays !== null && contractEndDays > 0 && (
                      <span className="text-tertiary text-xs ml-2">
                        (осталось {formatDuration(contractEndDays)})
                      </span>
                    )}
                    {contractEndDays !== null && contractEndDays <= 0 && (
                      <span className="text-xs ml-2" style={{ color: "var(--color-text-danger)" }}>
                        (договор истёк)
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Зарплата */}
              {application.salary_rub && (
                <div>
                  <div className="text-[11px] text-tertiary flex items-center gap-1">
                    Зарплата
                    <StatusIcon check={salaryCheck} />
                  </div>
                  <div className="text-sm text-primary">
                    {formatRub(application.salary_rub)}
                    <span className="text-tertiary text-xs ml-2">
                      (~{rubToEur(application.salary_rub)} €/мес)
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
