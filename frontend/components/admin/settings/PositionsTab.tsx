"use client";

import { useEffect, useState } from "react";
import { Plus, Loader2, Edit2, Power } from "lucide-react";
import {
  PositionResponse,
  CompanyResponse,
  listPositions,
  listCompanies,
  deletePosition,
} from "@/lib/api";
import { PositionDrawer } from "./PositionDrawer";

export function PositionsTab() {
  const [positions, setPositions] = useState<PositionResponse[]>([]);
  const [companies, setCompanies] = useState<CompanyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [showInactive, setShowInactive] = useState(false);
  const [filterCompanyId, setFilterCompanyId] = useState<number | "">("");

  async function load() {
    setError(null);
    try {
      const [posData, compData] = await Promise.all([
        listPositions(filterCompanyId || undefined, showInactive),
        listCompanies(true),
      ]);
      setPositions(posData);
      setCompanies(compData);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    load();
  }, [showInactive, filterCompanyId]);

  async function handleDeactivate(id: number, title: string) {
    if (!confirm(`Деактивировать должность "${title}"?`)) return;
    try {
      await deletePosition(id);
      await load();
    } catch (e) {
      alert(`Ошибка: ${(e as Error).message}`);
    }
  }

  function getCompanyName(companyId: number) {
    return companies.find((c) => c.id === companyId)?.short_name || "—";
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="text-base font-semibold text-primary">
            Должности <span className="text-tertiary text-sm font-normal">({positions.length})</span>
          </h2>
          <select value={filterCompanyId}
            onChange={(e) => setFilterCompanyId(e.target.value ? parseInt(e.target.value, 10) : "")}
            className="px-2 py-1 text-xs rounded-md border bg-primary text-primary"
            style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}>
            <option value="">Все компании</option>
            {companies.map((c) => <option key={c.id} value={c.id}>{c.short_name}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-tertiary cursor-pointer">
            <input type="checkbox" checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)} />
            Показать неактивные
          </label>
        </div>
        <button onClick={() => setEditingId("new")}
          className="px-3 py-1.5 rounded-md text-sm font-medium text-white flex items-center gap-1.5"
          style={{ background: "var(--color-accent)" }}>
          <Plus className="w-4 h-4" />
          Добавить должность
        </button>
      </div>

      {error && <div className="bg-danger text-danger text-sm p-3 rounded-md mb-3">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
        </div>
      ) : positions.length === 0 ? (
        <div className="bg-primary rounded-xl border p-8 text-center text-tertiary text-sm"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
          Должностей пока нет.
        </div>
      ) : (
        <div className="bg-primary rounded-xl border overflow-hidden"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
          <table className="w-full text-sm">
            <thead style={{ background: "var(--color-bg-secondary)" }}>
              <tr className="text-left text-xs uppercase tracking-wide text-tertiary">
                <th className="px-4 py-2">Название</th>
                <th className="px-4 py-2">Компания</th>
                <th className="px-4 py-2">Зарплата</th>
                <th className="px-4 py-2">Обязанностей</th>
                <th className="px-4 py-2">Заявок</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.id} className={`border-t ${!p.is_active ? "opacity-50" : ""}`}
                  style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                  <td className="px-4 py-2.5 text-primary font-medium line-clamp-1">{p.title_ru}</td>
                  <td className="px-4 py-2.5 text-secondary text-xs">
                    {p.company_short_name || getCompanyName(p.company_id)}
                  </td>
                  <td className="px-4 py-2.5 text-tertiary text-xs">
                    {p.salary_rub_default ? `${Number(p.salary_rub_default).toLocaleString("ru-RU")} ₽` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-tertiary text-xs">{p.duties?.length || 0}</td>
                  <td className="px-4 py-2.5 text-tertiary">{p.application_count ?? 0}</td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setEditingId(p.id)}
                        className="p-1.5 rounded-md text-tertiary hover:text-primary hover:bg-secondary"
                        title="Редактировать">
                        <Edit2 className="w-4 h-4" />
                      </button>
                      {p.is_active && (
                        <button onClick={() => handleDeactivate(p.id, p.title_ru)}
                          className="p-1.5 rounded-md text-tertiary hover:text-danger hover:bg-danger"
                          title="Деактивировать">
                          <Power className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editingId !== null && (
        <PositionDrawer positionId={editingId === "new" ? null : editingId}
          companies={companies}
          onClose={() => setEditingId(null)}
          onSaved={() => { setEditingId(null); load(); }} />
      )}
    </div>
  );
}
