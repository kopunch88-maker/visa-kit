"use client";

import { useEffect, useRef, useState } from "react";
import { StickyNote, Pencil, Save, X, Loader2 } from "lucide-react";
import { ApplicationResponse, patchApplication } from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onSaved: () => void;
}

/**
 * Pack 32.1 — блок заметок по заявке.
 * Pack 32.2 — белый фон, жёлтая рамка; живёт внутри шапки заявки.
 *
 * Использует существующее поле Application.internal_notes (нет миграции БД).
 * Два режима:
 *   - view: белая карточка с жёлтой рамкой; текст и кнопка «✎ Изменить».
 *           Если заметок нет — приглашение «Добавить заметку…».
 *   - edit: textarea + кнопки «Сохранить» / «Отмена».
 *
 * Сохраняет через PATCH /admin/applications/{id} с payload { internal_notes }.
 */
export function NotesCard({ application, onSaved }: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(application.internal_notes || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Если родитель перезагрузил заявку (loadAll), синхронизируем локальный
  // state с пришедшим значением — но ТОЛЬКО когда мы не редактируем,
  // иначе затрём то, что менеджер только что напечатал.
  useEffect(() => {
    if (!editing) {
      setValue(application.internal_notes || "");
    }
  }, [application.internal_notes, editing]);

  // Автофокус и курсор в конец при входе в режим редактирования.
  useEffect(() => {
    if (editing && textareaRef.current) {
      const el = textareaRef.current;
      el.focus();
      el.selectionStart = el.selectionEnd = el.value.length;
    }
  }, [editing]);

  const hasNotes = !!(application.internal_notes && application.internal_notes.trim());

  function handleStartEdit() {
    setError(null);
    setValue(application.internal_notes || "");
    setEditing(true);
  }

  function handleCancel() {
    setError(null);
    setValue(application.internal_notes || "");
    setEditing(false);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const cleaned = value.replace(/^\s+|\s+$/g, "");
      await patchApplication(application.id, { internal_notes: cleaned });
      setEditing(false);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  // Ctrl/Cmd + Enter — сохранить, Esc — отмена.
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSave();
    } else if (e.key === "Escape") {
      e.preventDefault();
      handleCancel();
    }
  }

  return (
    <div
      className="rounded-lg p-3"
      style={{
        // Pack 32.2 — белый фон, жёлтая рамка для акцента.
        background: "var(--color-bg-primary)",
        borderColor: "var(--color-border-warning)",
        borderWidth: 1,
        borderStyle: "solid",
      }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <h3
          className="text-[11px] font-semibold uppercase tracking-wide flex items-center gap-1.5"
          style={{ color: "var(--color-text-warning)" }}
        >
          <StickyNote className="w-3.5 h-3.5" />
          Заметки по клиенту
        </h3>
        {!editing && (
          <button
            onClick={handleStartEdit}
            className="text-xs px-2 py-1 rounded-md transition-colors flex items-center gap-1 hover:bg-secondary"
            style={{ color: "var(--color-text-warning)" }}
            title={hasNotes ? "Редактировать заметки" : "Добавить заметку"}
          >
            <Pencil className="w-3 h-3" />
            {hasNotes ? "Изменить" : "Добавить"}
          </button>
        )}
      </div>

      {!editing ? (
        hasNotes ? (
          <div
            className="text-sm whitespace-pre-wrap break-words leading-relaxed text-primary"
          >
            {application.internal_notes}
          </div>
        ) : (
          <button
            onClick={handleStartEdit}
            className="w-full text-left text-sm italic py-1 hover:underline text-tertiary"
          >
            Добавить заметку — её увидят все менеджеры…
          </button>
        )
      ) : (
        <div className="space-y-2">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={saving}
            rows={4}
            placeholder="Например: клиент работает в IT, оплата 14-го числа, ВНЖ Сербии…"
            className="w-full text-sm rounded-md p-2 outline-none resize-y leading-relaxed"
            style={{
              background: "var(--color-bg-primary)",
              color: "var(--color-text-primary)",
              border: "0.5px solid var(--color-border-tertiary)",
              minHeight: 90,
            }}
          />

          {error && (
            <div
              className="text-xs"
              style={{ color: "var(--color-text-danger)" }}
            >
              {error}
            </div>
          )}

          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="text-[11px] text-tertiary">
              Ctrl + Enter — сохранить, Esc — отменить
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCancel}
                disabled={saving}
                className="px-3 py-1.5 rounded-md text-xs border transition-colors flex items-center gap-1 text-secondary hover:bg-secondary"
                style={{
                  borderColor: "var(--color-border-tertiary)",
                  borderWidth: 0.5,
                  background: "var(--color-bg-primary)",
                }}
              >
                <X className="w-3 h-3" />
                Отмена
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-3 py-1.5 rounded-md text-xs font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-1"
                style={{ background: "var(--color-accent)" }}
              >
                {saving ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Save className="w-3 h-3" />
                )}
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
