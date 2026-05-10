"""
Pack 26.0 Stage B — Endpoint + Frontend для импорта компаний из DOCX.

Применяет:
1. backend/app/api/companies.py — добавляет POST /extract-from-document
2. frontend/lib/api.ts — функция extractCompanyFromDocument()
3. frontend/components/admin/settings/CompanyImportDialog.tsx — НОВЫЙ диалог
4. frontend/components/admin/settings/CompanyDrawer.tsx — добавляет prop initialFields
5. frontend/components/admin/settings/CompaniesTab.tsx — добавляет кнопку «Загрузить реквизиты»

Запуск:
    cd D:\\VISA\\visa_kit
    python apply_pack26_0_stage_b.py
"""
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT_CANDIDATES = [Path.cwd(), Path.cwd().parent, Path.cwd().parent.parent]
ROOT = None
for c in ROOT_CANDIDATES:
    if (c / "backend" / "app" / "api" / "companies.py").exists() and \
       (c / "frontend" / "lib" / "api.ts").exists():
        ROOT = c
        break

if ROOT is None:
    print("ERROR: visa_kit root not found. Run from D:\\VISA\\visa_kit")
    sys.exit(1)

print(f"visa_kit root: {ROOT}")

COMPANIES_PY = ROOT / "backend" / "app" / "api" / "companies.py"
API_TS = ROOT / "frontend" / "lib" / "api.ts"
COMPANY_DRAWER = ROOT / "frontend" / "components" / "admin" / "settings" / "CompanyDrawer.tsx"
COMPANIES_TAB = ROOT / "frontend" / "components" / "admin" / "settings" / "CompaniesTab.tsx"
IMPORT_DIALOG = ROOT / "frontend" / "components" / "admin" / "settings" / "CompanyImportDialog.tsx"

ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# === 1. Бэкапы ===
backups = {}
for f in (COMPANIES_PY, API_TS, COMPANY_DRAWER, COMPANIES_TAB):
    bak = f.with_name(f.name + f".bak_pre_pack26_0_b_{ts}")
    shutil.copy2(f, bak)
    backups[f] = bak
print(f"[1/5] Бэкапы:")
for orig, bak in backups.items():
    print(f"      {bak.name}")

patches_done = 0
patches_total = 0

# === 2. Patch backend companies.py ===
patches_total += 1
companies_text = COMPANIES_PY.read_text(encoding="utf-8")

# Импорты — добавим File, UploadFile, и наш сервис
old_imports = '''from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.models import Company, CompanyCreate, CompanyUpdate, CompanyRead, Application
from app.services.transliteration import transliterate_name
from .dependencies import require_manager  # JWT + role check'''

new_imports = '''from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.models import Company, CompanyCreate, CompanyUpdate, CompanyRead, Application
from app.services.transliteration import transliterate_name
# Pack 26.0 — импорт реквизитов из DOCX
from app.services.company_extractor import (
    extract_company_from_docx,
    CompanyExtractError,
)
from .dependencies import require_manager  # JWT + role check'''

if old_imports in companies_text:
    companies_text = companies_text.replace(old_imports, new_imports)
else:
    print(f"[2/5] [!] WARN: блок импортов в companies.py не найден точно — попробую гибче")
    # Гибче: добавим одну строку File, UploadFile к существующему fastapi-импорту
    if "from fastapi import APIRouter, Depends, HTTPException, Query" in companies_text:
        companies_text = companies_text.replace(
            "from fastapi import APIRouter, Depends, HTTPException, Query",
            "from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile",
            1,
        )
    if "from app.services.transliteration import transliterate_name" in companies_text and \
       "from app.services.company_extractor import" not in companies_text:
        companies_text = companies_text.replace(
            "from app.services.transliteration import transliterate_name",
            "from app.services.transliteration import transliterate_name\n"
            "# Pack 26.0 — импорт реквизитов из DOCX\n"
            "from app.services.company_extractor import (\n"
            "    extract_company_from_docx,\n"
            "    CompanyExtractError,\n"
            ")",
            1,
        )

