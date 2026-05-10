"""
Pack 27.0 Stage B — Frontend для Корзины.

Создаёт/изменяет:
1. frontend/lib/api.ts — функции softDeleteApplication, restoreApplication,
   permanentDeleteApplication + расширение listApplications параметром trash
2. frontend/components/admin/DeleteButton.tsx — НОВЫЙ компонент кнопки удаления
3. frontend/app/admin/trash/page.tsx — НОВАЯ страница корзины
4. frontend/components/admin/ApplicationDetail.tsx — добавить DeleteButton рядом с ArchiveButton

Запуск:
    cd D:\\VISA\\visa_kit
    python apply_pack27_0_stage_b.py
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT_CANDIDATES = [Path.cwd(), Path.cwd().parent]
ROOT = None
for c in ROOT_CANDIDATES:
    if (c / "frontend" / "lib" / "api.ts").exists() and \
       (c / "frontend" / "components" / "admin" / "ArchiveButton.tsx").exists():
        ROOT = c
        break

if ROOT is None:
    print("ERROR: visa_kit root not found. Run from D:\\VISA\\visa_kit")
    sys.exit(1)

print(f"visa_kit root: {ROOT}")

API_TS = ROOT / "frontend" / "lib" / "api.ts"
APP_DETAIL = ROOT / "frontend" / "components" / "admin" / "ApplicationDetail.tsx"
DELETE_BUTTON = ROOT / "frontend" / "components" / "admin" / "DeleteButton.tsx"
TRASH_PAGE = ROOT / "frontend" / "app" / "admin" / "trash" / "page.tsx"
ADMIN_PAGE = ROOT / "frontend" / "app" / "admin" / "page.tsx"

ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# Бэкапы для модифицируемых файлов (не для новых)
backups = {}
for f in (API_TS, APP_DETAIL, ADMIN_PAGE):
    bak = f.with_name(f.name + f".bak_pre_pack27_0_b_{ts}")
    shutil.copy2(f, bak)
    backups[f] = bak
print(f"[1/5] Бэкапы:")
for orig, bak in backups.items():
    print(f"      {bak.name}")


# === 2. lib/api.ts — добавить функции и расширить listApplications ===
api_text = API_TS.read_text(encoding="utf-8")
api_patches = 0

# 2a. Расширить listApplications параметром trash
old_list_sig = '''export async function listApplications(
  status?: string,
  archived: boolean = false,
): Promise<ApplicationResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/admin/applications`);
  if (status) url.searchParams.set("status", status);
  if (archived) url.searchParams.set("archived", "true");'''

new_list_sig = '''export async function listApplications(
  status?: string,
  archived: boolean = false,
  trash: boolean = false,
): Promise<ApplicationResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/admin/applications`);
  if (status) url.searchParams.set("status", status);
  if (archived) url.searchParams.set("archived", "true");
  if (trash) url.searchParams.set("trash", "true");'''

if old_list_sig in api_text:
    api_text = api_text.replace(old_list_sig, new_list_sig, 1)
    api_patches += 1
    print(f"[2/5a] api.ts: listApplications расширен параметром trash")
else:
    print(f"[2/5a] [!] WARN: сигнатура listApplications не найдена точно")

# 2b. Добавить три новые функции в конец файла
api_addition = '''

// Pack 27.0 — Корзина (soft-delete с автоудалением через 7 дней)

/**
 * Soft-delete: помещает заявку в корзину. Обратимо в течение 7 дней через restoreApplication.
 * Доступно из любого статуса. Если заявка в архиве — выводит из архива и удаляет.
 */
export async function softDeleteApplication(appId: number): Promise<{ id: number; deleted_at: string }> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось удалить: ${res.status} ${await res.text()}`);
  return res.json();
}

/**
 * Восстановить заявку из корзины. Очищает deleted_at.
 */
export async function restoreApplication(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/restore`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось восстановить: ${res.status} ${await res.text()}`);
  return res.json();
}

/**
 * Удалить заявку НАВСЕГДА. Удаляет:
 * - файлы R2 (applicant_document, generated_document, uploaded_file)
 * - все связанные записи (family_member, timeline_event, translation, и т.д.)
 * - саму application
 * applicant НЕ удаляется (может быть привязан к другой заявке).
 */
export async function permanentDeleteApplication(appId: number): Promise<{ deleted: boolean; reference: string }> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/permanent`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось удалить навсегда: ${res.status} ${await res.text()}`);
  return res.json();
}
'''

if "softDeleteApplication" in api_text:
    print(f"[2/5b] api.ts: softDeleteApplication уже есть — пропуск")
else:
    api_text = api_text.rstrip() + api_addition
    api_patches += 1
    print(f"[2/5b] api.ts: добавлены softDelete/restore/permanentDelete")

API_TS.write_text(api_text, encoding="utf-8")


# === 3. Создать DeleteButton.tsx ===
delete_button_code = '''"use client";

import { useState } from "react";
import { Trash2, Loader2 } from "lucide-react";
import {
  ApplicationResponse,
  softDeleteApplication,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onDeleted: () => void;
}

/**
 * Pack 27.0 — кнопка "Удалить" (мягкое удаление в корзину).
 *
 * Размещается в шапке ApplicationDetail рядом с ArchiveButton.
 * Доступна из любого статуса. После удаления заявка попадает в корзину
 * и автоматически удалится навсегда через 7 дней.
 *
 * Использование:
 *   <DeleteButton application={application} onDeleted={() => router.push("/admin")} />
 */
export function DeleteButton({ application, onDeleted }: Props) {
  const [loading, setLoading] = useState(false);

  async function handleDelete() {
    const ok = window.confirm(
      `Переместить заявку ${application.reference} в корзину?\\n\\n` +
      `Заявка будет удалена навсегда автоматически через 7 дней. ` +
      `До этого её можно восстановить из раздела «Корзина».`
    );
    if (!ok) return;

    setLoading(true);
    try {
      await softDeleteApplication(application.id);
      onDeleted();
    } catch (e) {
      alert(`Не удалось удалить: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleDelete}
      disabled={loading}
      className="px-3 py-1.5 rounded-md text-sm font-medium border flex items-center gap-1.5 transition-colors disabled:opacity-50"
      style={{
        borderColor: "var(--color-border-danger)",
        borderWidth: 0.5,
        color: "var(--color-text-danger)",
        background: "var(--color-bg-primary)",
      }}
      title="Переместить в корзину (auto-delete через 7 дней)"
    >
      {loading ? (
        <>
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Удаление...
        </>
      ) : (
        <>
          <Trash2 className="w-3.5 h-3.5" />
          Удалить
        </>
      )}
    </button>
  );
}
'''

if DELETE_BUTTON.exists():
    print(f"[3/5] [!] DeleteButton.tsx уже есть — заменяю")
DELETE_BUTTON.write_text(delete_button_code, encoding="utf-8")
print(f"[3/5] DeleteButton.tsx: создан ({len(delete_button_code.splitlines())} строк)")


# === 4. Создать страницу /admin/trash/page.tsx ===
TRASH_PAGE.parent.mkdir(parents=True, exist_ok=True)

trash_page_code = '''"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Search, RotateCcw, Trash2, AlertTriangle } from "lucide-react";
import {
  listApplications,
  restoreApplication,
  permanentDeleteApplication,
  ApplicationResponse,
  STATUS_LABELS,
  getToken,
} from "@/lib/api";

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  draft: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
  raw: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
  approved: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  rejected: { bg: "var(--color-bg-danger)", text: "var(--color-text-danger)" },
  cancelled: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
};

function formatDate(dateStr?: string): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("ru");
}

/**
 * Pack 27.0 — Страница «Корзина».
 *
 * Показывает заявки с deleted_at IS NOT NULL.
 * При открытии backend выполняет lazy cleanup записей старше 7 дней.
 * Менеджер видит сколько дней осталось до автоудаления каждой записи.
 *
 * Действия: Восстановить (вернуть в активные) | Удалить навсегда (R2 + БД).
 */
export default function TrashPage() {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [items, setItems] = useState<ApplicationResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [actingId, setActingId] = useState<number | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/admin/login");
    } else {
      setAuthChecked(true);
    }
  }, [router]);

  async function load() {
    setError(null);
    try {
      // listApplications(status, archived, trash)
      const data = await listApplications(undefined, false, true);
      setItems(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (authChecked) {
      setLoading(true);
      load();
    }
  }, [authChecked]);

  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) return items;
    const q = searchQuery.trim().toLowerCase();
    return items.filter(
      (a) =>
        a.reference.toLowerCase().includes(q) ||
        (a.internal_notes || "").toLowerCase().includes(q) ||
        (a.applicant_name_native || "").toLowerCase().includes(q) ||
        (a.applicant_name_latin || "").toLowerCase().includes(q),
    );
  }, [items, searchQuery]);

  /**
   * Считает количество дней до автоудаления.
   * Backend удаляет если deleted_at < now() - 7 days.
   */
  function daysUntilAutoDelete(deletedAt?: string): number {
    if (!deletedAt) return 7;
    const deleted = new Date(deletedAt);
    const cutoff = new Date(deleted);
    cutoff.setDate(cutoff.getDate() + 7);
    const ms = cutoff.getTime() - Date.now();
    return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
  }

  async function handleRestore(id: number) {
    if (!window.confirm("Восстановить заявку из корзины?")) return;
    setActingId(id);
    try {
      await restoreApplication(id);
      await load();
    } catch (e) {
      alert(`Не удалось: ${(e as Error).message}`);
    } finally {
      setActingId(null);
    }
  }

  async function handlePermanentDelete(id: number, ref: string) {
    if (!window.confirm(
      `Удалить заявку ${ref} НАВСЕГДА?\\n\\n` +
      `Это удалит:\\n` +
      `• Все загруженные файлы (паспорта, дипломы и т.д.)\\n` +
      `• Все сгенерированные документы\\n` +
      `• Все записи о клиенте по этой заявке\\n\\n` +
      `Действие НЕОБРАТИМО.`
    )) return;
    setActingId(id);
    try {
      await permanentDeleteApplication(id);
      await load();
    } catch (e) {
      alert(`Не удалось: ${(e as Error).message}`);
    } finally {
      setActingId(null);
    }
  }

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--color-bg-secondary)" }}>
        <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--color-bg-secondary)" }}>
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => router.push("/admin")}
            className="p-2 rounded-md hover:bg-primary text-tertiary"
            title="Назад к заявкам"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex items-center gap-2">
            <Trash2 className="w-5 h-5" style={{ color: "var(--color-text-danger)" }} />
            <h1 className="text-xl font-semibold text-primary">
              Корзина
              <span className="text-tertiary text-base font-normal ml-2">
                ({items.length})
              </span>
            </h1>
          </div>
        </div>

        {/* Info banner */}
        <div
          className="mb-4 p-3 rounded-md text-sm flex items-start gap-2"
          style={{
            background: "var(--color-bg-info)",
            color: "var(--color-text-info)",
            border: "0.5px solid var(--color-border-info)",
          }}
        >
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-medium">Автоматическое удаление</div>
            <div className="text-xs mt-0.5">
              Заявки в корзине автоматически удаляются навсегда через 7 дней.
              До этого их можно восстановить.
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="mb-4 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-tertiary" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Поиск по reference, ФИО, заметкам..."
            className="w-full pl-10 pr-4 py-2 rounded-md text-sm border bg-primary text-primary"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
          />
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md text-sm" style={{
            background: "var(--color-bg-danger)",
            color: "var(--color-text-danger)",
            border: "0.5px solid var(--color-border-danger)",
          }}>
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
          </div>
        ) : filteredItems.length === 0 ? (
          <div
            className="bg-primary rounded-xl border p-12 text-center text-tertiary"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
          >
            <Trash2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <div className="text-base font-medium mb-1">
              {searchQuery ? "Ничего не найдено" : "Корзина пуста"}
            </div>
            <div className="text-sm">
              {searchQuery
                ? "Попробуйте другой запрос"
                : "Удалённые заявки появятся здесь и будут автоматически удалены через 7 дней"}
            </div>
          </div>
        ) : (
          <div
            className="bg-primary rounded-xl border overflow-hidden"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
          >
            <table className="w-full text-sm">
              <thead style={{ background: "var(--color-bg-secondary)" }}>
                <tr className="text-left text-xs uppercase tracking-wide text-tertiary">
                  <th className="px-4 py-2">Reference</th>
                  <th className="px-4 py-2">Кандидат</th>
                  <th className="px-4 py-2">Статус</th>
                  <th className="px-4 py-2">Удалена</th>
                  <th className="px-4 py-2">Авто-удаление</th>
                  <th className="px-4 py-2 text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((a) => {
                  const days = daysUntilAutoDelete(a.deleted_at);
                  const status = a.status as string;
                  const colors = STATUS_COLORS[status] || STATUS_COLORS.draft;
                  const isActing = actingId === a.id;

                  return (
                    <tr
                      key={a.id}
                      className="border-t"
                      style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}
                    >
                      <td className="px-4 py-2.5 font-mono text-xs text-primary">{a.reference}</td>
                      <td className="px-4 py-2.5 text-secondary text-xs line-clamp-1">
                        {a.applicant_name_native || a.applicant_name_latin || "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className="inline-block px-2 py-0.5 rounded text-xs"
                          style={{ background: colors.bg, color: colors.text }}
                        >
                          {STATUS_LABELS[status] || status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-tertiary">
                        {formatDate(a.deleted_at)}
                      </td>
                      <td className="px-4 py-2.5 text-xs">
                        <span style={{
                          color: days <= 1 ? "var(--color-text-danger)" : days <= 3 ? "var(--color-text-warning)" : "var(--color-text-tertiary)",
                          fontWeight: days <= 3 ? 600 : 400,
                        }}>
                          {days === 0 ? "сегодня" : `через ${days} дн.`}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleRestore(a.id)}
                            disabled={isActing}
                            className="p-1.5 rounded-md text-tertiary hover:text-primary hover:bg-secondary transition-colors disabled:opacity-50"
                            title="Восстановить"
                          >
                            {isActing ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <RotateCcw className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => handlePermanentDelete(a.id, a.reference)}
                            disabled={isActing}
                            className="p-1.5 rounded-md transition-colors disabled:opacity-50"
                            style={{ color: "var(--color-text-danger)" }}
                            title="Удалить навсегда"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
'''

if TRASH_PAGE.exists():
    print(f"[4/5] [!] /admin/trash/page.tsx уже есть — заменяю")
TRASH_PAGE.write_text(trash_page_code, encoding="utf-8")
print(f"[4/5] /admin/trash/page.tsx: создан ({len(trash_page_code.splitlines())} строк)")


# === 5. Patch ApplicationDetail.tsx — добавить DeleteButton ===
detail_text = APP_DETAIL.read_text(encoding="utf-8")
detail_patches = 0

# 5a. Импорт DeleteButton
import re
m = re.search(r'import \{ ArchiveButton \} from "@/components/admin/ArchiveButton";', detail_text)
if m:
    insertion = m.group(0) + '\n// Pack 27.0 — кнопка удаления в корзину\nimport { DeleteButton } from "@/components/admin/DeleteButton";'
    detail_text = detail_text.replace(m.group(0), insertion, 1)
    detail_patches += 1
    print(f"[5/5a] ApplicationDetail: импорт DeleteButton добавлен")
else:
    # Гибче — поищем любой импорт ArchiveButton
    m2 = re.search(r'import \{ ArchiveButton \}.*?;', detail_text)
    if m2:
        detail_text = detail_text.replace(
            m2.group(0),
            m2.group(0) + '\nimport { DeleteButton } from "@/components/admin/DeleteButton";',
            1
        )
        detail_patches += 1
        print(f"[5/5a] ApplicationDetail: импорт DeleteButton добавлен (fallback)")
    else:
        print(f"[5/5a] [!] WARN: импорт ArchiveButton не найден")

# 5b. Найти ArchiveButton в JSX и добавить DeleteButton рядом
# Паттерн: <ArchiveButton application={application} onChanged={handleArchiveChanged} />
old_archive_btn = '<ArchiveButton application={application} onChanged={handleArchiveChanged} />'
if old_archive_btn in detail_text:
    new_btns = (
        old_archive_btn +
        '\n              {/* Pack 27.0 — удаление в корзину */}\n'
        '              <DeleteButton\n'
        '                application={application}\n'
        '                onDeleted={() => { router.push("/admin"); }}\n'
        '              />'
    )
    detail_text = detail_text.replace(old_archive_btn, new_btns, 1)
    detail_patches += 1
    print(f"[5/5b] ApplicationDetail: DeleteButton добавлен в JSX")
else:
    # Гибкий regex
    m3 = re.search(r'<ArchiveButton[^/]*/>', detail_text)
    if m3:
        new_btns = (
            m3.group(0) +
            '\n              {/* Pack 27.0 */}\n'
            '              <DeleteButton application={application} onDeleted={() => { router.push("/admin"); }} />'
        )
        detail_text = detail_text.replace(m3.group(0), new_btns, 1)
        detail_patches += 1
        print(f"[5/5b] ApplicationDetail: DeleteButton добавлен (fallback)")
    else:
        print(f"[5/5b] [!] WARN: <ArchiveButton .../> не найден в JSX")

if detail_patches >= 2:
    APP_DETAIL.write_text(detail_text, encoding="utf-8")
    print(f"[5/5 ] ApplicationDetail: записан ({detail_patches}/2 патчей)")
else:
    print(f"[5/5 ] [!] ApplicationDetail НЕ записан — патчи неполные. Нужна ручная правка.")


# === 6. Добавить ссылку «Корзина» в /admin/page.tsx (рядом с Archive) ===
# Это nice-to-have. Если упадёт — менеджер всё равно может попасть на /admin/trash напрямую.
admin_text = ADMIN_PAGE.read_text(encoding="utf-8")
admin_patches = 0

# Импорт Trash2
if "Trash2" not in admin_text:
    old_imports = 'import { Plus, Search, Loader2, Settings, Archive, Package } from "lucide-react";'
    new_imports = 'import { Plus, Search, Loader2, Settings, Archive, Package, Trash2 } from "lucide-react";'
    if old_imports in admin_text:
        admin_text = admin_text.replace(old_imports, new_imports, 1)
        admin_patches += 1
        ADMIN_PAGE.write_text(admin_text, encoding="utf-8")
        print(f"[6/5] /admin/page.tsx: импорт Trash2 добавлен (для будущей кнопки 'Корзина' в шапке)")
    else:
        print(f"[6/5] [!] WARN: блок импортов admin/page.tsx не найден точно — пропуск")

# === Итог ===
print(f"\n=== Pack 27.0 Stage B применён ===\n")

print("Дальше:")
print(f"  cd {ROOT}")
print("  git add frontend/lib/api.ts \\")
print("    frontend/components/admin/ApplicationDetail.tsx \\")
print("    frontend/components/admin/DeleteButton.tsx \\")
print("    frontend/app/admin/trash/page.tsx \\")
print("    frontend/app/admin/page.tsx")
print("  git status   # 5 файлов")
print("  git commit -m 'Pack 27.0 Stage B: trash UI (delete button + /admin/trash page)'")
print("  git push")
print()
print("Тест после Vercel-деплоя:")
print("  1. Открыть https://visa-kit.vercel.app/admin → выбрать любую заявку")
print("  2. В шапке справа — кнопка «Удалить» рядом с «В архив»")
print("  3. Нажать «Удалить» → confirm → заявка пропадает из списка")
print("  4. Вручную перейти на https://visa-kit.vercel.app/admin/trash")
print("  5. Видим заявку с пометкой «через 7 дн.», кнопками Восстановить и Удалить навсегда")
print("  6. Тест Восстановить: нажать → заявка возвращается в /admin")
print("  7. Тест Удалить навсегда: нажать → заявка исчезает из БД и R2")
print()
print(f"Откат:")
for orig, bak in backups.items():
    print(f"  Copy-Item -Force '{bak}' '{orig}'")
print(f"  Remove-Item '{DELETE_BUTTON}'")
print(f"  Remove-Item '{TRASH_PAGE}'")
print(f"  Remove-Item '{TRASH_PAGE.parent}' -Force  # пустая папка trash/")
