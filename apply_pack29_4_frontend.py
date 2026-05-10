# -*- coding: utf-8 -*-
"""
Pack 29.4 — Frontend integration of per-company contract templates.

Изменения:
  1. frontend/lib/api.ts — добавить тип ContractTemplateOption + listContractTemplates() + поле в CompanyResponse
  2. frontend/components/admin/settings/CompanyDrawer.tsx — dropdown шаблона договора
  3. frontend/components/admin/DocumentsGrid.tsx — обработка 409 → модалка
  4. frontend/components/admin/ContractTemplatePickerModal.tsx — НОВЫЙ файл с модалкой
  5. frontend/components/admin/ApplicationDetail.tsx — передать companyId в DocumentsGrid
  6. УДАЛИТЬ frontend/src/components/ContractTemplateComponents.tsx — артефакт Pack 29.0,
     лежал не там (Next.js без папки src/)

Применять:
    cd D:\\VISA\\visa_kit\\frontend
    python ../backend/apply_pack29_4_frontend.py
    
Frontend нужен пересборка (npm run build / vercel deploy после push).
"""
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(os.environ.get("VISA_REPO_ROOT", r"D:\VISA\visa_kit"))
FRONTEND = REPO_ROOT / "frontend"


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak_pre_pack29_4_{stamp}")
    shutil.copy2(path, bak)
    return bak


def replace_in_file(path: Path, old: str, new: str, count: int = 1) -> bool:
    raw = path.read_bytes()
    has_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    text_lf = text.replace("\r\n", "\n") if has_crlf else text

    occurrences = text_lf.count(old)
    if occurrences == 0:
        print(f"  ✗ NOT FOUND in {path.name}: {old[:60]!r}...")
        return False
    if count == 1 and occurrences > 1:
        print(f"  ✗ AMBIGUOUS in {path.name}: '{old[:60]}...' found {occurrences} times")
        return False

    new_text_lf = text_lf.replace(old, new, count)
    new_text = new_text_lf.replace("\n", "\r\n") if has_crlf else new_text_lf
    path.write_bytes(new_text.encode("utf-8"))
    print(f"  ✓ Patched {path.name}: {occurrences} replacement(s)")
    return True


