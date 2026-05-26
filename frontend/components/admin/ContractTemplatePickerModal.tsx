"use client";

/**
 * Pack 29.4 — Модалка выбора шаблона договора.
 *
 * Открывается из DocumentsGrid когда backend возвращает 409 NEEDS_CONTRACT_TEMPLATE
 * (в payload — список available_templates). Менеджер выбирает шаблон,
 * мы сохраняем его в company.contract_template_slug через PATCH /api/admin/companies/{id},
 * затем callback onSaved тригерит повторную генерацию пакета.
 */

import { useEffect, useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import {
  ContractTemplateOption,
  listContractTemplates,
  EmploymentContractTemplateOption,
  listEmploymentContractTemplates,
  updateCompany,
} from "@/lib/api";

interface Props {
  companyId: number;
  companyShortName: string;
  onClose: () => void;
  onSaved: () => void;
  // Pack 50.1-G — какой шаблон выбираем: договор самозанятого либо трудовой.
  // Default: "contract" (обратная совместимость с Pack 29.4).
  kind?: "contract" | "employment";
}

const ARCHETYPE_LABELS: Record<string, { label: string; bg: string; color: string }> = {
  vozmezdnoe: {
    label: "Возмездный",
    bg: "var(--color-bg-success)",
    color: "var(--color-text-success)",
  },
  vozmezdnoe_hourly: {
    label: "Почасовой",
    bg: "var(--color-bg-info)",
    color: "var(--color-text-info)",
  },
  gph: {
    label: "ГПХ (подряд)",
    bg: "var(--color-bg-warning)",
    color: "var(--color-text-warning)",
  },
  // Pack 50.1-G — Трудовой договор (найм).
  employment: {
    label: "Трудовой",
    bg: "var(--color-bg-info)",
    color: "var(--color-text-info)",
  },
};

export function ContractTemplatePickerModal({
  companyId,
  companyShortName,
  onClose,
  onSaved,
  kind = "contract",
}: Props) {
  const [templates, setTemplates] = useState<Array<ContractTemplateOption | EmploymentContractTemplateOption>>([]);
  const [selectedSlug, setSelectedSlug] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    // Pack 50.1-G — для kind="employment" используем другой endpoint.
    const loader = kind === "employment"
      ? listEmploymentContractTemplates()
      : listContractTemplates();
    loader
      .then((list) => {
        setTemplates(list);
        // Для contract — по умолчанию "default" если есть.
        // Для employment — список без "default", оставляем без preselect.
        if (kind === "contract") {
          const defaultOption = list.find((t) => t.slug === "default");
          if (defaultOption) setSelectedSlug("default");
        }
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [kind]);

  async function handleSave() {
    if (!selectedSlug) {
      setError("Выберите шаблон договора");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      // Pack 50.1-G — для employment сохраняем в другое поле company.
      const payload = kind === "employment"
        ? { employment_contract_template_slug: selectedSlug } as any
        : { contract_template_slug: selectedSlug };
      await updateCompany(companyId, payload);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/40 z-40"
        onClick={saving ? undefined : onClose}
      />
      <div
        className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-primary rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col"
        style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
      >
        {/* Header */}
        <div
          className="px-5 py-4 flex items-center justify-between border-b sticky top-0 bg-primary rounded-t-xl"
          style={{ borderColor: "var(--color-border-tertiary)", borderBottomWidth: 0.5 }}
        >
          <div>
            <h2 className="text-lg font-semibold text-primary">
              {kind === "employment" ? "Выбор шаблона Трудового договора" : "Выбор шаблона договора"}
            </h2>
            <p className="text-sm text-tertiary mt-0.5">
              Для компании <span className="font-medium text-secondary">{companyShortName}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={saving}
            className="p-1 rounded-md text-tertiary hover:text-primary hover:bg-secondary disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 overflow-y-auto flex-1">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
            </div>
          ) : (
            <>
              <div className="flex items-start gap-2 mb-4 p-3 rounded-md" style={{ background: "var(--color-bg-info)" }}>
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: "var(--color-text-info)" }} />
                <p className="text-sm" style={{ color: "var(--color-text-info)" }}>
                  У этой компании не выбран шаблон договора. Выберите подходящий из списка ниже —
                  он сохранится в карточке компании, и в будущем модалка появляться не будет.
                </p>
              </div>

              <div className="space-y-2">
                {templates.map((t) => {
                  const archetype = ARCHETYPE_LABELS[t.archetype] || {
                    label: t.archetype,
                    bg: "var(--color-bg-secondary)",
                    color: "var(--color-text-tertiary)",
                  };
                  const isSelected = selectedSlug === t.slug;
                  return (
                    <label
                      key={t.slug}
                      className={`flex items-start gap-3 p-3 rounded-md cursor-pointer transition-colors ${
                        isSelected ? "ring-2" : "hover:bg-secondary"
                      }`}
                      style={{
                        background: isSelected ? "var(--color-bg-info)" : "var(--color-bg-secondary)",
                        borderColor: "var(--color-border-secondary)",
                        borderWidth: 0.5,
                      }}
                    >
                      <input
                        type="radio"
                        name="contract-template"
                        value={t.slug}
                        checked={isSelected}
                        onChange={(e) => setSelectedSlug(e.target.value)}
                        className="mt-1"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-primary text-sm">{t.label}</span>
                          <span
                            className="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide"
                            style={{ background: archetype.bg, color: archetype.color }}
                          >
                            {archetype.label}
                          </span>
                        </div>
                        <p className="text-xs text-tertiary mt-1">{t.description}</p>
                      </div>
                    </label>
                  );
                })}
              </div>
            </>
          )}

          {error && (
            <div className="mt-4 bg-danger text-danger text-sm p-3 rounded-md">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="px-5 py-3 flex items-center justify-end gap-2 border-t sticky bottom-0 bg-primary rounded-b-xl"
          style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}
        >
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
          >
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading || !selectedSlug}
            className="px-4 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{ background: "var(--color-accent)" }}
          >
            {saving ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Сохранение...
              </>
            ) : (
              "Сохранить и сгенерировать"
            )}
          </button>
        </div>
      </div>
    </>
  );
}
