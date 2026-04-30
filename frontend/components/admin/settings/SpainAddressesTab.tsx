"use client";

import { useEffect, useState } from "react";
import { Plus, Loader2, Edit2, Power } from "lucide-react";
import {
  SpainAddressResponse,
  listSpainAddresses,
  deleteSpainAddress,
} from "@/lib/api";
import { SpainAddressDrawer } from "./SpainAddressDrawer";

export function SpainAddressesTab() {
  const [items, setItems] = useState<SpainAddressResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  async function load() {
    setError(null);
    try { setItems(await listSpainAddresses(showInactive)); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }

  useEffect(() => { setLoading(true); load(); }, [showInactive]);

  async function handleDeactivate(id: number, label: string) {
    if (!confirm(`Деактивировать адрес "${label}"?`)) return;
    try { await deleteSpainAddress(id); await load(); }
    catch (e) { alert(`Ошибка: ${(e as Error).message}`); }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold text-primary">
            Адреса в Испании <span className="text-tertiary text-sm font-normal">({items.length})</span>
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
          <Plus className="w-4 h-4" /> Добавить адрес
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
          Адресов пока нет.
        </div>
      ) : (
        <div className="bg-primary rounded-xl border overflow-hidden"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
          <table className="w-full text-sm">
            <thead style={{ background: "var(--color-bg-secondary)" }}>
              <tr className="text-left text-xs uppercase tracking-wide text-tertiary">
                <th className="px-4 py-2">Метка</th>
                <th className="px-4 py-2">Адрес</th>
                <th className="px-4 py-2">Город</th>
                <th className="px-4 py-2">UGE</th>
                <th className="px-4 py-2">Заявок</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className={`border-t ${!a.is_active ? "opacity-50" : ""}`}
                  style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                  <td className="px-4 py-2.5 text-primary font-medium line-clamp-1">{a.label}</td>
                  <td className="px-4 py-2.5 text-secondary text-xs">
                    {a.street}, {a.number}{a.floor ? `, ${a.floor}` : ""}
                  </td>
                  <td className="px-4 py-2.5 text-tertiary text-xs">
                    {a.city} ({a.zip})
                  </td>
                  <td className="px-4 py-2.5 text-tertiary text-xs">{a.uge_office}</td>
                  <td className="px-4 py-2.5 text-tertiary">{a.application_count ?? 0}</td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setEditingId(a.id)}
                        className="p-1.5 rounded-md text-tertiary hover:text-primary hover:bg-secondary"
                        title="Редактировать">
                        <Edit2 className="w-4 h-4" />
                      </button>
                      {a.is_active && (
                        <button onClick={() => handleDeactivate(a.id, a.label)}
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
        <SpainAddressDrawer addressId={editingId === "new" ? null : editingId}
          onClose={() => setEditingId(null)}
          onSaved={() => { setEditingId(null); load(); }} />
      )}
    </div>
  );
}