def patch_api_ts():
    """Add ContractTemplateOption type + listContractTemplates() + field in CompanyResponse."""
    path = FRONTEND / "lib" / "api.ts"
    print(f"\n[1/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    # 1.1: Добавить contract_template_slug в CompanyResponse (перед is_active)
    replace_in_file(path,
        "  egryl_extract_date?: string;\n"
        "  egryl_is_fresh?: boolean;\n"
        "  is_active: boolean;",
        "  egryl_extract_date?: string;\n"
        "  egryl_is_fresh?: boolean;\n"
        "  contract_template_slug?: string | null;  // Pack 29.0\n"
        "  is_active: boolean;"
    )

    # 1.2: Добавить ContractTemplateOption type + listContractTemplates() после deleteCompany
    replace_in_file(path,
        "export async function deleteCompany(id: number): Promise<void> {\n"
        "  const res = await fetch(`${API_BASE_URL}/api/admin/companies/${id}`, {\n"
        "    method: \"DELETE\", headers: authHeaders(),\n"
        "  });\n"
        "  if (!res.ok) throw new Error(`Не удалось удалить: ${res.status}`);\n"
        "}",

        "export async function deleteCompany(id: number): Promise<void> {\n"
        "  const res = await fetch(`${API_BASE_URL}/api/admin/companies/${id}`, {\n"
        "    method: \"DELETE\", headers: authHeaders(),\n"
        "  });\n"
        "  if (!res.ok) throw new Error(`Не удалось удалить: ${res.status}`);\n"
        "}\n"
        "\n"
        "// ============================================================================\n"
        "// Pack 29.0/29.4 — Contract templates\n"
        "// ============================================================================\n"
        "\n"
        "export type ContractTemplateOption = {\n"
        "  slug: string;\n"
        "  label: string;\n"
        "  archetype: string;       // 'vozmezdnoe' | 'vozmezdnoe_hourly' | 'gph'\n"
        "  description: string;\n"
        "};\n"
        "\n"
        "export async function listContractTemplates(): Promise<ContractTemplateOption[]> {\n"
        "  const res = await fetch(`${API_BASE_URL}/api/admin/companies/contract-templates`, {\n"
        "    headers: authHeaders(),\n"
        "  });\n"
        "  if (!res.ok) throw new Error(`Contract templates: ${res.status}`);\n"
        "  const data = await res.json();\n"
        "  return data.templates;\n"
        "}"
    )


def patch_company_drawer():
    """Add contract template dropdown section to CompanyDrawer."""
    path = FRONTEND / "components" / "admin" / "settings" / "CompanyDrawer.tsx"
    print(f"\n[2/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    # 2.1: Импорт listContractTemplates + ContractTemplateOption
    replace_in_file(path,
        "import {\n"
        "  CompanyResponse,\n"
        "  BankResponse,\n"
        "  getCompany,\n"
        "  createCompany,\n"
        "  updateCompany,\n"
        "  listBanks,\n"
        "  generateAccount,\n"
        "} from \"@/lib/api\";",

        "import {\n"
        "  CompanyResponse,\n"
        "  BankResponse,\n"
        "  getCompany,\n"
        "  createCompany,\n"
        "  updateCompany,\n"
        "  listBanks,\n"
        "  generateAccount,\n"
        "  // Pack 29.4\n"
        "  ContractTemplateOption,\n"
        "  listContractTemplates,\n"
        "} from \"@/lib/api\";"
    )

    # 2.2: Добавить state contract_template_slug в дефолтную форму
    replace_in_file(path,
        "    bank_name: \"\",\n"
        "    bank_account: \"\",\n"
        "    bank_bic: \"\",\n"
        "    bank_correspondent_account: \"\",\n"
        "    notes: \"\",\n"
        "  });",

        "    bank_name: \"\",\n"
        "    bank_account: \"\",\n"
        "    bank_bic: \"\",\n"
        "    bank_correspondent_account: \"\",\n"
        "    contract_template_slug: null,  // Pack 29.4\n"
        "    notes: \"\",\n"
        "  });\n"
        "\n"
        "  // Pack 29.4 — список доступных шаблонов договоров\n"
        "  const [contractTemplates, setContractTemplates] = useState<ContractTemplateOption[]>([]);"
    )

    # 2.3: Добавить useEffect для загрузки templates после useEffect банков
    replace_in_file(path,
        "  // Pack 29.0 — загрузка справочника банков\n"
        "  useEffect(() => {\n"
        "    listBanks().then(setBanks).catch((e) => {\n"
        "      console.warn(\"Failed to load banks:\", e);\n"
        "    });\n"
        "  }, []);",

        "  // Pack 29.0 — загрузка справочника банков\n"
        "  useEffect(() => {\n"
        "    listBanks().then(setBanks).catch((e) => {\n"
        "      console.warn(\"Failed to load banks:\", e);\n"
        "    });\n"
        "  }, []);\n"
        "\n"
        "  // Pack 29.4 — загрузка списка контрактных шаблонов\n"
        "  useEffect(() => {\n"
        "    listContractTemplates().then(setContractTemplates).catch((e) => {\n"
        "      console.warn(\"Failed to load contract templates:\", e);\n"
        "    });\n"
        "  }, []);"
    )

    # 2.4: Добавить новую секцию "Шаблон договора" между "Идентификация" и "Налоговые ID"
    # Найдём конец секции "Идентификация" (закрывающий </Section>) перед "<Section title="Налоговые ID"...
    replace_in_file(path,
        "              <Section title=\"Налоговые ID\">\n"
        "                <Grid>\n"
        "                  <TextField label=\"ИНН (или BIN для KZ)\" required value={form.tax_id_primary || \"\"}\n"
        "                    onChange={(v) => setField(\"tax_id_primary\", v)} placeholder=\"7715998877\" />\n"
        "                  <TextField label=\"КПП (только для РФ)\" value={form.tax_id_secondary || \"\"}\n"
        "                    onChange={(v) => setField(\"tax_id_secondary\", v)} placeholder=\"771501001\" />\n"
        "                </Grid>\n"
        "              </Section>",

        "              <Section title=\"Налоговые ID\">\n"
        "                <Grid>\n"
        "                  <TextField label=\"ИНН (или BIN для KZ)\" required value={form.tax_id_primary || \"\"}\n"
        "                    onChange={(v) => setField(\"tax_id_primary\", v)} placeholder=\"7715998877\" />\n"
        "                  <TextField label=\"КПП (только для РФ)\" value={form.tax_id_secondary || \"\"}\n"
        "                    onChange={(v) => setField(\"tax_id_secondary\", v)} placeholder=\"771501001\" />\n"
        "                </Grid>\n"
        "              </Section>\n"
        "\n"
        "              {/* Pack 29.4 — Шаблон договора */}\n"
        "              <Section title=\"Шаблон договора\">\n"
        "                <div>\n"
        "                  <label className=\"block text-xs font-medium text-secondary mb-1\">\n"
        "                    Шаблон, по которому будет рендериться 01_Договор.docx\n"
        "                  </label>\n"
        "                  <select\n"
        "                    value={form.contract_template_slug || \"\"}\n"
        "                    onChange={(e) => setField(\"contract_template_slug\", e.target.value || null)}\n"
        "                    className=\"w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2\"\n"
        "                    style={{ borderColor: \"var(--color-border-secondary)\", borderWidth: 0.5 }}\n"
        "                  >\n"
        "                    <option value=\"\">— Не выбран (модалка при генерации) —</option>\n"
        "                    {contractTemplates.map((t) => (\n"
        "                      <option key={t.slug} value={t.slug}>\n"
        "                        {t.label} [{t.archetype}]\n"
        "                      </option>\n"
        "                    ))}\n"
        "                  </select>\n"
        "                  {form.contract_template_slug && (\n"
        "                    <p className=\"text-xs text-tertiary mt-1\">\n"
        "                      {contractTemplates.find((t) => t.slug === form.contract_template_slug)?.description || \"\"}\n"
        "                    </p>\n"
        "                  )}\n"
        "                </div>\n"
        "              </Section>"
    )


def patch_documents_grid():
    """Add 409 handling + modal trigger to DocumentsGrid."""
    path = FRONTEND / "components" / "admin" / "DocumentsGrid.tsx"
    print(f"\n[3/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    # 3.1: Импорт компонента модалки + типа Props с companyId
    replace_in_file(path,
        "import { useState } from \"react\";\n"
        "import { Download, Loader2, Check, RefreshCw } from \"lucide-react\";\n"
        "import { API_BASE_URL, getToken } from \"@/lib/api\";\n"
        "\n"
        "interface Props {\n"
        "  applicationId: number;\n"
        "}",

        "import { useState } from \"react\";\n"
        "import { Download, Loader2, Check, RefreshCw } from \"lucide-react\";\n"
        "import { API_BASE_URL, getToken } from \"@/lib/api\";\n"
        "// Pack 29.4\n"
        "import { ContractTemplatePickerModal } from \"./ContractTemplatePickerModal\";\n"
        "\n"
        "interface Props {\n"
        "  applicationId: number;\n"
        "  // Pack 29.4 — для модалки выбора шаблона договора\n"
        "  companyId?: number | null;\n"
        "}"
    )

    # 3.2: Принять companyId в функции
    replace_in_file(path,
        "export function DocumentsGrid({ applicationId }: Props) {\n"
        "  const [downloadingZip, setDownloadingZip] = useState(false);\n"
        "  const [zipDownloaded, setZipDownloaded] = useState(false);\n"
        "  const [downloadingId, setDownloadingId] = useState<string | null>(null);\n"
        "  const [error, setError] = useState<string | null>(null);",

        "export function DocumentsGrid({ applicationId, companyId }: Props) {\n"
        "  const [downloadingZip, setDownloadingZip] = useState(false);\n"
        "  const [zipDownloaded, setZipDownloaded] = useState(false);\n"
        "  const [downloadingId, setDownloadingId] = useState<string | null>(null);\n"
        "  const [error, setError] = useState<string | null>(null);\n"
        "\n"
        "  // Pack 29.4 — состояние модалки выбора шаблона при 409 NEEDS_CONTRACT_TEMPLATE\n"
        "  const [pickerState, setPickerState] = useState<{\n"
        "    isOpen: boolean;\n"
        "    companyId: number;\n"
        "    companyShortName: string;\n"
        "    onSaved: () => void;\n"
        "  } | null>(null);"
    )

    # 3.3: Добавить хелпер handle409 после useState
    # Замена через handleDownloadZip — добавим хелпер в начале функции после состояния pickerState
    replace_in_file(path,
        "  async function handleDownloadZip() {\n"
        "    setDownloadingZip(true);\n"
        "    setError(null);\n"
        "    try {\n"
        "      const token = getToken();\n"
        "      const res = await fetch(\n"
        "        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package`,\n"
        "        { method: \"POST\", headers: { Authorization: `Bearer ${token}` } },\n"
        "      );\n"
        "      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);\n"
        "\n"
        "      const blob = await res.blob();\n"
        "      _triggerBrowserDownload(blob, `package_${applicationId}.zip`);\n"
        "\n"
        "      setZipDownloaded(true);\n"
        "      setTimeout(() => setZipDownloaded(false), 3000);\n"
        "    } catch (e) {\n"
        "      setError((e as Error).message);\n"
        "    } finally {\n"
        "      setDownloadingZip(false);\n"
        "    }\n"
        "  }",

        "  // Pack 29.4 — проверка 409 NEEDS_CONTRACT_TEMPLATE\n"
        "  // Возвращает true если открыли модалку (нужно прервать обработку), false если 409 не пришла\n"
        "  async function handle409IfNeedsTemplate(res: Response, retryFn: () => void): Promise<boolean> {\n"
        "    if (res.status !== 409) return false;\n"
        "    let detail: any;\n"
        "    try {\n"
        "      const json = await res.json();\n"
        "      detail = json.detail;\n"
        "    } catch {\n"
        "      return false;\n"
        "    }\n"
        "    if (!detail || detail.code !== \"NEEDS_CONTRACT_TEMPLATE\") return false;\n"
        "    setPickerState({\n"
        "      isOpen: true,\n"
        "      companyId: detail.company_id,\n"
        "      companyShortName: detail.company_short_name || `id=${detail.company_id}`,\n"
        "      onSaved: retryFn,\n"
        "    });\n"
        "    return true;\n"
        "  }\n"
        "\n"
        "  async function handleDownloadZip() {\n"
        "    setDownloadingZip(true);\n"
        "    setError(null);\n"
        "    try {\n"
        "      const token = getToken();\n"
        "      const res = await fetch(\n"
        "        `${API_BASE_URL}/api/admin/applications/${applicationId}/render-package`,\n"
        "        { method: \"POST\", headers: { Authorization: `Bearer ${token}` } },\n"
        "      );\n"
        "      // Pack 29.4 — обработка 409 NEEDS_CONTRACT_TEMPLATE\n"
        "      if (await handle409IfNeedsTemplate(res, () => handleDownloadZip())) {\n"
        "        return;\n"
        "      }\n"
        "      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);\n"
        "\n"
        "      const blob = await res.blob();\n"
        "      _triggerBrowserDownload(blob, `package_${applicationId}.zip`);\n"
        "\n"
        "      setZipDownloaded(true);\n"
        "      setTimeout(() => setZipDownloaded(false), 3000);\n"
        "    } catch (e) {\n"
        "      setError((e as Error).message);\n"
        "    } finally {\n"
        "      setDownloadingZip(false);\n"
        "    }\n"
        "  }"
    )

    # 3.4: То же самое для handleDownloadOne — добавить 409 handler
    replace_in_file(path,
        "  async function handleDownloadOne(doc: DocItem) {\n"
        "    setDownloadingId(doc.id);\n"
        "    setError(null);\n"
        "    try {\n"
        "      const token = getToken();\n"
        "      const res = await fetch(\n"
        "        `${API_BASE_URL}/api/admin/applications/${applicationId}/download-file/${doc.id}`,\n"
        "        { method: \"GET\", headers: { Authorization: `Bearer ${token}` } },\n"
        "      );\n"
        "      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);\n"
        "\n"
        "      const blob = await res.blob();\n"
        "      _triggerBrowserDownload(blob, doc.filename);\n"
        "    } catch (e) {\n"
        "      setError((e as Error).message);\n"
        "    } finally {\n"
        "      setDownloadingId(null);\n"
        "    }\n"
        "  }",

        "  async function handleDownloadOne(doc: DocItem) {\n"
        "    setDownloadingId(doc.id);\n"
        "    setError(null);\n"
        "    try {\n"
        "      const token = getToken();\n"
        "      const res = await fetch(\n"
        "        `${API_BASE_URL}/api/admin/applications/${applicationId}/download-file/${doc.id}`,\n"
        "        { method: \"GET\", headers: { Authorization: `Bearer ${token}` } },\n"
        "      );\n"
        "      // Pack 29.4 — обработка 409 NEEDS_CONTRACT_TEMPLATE\n"
        "      if (await handle409IfNeedsTemplate(res, () => handleDownloadOne(doc))) {\n"
        "        return;\n"
        "      }\n"
        "      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);\n"
        "\n"
        "      const blob = await res.blob();\n"
        "      _triggerBrowserDownload(blob, doc.filename);\n"
        "    } catch (e) {\n"
        "      setError((e as Error).message);\n"
        "    } finally {\n"
        "      setDownloadingId(null);\n"
        "    }\n"
        "  }"
    )

    # 3.5: Добавить рендер модалки в return — найдём последнюю closing </div> перед закрывающим }
    # Лучше добавить перед закрывающим </div> главного контейнера. Найдём по </div>$
    replace_in_file(path,
        "      </div>\n"
        "    </div>\n"
        "  );\n"
        "}",

        "      </div>\n"
        "\n"
        "      {/* Pack 29.4 — Модалка выбора шаблона договора при 409 */}\n"
        "      {pickerState && pickerState.isOpen && (\n"
        "        <ContractTemplatePickerModal\n"
        "          companyId={pickerState.companyId}\n"
        "          companyShortName={pickerState.companyShortName}\n"
        "          onClose={() => setPickerState(null)}\n"
        "          onSaved={() => {\n"
        "            const retry = pickerState.onSaved;\n"
        "            setPickerState(null);\n"
        "            // Небольшая задержка чтобы UI закрыл модалку перед повторной попыткой\n"
        "            setTimeout(() => retry(), 100);\n"
        "          }}\n"
        "        />\n"
        "      )}\n"
        "    </div>\n"
        "  );\n"
        "}"
    )


def create_picker_modal():
    """Create new ContractTemplatePickerModal.tsx component."""
    path = FRONTEND / "components" / "admin" / "ContractTemplatePickerModal.tsx"
    print(f"\n[4/5] Creating {path.relative_to(REPO_ROOT)}")

    if path.exists():
        print(f"  ! file already exists, backing up")
        backup(path)

    content = '''"use client";

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
  updateCompany,
} from "@/lib/api";

interface Props {
  companyId: number;
  companyShortName: string;
  onClose: () => void;
  onSaved: () => void;
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
};

export function ContractTemplatePickerModal({
  companyId,
  companyShortName,
  onClose,
  onSaved,
}: Props) {
  const [templates, setTemplates] = useState<ContractTemplateOption[]>([]);
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
    listContractTemplates()
      .then((list) => {
        setTemplates(list);
        // По умолчанию выберем "default" если есть
        const defaultOption = list.find((t) => t.slug === "default");
        if (defaultOption) setSelectedSlug("default");
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    if (!selectedSlug) {
      setError("Выберите шаблон договора");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateCompany(companyId, { contract_template_slug: selectedSlug });
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
              Выбор шаблона договора
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
'''
    path.write_text(content, encoding="utf-8", newline="\r\n")
    print(f"  ✓ Created {path.name} ({len(content)} bytes)")


def patch_application_detail():
    """Pass companyId to DocumentsGrid."""
    path = FRONTEND / "components" / "admin" / "ApplicationDetail.tsx"
    print(f"\n[5/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    replace_in_file(path,
        "      {isAssigned && <DocumentsGrid applicationId={application.id} />}",
        "      {isAssigned && <DocumentsGrid applicationId={application.id} companyId={application.company_id} />}"
    )


def cleanup_old_artifact():
    """Pack 29.0 положил ContractTemplateComponents.tsx в frontend/src/components/.
    У вас Next.js без папки src/, так что этот файл лежит в неправильном месте.
    Удалим его (его содержимое было полностью переписано в Pack 29.4)."""
    print(f"\n[cleanup] Removing Pack 29.0 misplaced artifact")
    bad_dir = FRONTEND / "src"
    if bad_dir.exists():
        try:
            shutil.rmtree(bad_dir)
            print(f"  ✓ Removed {bad_dir.relative_to(REPO_ROOT)}")
        except Exception as e:
            print(f"  ! Could not remove {bad_dir}: {e}")
            print(f"    Удалите вручную: Remove-Item -Recurse -Force \"{bad_dir}\"")
    else:
        print(f"  = Already removed, skip")


def main():
    print("=" * 75)
    print("Pack 29.4 — Frontend integration of contract templates")
    print("=" * 75)
    print(f"Repo: {REPO_ROOT}")
    print(f"Frontend: {FRONTEND}")

    if not FRONTEND.exists():
        print(f"ERROR: frontend dir not found: {FRONTEND}")
        sys.exit(1)

    patch_api_ts()
    patch_company_drawer()
    patch_documents_grid()
    create_picker_modal()
    patch_application_detail()
    cleanup_old_artifact()

    print("\n" + "=" * 75)
    print("✅ Pack 29.4 frontend integration applied")
    print("=" * 75)
    print("\nNext steps:")
    print("  1. cd frontend && npm install (если изменились зависимости — здесь не должно)")
    print("  2. Локально проверить:  cd frontend && npm run dev")
    print("  3. git add frontend/lib/api.ts frontend/components/admin/")
    print("  4. git commit -m 'Pack 29.4: frontend — contract template picker modal + dropdown'")
    print("  5. git push  (Vercel автоматически пересоберёт frontend)")
    print("\nTesting:")
    print("  - Откройте Settings → Компании → отредактируйте например АГАЛАРОВ-ДЕВЕЛОПМЕНТ")
    print("  - Должна появиться новая секция 'Шаблон договора' между 'Налоговые ID' и 'Адреса'")
    print("  - ИЛИ откройте заявку для АГАЛАРОВ → жмёте 'Скачать ZIP' →")
    print("    должна появиться модалка с 11 опциями шаблонов")


if __name__ == "__main__":
    main()
