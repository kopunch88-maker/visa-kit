"use client";

/**
 * Pack 28.5 — модал прогресса уточнения даты регистрации НПД.
 *
 * Открывается из ApplicantDrawer когда менеджер жмёт «Уточнить точную дату».
 * Стартует backend task (бинпоиск, ~6-7 мин), поллит каждые 5 сек,
 * показывает прогресс (текст + полоса), позволяет закрыть в любой момент
 * (бинпоиск продолжается в фоне).
 *
 * При status='done' автоматически вызывает onSuccess() — родительский
 * ApplicantDrawer рефрешит данные и обновляет UI.
 */

import { useEffect, useRef, useState } from "react";
import {
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  Calendar,
  Search,
} from "lucide-react";
import {
  startRefineInnDate,
  getRefineTask,
  RefineInnDateTask,
} from "@/lib/api";

interface Props {
  applicantId: number;
  applicantName: string;
  inn: string;
  onClose: () => void;
  onSuccess: (newDate: string) => void;
}

const POLL_INTERVAL_MS = 5000;
const MAX_POLL_TIME_MS = 12 * 60 * 1000; // 12 мин (запас на rate-limit ФНС)

export function RefineInnDateModal({
  applicantId,
  applicantName,
  inn,
  onClose,
  onSuccess,
}: Props) {
  const [task, setTask] = useState<RefineInnDateTask | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt] = useState(() => Date.now());
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const successFiredRef = useRef(false);

  useEffect(() => {
    startTask();
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startTask() {
    setError(null);
    try {
      const t = await startRefineInnDate(applicantId);
      setTask(t);
      // Если task мгновенно done (idempotency hit на завершённой задаче) —
      // сразу вызываем onSuccess
      if (t.status === "done" && t.result_registration_date && !successFiredRef.current) {
        successFiredRef.current = true;
        onSuccess(t.result_registration_date);
        return;
      }
      pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function poll() {
    if (!task) return;
    try {
      const t = await getRefineTask(task.id);
      setTask(t);

      if (t.status === "done") {
        if (t.result_registration_date && !successFiredRef.current) {
          successFiredRef.current = true;
          onSuccess(t.result_registration_date);
        }
        return;
      }

      if (t.status === "failed") {
        setError(t.error || "Не удалось уточнить дату — см. логи Railway");
        return;
      }

      // Проверяем что не превышен max poll time
      if (Date.now() - startedAt > MAX_POLL_TIME_MS) {
        setError(
          "Бинпоиск длится слишком долго (>12 мин). Закройте окно — задача " +
          "продолжится в фоне. Дату можно проверить позже в карточке клиента."
        );
        return;
      }

      pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    } catch (e) {
      // Сетевая ошибка — пробуем ещё раз
      console.warn("[RefineInnDateModal] poll error:", e);
      pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    }
  }

  const elapsedSec = Math.floor((Date.now() - startedAt) / 1000);
  const elapsedText = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, "0")}`;

  const progressPct = task && task.progress_total > 0
    ? Math.min(100, Math.round((task.progress_current / task.progress_total) * 100))
    : 0;

  const isRunning = task && (task.status === "pending" || task.status === "running");
  const isDone = task && task.status === "done";
  const isFailed = task && task.status === "failed";

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={isRunning ? undefined : onClose}
    >
      <div
        className="w-full max-w-xl rounded-lg flex flex-col"
        style={{
          background: "var(--color-bg-primary)",
          border: "0.5px solid var(--color-border-tertiary)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderBottomWidth: 0.5,
          }}
        >
          <div className="flex items-center gap-2">
            {isRunning && <Loader2 className="w-5 h-5 animate-spin" style={{ color: "var(--color-accent)" }} />}
            {isDone && <CheckCircle2 className="w-5 h-5" style={{ color: "var(--color-text-success)" }} />}
            {isFailed && <XCircle className="w-5 h-5" style={{ color: "var(--color-text-danger)" }} />}
            {!task && <Search className="w-5 h-5" style={{ color: "var(--color-accent)" }} />}
            <span className="text-base font-semibold text-primary">
              Уточнение даты регистрации НПД
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors text-tertiary"
            aria-label="Закрыть"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          <div className="text-sm text-secondary">
            <div>
              Клиент: <span className="text-primary">{applicantName}</span>
            </div>
            <div className="font-mono text-xs text-tertiary mt-0.5">
              ИНН: {inn}
            </div>
          </div>

          {error && (
            <div
              className="p-3 rounded-md text-sm"
              style={{
                background: "var(--color-bg-danger)",
                color: "var(--color-text-danger)",
                border: "0.5px solid var(--color-border-danger)",
              }}
            >
              {error}
            </div>
          )}

          {isRunning && (
            <>
              <div
                className="p-4 rounded-md space-y-3"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "0.5px solid var(--color-border-secondary)",
                }}
              >
                <div className="flex items-center gap-3">
                  <div className="flex-1 text-sm text-primary">
                    Бинпоиск даты через ФНС API...
                  </div>
                  <div className="text-sm font-mono text-tertiary tabular-nums">
                    {elapsedText}
                  </div>
                </div>

                {task && task.progress_text && (
                  <div className="text-xs text-secondary">
                    {task.progress_text}
                  </div>
                )}

                {task && task.progress_total > 0 && (
                  <div>
                    <div className="flex items-center justify-between text-xs text-tertiary mb-1">
                      <span>Прогресс</span>
                      <span className="font-mono tabular-nums">
                        {task.progress_current} / {task.progress_total}
                      </span>
                    </div>
                    <div
                      className="h-2 rounded-full overflow-hidden"
                      style={{ background: "var(--color-bg-tertiary)" }}
                    >
                      <div
                        className="h-full transition-all duration-500"
                        style={{
                          width: `${progressPct}%`,
                          background: "var(--color-accent)",
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="text-[11px] text-tertiary leading-relaxed">
                ФНС API ограничивает запросы (2/мин). Бинпоиск делает ~12
                запросов = ~6-7 минут. Можно закрыть окно — задача продолжится
                в фоне, и при следующем открытии карточки клиента вы увидите
                реальную дату.
              </div>
            </>
          )}

          {isDone && task && task.result_registration_date && (
            <div
              className="p-4 rounded-md space-y-2"
              style={{
                background: "var(--color-bg-success)",
                color: "var(--color-text-success)",
                border: "0.5px solid var(--color-border-success)",
              }}
            >
              <div className="font-medium flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" />
                Дата найдена
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5" />
                <span className="font-mono">
                  {formatDate(task.result_registration_date)}
                </span>
              </div>
              <div className="text-xs">
                Дата сохранена в карточку клиента и пометка изменена
                с «Ориентировочная» на «Реальная».
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="px-5 py-4 border-t flex justify-end gap-2"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderTopWidth: 0.5,
          }}
        >
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
          >
            {isRunning ? "Закрыть (бинпоиск продолжится)" : "Закрыть"}
          </button>
        </div>
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${m[3]}.${m[2]}.${m[1]}`;
}
