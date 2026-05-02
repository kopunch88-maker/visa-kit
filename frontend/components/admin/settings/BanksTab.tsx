"use client";

import { useEffect, useState } from "react";
import { Plus, Loader2, Edit2, Power } from "lucide-react";
import {
  BankResponse,
  listBanks,
  deleteBank,
} from "@/lib/api";
import { BankDrawer } from "./BankDrawer";

export function BanksTab() {
  const [banks, setBanks] = useState<BankResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  async function load() {
    setError(null);
    try {
      const data = await listBanks(showInactive);
      setBanks(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    load();
  }, [showInactive]);

  async function handleDeactivate(id: number, name: string) {
    if (!confirm(`Деактивировать "${name}"? Банк скроется из списков, но история заявок останется.`)) return;
    try {
      await deleteBank(id);
      await load();
    } catch (e) {
      alert(`Ошибка: ${(e as Error).message}`);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold text-primary">
            Банки <span className="text-tertiary text-sm font-normal">({banks.length})</span>
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
          <Plus className="w-4 h-4" />
          Добавить банк
        </button>
      </div>

      {error && <div className="bg-danger text-danger text-sm p-3 rounded-md mb-3">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
        </div>
      ) : banks.length === 0 ? (
        <div className="bg-primary rounded-xl border p-8 text-center text-tertiary text-sm"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
          Банков пока нет. Нажмите «Добавить банк» чтобы создать первый.
        </div>
      ) : (
        <div className="bg-primary rounded-xl border overflow-hidden"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
          <table className="w-full text-sm">
            <thead style={{ background: "var(--color-bg-secondary)" }}>
              <tr className="text-left text-xs uppercase tracking-wide text-tertiary">
                <th className="px-4 py-2">Название</th>
                <th className="px-4 py-2">БИК</th>
                <th className="px-4 py-2">ИНН</th>
                <th className="px-4 py-2">Корр. счёт</th>
                <th className="px-4 py-2">Клиентов</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {banks.map((b) => (
                <tr key={b.id} className={`border-t ${!b.is_active ? "opacity-50" : ""}`}
                  style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                  <td className="px-4 py-2.5 text-primary font-medium line-clamp-1">{b.name}</td>
                  <td className="px-4 py-2.5 text-tertiary font-mono text-xs">{b.bik}</td>
                  <td className="px-4 py-2.5 text-tertiary font-mono text-xs">{b.inn}</td>
                  <td className="px-4 py-2.5 text-tertiary font-mono text-xs">{b.correspondent_account}</td>
                  <td className="px-4 py-2.5 text-tertiary">{b.applicant_count ?? 0}</td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setEditingId(b.id)}
                        className="p-1.5 rounded-md text-tertiary hover:text-primary hover:bg-secondary"
                        title="Редактировать">
                        <Edit2 className="w-4 h-4" />
                      </button>
                      {b.is_active && (
                        <button onClick={() => handleDeactivate(b.id, b.name)}
                          className="p-1.5 rounded-md text-tertiary hover:text-danger hover:bg-danger transition-colors"
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
        <BankDrawer
          bankId={editingId === "new" ? null : editingId}
          onClose={() => setEditingId(null)}
          onSaved={() => { setEditingId(null); load(); }}
        />
      )}
    </div>
  );
}
