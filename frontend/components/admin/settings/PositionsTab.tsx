"use client";

import { useEffect, useState, useMemo } from "react";
import { Plus, Loader2, Edit2, Power, ChevronDown, ChevronRight } from "lucide-react";
import {
  PositionResponse,
  CompanyResponse,
  listPositions,
  listCompanies,
  deletePosition,
} from "@/lib/api";
import { PositionDrawer } from "./PositionDrawer";

// Pack 20.1: метки уровней для отображения
const LEVEL_LABELS: Record<number, string> = {
  1: "Junior",
  2: "Middle",
  3: "Senior",
  4: "Lead",
};

// Pack 20.1: метка для группы без специальности
const NO_SPECIALTY_LABEL = "Без специальности";

interface GroupedPositions {
  specialtyKey: string; // code или "" для unmarked
  specialtyCode: string | null;
  specialtyName: string;
  positions: PositionResponse[];
}

export function PositionsTab() {
  const [positions, setPositions] = useState<PositionResponse[]>([]);
  const [companies, setCompanies] = useState<CompanyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  // Pack 20.1: какие группы развёрнуты
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    // По умолчанию — все свёрнуты, кроме "Без специальности" (чтобы видеть мусор)
    "": true,
  });

  async function load() {
    setError(null);
    try {
      const [posData, compData] = await Promise.all([
        listPositions(undefined, showInactive),
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
  }, [showInactive]);

  async function handleDeactivate(id: number, title: string) {
    if (!confirm(`Деактивировать должность "${title}"?`)) return;
    try {
      await deletePosition(id);
      await load();
    } catch (e) {
      alert(`Ошибка: ${(e as Error).message}`);
    }
  }

  function toggleGroup(key: string) {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  // Pack 20.1: группировка должностей по специальности
  const grouped = useMemo<GroupedPositions[]>(() => {
    const groups = new Map<string, GroupedPositions>();

    for (const p of positions) {
      // Достаём specialty_code и specialty_name из ответа API
      // (поля добавлены в PositionRead в Pack 20.1)
      const code = (p as any).specialty_code || null;
      const name = (p as any).specialty_name || NO_SPECIALTY_LABEL;
      const key = code || "";

      if (!groups.has(key)) {
        groups.set(key, {
          specialtyKey: key,
          specialtyCode: code,
          specialtyName: name,
          positions: [],
        });
      }
      groups.get(key)!.positions.push(p);
    }

    // Сортировка: сначала размеченные группы по коду specialty, потом неразмеченные
    const result = Array.from(groups.values()).sort((a, b) => {
      // "Без специальности" — последняя
      if (!a.specialtyCode && b.specialtyCode) return 1;
      if (a.specialtyCode && !b.specialtyCode) return -1;
      if (!a.specialtyCode && !b.specialtyCode) return 0;
      return a.specialtyCode!.localeCompare(b.specialtyCode!);
    });

    // Внутри каждой группы — сортируем по level (1..4), потом по id
    for (const g of result) {
      g.positions.sort((a, b) => {
        const la = (a as any).level ?? 99;
        const lb = (b as any).level ?? 99;
        if (la !== lb) return la - lb;
        return a.id - b.id;
      });
    }

    return result;
  }, [positions]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="text-base font-semibold text-primary">
            Должности <span className="text-tertiary text-sm font-normal">({positions.length})</span>
          </h2>
          <label className="flex items-center gap-1.5 text-xs text-tertiary cursor-pointer">
            <input type="checkbox" checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)} />
            Показать неактивные
          </label>
          {/* Pack 20.1: кнопки развернуть/свернуть всё */}
          <button
            onClick={() => {
              const all: Record<string, boolean> = {};
              for (const g of grouped) all[g.specialtyKey] = true;
              setExpandedGroups(all);
            }}
            className="text-xs text-tertiary hover:text-primary px-2 py-1 rounded-md hover:bg-secondary"
          >
            Развернуть все
          </button>
          <button
            onClick={() => setExpandedGroups({})}
            className="text-xs text-tertiary hover:text-primary px-2 py-1 rounded-md hover:bg-secondary"
          >
            Свернуть все
          </button>
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
        <div className="space-y-2">
          {grouped.map((group) => {
            const isExpanded = !!expandedGroups[group.specialtyKey];
            const isUnmarked = !group.specialtyCode;
            return (
              <div
                key={group.specialtyKey}
                className="bg-primary rounded-xl border overflow-hidden"
                style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
              >
                {/* Заголовок группы — кликабельный */}
                <button
                  onClick={() => toggleGroup(group.specialtyKey)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-secondary transition-colors"
                  style={{ background: isUnmarked ? "var(--color-bg-secondary)" : "transparent" }}
                >
                  <div className="flex items-center gap-2">
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-tertiary" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-tertiary" />
                    )}
                    {group.specialtyCode && (
                      <span className="text-xs font-mono text-tertiary">{group.specialtyCode}</span>
                    )}
                    <span className={`text-sm font-medium ${isUnmarked ? "text-tertiary italic" : "text-primary"}`}>
                      {group.specialtyName}
                    </span>
                    <span className="text-xs text-tertiary">({group.positions.length})</span>
                  </div>
                </button>

                {/* Тело группы — таблица должностей */}
                {isExpanded && (
                  <div className="border-t" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                    <table className="w-full text-sm">
                      <thead style={{ background: "var(--color-bg-secondary)" }}>
                        <tr className="text-left text-xs uppercase tracking-wide text-tertiary">
                          <th className="px-4 py-2 w-20">Уровень</th>
                          <th className="px-4 py-2">Название</th>
                          <th className="px-4 py-2 w-32">Зарплата</th>
                          <th className="px-4 py-2 w-28">Обязанностей</th>
                          <th className="px-4 py-2 w-20">Заявок</th>
                          <th className="px-4 py-2 w-24"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.positions.map((p) => {
                          const level = (p as any).level as number | null | undefined;
                          const levelLabel = level ? LEVEL_LABELS[level] : null;
                          return (
                            <tr key={p.id} className={`border-t ${!p.is_active ? "opacity-50" : ""}`}
                              style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                              <td className="px-4 py-2.5 text-tertiary text-xs">
                                {level && (
                                  <span className="inline-flex items-center gap-1">
                                    <span className="font-mono">L{level}</span>
                                    <span className="text-tertiary">{levelLabel}</span>
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-2.5 text-primary font-medium">{p.title_ru}</td>
                              <td className="px-4 py-2.5 text-tertiary text-xs">
                                {p.salary_rub_default
                                  ? `${Number(p.salary_rub_default).toLocaleString("ru-RU")} ₽`
                                  : "—"}
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
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {editingId !== null && (
        <PositionDrawer positionId={editingId === "new" ? null : editingId}
          companies={companies}
          allPositions={positions}
          onClose={() => setEditingId(null)}
          onSaved={() => { setEditingId(null); load(); }} />
      )}
    </div>
  );
}
