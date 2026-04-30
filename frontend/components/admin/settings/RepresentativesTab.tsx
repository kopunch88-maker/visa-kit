"use client";

import { useEffect, useState } from "react";
import { Plus, Loader2, Edit2, Power } from "lucide-react";
import {
  RepresentativeResponse,
  listRepresentatives,
  deleteRepresentative,
} from "@/lib/api";
import { RepresentativeDrawer } from "./RepresentativeDrawer";

export function RepresentativesTab() {
  const [items, setItems] = useState<RepresentativeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  async function load() {
    setError(null);
    try {
      setItems(await listRepresentatives(showInactive));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { setLoading(true); load(); }, [showInactive]);

  async function handleDeactivate(id: number, name: string) {
    if (!confirm(`Деактивировать представителя "${name}"?`)) return;
    try { await deleteRepresentative(id); await load(); }
    catch (e) { alert(`Ошибка: ${(e as Error).message}`); }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold text-primary">
            Представители <span className="text-tertiary text-sm font-normal">({items.length})</span>
          </h2>
          <label className="flex items-center gap-1.5 text-xs text-tertiary cursor-pointer">
            <input type="checkbox" checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)} />
            Показать неактивные
          </label>
        </div>
        <button onClick={() => setEditingId("new")}
          className="px-3 py-1.5 rounded-md text-sm font-medium text-white flex items-center gap-1.5"
          style={{ background: "var(--color-accent)" }}>
          <Plus className="w-4 h-4" /> Добавить представителя
        </button>
      </div>

      {error && <div className="bg-danger text-danger text-sm p-3 rounded-md mb-3">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-primary rounded-xl border p-8 text-center text-tertiary text-sm"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
          Представителей пока нет.
        </div>
      ) : (
        <div className="bg-primary rounded-xl border overflow-hidden"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
          <table className="w-full text-sm">
            <thead style={{ background: "var(--color-bg-secondary)" }}>
              <tr className="text-left text-xs uppercase tracking-wide text-tertiary">
                <th className="px-4 py-2">Имя</th>
                <th className="px-4 py-2">NIE</th>
                <th className="px-4 py-2">Город</th>
                <th className="px-4 py-2">Email</th>
                <th className="px-4 py-2">Заявок</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className={`border-t ${!r.is_active ? "opacity-50" : ""}`}
                  style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                  <td className="px-4 py-2.5 text-primary font-medium">
                    {r.full_name || `${r.first_name} ${r.last_name}`}
                  </td>
                  <td className="px-4 py-2.5 text-tertiary font-mono text-xs">{r.nie}</td>
                  <td className="px-4 py-2.5 text-secondary text-xs">{r.address_city}</td>
                  <td className="px-4 py-2.5 text-secondary text-xs line-clamp-1">{r.email}</td>
                  <td className="px-4 py-2.5 text-tertiary">{r.application_count ?? 0}</td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setEditingId(r.id)}
                        className="p-1.5 rounded-md text-tertiary hover:text-primary hover:bg-secondary"
                        title="Редактировать">
                        <Edit2 className="w-4 h-4" />
                      </button>
                      {r.is_active && (
                        <button onClick={() => handleDeactivate(r.id, r.full_name || `${r.first_name} ${r.last_name}`)}
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
        <RepresentativeDrawer representativeId={editingId === "new" ? null : editingId}
          onClose={() => setEditingId(null)}
          onSaved={() => { setEditingId(null); load(); }} />
      )}
    </div>
  );
}
