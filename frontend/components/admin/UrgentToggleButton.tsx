"use client";

// Pack 30.0 — UrgentToggleButton. Кнопка-иконка "огонёк" рядом с именем клиента
// в шапке ApplicationDetail. Клик — переключает флаг is_urgent на Application.
// Срочные заявки уходят на верх списка слева, внутри urgent-группы сортируются
// по алфавиту ФИО (логика на backend в list_applications).

import { useState } from "react";
import { Flame, Loader2 } from "lucide-react";
import { ApplicationResponse, toggleUrgent } from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onChanged: () => void;
}

export function UrgentToggleButton({ application, onChanged }: Props) {
  const [loading, setLoading] = useState(false);
  const isUrgent = application.is_urgent === true;

  async function handleClick() {
    setLoading(true);
    try {
      await toggleUrgent(application.id);
      onChanged();
    } catch (e) {
      alert(`Не удалось переключить флаг "срочно": ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      title={isUrgent ? "Снять флаг «срочно»" : "Отметить как срочное"}
      aria-label={isUrgent ? "Снять флаг срочно" : "Отметить как срочное"}
      aria-pressed={isUrgent}
      className="inline-flex items-center justify-center w-8 h-8 rounded-md border transition-colors disabled:opacity-50 hover:bg-secondary"
      style={{
        borderColor: isUrgent ? "#f97316" : "var(--color-border-tertiary)",
        borderWidth: 0.5,
        background: isUrgent ? "rgba(249, 115, 22, 0.10)" : "transparent",
      }}
    >
      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : (
        <Flame
          className="w-4 h-4"
          style={{
            color: isUrgent ? "#f97316" : "var(--color-text-tertiary)",
            fill: isUrgent ? "#f97316" : "none",
          }}
        />
      )}
    </button>
  );
}
