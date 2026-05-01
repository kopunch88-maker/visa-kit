"use client";

import { useEffect, useRef, useState } from "react";
import {
  Languages, Download, RefreshCw, Loader2, Check, AlertCircle,
  Trash2, Clock, Package,
} from "lucide-react";
import {
  startPackageTranslation,
  startSingleTranslation,
  getTranslations,
  deleteAllTranslations,
  downloadTranslationsZip,
  downloadTranslationFile,
  TranslationItem,
  TranslationsSummary,
  TranslationKind,
  TRANSLATION_KIND_INFO,
} from "@/lib/api";

interface Props {
  applicationId: number;
}

const POLL_INTERVAL_MS = 3000;

function _triggerBrowserDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function TranslationPanel({ applicationId }: Props) {
  const [items, setItems] = useState<TranslationItem[]>([]);
  const [summary, setSummary] = useState<TranslationsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);  // блокировка действий пока идёт операция
  const [downloadingId, setDownloadingId] = useState<TranslationKind | null>(null);
  const [downloadingZip, setDownloadingZip] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Загрузка + polling
  async function load() {
    try {
      const data = await getTranslations(applicationId);
      // Сортируем по order из TRANSLATION_KIND_INFO
      const sorted = [...data.translations].sort(
        (a, b) => TRANSLATION_KIND_INFO[a.kind].order - TRANSLATION_KIND_INFO[b.kind].order,
      );
      setItems(sorted);
      setSummary(data.summary);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  // Polling — пока есть pending/in_progress
  useEffect(() => {
    if (summary?.is_active) {
      if (!pollRef.current) {
        pollRef.current = setInterval(load, POLL_INTERVAL_MS);
      }
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary?.is_active]);

  async function handleStartPackage() {
    setBusy(true);
    setError(null);
    try {
      await startPackageTranslation(applicationId);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRetranslateAll() {
    if (!confirm("Удалить все переводы и перевести заново? Старые файлы будут потеряны.")) return;
    setBusy(true);
    setError(null);
    try {
      await deleteAllTranslations(applicationId);
      await startPackageTranslation(applicationId);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleClearAll() {
    if (!confirm("Удалить все переводы без перевода заново?")) return;
    setBusy(true);
    setError(null);
    try {
      await deleteAllTranslations(applicationId);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRetranslateOne(kind: TranslationKind) {
    setBusy(true);
    setError(null);
    try {
      await startSingleTranslation(applicationId, kind);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDownloadOne(item: TranslationItem) {
    setDownloadingId(item.kind);
    setError(null);
    try {
      const blob = await downloadTranslationFile(applicationId, item.kind);
      const filename = item.file_name || TRANSLATION_KIND_INFO[item.kind].es_filename;
      _triggerBrowserDownload(blob, filename);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloadingId(null);
    }
  }

  async function handleDownloadZip() {
    setDownloadingZip(true);
    setError(null);
    try {
      const blob = await downloadTranslationsZip(applicationId);
      _triggerBrowserDownload(blob, `translations_${applicationId}.zip`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloadingZip(false);
    }
  }

  if (loading) {
    return (
      <div
        className="bg-primary rounded-xl border p-4"
        style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
      >
        <div className="flex items-center gap-2 text-sm text-tertiary">
          <Loader2 className="w-4 h-4 animate-spin" />
          Загрузка переводов…
        </div>
      </div>
    );
  }

  const hasAny = summary?.has_any ?? false;
  const isActive = summary?.is_active ?? false;
  const allDone = hasAny && !isActive && (summary?.failed ?? 0) === 0;

  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary flex items-center gap-1.5">
          <Languages className="w-3.5 h-3.5" />
          Испанский перевод
          {hasAny && (
            <span className="text-tertiary normal-case font-normal">
              ({summary!.done}/{summary!.total} готово
              {(summary!.failed ?? 0) > 0 ? `, ${summary!.failed} ошибок` : ""})
            </span>
          )}
        </h3>

        <div className="flex items-center gap-2 flex-wrap">
          {!hasAny && (
            <button
              onClick={handleStartPackage}
              disabled={busy}
              className="px-4 py-1.5 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-1.5"
              style={{ background: "var(--color-accent)" }}
            >
              {busy ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Запуск…
                </>
              ) : (
                <>
                  <Languages className="w-3.5 h-3.5" />
                  Перевести пакет
                </>
              )}
            </button>
          )}

          {hasAny && !isActive && (
            <>
              {(summary?.done ?? 0) > 0 && (
                <button
                  onClick={handleDownloadZip}
                  disabled={downloadingZip || busy}
                  className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
                  style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
                  title="Скачать архив со всеми переведёнными документами"
                >
                  {downloadingZip ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Архивация…
                    </>
                  ) : (
                    <>
                      <Package className="w-3.5 h-3.5" />
                      Скачать архив
                    </>
                  )}
                </button>
              )}
              <button
                onClick={handleRetranslateAll}
                disabled={busy}
                className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
                style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
                title="Удалить все переводы и перевести заново"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
                Перевести заново
              </button>
              <button
                onClick={handleClearAll}
                disabled={busy}
                className="p-1.5 rounded-md border text-tertiary hover:bg-secondary disabled:opacity-50 transition-colors"
                style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
                title="Удалить все переводы"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </>
          )}

          {isActive && (
            <span className="text-sm text-tertiary flex items-center gap-1.5">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Переводим… {summary!.done + summary!.failed} из {summary!.total}
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-3 bg-danger text-danger text-sm p-3 rounded-md">
          {error}
        </div>
      )}

      {!hasAny && (
        <div className="text-sm text-tertiary py-2">
          Переводов ещё нет. Нажмите «Перевести пакет», чтобы перевести 10 русских документов на испанский через AI. Это займёт около минуты.
        </div>
      )}

      {hasAny && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {items.map((item) => (
            <TranslationRow
              key={item.kind}
              item={item}
              isDownloading={downloadingId === item.kind}
              busy={busy || isActive}
              onDownload={() => handleDownloadOne(item)}
              onRetranslate={() => handleRetranslateOne(item.kind)}
            />
          ))}
        </div>
      )}

      {allDone && (
        <div className="mt-3 text-xs text-success flex items-center gap-1.5">
          <Check className="w-3.5 h-3.5" />
          Все документы успешно переведены
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Row component
// ============================================================================

interface RowProps {
  item: TranslationItem;
  isDownloading: boolean;
  busy: boolean;
  onDownload: () => void;
  onRetranslate: () => void;
}

function TranslationRow({ item, isDownloading, busy, onDownload, onRetranslate }: RowProps) {
  const info = TRANSLATION_KIND_INFO[item.kind];
  const isDone = item.status === "done";
  const isFailed = item.status === "failed";
  const isPending = item.status === "pending";
  const isInProgress = item.status === "in_progress";

  let statusIcon: React.ReactNode;
  let statusText: string;
  let statusColors: { bg: string; color: string };

  if (isDone) {
    statusIcon = <Check className="w-3.5 h-3.5" />;
    statusText = "Готово";
    statusColors = { bg: "var(--color-bg-success)", color: "var(--color-text-success)" };
  } else if (isFailed) {
    statusIcon = <AlertCircle className="w-3.5 h-3.5" />;
    statusText = "Ошибка";
    statusColors = { bg: "var(--color-bg-danger)", color: "var(--color-text-danger)" };
  } else if (isInProgress) {
    statusIcon = <Loader2 className="w-3.5 h-3.5 animate-spin" />;
    statusText = "Переводится";
    statusColors = { bg: "var(--color-bg-info)", color: "var(--color-text-info)" };
  } else {
    statusIcon = <Clock className="w-3.5 h-3.5" />;
    statusText = "В очереди";
    statusColors = { bg: "var(--color-bg-secondary)", color: "var(--color-text-tertiary)" };
  }

  return (
    <div
      className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm"
      style={{ background: "var(--color-bg-secondary)" }}
    >
      <div
        className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
        style={statusColors}
        title={statusText}
      >
        {statusIcon}
      </div>

      <div className="min-w-0 flex-1">
        <div className="text-sm text-primary line-clamp-1">
          {info.es_filename}
        </div>
        <div className="text-xs text-tertiary line-clamp-1">
          {isFailed && item.error_message ? (
            <span className="text-danger" title={item.error_message}>
              {item.error_message}
            </span>
          ) : (
            <>
              {info.ru_label} → испанский
              {isDone && item.file_size && (
                <> · {Math.round(item.file_size / 1024)} КБ</>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 flex-shrink-0">
        {isDone && (
          <button
            onClick={onDownload}
            disabled={isDownloading || busy}
            className="p-1.5 rounded hover:bg-primary disabled:opacity-50 transition-colors"
            title="Скачать"
          >
            {isDownloading ? (
              <Loader2 className="w-4 h-4 animate-spin text-tertiary" />
            ) : (
              <Download className="w-4 h-4 text-tertiary" />
            )}
          </button>
        )}

        {(isDone || isFailed) && (
          <button
            onClick={onRetranslate}
            disabled={busy}
            className="p-1.5 rounded hover:bg-primary disabled:opacity-50 transition-colors"
            title="Перевести этот документ заново"
          >
            <RefreshCw className="w-4 h-4 text-tertiary" />
          </button>
        )}
      </div>
    </div>
  );
}