# Endpoint — добавляем в конец файла
endpoint_addition = '''


# ============================================================================
# Pack 26.0 — извлечение реквизитов компании из DOCX-файла
# ============================================================================

class ExtractedCompanyFields(BaseModel):
    """Pack 26.0 response: распознанные поля + проверка на дубликат по ИНН."""
    fields: dict
    existing_company_id: int | None = None
    existing_company_name: str | None = None


@router.post("/extract-from-document", response_model=ExtractedCompanyFields)
async def extract_company_from_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> ExtractedCompanyFields:
    """
    Pack 26.0 — Принимает DOCX-файл с реквизитами, возвращает структурированные поля.

    Workflow:
    1. Менеджер кидает DOCX в UI
    2. Backend читает текст из DOCX и отправляет LLM
    3. LLM возвращает поля + склонения директора
    4. Backend ищет компанию с таким ИНН в БД
    5. Возвращает поля + existing_company_id (если найдена)

    UI после этого:
    - Если existing_company_id null → открывает CompanyDrawer (создание) с prefilled полями
    - Если есть → диалог «Обновить / Создать новую / Отмена»

    Поддерживается ТОЛЬКО .docx. PDF/JPG в следующих пакетах.
    """
    filename = file.filename or "unknown"
    if not filename.lower().endswith(".docx"):
        raise HTTPException(
            400,
            f"Поддерживается только .docx. Получено: {filename}",
        )

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:  # 5 MB лимит
        raise HTTPException(400, "Файл слишком большой (>5 МБ)")
    if len(contents) < 100:
        raise HTTPException(400, "Файл слишком маленький (<100 байт), битый?")

    try:
        fields = await extract_company_from_docx(contents)
    except CompanyExtractError as e:
        raise HTTPException(422, f"Не удалось распознать реквизиты: {e}")
    except Exception as e:
        # Любая другая ошибка — лог + 500
        import logging
        logging.getLogger(__name__).error(
            f"Pack 26.0: unexpected error: {e}", exc_info=True
        )
        raise HTTPException(500, f"Ошибка обработки: {e}")

    # Поиск дубликата по ИНН
    existing_company_id = None
    existing_company_name = None
    inn = fields.get("inn")
    if inn:
        existing = session.exec(
            select(Company).where(Company.tax_id_primary == inn)
        ).first()
        if existing:
            existing_company_id = existing.id
            existing_company_name = existing.short_name

    return ExtractedCompanyFields(
        fields=fields,
        existing_company_id=existing_company_id,
        existing_company_name=existing_company_name,
    )
'''

if "extract_company_from_document" in companies_text:
    print(f"[2/5] companies.py: endpoint уже есть — пропуск")
else:
    companies_text = companies_text.rstrip() + endpoint_addition + "\n"
    COMPANIES_PY.write_text(companies_text, encoding="utf-8")
    patches_done += 1
    print(f"[2/5] companies.py: добавлен POST /extract-from-document")

# === 3. Patch frontend lib/api.ts ===
patches_total += 1
api_text = API_TS.read_text(encoding="utf-8")

api_addition = '''

// Pack 26.0 — извлечение реквизитов компании из DOCX
export interface ExtractedCompanyFields {
  fields: {
    full_name_ru?: string | null;
    full_name_es?: string | null;
    short_name?: string | null;
    ogrn?: string | null;
    inn?: string | null;
    kpp?: string | null;
    legal_address?: string | null;
    postal_address?: string | null;
    director_full_name_ru?: string | null;
    director_full_name_genitive_ru?: string | null;
    director_short_ru?: string | null;
    director_full_name_latin?: string | null;
    director_position_ru?: string | null;
    bank_name?: string | null;
    bank_account?: string | null;
    bank_bic?: string | null;
    bank_correspondent_account?: string | null;
    charter_capital?: string | null;
  };
  existing_company_id: number | null;
  existing_company_name: string | null;
}

/**
 * Загружает DOCX с реквизитами компании на бэкенд, возвращает извлечённые поля
 * + existing_company_id если компания с таким ИНН уже есть в БД.
 */
export async function extractCompanyFromDocument(
  file: File
): Promise<ExtractedCompanyFields> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(
    `${API_BASE_URL}/api/admin/companies/extract-from-document`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: formData,
    }
  );
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Не удалось извлечь реквизиты (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}
'''

if "extractCompanyFromDocument" in api_text:
    print(f"[3/5] api.ts: extractCompanyFromDocument уже есть — пропуск")
else:
    api_text = api_text.rstrip() + api_addition
    API_TS.write_text(api_text, encoding="utf-8")
    patches_done += 1
    print(f"[3/5] api.ts: добавлены extractCompanyFromDocument + типы")

