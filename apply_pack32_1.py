"""
Pack 32.1 — блок «Заметки» в карточке заявки.

Что делает:
  Добавляет редактируемый блок заметок между шапкой заявки и сеткой карточек
  «Кандидат / Компания / Подача». Менеджер пишет произвольный текст про клиента;
  все остальные менеджеры его видят при открытии той же заявки.

Технически:
  Никакого backend-кода НЕ трогаем — поле Application.internal_notes уже есть,
  PATCH /admin/applications/{id} его принимает (ApplicationPatch.internal_notes),
  frontend/lib/api.ts:patchApplication уже типизирован с internal_notes: string.

  Это поле ДО Pack 32.1 уже использовалось:
    - формой «+ Создать заявку» (поле «Внутренняя заметка»),
    - как fallback для шапки заявки если applicant пустой.
  Никакой конфликтов нет — мы просто даём UI для просмотра и редактирования.

Файлы:
  frontend/components/admin/cards/NotesCard.tsx     — НОВЫЙ компонент
  frontend/components/admin/ApplicationDetail.tsx   — добавить импорт + JSX

Запуск (PowerShell, из D:\\VISA\\visa_kit):
    python apply_pack32_1.py
    git add frontend/components/admin/cards/NotesCard.tsx \\
            frontend/components/admin/ApplicationDetail.tsx
    git commit -m "Pack 32.1: notes block in application card"
    git push
"""

from __future__ import annotations

import sys
from pathlib import Path


# =============================================================================
# NEW FILE — NotesCard.tsx
# =============================================================================

NOTES_CARD_TSX = '''"use client";

import { useEffect, useRef, useState } from "react";
import { StickyNote, Pencil, Save, X, Loader2 } from "lucide-react";
import { ApplicationResponse, patchApplication } from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onSaved: () => void;
}

/**
 * Pack 32.1 — блок заметок по заявке.
 *
 * Использует существующее поле Application.internal_notes (нет миграции БД).
 * Два режима:
 *   - view: жёлтый блок-стикер с текстом и кнопкой «✎ Изменить» в углу.
 *           Если заметок нет — приглашение «Добавить заметку».
 *   - edit: textarea + кнопки «Сохранить» / «Отмена». Авто-фокус и
 *           поднятие курсора в конец при открытии.
 *
 * Сохраняет через PATCH /admin/applications/{id} с payload { internal_notes }.
 * Пустая строка сохраняется как пустая (backend трактует как «без заметок»).
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
      // Trim — лишние пробелы в начале/конце ни к чему. Внутренние переводы
      // строк сохраняются как есть.
      const cleaned = value.replace(/^\\s+|\\s+$/g, "");
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
      className="rounded-xl border p-4"
      style={{
        // Лёгкий «стикерный» вид — тёплый жёлтый, тонкая рамка.
        // Используем CSS-переменные темы — корректно в тёмном/светлом.
        background: "var(--color-bg-warning)",
        borderColor: "var(--color-border-warning)",
        borderWidth: 0.5,
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <h3
          className="text-xs font-semibold uppercase tracking-wide flex items-center gap-1.5"
          style={{ color: "var(--color-text-warning)" }}
        >
          <StickyNote className="w-3.5 h-3.5" />
          Заметки по клиенту
        </h3>
        {!editing && (
          <button
            onClick={handleStartEdit}
            className="text-xs px-2 py-1 rounded-md transition-colors flex items-center gap-1 hover:bg-primary"
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
            className="text-sm whitespace-pre-wrap break-words leading-relaxed"
            style={{ color: "var(--color-text-warning)" }}
          >
            {application.internal_notes}
          </div>
        ) : (
          <button
            onClick={handleStartEdit}
            className="w-full text-left text-sm italic py-2 hover:underline"
            style={{ color: "var(--color-text-warning)", opacity: 0.7 }}
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
            rows={5}
            placeholder="Например: клиент работает в IT, оплата 14-го числа, ВНЖ Сербии…"
            className="w-full text-sm rounded-md p-2 outline-none resize-y leading-relaxed"
            style={{
              background: "var(--color-bg-primary)",
              color: "var(--color-text-primary)",
              border: "0.5px solid var(--color-border-tertiary)",
              minHeight: 100,
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

          <div className="flex items-center justify-between gap-2">
            <div
              className="text-[11px]"
              style={{ color: "var(--color-text-warning)", opacity: 0.7 }}
            >
              Ctrl + Enter — сохранить, Esc — отменить
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCancel}
                disabled={saving}
                className="px-3 py-1.5 rounded-md text-xs border transition-colors flex items-center gap-1 hover:bg-primary"
                style={{
                  borderColor: "var(--color-border-tertiary)",
                  borderWidth: 0.5,
                  color: "var(--color-text-secondary)",
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
'''


# =============================================================================
# Patch ApplicationDetail.tsx — точечные str_replace
# =============================================================================

# (1) Импорт нового компонента — после импорта CandidateCard.
APP_DETAIL_OLD_IMPORT = '''import { CandidateCard } from "./cards/CandidateCard";
import { CompanyCard } from "./cards/CompanyCard";
import { SubmissionCard } from "./cards/SubmissionCard";'''

APP_DETAIL_NEW_IMPORT = '''import { CandidateCard } from "./cards/CandidateCard";
import { CompanyCard } from "./cards/CompanyCard";
import { SubmissionCard } from "./cards/SubmissionCard";
// Pack 32.1 — блок заметок по клиенту
import { NotesCard } from "./cards/NotesCard";'''


