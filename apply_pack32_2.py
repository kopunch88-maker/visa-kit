"""
Pack 32.2 — переезд блока «Заметки» внутрь шапки заявки.

Что меняется относительно Pack 32.1:
  1. Блок NotesCard перемещается из позиции «между шапкой и сеткой карточек»
     внутрь левой колонки шапки заявки — под мета-строкой
     (#номер · статус · обновлено N ч назад).
  2. Цветовая схема меняется: фон БЕЛЫЙ (var(--color-bg-primary)),
     рамка ЖЁЛТАЯ (var(--color-border-warning)). Вспомогательные элементы
     (иконка, заголовок «ЗАМЕТКИ ПО КЛИЕНТУ») остаются жёлтыми для акцента.
  3. Margin-top чтобы был воздух между мета-строкой и блоком заметок.

Файлы:
  frontend/components/admin/cards/NotesCard.tsx     — полная замена (новые цвета)
  frontend/components/admin/ApplicationDetail.tsx   — переносим JSX-вызов

Запуск (PowerShell, из D:\\VISA\\visa_kit):
    python apply_pack32_2.py
    git add frontend/components/admin/cards/NotesCard.tsx \\
            frontend/components/admin/ApplicationDetail.tsx
    git commit -m "Pack 32.2: notes block moved into header + white bg yellow border"
    git push
"""

from __future__ import annotations

import sys
from pathlib import Path


# =============================================================================
# NotesCard.tsx — полная замена (белый фон, жёлтая рамка)
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
'''


# =============================================================================
# Patch ApplicationDetail.tsx
# =============================================================================
# Стратегия: убрать старое JSX-место (под шапкой) и вставить новое внутрь
# левой колонки шапки — после блока с #номер · статус · обновлено.

# Старый JSX (Pack 32.1) — между шапкой и сеткой карточек.
OLD_BETWEEN = '''      {/* Pack 32.1 — заметки по клиенту (видны всем менеджерам) */}
      <NotesCard application={application} onSaved={loadAll} />

      {/* Сетка карточек: 1 кандидат сверху, 2 (компания + подача) ниже */}'''

# Без NotesCard — то, что хотим оставить после старого места.
OLD_BETWEEN_REPLACEMENT = '''      {/* Сетка карточек: 1 кандидат сверху, 2 (компания + подача) ниже */}'''


# Новое место — после закрытия мета-строки (#номер · статус · обновлено) внутри
# левой колонки шапки. Якорь — закрывающие теги мета-блока перед `</div>` который
# закрывает `flex-1 min-w-0`. Конкретно:
#
#   <span className="text-tertiary text-xs">
#     обновлено {formatRelativeTime(application.created_at)}
#   </span>
# </div>            ← конец .flex.items-center.gap-2 (мета)
#                    ↑ ВСТАВЛЯЕМ NotesCard ЗДЕСЬ
# </div>            ← конец .flex-1.min-w-0 (левая колонка)
#
# Для надёжности используем уникальную последовательность:

OLD_HEADER_ANCHOR = '''              <span className="text-tertiary text-xs">
                обновлено {formatRelativeTime(application.created_at)}
              </span>
            </div>
          </div>

          <div className="flex flex-col items-stretch gap-2 min-w-[260px]">'''

NEW_HEADER_ANCHOR = '''              <span className="text-tertiary text-xs">
                обновлено {formatRelativeTime(application.created_at)}
              </span>
            </div>

            {/* Pack 32.2 — заметки по клиенту, размещены под мета-строкой */}
            <div className="mt-3">
              <NotesCard application={application} onSaved={loadAll} />
            </div>
          </div>

          <div className="flex flex-col items-stretch gap-2 min-w-[260px]">'''


def patch_application_detail(repo_root: Path) -> None:
    path = repo_root / "frontend" / "components" / "admin" / "ApplicationDetail.tsx"
    if not path.exists():
        raise SystemExit(f"[FATAL] not found: {path}")

    text = path.read_text(encoding="utf-8")

    # Idempotency check
    if "Pack 32.2" in text:
        print("    [SKIP] ApplicationDetail.tsx: Pack 32.2 уже применён")
        return

    if "import { NotesCard }" not in text:
        raise SystemExit(
            "[FATAL] ApplicationDetail.tsx: импорт NotesCard не найден.\n"
            "        Сначала примени Pack 32.1, потом 32.2."
        )

    # 1) Удалить старое JSX-место (Pack 32.1).
    if OLD_BETWEEN in text:
        text = text.replace(OLD_BETWEEN, OLD_BETWEEN_REPLACEMENT, 1)
        print("    [OK] ApplicationDetail.tsx: старое место NotesCard убрано")
    else:
        # Возможно уже убрано — это ок.
        print("    [INFO] ApplicationDetail.tsx: старое место NotesCard не найдено (ок если уже убрано)")

    # 2) Вставить в новое место — внутрь левой колонки шапки.
    if OLD_HEADER_ANCHOR not in text:
        raise SystemExit(
            "[FATAL] ApplicationDetail.tsx: якорь для вставки в шапку не найден.\n"
            "        Ожидался блок с 'обновлено {formatRelativeTime…}' и следующей\n"
            "        правой колонкой 'flex flex-col items-stretch gap-2 min-w-[260px]'."
        )
    text = text.replace(OLD_HEADER_ANCHOR, NEW_HEADER_ANCHOR, 1)
    print("    [OK] ApplicationDetail.tsx: NotesCard вставлен внутрь шапки заявки")

    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"    [OK] ApplicationDetail.tsx сохранён: {path}")


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
    print(f"== Pack 32.2 ==")
    print(f"   repo: {repo_root}")
    print()

    print("[1/2] frontend/components/admin/cards/NotesCard.tsx — полная замена")
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
    print('    git commit -m "Pack 32.2: notes block moved into header + white bg yellow border"')
    print("    git push")
    print()
    print("Vercel пересоберёт за ~30-60 сек.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