# === 4. Создать CompanyImportDialog.tsx ===
patches_total += 1
import_dialog_code = '''"use client";

/**
 * Pack 26.0 — диалог загрузки DOCX-файла с реквизитами компании.
 *
 * Workflow:
 * 1. Менеджер перетаскивает DOCX в зону drop (или через file input)
 * 2. Файл отправляется на /api/admin/companies/extract-from-document
 * 3. Если existing_company_id есть → показываем диалог конфликта (Обновить/Создать/Отмена)
 * 4. По выбору вызываем onSelect с полями + флагом действия
 */

import { useState, useRef } from "react";
import { X, Loader2, AlertCircle, FileText, Upload } from "lucide-react";
import {
  ExtractedCompanyFields,
  extractCompanyFromDocument,
} from "@/lib/api";

type Action =
  | { type: "create_new"; fields: ExtractedCompanyFields["fields"] }
  | {
      type: "update_existing";
      companyId: number;
      fields: ExtractedCompanyFields["fields"];
    };

interface Props {
  onClose: () => void;
  onSelect: (action: Action) => void;
}

export function CompanyImportDialog({ onClose, onSelect }: Props) {
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<ExtractedCompanyFields | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setError(null);
    setConflict(null);
    if (!file.name.toLowerCase().endsWith(".docx")) {
      setError(`Нужен .docx файл. Получено: ${file.name}`);
      return;
    }
    setExtracting(true);
    try {
      const result = await extractCompanyFromDocument(file);
      if (result.existing_company_id !== null) {
        setConflict(result);
      } else {
        onSelect({ type: "create_new", fields: result.fields });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExtracting(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  // ===== Conflict dialog =====
  if (conflict && conflict.existing_company_id) {
    return (
      <>
        <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="bg-primary rounded-lg shadow-2xl max-w-md w-full p-6"
            style={{ border: "0.5px solid var(--color-border-tertiary)" }}
          >
            <div className="flex items-start gap-3 mb-4">
              <AlertCircle
                className="w-6 h-6 flex-shrink-0 mt-0.5"
                style={{ color: "var(--color-text-warning)" }}
              />
              <div>
                <h3 className="text-base font-semibold text-primary mb-1">
                  Компания уже существует
                </h3>
                <p className="text-sm text-secondary">
                  Компания с ИНН <strong>{conflict.fields.inn}</strong> уже есть в
                  базе:{" "}
                  <strong>{conflict.existing_company_name}</strong>.
                </p>
              </div>
            </div>
            <div className="space-y-2">
              <button
                type="button"
                onClick={() =>
                  onSelect({
                    type: "update_existing",
                    companyId: conflict.existing_company_id!,
                    fields: conflict.fields,
                  })
                }
                className="w-full px-4 py-2 rounded-md text-sm font-medium text-white"
                style={{ background: "var(--color-accent)" }}
              >
                Обновить существующую
              </button>
              <button
                type="button"
                onClick={() =>
                  onSelect({ type: "create_new", fields: conflict.fields })
                }
                className="w-full px-4 py-2 rounded-md text-sm font-medium border text-primary hover:bg-secondary"
                style={{
                  borderColor: "var(--color-border-tertiary)",
                  borderWidth: 0.5,
                }}
              >
                Создать новую (несмотря на дубль ИНН)
              </button>
              <button
                type="button"
                onClick={onClose}
                className="w-full px-4 py-2 rounded-md text-sm text-tertiary hover:text-primary"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      </>
    );
  }

  // ===== Main upload dialog =====
  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="bg-primary rounded-lg shadow-2xl max-w-md w-full"
          style={{ border: "0.5px solid var(--color-border-tertiary)" }}
        >
          <div
            className="flex items-center justify-between px-5 py-4 border-b"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderBottomWidth: 0.5,
            }}
          >
            <h3 className="text-base font-semibold text-primary flex items-center gap-2">
              <FileText className="w-5 h-5" />
              Загрузить реквизиты компании
            </h3>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md hover:bg-secondary text-tertiary"
              disabled={extracting}
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="p-5 space-y-4">
            <p className="text-xs text-tertiary">
              Перетащите DOCX-файл с реквизитами компании. Система распознает
              ИНН, КПП, ОГРН, юр. адрес, банк, директора (включая склонения) и
              откроет редактор компании с заполненными полями.
            </p>

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

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => !extracting && fileInputRef.current?.click()}
              className="rounded-md border-2 border-dashed p-8 text-center cursor-pointer transition-colors"
              style={{
                borderColor: dragActive
                  ? "var(--color-accent)"
                  : "var(--color-border-tertiary)",
                background: dragActive
                  ? "var(--color-bg-info)"
                  : "var(--color-bg-secondary)",
                opacity: extracting ? 0.5 : 1,
              }}
            >
              {extracting ? (
                <div className="flex flex-col items-center gap-2">
                  <Loader2 className="w-8 h-8 animate-spin text-tertiary" />
                  <span className="text-sm text-tertiary">
                    Распознаём реквизиты...
                  </span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Upload className="w-8 h-8 text-tertiary" />
                  <span className="text-sm text-secondary font-medium">
                    Перетащите .docx или нажмите для выбора
                  </span>
                  <span className="text-xs text-tertiary">
                    Поддерживается только .docx (до 5 МБ)
                  </span>
                </div>
              )}
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={handleFileInput}
              disabled={extracting}
            />
          </div>

          <div
            className="px-5 py-4 border-t flex justify-end"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderTopWidth: 0.5,
            }}
          >
            <button
              onClick={onClose}
              disabled={extracting}
              className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
            >
              Отмена
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
'''