# (2) Вставка JSX — между закрывающим тегом шапки заявки и сеткой карточек.
# Якорь: комментарий "{/* Сетка карточек: 1 кандидат сверху, 2 ..." — стабильно
# присутствует и хорошо изолирует.
APP_DETAIL_OLD_JSX_ANCHOR = '''      {/* Сетка карточек: 1 кандидат сверху, 2 (компания + подача) ниже */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pack 32.0 — onEdit передаётся всегда: handleEditApplicant сам решит,
            создавать пустого applicant'а или сразу открывать Drawer. */}
        <CandidateCard'''

APP_DETAIL_NEW_JSX_ANCHOR = '''      {/* Pack 32.1 — заметки по клиенту (видны всем менеджерам) */}
      <NotesCard application={application} onSaved={loadAll} />

      {/* Сетка карточек: 1 кандидат сверху, 2 (компания + подача) ниже */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pack 32.0 — onEdit передаётся всегда: handleEditApplicant сам решит,
            создавать пустого applicant'а или сразу открывать Drawer. */}
        <CandidateCard'''

# Альтернативный якорь — если Pack 32.0 ещё не применён (или комментарий другой).
# Тогда используется CandidateCard без комментария Pack 32.0.
APP_DETAIL_OLD_JSX_FALLBACK = '''      {/* Сетка карточек: 1 кандидат сверху, 2 (компания + подача) ниже */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <CandidateCard'''

APP_DETAIL_NEW_JSX_FALLBACK = '''      {/* Pack 32.1 — заметки по клиенту (видны всем менеджерам) */}
      <NotesCard application={application} onSaved={loadAll} />

      {/* Сетка карточек: 1 кандидат сверху, 2 (компания + подача) ниже */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <CandidateCard'''


def patch_application_detail(repo_root: Path) -> None:
    path = repo_root / "frontend" / "components" / "admin" / "ApplicationDetail.tsx"
    if not path.exists():
        raise SystemExit(f"[FATAL] not found: {path}")

    text = path.read_text(encoding="utf-8")

    # Idempotency check
    if "Pack 32.1" in text and "NotesCard" in text:
        print("    [SKIP] ApplicationDetail.tsx: Pack 32.1 уже применён")
        return

    # 1) Импорт
    if APP_DETAIL_OLD_IMPORT in text:
        text = text.replace(APP_DETAIL_OLD_IMPORT, APP_DETAIL_NEW_IMPORT, 1)
        print("    [OK] ApplicationDetail.tsx: импорт NotesCard добавлен")
    elif "import { NotesCard }" in text:
        print("    [INFO] ApplicationDetail.tsx: импорт NotesCard уже есть")
    else:
        raise SystemExit(
            "[FATAL] ApplicationDetail.tsx: не найден якорь для вставки импорта.\n"
            "Ожидался блок:\n" + APP_DETAIL_OLD_IMPORT
        )

    # 2) JSX
    if APP_DETAIL_OLD_JSX_ANCHOR in text:
        text = text.replace(APP_DETAIL_OLD_JSX_ANCHOR, APP_DETAIL_NEW_JSX_ANCHOR, 1)
        print("    [OK] ApplicationDetail.tsx: JSX NotesCard вставлен (Pack 32.0 ветка)")
    elif APP_DETAIL_OLD_JSX_FALLBACK in text:
        text = text.replace(APP_DETAIL_OLD_JSX_FALLBACK, APP_DETAIL_NEW_JSX_FALLBACK, 1)
        print("    [OK] ApplicationDetail.tsx: JSX NotesCard вставлен (fallback ветка)")
    else:
        raise SystemExit(
            "[FATAL] ApplicationDetail.tsx: не найден якорь для вставки JSX.\n"
            "Ожидался один из двух блоков с комментарием 'Сетка карточек:'."
        )

    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"    [OK] ApplicationDetail.tsx обновлён: {path}")


# =============================================================================
# Helpers
# =============================================================================

def write_text(path: Path, text: str, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"    [OK] {label}: {path}")


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    repo_root = Path.cwd()
    print(f"== Pack 32.1 ==")
    print(f"   repo: {repo_root}")
    print()

    print("[1/2] frontend/components/admin/cards/NotesCard.tsx — новый файл")
    write_text(
        repo_root / "frontend" / "components" / "admin" / "cards" / "NotesCard.tsx",
        NOTES_CARD_TSX,
        "NotesCard.tsx",
    )
    print()

    print("[2/2] frontend/components/admin/ApplicationDetail.tsx — патч")
    patch_application_detail(repo_root)
    print()

    print("== DONE ==")
    print()
    print("Дальше:")
    print("    git add frontend/components/admin/cards/NotesCard.tsx \\")
    print("            frontend/components/admin/ApplicationDetail.tsx")
    print('    git commit -m "Pack 32.1: notes block in application card"')
    print("    git push")
    print()
    print("Vercel пересоберёт frontend за ~30-60 сек. Backend трогать не нужно.")
    print()
    print("Тест:")
    print("  1. Открой любую заявку")
    print("  2. Под шапкой увидишь жёлтый блок «Заметки по клиенту»")
    print("  3. Если заметок нет — приглашение «Добавить заметку»")
    print("  4. Клик → textarea → пиши → Ctrl+Enter или «Сохранить»")
    print("  5. Заметка останется и будет видна другим менеджерам")
    return 0


if __name__ == "__main__":
    sys.exit(main())
