"use client";

import { Check, X, AlertCircle } from "lucide-react";
import {
  ApplicationResponse,
  ApplicantResponse,
  CompanyResponse,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  applicant: ApplicantResponse | null;
  company?: CompanyResponse;
}

interface Check {
  status: "ok" | "fail" | "pending";
  text: string;
}

const EUR_RATE_FALLBACK = 90;
const EUR_THRESHOLD = 2762;

function buildChecks(
  application: ApplicationResponse,
  applicant: ApplicantResponse | null,
): Check[] {
  const checks: Check[] = [];

  if (application.contract_sign_date && application.submission_date) {
    const signDate = new Date(application.contract_sign_date);
    const submitDate = new Date(application.submission_date);
    const days = Math.floor(
      (submitDate.getTime() - signDate.getTime()) / (1000 * 60 * 60 * 24),
    );
    if (days >= 90) {
      checks.push({
        status: "ok",
        text: `Договор подписан ${days} дн. назад (минимум 90)`,
      });
    } else {
      checks.push({
        status: "fail",
        text: `Договор подписан только ${days} дн. назад — нужно минимум 90`,
      });
    }
  } else {
    checks.push({
      status: "pending",
      text: "Договор не подписан или не задана дата подачи",
    });
  }

  if (application.salary_rub) {
    const eurAmount = Math.round(application.salary_rub / EUR_RATE_FALLBACK);
    if (eurAmount >= EUR_THRESHOLD) {
      checks.push({
        status: "ok",
        text: `Эквивалент в евро ~${eurAmount} € — выше порога ${EUR_THRESHOLD} €`,
      });
    } else {
      checks.push({
        status: "fail",
        text: `Эквивалент в евро ~${eurAmount} € — ниже порога ${EUR_THRESHOLD} €`,
      });
    }
  } else {
    checks.push({
      status: "pending",
      text: "Зарплата не задана",
    });
  }

  if (applicant) {
    const requiredFields = [
      applicant.last_name_native,
      applicant.first_name_native,
      applicant.last_name_latin,
      applicant.first_name_latin,
      applicant.birth_date,
      applicant.passport_number,
      applicant.email,
      applicant.phone,
    ];
    const filled = requiredFields.filter(Boolean).length;
    if (filled === requiredFields.length) {
      checks.push({
        status: "ok",
        text: "Анкета клиента полностью заполнена",
      });
    } else {
      checks.push({
        status: "fail",
        text: `Анкета заполнена не полностью (${filled} из ${requiredFields.length})`,
      });
    }
  } else {
    checks.push({
      status: "pending",
      text: "Клиент ещё не начал заполнять анкету",
    });
  }

  const isAssigned =
    application.company_id &&
    application.position_id &&
    application.representative_id &&
    application.spain_address_id;
  if (isAssigned) {
    checks.push({
      status: "ok",
      text: "Распределение завершено: компания, должность, представитель и адрес",
    });
  } else {
    checks.push({
      status: "pending",
      text: "Распределение не завершено",
    });
  }

  const docsGenerated = [
    "drafts_generated",
    "at_translator",
    "awaiting_scans",
    "awaiting_digital_sign",
    "submitted",
    "approved",
  ].includes(application.status);
  if (docsGenerated) {
    checks.push({
      status: "ok",
      text: "Все 10 документов сгенерированы",
    });
  }

  return checks;
}

export function BusinessChecksBlock({ application, applicant, company }: Props) {
  const checks = buildChecks(application, applicant);
  if (checks.length === 0) return null;

  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
        Чек-лист
      </h3>
      <div className="space-y-2">
        {checks.map((check, idx) => (
          <CheckRow key={idx} check={check} />
        ))}
      </div>
    </div>
  );
}

function CheckRow({ check }: { check: Check }) {
  const config = {
    ok: {
      Icon: Check,
      bg: "var(--color-bg-success)",
      iconColor: "var(--color-text-success)",
      textColor: "var(--color-text-success)",
    },
    fail: {
      Icon: X,
      bg: "var(--color-bg-danger)",
      iconColor: "var(--color-text-danger)",
      textColor: "var(--color-text-danger)",
    },
    pending: {
      Icon: AlertCircle,
      bg: "var(--color-bg-warning)",
      iconColor: "var(--color-text-warning)",
      textColor: "var(--color-text-warning)",
    },
  }[check.status];

  const { Icon } = config;

  return (
    <div
      className="flex items-start gap-2.5 px-3 py-2 rounded-md text-sm"
      style={{ background: config.bg, color: config.textColor }}
    >
      <Icon className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: config.iconColor }} />
      <span>{check.text}</span>
    </div>
  );
}
