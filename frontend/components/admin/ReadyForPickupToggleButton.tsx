"use client";

// Pack 34.2 — ReadyForPickupToggleButton. Кнопка-иконка "чемодан" рядом
// с UrgentToggleButton в шапке ApplicationDetail. Клик — переключает флаг
// is_ready_for_pickup на Application.
// Логика сортировки: огонь приоритетнее чемодана (Pack 34.2 в applications.py),
// внутри ready-группы — алфавит ФИО.

import { useState } from "react";
import { Briefcase, Loader2 } from "lucide-react";
import { ApplicationResponse, toggleReady } from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onChanged: () => void;
}

export function ReadyForPickupToggleButton({ application, onChanged }: Props) {
  const [loading, setLoading] = useState(false);
  const isReady = application.is_ready_for_pickup === true;

  async function handleClick() {
    setLoading(true);
    try {
      await toggleReady(application.id);
      onChanged();
    } catch (e) {
      alert(`Не удалось переключить флаг "готово": ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      title={isReady ? "Снять флаг «готово к выдаче»" : "Готово, можно забирать"}
      aria-label={isReady ? "Снять флаг готово к выдаче" : "Готово, можно забирать"}
      aria-pressed={isReady}
      className="inline-flex items-center justify-center w-8 h-8 rounded-md border transition-colors disabled:opacity-50 hover:bg-secondary"
      style={{
        borderColor: isReady ? "#10b981" : "var(--color-border-tertiary)",
        borderWidth: 0.5,
        background: isReady ? "rgba(16, 185, 129, 0.10)" : "transparent",
      }}
    >
      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : (
        <Briefcase
          className="w-4 h-4"
          style={{
            color: isReady ? "#10b981" : "var(--color-text-tertiary)",
            fill: isReady ? "rgba(16, 185, 129, 0.15)" : "none",
          }}
        />
      )}
    </button>
  );
}
