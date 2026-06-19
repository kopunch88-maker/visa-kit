"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Search, RotateCcw, ExternalLink } from "lucide-react";
import {
  listApplications,
  unarchiveApplication,
  ApplicationResponse,
  STATUS_LABELS,
  getToken,
} from "@/lib/api";

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  approved: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  rejected: { bg: "var(--color-bg-danger)", text: "var(--color-text-danger)" },
  cancelled: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
};

function formatDate(dateStr?: string): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("ru");
}

export default function ArchivePage() {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [items, setItems] = useState<ApplicationResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [unarchivingId, setUnarchivingId] = useState<number | null>(null);

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
      const data = await listApplications(undefined, true);
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
    let filtered = items;
    if (statusFilter) {
      filtered = filtered.filter((a) => a.status === statusFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      filtered = filtered.filter(
        (a) =>
          a.reference.toLowerCase().includes(q) ||
          (a.internal_notes || "").toLowerCase().includes(q) ||
          (a.applicant_name_native || "").toLowerCase().includes(q) ||
          (a.applicant_name_latin || "").toLowerCase().includes(q),
      );
    }
    return filtered;
  }, [items, searchQuery, statusFilter]);

  async function handleUnarchive(id: number) {
    if (!confirm("Вернуть заявку в работу? Она снова появится в основном списке.")) return;
    setUnarchivingId(id);
    try {
      await unarchiveApplication(id);
      await load();
    } catch (e) {
      alert(`Ошибка: ${(e as Error).message}`);
    } finally {
      setUnarchivingId(null);
    }
  }

  function handleOpenDetails(id: number) {
    // Открываем детали в обычной странице. Так как заявка архивная,
    // там покажется баннер «эта заявка в архиве» (см. ApplicationDetail).
    router.push(`/admin?id=${id}&from=archive`);
  }

  if (!authChecked) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-tertiary" />
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 py-4">
      {/* Шапка */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/admin")}
            className="p-1.5 rounded-md text-tertiary hover:text-primary hover:bg-secondary transition-colors"
            title="Вернуться к заявкам"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-semibold text-primary">
            Архив <span className="text-tertiary text-sm font-normal">({filteredItems.length})</span>
          </h1>
        </div>
      </div>

      {/* Фильтры */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[240px] max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-tertiary" />
          <input
            type="text"
            placeholder="Поиск по номеру, ФИО, заметкам..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-md border bg-primary text-primary"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
        >
          <option value="">Все исходы</option>
          <option value="approved">Одобренные</option>
          <option value="rejected">Отказанные</option>
          <option value="cancelled">Отменённые</option>
        </select>
      </div>

      {error && (
        <div className="bg-danger text-danger text-sm p-3 rounded-md mb-3">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
        </div>
      ) : filteredItems.length === 0 ? (
        <div
          className="bg-primary rounded-xl border p-12 text-center text-tertiary text-sm"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
        >
          {items.length === 0
            ? "Архив пуст. Завершённые заявки можно отправить в архив со страницы заявки."
            : "Нет заявок по выбранным фильтрам."}
        </div>
      ) : (
        <div
          className="bg-primary rounded-xl border overflow-hidden"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
        >
          <table className="w-full text-sm">
            <thead style={{ background: "var(--color-bg-secondary)" }}>
              <tr className="text-left text-xs uppercase tracking-wide text-tertiary">
                <th className="px-4 py-2.5">№ заявки</th>
                <th className="px-4 py-2.5">ФИО заявителя</th>
                <th className="px-4 py-2.5">Исход</th>
                <th className="px-4 py-2.5">Подача в UGE</th>
                <th className="px-4 py-2.5">Архивирована</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((a) => {
                const colors =
                  STATUS_COLORS[a.status] || {
                    bg: "var(--color-bg-secondary)",
                    text: "var(--color-text-tertiary)",
                  };
                return (
                  <tr
                    key={a.id}
                    className="border-t hover:bg-secondary/50 cursor-pointer"
                    style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}
                    onClick={() => handleOpenDetails(a.id)}
                  >
                    <td className="px-4 py-2.5 text-primary font-mono text-xs">
                      #{a.reference}
                    </td>
                    <td className="px-4 py-2.5">
                      {a.applicant_name_native || a.applicant_name_latin ? (
                        <div className="min-w-0">
                          <div className="text-sm text-primary line-clamp-1">
                            {a.applicant_name_native || "—"}
                          </div>
                          {a.applicant_name_latin && (
                            <div className="text-[10px] text-tertiary uppercase tracking-wide line-clamp-1">
                              {a.applicant_name_latin}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-tertiary text-xs">— анкета не заполнена —</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className="inline-block px-2 py-0.5 rounded text-xs font-medium"
                        style={{ background: colors.bg, color: colors.text }}
                      >
                        {STATUS_LABELS[a.status] || a.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-tertiary text-xs">
                      {formatDate(a.submission_date)}
                    </td>
                    <td className="px-4 py-2.5 text-tertiary text-xs">
                      {formatDate(a.archived_at)}
                    </td>
                    <td className="px-4 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleOpenDetails(a.id)}
                          className="p-1.5 rounded-md text-tertiary hover:text-primary hover:bg-secondary"
                          title="Открыть детали"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleUnarchive(a.id)}
                          disabled={unarchivingId === a.id}
                          className="p-1.5 rounded-md text-tertiary hover:text-info hover:bg-info disabled:opacity-50"
                          title="Вернуть в работу"
                        >
                          {unarchivingId === a.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <RotateCcw className="w-4 h-4" />
                          )}
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
  );
}
