"use client";
// Pack 38.1 — PaidToggleButton. Кнопка "$" рядом с именем клиента.
// Клик — переключает флаг is_paid на Application.
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { ApplicationResponse, togglePaid } from "@/lib/api";
interface Props {
  application: ApplicationResponse;
  onChanged: () => void;
}
export function PaidToggleButton({ application, onChanged }: Props) {
  const [loading, setLoading] = useState(false);
  const isPaid = application.is_paid === true;
  async function handleClick() {
    setLoading(true);
    try {
      await togglePaid(application.id);
      onChanged();
    } catch (e) {
      alert(`Не удалось переключить флаг "оплачен": ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }
  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      title={isPaid ? "Снять флаг «оплачен»" : "Отметить как оплачено"}
      aria-label={isPaid ? "Снять флаг оплачен" : "Отметить как оплачено"}
      aria-pressed={isPaid}
      className="inline-flex items-center justify-center w-8 h-8 rounded-md border transition-colors disabled:opacity-50 hover:bg-secondary"
      style={{
        borderColor: isPaid ? "#22c55e" : "var(--color-border-tertiary)",
        borderWidth: 0.5,
        background: isPaid ? "rgba(34, 197, 94, 0.10)" : "transparent",
      }}
    >
      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : (
        <span
          className="text-xs font-bold"
          style={{ color: isPaid ? "#22c55e" : "var(--color-text-tertiary)" }}
        >
          $
        </span>
      )}
    </button>
  );
}
