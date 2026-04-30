"use client";

import { Building2, Edit2 } from "lucide-react";
import { CompanyResponse, PositionResponse, ApplicationResponse } from "@/lib/api";

interface Props {
  company?: CompanyResponse;
  position?: PositionResponse;
  application: ApplicationResponse;
  onEdit: () => void;
}

function daysSince(dateStr?: string): number | null {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  const now = new Date();
  return Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
}

function formatRub(amount?: number): string {
  if (!amount) return "—";
  return new Intl.NumberFormat("ru-RU").format(amount) + " ₽/мес";
}

export function CompanyCard({ company, position, application, onEdit }: Props) {
  const days = daysSince(application.contract_sign_date);
  const inn = company?.inn || company?.tax_id_primary;

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
          <div>
            <div className="text-[11px] text-tertiary">Заказчик</div>
            <div className="text-sm text-primary">
              {company.short_name}
              {inn && (
                <span className="text-tertiary text-xs ml-2 font-mono">ИНН {inn}</span>
              )}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-tertiary">Должность</div>
            <div className="text-sm text-primary">{position?.title_ru || "—"}</div>
          </div>

          {(application.contract_sign_date || application.salary_rub) && (
            <div
              className="border-t pt-2 mt-2"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderTopWidth: 0.5,
              }}
            >
              {application.contract_sign_date && (
                <div className="mb-1.5">
                  <div className="text-[11px] text-tertiary">Договор подписан</div>
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
              {application.salary_rub && (
                <div>
                  <div className="text-[11px] text-tertiary">Зарплата</div>
                  <div className="text-sm text-primary">
                    {formatRub(application.salary_rub)}
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