if IMPORT_DIALOG.exists():
    print(f"[4/5] [!] CompanyImportDialog.tsx уже есть — заменяю")
IMPORT_DIALOG.write_text(import_dialog_code, encoding="utf-8")
patches_done += 1
print(f"[4/5] CompanyImportDialog.tsx: создан ({len(import_dialog_code.splitlines())} строк)")

# === 5. Patch CompanyDrawer.tsx — добавить prop initialFields ===
patches_total += 1
drawer_text = COMPANY_DRAWER.read_text(encoding="utf-8")
drawer_patches = 0

# 5a. Расширить Props
old_props = '''interface Props {
  companyId: number | null; // null = создание новой
  onClose: () => void;
  onSaved: () => void;
}'''
# Файл с русским комментарием — может быть закодирован иначе. Используем гибкий поиск.
import re
props_pattern = re.compile(
    r'interface Props \{\s*\n'
    r'\s*companyId:[^\n]*\n'
    r'\s*onClose:[^\n]*\n'
    r'\s*onSaved:[^\n]*\n'
    r'\}',
    re.MULTILINE
)
m = props_pattern.search(drawer_text)
if m:
    new_props = '''interface Props {
  companyId: number | null;
  // Pack 26.0 — опционально: prefilled поля при импорте из DOCX
  initialFields?: Partial<CompanyResponse>;
  onClose: () => void;
  onSaved: () => void;
}'''
    drawer_text = drawer_text.replace(m.group(0), new_props, 1)
    drawer_patches += 1
    print(f"[5/5a] CompanyDrawer: Props расширен")
else:
    print(f"[5/5a] [!] WARN: интерфейс Props не найден")

# 5b. Сигнатура компонента
old_sig = "export function CompanyDrawer({ companyId, onClose, onSaved }: Props) {"
new_sig = "export function CompanyDrawer({ companyId, initialFields, onClose, onSaved }: Props) {"
if old_sig in drawer_text:
    drawer_text = drawer_text.replace(old_sig, new_sig, 1)
    drawer_patches += 1
    print(f"[5/5b] CompanyDrawer: сигнатура обновлена")
else:
    print(f"[5/5b] [!] WARN: сигнатура компонента не найдена")

# 5c. После useState формы — добавить useEffect который применяет initialFields
old_form_block_pattern = re.compile(
    r'(const \[form, setForm\] = useState<Partial<CompanyResponse>>\(\{[\s\S]*?\}\);)',
    re.MULTILINE
)
m = old_form_block_pattern.search(drawer_text)
if m:
    insertion_after = m.group(1)
    addition = '''

  // Pack 26.0 — если переданы initialFields (импорт из DOCX) — применяем их к форме.
  // Делаем при первом рендере и при смене initialFields. Для existing-режима поверх
  // уже подгруженных через getCompany данных тоже применятся (LLM-распознавание имеет
  // приоритет, менеджер видит и правит).
  useEffect(() => {
    if (!initialFields) return;
    setForm((prev) => ({ ...prev, ...initialFields }));
  }, [initialFields]);'''
    drawer_text = drawer_text.replace(insertion_after, insertion_after + addition, 1)
    drawer_patches += 1
    print(f"[5/5c] CompanyDrawer: useEffect для initialFields добавлен")
