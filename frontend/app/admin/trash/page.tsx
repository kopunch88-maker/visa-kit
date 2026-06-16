"use client";

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
import { matchesSearch } from "@/lib/searchNormalize";

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
    return items.filter((a) =>
      matchesSearch(
        searchQuery,
        a.reference,
        a.internal_notes,
        a.applicant_name_native,
        a.applicant_name_latin,
      ),
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
      `Удалить заявку ${ref} НАВСЕГДА?\n\n` +
      `Это удалит:\n` +
      `• Все загруженные файлы (паспорта, дипломы и т.д.)\n` +
      `• Все сгенерированные документы\n` +
      `• Все записи о клиенте по этой заявке\n\n` +
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
