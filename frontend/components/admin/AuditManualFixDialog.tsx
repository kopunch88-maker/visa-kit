"use client";

import { useState, useEffect } from "react";
import { X, Loader2, Wrench } from "lucide-react";
import { AuditFinding, manualFixAuditFinding } from "@/lib/api";

interface Props {
  finding: AuditFinding;
  onClose: () => void;
  onApplied: () => void;
}

/**
 * Pack 37.0-D — диалог ручного исправления finding.
 *
 * Менеджер вводит правильное значение для field_path. Если у finding нет
 * field_path (например финансовое замечание про сумму в договоре) — менеджер
 * может либо указать поле сам, либо просто отклонить finding.
 */
export function AuditManualFixDialog({ finding, onClose, onApplied }: Props) {
  const [fieldPath, setFieldPath] = useState(finding.field_path || "");
  const [newValue, setNewValue] = useState(finding.suggested_value || finding.current_value || "");
  const [note, setNote] = useState("");
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Закрытие по Esc
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !applying) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [applying, onClose]);

  async function handleApply() {
    if (!fieldPath.trim() || !fieldPath.includes(".")) {
      setError("field_path должен быть в формате 'applicant.field_name' или 'company.field_name'");
      return;
    }
    setApplying(true);
    setError(null);
    try {
      await manualFixAuditFinding(finding.id, fieldPath.trim(), newValue, note || undefined);
      onApplied();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <Wrench className="w-5 h-5 text-violet-600" />
            <h2 className="text-lg font-semibold text-gray-900">Ручное исправление</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 disabled:opacity-50"
            disabled={applying}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 space-y-4">
          {/* Что говорил аудитор */}
          <div className="bg-gray-50 border border-gray-200 rounded-md p-3 space-y-2">
            <p className="text-sm font-medium text-gray-700">{finding.title}</p>
            {finding.description && (
              <p className="text-xs text-gray-600 whitespace-pre-wrap">{finding.description}</p>
            )}
            {finding.evidence && (
              <details className="text-xs text-gray-500">
                <summary className="cursor-pointer hover:text-gray-700">Обоснование</summary>
                <p className="mt-1 whitespace-pre-wrap">{finding.evidence}</p>
              </details>
            )}
          </div>

          {/* Поле для редактирования */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Путь к полю
            </label>
            <input
              type="text"
              value={fieldPath}
              onChange={(e) => setFieldPath(e.target.value)}
              placeholder="applicant.last_name_native"
              disabled={applying}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-accent disabled:bg-gray-50"
            />
            <p className="text-xs text-gray-500 mt-1">
              Формат: <code>applicant.&lt;поле&gt;</code> или <code>company.&lt;поле&gt;</code>
            </p>
          </div>

          {/* Текущее значение (read-only) */}
          {finding.current_value !== null && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Текущее значение
              </label>
              <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-900 font-mono break-all">
                {String(finding.current_value) || "(пусто)"}
              </div>
            </div>
          )}

          {/* Новое значение */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Новое значение
            </label>
            <input
              type="text"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              disabled={applying}
              autoFocus
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-accent disabled:bg-gray-50"
            />
            {finding.suggested_value && finding.suggested_value !== newValue && (
              <button
                type="button"
                onClick={() => setNewValue(finding.suggested_value!)}
                className="text-xs text-accent hover:underline mt-1"
                disabled={applying}
              >
                Использовать предложение ИИ: «{finding.suggested_value}»
              </button>
            )}
          </div>

          {/* Заметка */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Заметка (необязательно)
            </label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={applying}
              rows={2}
              placeholder="Почему именно это значение..."
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-accent disabled:bg-gray-50"
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-900 text-sm px-3 py-2 rounded-md">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onClose}
            disabled={applying}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            Отмена
          </button>
          <button
            onClick={handleApply}
            disabled={applying || !fieldPath.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-violet-600 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2"
          >
            {applying ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Применяю...
              </>
            ) : (
              "Применить исправление"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
