"use client";

import { useState } from "react";
import { Trash2, Loader2 } from "lucide-react";
import {
  ApplicationResponse,
  softDeleteApplication,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onDeleted: () => void;
}

/**
 * Pack 27.0 — кнопка "Удалить" (мягкое удаление в корзину).
 *
 * Размещается в шапке ApplicationDetail рядом с ArchiveButton.
 * Доступна из любого статуса. После удаления заявка попадает в корзину
 * и автоматически удалится навсегда через 7 дней.
 *
 * Использование:
 *   <DeleteButton application={application} onDeleted={() => router.push("/admin")} />
 */
export function DeleteButton({ application, onDeleted }: Props) {
  const [loading, setLoading] = useState(false);

  async function handleDelete() {
    const ok = window.confirm(
      `Переместить заявку ${application.reference} в корзину?\n\n` +
      `Заявка будет удалена навсегда автоматически через 7 дней. ` +
      `До этого её можно восстановить из раздела «Корзина».`
    );
    if (!ok) return;

    setLoading(true);
    try {
      await softDeleteApplication(application.id);
      onDeleted();
    } catch (e) {
      alert(`Не удалось удалить: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleDelete}
      disabled={loading}
      className="px-3 py-1.5 rounded-md text-sm font-medium border flex items-center gap-1.5 transition-colors disabled:opacity-50"
      style={{
        borderColor: "var(--color-border-danger)",
        borderWidth: 0.5,
        color: "var(--color-text-danger)",
        background: "var(--color-bg-primary)",
      }}
      title="Переместить в корзину (auto-delete через 7 дней)"
    >
      {loading ? (
        <>
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Удаление...
        </>
      ) : (
        <>
          <Trash2 className="w-3.5 h-3.5" />
          Удалить
        </>
      )}
    </button>
  );
}