else:
    print(f"[5/5c] [!] WARN: блок useState<Partial<CompanyResponse>> не найден")

if drawer_patches >= 2:
    COMPANY_DRAWER.write_text(drawer_text, encoding="utf-8")
    patches_done += 1
    print(f"[5/5 ] CompanyDrawer: записан ({drawer_patches}/3 подпатчей)")
else:
    print(f"[5/5 ] [!] CompanyDrawer не записан — слишком мало успешных подпатчей")

# === 6. Patch CompaniesTab.tsx — добавить кнопку «Загрузить реквизиты» ===
patches_total += 1
tab_text = COMPANIES_TAB.read_text(encoding="utf-8")
tab_patches = 0

# 6a. Импорты
old_tab_imports = '''import { Plus, Loader2, Edit2, Power } from "lucide-react";
import {
  CompanyResponse,
  listCompanies,
  deleteCompany,
} from "@/lib/api";
import { CompanyDrawer } from "./CompanyDrawer";'''

new_tab_imports = '''import { Plus, Loader2, Edit2, Power, FileUp } from "lucide-react";
import {
  CompanyResponse,
  listCompanies,
  deleteCompany,
} from "@/lib/api";
import { CompanyDrawer } from "./CompanyDrawer";
// Pack 26.0 — диалог импорта реквизитов из DOCX
import { CompanyImportDialog } from "./CompanyImportDialog";'''

if old_tab_imports in tab_text:
    tab_text = tab_text.replace(old_tab_imports, new_tab_imports, 1)
    tab_patches += 1
    print(f"[6/5a] CompaniesTab: импорты обновлены")
else:
    print(f"[6/5a] [!] WARN: блок импортов не найден")

# 6b. State для импорта
old_state = '''  const [companies, setCompanies] = useState<CompanyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [showInactive, setShowInactive] = useState(false);'''

new_state = '''  const [companies, setCompanies] = useState<CompanyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [showInactive, setShowInactive] = useState(false);
  // Pack 26.0 — состояние для импорта реквизитов из DOCX
  const [importOpen, setImportOpen] = useState(false);
  const [importedFields, setImportedFields] = useState<Partial<CompanyResponse> | null>(null);'''

if old_state in tab_text:
    tab_text = tab_text.replace(old_state, new_state, 1)
    tab_patches += 1
    print(f"[6/5b] CompaniesTab: state обновлён")
else:
    print(f"[6/5b] [!] WARN: блок useState не найден")

# 6c. Кнопка «Загрузить реквизиты» рядом с «Добавить компанию»
old_button = '''        <button onClick={() => setEditingId("new")}
          className="px-3 py-1.5 rounded-md text-sm font-medium text-white flex items-center gap-1.5"
          style={{ background: "var(--color-accent)" }}>
          <Plus className="w-4 h-4" />
          Добавить компанию
        </button>'''

new_buttons = '''        <div className="flex items-center gap-2">
          <button onClick={() => setImportOpen(true)}
            className="px-3 py-1.5 rounded-md text-sm font-medium border flex items-center gap-1.5 hover:bg-secondary"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            title="Загрузить DOCX с реквизитами — система сама заполнит поля">
            <FileUp className="w-4 h-4" />
            Загрузить реквизиты
          </button>
          <button onClick={() => { setImportedFields(null); setEditingId("new"); }}
            className="px-3 py-1.5 rounded-md text-sm font-medium text-white flex items-center gap-1.5"
            style={{ background: "var(--color-accent)" }}>
            <Plus className="w-4 h-4" />
            Добавить компанию
          </button>
        </div>'''

# old_button может иметь другие пробелы из-за кодировки русских комментариев — попробуем гибкий поиск
flexible_old_button = re.search(
    r'<button onClick=\{\(\) => setEditingId\("new"\)\}[\s\S]*?Добавить компанию[\s\S]*?</button>',
    tab_text
)
if flexible_old_button:
    tab_text = tab_text.replace(flexible_old_button.group(0), new_buttons, 1)
    tab_patches += 1
    print(f"[6/5c] CompaniesTab: кнопка «Загрузить реквизиты» добавлена")
