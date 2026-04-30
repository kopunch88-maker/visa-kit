"use client";

import { useState } from "react";
import { Archive, RotateCcw, Loader2 } from "lucide-react";
import {
  ApplicationResponse,
  archiveApplication,
  unarchiveApplication,
} from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onChanged: () => void;
}

/**
 * Pack 10: кнопка архивирования / возврата из архива.
 *
 * Использование в ApplicationDetail.tsx — вставить в шапку рядом с
 * другими кнопками (например, рядом с "Изменить статус"):
 *
 *   <ArchiveButton application={application} onChanged={loadApplication} />
 *
 * Поведение:
 * - Если заявка не в архиве и можно архивировать → кнопка "В архив"
 * - Если заявка не в архиве, но статус не финальный → кнопка disabled с подсказкой
 * - Если заявка в архиве → кнопка "Вернуть в работу"
 */
export function ArchiveButton({ application, onChanged }: Props) {
  const [loading, setLoading] = useState(false);

  const isArchived = application.is_archived === true;
  const canArchive = application.can_be_archived === true;

  async function handleArchive() {
    if (!confirm(
      "Перенести эту заявку в архив? Она пропадёт из основного списка, " +
      "но останется доступна на странице /admin/archive."
    )) return;

    setLoading(true);
    try {
      await archiveApplication(application.id);
      onChanged();
    } catch (e) {
      alert(`Не удалось: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleUnarchive() {
    if (!confirm("Вернуть заявку в работу? Она снова появится в основном списке.")) return;

    setLoading(true);
    try {
      await unarchiveApplication(application.id);
      onChanged();
    } catch (e) {
      alert(`Не удалось: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  if (isArchived) {
    return (
      <button
        onClick={handleUnarchive}
        disabled={loading}
        className="px-3 py-1.5 rounded-md text-sm border text-info hover:bg-info disabled:opacity-50 transition-colors flex items-center gap-1.5"
        style={{
          borderColor: "var(--color-border-info, var(--color-border-tertiary))",
          borderWidth: 0.5,
        }}
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
        Вернуть в работу
      </button>
    );
  }

  return (
    <button
      onClick={handleArchive}
      disabled={loading || !canArchive}
      title={
        canArchive
          ? "Перенести в архив"
          : "Архивировать можно только заявки со статусом «Одобрена», «Отказ» или «Отменена»"
      }
      className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
      style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
    >
      {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Archive className="w-3.5 h-3.5" />}
      В архив
    </button>
  );
}


/**
 * Pack 10: баннер «Эта заявка в архиве» — показывается на странице
 * деталей если is_archived=true.
 *
 * Использование в ApplicationDetail.tsx — вставить в самом начале
 * содержимого, перед всеми блоками:
 *
 *   {application.is_archived && <ArchiveBanner application={application} onChanged={loadApplication} />}
 */
export function ArchiveBanner({ application, onChanged }: Props) {
  const [loading, setLoading] = useState(false);

  async function handleUnarchive() {
    if (!confirm("Вернуть заявку в работу? Она снова появится в основном списке.")) return;
    setLoading(true);
    try {
      await unarchiveApplication(application.id);
      onChanged();
    } catch (e) {
      alert(`Не удалось: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  const archivedAtStr = application.archived_at
    ? new Date(application.archived_at).toLocaleDateString("ru")
    : "—";

  return (
    <div
      className="rounded-md p-3 mb-4 flex items-start gap-3 border"
      style={{
        background: "var(--color-bg-secondary)",
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
    >
      <Archive className="w-5 h-5 text-tertiary flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-primary">Эта заявка в архиве</div>
        <div className="text-xs text-tertiary">
          Архивирована {archivedAtStr}. Не отображается в основном списке.
        </div>
      </div>
      <button
        onClick={handleUnarchive}
        disabled={loading}
        className="px-3 py-1.5 rounded-md text-sm font-medium text-white disabled:opacity-50 flex items-center gap-1.5 flex-shrink-0"
        style={{ background: "var(--color-accent)" }}
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
        Вернуть в работу
      </button>
    </div>
  );
}
