"use client";

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

/**
 * Pack 26.0.1 — переименование полей backend-ответа в имена CompanyResponse.
 * Backend возвращает inn/kpp (как в реквизитах), но в схеме они tax_id_primary/secondary.
 */
function mapFieldsToCompany(
  raw: ExtractedCompanyFields["fields"]
): Record<string, string | null | undefined> {
  const { inn, kpp, ...rest } = raw;
  return {
    ...rest,
    tax_id_primary: inn,
    tax_id_secondary: kpp,
  };
}

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
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".docx") && !lower.endsWith(".pdf")) {
      setError(`Нужен .docx или .pdf файл. Получено: ${file.name}`);
      return;
    }
    setExtracting(true);
    try {
      const result = await extractCompanyFromDocument(file);
      if (result.existing_company_id !== null) {
        setConflict(result);
      } else {
        onSelect({ type: "create_new", fields: mapFieldsToCompany(result.fields) as any });
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
                    fields: mapFieldsToCompany(conflict.fields) as any,
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
                  onSelect({ type: "create_new", fields: mapFieldsToCompany(conflict.fields) as any })
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
              Перетащите DOCX или PDF-файл с реквизитами компании. Система распознает
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
                    Перетащите .docx / .pdf или нажмите для выбора
                  </span>
                  <span className="text-xs text-tertiary">
                    Поддерживается .docx и .pdf (до 5 МБ)
                  </span>
                </div>
              )}
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".docx,.pdf"
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