else:
    print(f"[6/5c] [!] WARN: кнопка «Добавить компанию» не найдена")

# 6d. Рендер CompanyImportDialog + проброс initialFields в CompanyDrawer
old_drawer_block = '''      {editingId !== null && (
        <CompanyDrawer
          companyId={editingId === "new" ? null : editingId}
          onClose={() => setEditingId(null)}
          onSaved={() => { setEditingId(null); load(); }}
        />
      )}'''

new_drawer_block = '''      {editingId !== null && (
        <CompanyDrawer
          companyId={editingId === "new" ? null : editingId}
          initialFields={importedFields ?? undefined}
          onClose={() => { setEditingId(null); setImportedFields(null); }}
          onSaved={() => { setEditingId(null); setImportedFields(null); load(); }}
        />
      )}

      {/* Pack 26.0 — диалог загрузки DOCX с реквизитами */}
      {importOpen && (
        <CompanyImportDialog
          onClose={() => setImportOpen(false)}
          onSelect={(action) => {
            setImportOpen(false);
            // applyAction: open drawer with prefilled fields
            // create_new → new drawer; update_existing → edit drawer for that company
            setImportedFields(action.fields as Partial<CompanyResponse>);
            if (action.type === "create_new") {
              setEditingId("new");
            } else {
              setEditingId(action.companyId);
            }
          }}
        />
      )}'''

if old_drawer_block in tab_text:
    tab_text = tab_text.replace(old_drawer_block, new_drawer_block, 1)
    tab_patches += 1
    print(f"[6/5d] CompaniesTab: Drawer + ImportDialog подключены")
else:
    # Гибкий поиск
    flexible_drawer = re.search(
        r'\{editingId !== null && \(\s*<CompanyDrawer[\s\S]*?</CompanyDrawer>\s*\)\}|'
        r'\{editingId !== null && \(\s*<CompanyDrawer[\s\S]*?/>\s*\)\}',
        tab_text
    )
    if flexible_drawer:
        tab_text = tab_text.replace(flexible_drawer.group(0), new_drawer_block, 1)
        tab_patches += 1
        print(f"[6/5d] CompaniesTab: Drawer + ImportDialog подключены (fallback)")
    else:
        print(f"[6/5d] [!] WARN: блок CompanyDrawer не найден")

if tab_patches >= 3:
    COMPANIES_TAB.write_text(tab_text, encoding="utf-8")
    patches_done += 1
    print(f"[6/5 ] CompaniesTab: записан ({tab_patches}/4 подпатчей)")
else:
    print(f"[6/5 ] [!] CompaniesTab не записан — слишком мало успешных подпатчей")

# === Финальная проверка синтаксиса Python ===
try:
    ast.parse(COMPANIES_PY.read_text(encoding="utf-8"))
    print("\n[OK] companies.py syntax OK")
except SyntaxError as e:
    print(f"\n[FAIL] companies.py: {e}")
    print(f"Откат: Copy-Item -Force '{backups[COMPANIES_PY]}' '{COMPANIES_PY}'")
    sys.exit(1)

print(f"\n=== Pack 26.0 Stage B применён ({patches_done}/{patches_total} основных + новый dialog) ===\n")

print("Дальше:")
print(f"  cd {ROOT}")
print("  git add backend/app/api/companies.py \\")
print("    frontend/lib/api.ts \\")
print("    frontend/components/admin/settings/CompanyDrawer.tsx \\")
print("    frontend/components/admin/settings/CompaniesTab.tsx \\")
print("    frontend/components/admin/settings/CompanyImportDialog.tsx")
print("  git status   # ровно 5 файлов")
print("  git commit -m 'Pack 26.0: import company requisites from DOCX (LLM extraction + UI)'")
print("  git push")
print()
print("После Railway+Vercel деплоя:")
print("  Админка → Настройки → Компании → кнопка «Загрузить реквизиты» → drag .docx")
print("  Тест на ООО РХИ.docx и ООО АГАЛАРОВ-ДЕВЕЛОПМЕНТ (если есть в DOCX)")
print()
print(f"Откат:")
for orig, bak in backups.items():
    print(f"  Copy-Item -Force '{bak}' '{orig}'")
print(f"  Remove-Item '{IMPORT_DIALOG}'")
