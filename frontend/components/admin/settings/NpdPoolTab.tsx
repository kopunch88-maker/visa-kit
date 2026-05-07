"use client";

/**
 * Pack 28.2 Часть Б — таб настроек «Пул самозанятых».
 *
 * Показывает:
 *   - Сводную статистику: всего кандидатов, по статусам, по регионам (verified)
 *   - Таблицу регионов с колонками verified / pending / rejected
 *   - Кнопку «Обновить весь пул» — стартует глобальный refill (ревалидация +
 *     добивка по ключевым регионам), показывает modal с прогрессом
 *
 * Cron еженедельно делает то же самое (вс 03:00 UTC через GitHub Actions).
 */

import { useState, useEffect, useRef } from "react";
import {
  RefreshCw,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Database,
  X,
} from "lucide-react";
import {
  getNpdPoolStats,
  getNpdPoolTask,
  refillPoolGlobal,
  NpdPoolStats,
  NpdRefillTask,
} from "@/lib/api";

// Ключевые регионы (синхронно с backend KEY_REGIONS из npd_pool.py)
const KEY_REGIONS: Array<{ code: string; name: string }> = [
  { code: "77", name: "Москва" },
  { code: "78", name: "Санкт-Петербург" },
  { code: "23", name: "Краснодарский край" },
  { code: "61", name: "Ростовская область" },
  { code: "66", name: "Свердловская область" },
  { code: "16", name: "Татарстан" },
  { code: "54", name: "Новосибирская область" },
  { code: "50", name: "Московская область" },
];

const TASK_POLL_INTERVAL_MS = 3000;

export function NpdPoolTab() {
  const [stats, setStats] = useState<NpdPoolStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Refill task state
  const [refillTask, setRefillTask] = useState<NpdRefillTask | null>(null);
  const [refillStartedAt, setRefillStartedAt] = useState<number | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    loadStats();
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadStats() {
    setLoading(true);
    setError(null);
    try {
      const data = await getNpdPoolStats();
      setStats(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleStartRefill() {
    if (refillTask) return;
    setError(null);
    try {
      const task = await refillPoolGlobal({
        target_per_region: 5,
        revalidate_first: true,
      });
      setRefillTask(task);
      setRefillStartedAt(Date.now());
      startPollingTask(task.id);
    } catch (e) {
      setError(`Не удалось запустить refill: ${(e as Error).message}`);
    }
  }

  function startPollingTask(taskId: number) {
    const poll = async () => {
      try {
        const t = await getNpdPoolTask(taskId);
        setRefillTask(t);

        if (t.status === "done" || t.status === "failed") {
          if (pollTimerRef.current) {
            clearTimeout(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          // Перезагружаем статистику
          await loadStats();
          return;
        }

        pollTimerRef.current = setTimeout(poll, TASK_POLL_INTERVAL_MS);
      } catch (e) {
        console.error("[NpdPoolTab] poll error:", e);
        pollTimerRef.current = setTimeout(poll, TASK_POLL_INTERVAL_MS);
      }
    };
    pollTimerRef.current = setTimeout(poll, TASK_POLL_INTERVAL_MS);
  }

  function closeRefillModal() {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setRefillTask(null);
    setRefillStartedAt(null);
  }

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div
        className="p-3 rounded-md text-sm flex gap-2 items-start"
        style={{
          background: "var(--color-bg-danger)",
          color: "var(--color-text-danger)",
          border: "0.5px solid var(--color-border-danger)",
        }}
      >
        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <span>{error}</span>
      </div>
    );
  }

  // Статистика по регионам — собираем все статусы для каждого региона
  // (для KEY_REGIONS показываем явно, для остальных — отдельный блок)
  const verified = stats?.by_region_verified || {};

  return (
    <div className="space-y-6">
      {/* Сводка */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Всего в пуле"
          value={stats?.total ?? 0}
          icon={<Database className="w-4 h-4" />}
        />
        <StatCard
          label="Verified (готовы к выдаче)"
          value={stats?.by_status?.verified ?? 0}
          icon={<CheckCircle2 className="w-4 h-4" />}
          accent="success"
        />
        <StatCard
          label="Pending (на проверке)"
          value={stats?.by_status?.pending ?? 0}
          icon={<Clock className="w-4 h-4" />}
        />
        <StatCard
          label="Used (выданы клиентам)"
          value={stats?.by_status?.used ?? 0}
          icon={<CheckCircle2 className="w-4 h-4" />}
        />
      </div>

      {/* Действия */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs text-tertiary">
          {stats?.last_refill_at && (
            <>
              Последний refill:{" "}
              <span className="text-secondary">
                {formatDateTime(stats.last_refill_at)}
              </span>
              {stats.last_refill_region && (
                <> (регион {stats.last_refill_region})</>
              )}
            </>
          )}
        </div>
        <button
          onClick={handleStartRefill}
          disabled={!!refillTask}
          className="px-4 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-2"
          style={{ background: "var(--color-accent)" }}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refillTask ? "animate-spin" : ""}`} />
          {refillTask ? "Refill идёт..." : "Обновить весь пул"}
        </button>
      </div>

      {error && (
        <div
          className="p-3 rounded-md text-sm flex gap-2 items-start"
          style={{
            background: "var(--color-bg-danger)",
            color: "var(--color-text-danger)",
            border: "0.5px solid var(--color-border-danger)",
          }}
        >
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Таблица по регионам */}
      <div>
        <div className="text-sm font-medium text-primary mb-2">
          По ключевым регионам
        </div>
        <div
          className="rounded-md overflow-hidden"
          style={{
            border: "0.5px solid var(--color-border-tertiary)",
          }}
        >
          <table className="w-full text-sm">
            <thead
              style={{
                background: "var(--color-bg-secondary)",
                borderBottom: "0.5px solid var(--color-border-tertiary)",
              }}
            >
              <tr>
                <th className="text-left px-3 py-2 font-medium text-secondary">
                  Регион
                </th>
                <th className="text-right px-3 py-2 font-medium text-secondary">
                  Verified
                </th>
                <th className="text-right px-3 py-2 font-medium text-tertiary">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {KEY_REGIONS.map((r) => {
                const v = verified[r.code] ?? 0;
                const ok = v >= 5;
                const warn = v > 0 && v < 5;
                const bad = v === 0;
                return (
                  <tr
                    key={r.code}
                    style={{
                      borderTop: "0.5px solid var(--color-border-tertiary)",
                    }}
                  >
                    <td className="px-3 py-2 text-primary">
                      <span className="text-tertiary mr-2 font-mono text-xs">
                        {r.code}
                      </span>
                      {r.name}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-primary">
                      {v}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {ok && (
                        <span
                          className="text-xs px-2 py-0.5 rounded inline-flex items-center gap-1"
                          style={{
                            background: "var(--color-bg-success)",
                            color: "var(--color-text-success)",
                          }}
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          OK
                        </span>
                      )}
                      {warn && (
                        <span
                          className="text-xs px-2 py-0.5 rounded inline-flex items-center gap-1"
                          style={{
                            background: "var(--color-bg-warning)",
                            color: "var(--color-text-warning)",
                          }}
                        >
                          <AlertCircle className="w-3 h-3" />
                          Мало
                        </span>
                      )}
                      {bad && (
                        <span
                          className="text-xs px-2 py-0.5 rounded inline-flex items-center gap-1"
                          style={{
                            background: "var(--color-bg-danger)",
                            color: "var(--color-text-danger)",
                          }}
                        >
                          <XCircle className="w-3 h-3" />
                          Пусто
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="text-[11px] text-tertiary mt-2">
          Цель — иметь минимум 5 verified кандидатов в каждом ключевом регионе.
          Когда менеджер генерирует ИНН клиенту в регионе с verified=0, backend
          автоматически стартует refill (5-10 мин) — менеджер ждёт со спиннером
          пока пул наполнится. Глобальный refill (кнопка выше или cron вс 03:00 UTC)
          сразу пополняет все регионы и ревалидирует существующих verified.
        </div>
      </div>

      {/* Прочие регионы где есть verified (не из KEY_REGIONS) */}
      {(() => {
        const keySet = new Set(KEY_REGIONS.map((r) => r.code));
        const others = Object.entries(verified).filter(([code]) => !keySet.has(code));
        if (others.length === 0) return null;
        return (
          <div>
            <div className="text-sm font-medium text-primary mb-2">
              Другие регионы (verified &gt; 0)
            </div>
            <div className="flex flex-wrap gap-2">
              {others.map(([code, count]) => (
                <span
                  key={code}
                  className="text-xs px-2 py-1 rounded font-mono"
                  style={{
                    background: "var(--color-bg-secondary)",
                    border: "0.5px solid var(--color-border-tertiary)",
                  }}
                >
                  {code}: {count}
                </span>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Modal с прогрессом refill */}
      {refillTask && (
        <RefillProgressModal
          task={refillTask}
          startedAt={refillStartedAt}
          onClose={closeRefillModal}
        />
      )}
    </div>
  );
}

// === Sub-components ===

function StatCard({
  label,
  value,
  icon,
  accent,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  accent?: "success" | "warning";
}) {
  const bg =
    accent === "success"
      ? "var(--color-bg-success)"
      : "var(--color-bg-secondary)";
  const color =
    accent === "success"
      ? "var(--color-text-success)"
      : "var(--color-text-primary)";
  return (
    <div
      className="p-3 rounded-md"
      style={{
        background: bg,
        border: "0.5px solid var(--color-border-tertiary)",
      }}
    >
      <div className="flex items-center gap-2 text-xs text-tertiary mb-1">
        {icon}
        {label}
      </div>
      <div className="text-2xl font-semibold tabular-nums" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function RefillProgressModal({
  task,
  startedAt,
  onClose,
}: {
  task: NpdRefillTask;
  startedAt: number | null;
  onClose: () => void;
}) {
  const elapsedSec = startedAt ? Math.floor((Date.now() - startedAt) / 1000) : 0;
  const elapsedText = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, "0")}`;

  const progressPct =
    task.progress_total > 0
      ? Math.min(100, Math.round((task.progress_current / task.progress_total) * 100))
      : 0;

  const isRunning = task.status === "pending" || task.status === "running";
  const isDone = task.status === "done";
  const isFailed = task.status === "failed";

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={isRunning ? undefined : onClose}
    >
      <div
        className="w-full max-w-xl max-h-[90vh] overflow-auto rounded-lg flex flex-col"
        style={{
          background: "var(--color-bg-primary)",
          border: "0.5px solid var(--color-border-tertiary)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderBottomWidth: 0.5,
          }}
        >
          <div className="flex items-center gap-2">
            {isRunning && (
              <Loader2
                className="w-5 h-5 animate-spin"
                style={{ color: "var(--color-accent)" }}
              />
            )}
            {isDone && (
              <CheckCircle2
                className="w-5 h-5"
                style={{ color: "var(--color-text-success)" }}
              />
            )}
            {isFailed && (
              <XCircle
                className="w-5 h-5"
                style={{ color: "var(--color-text-danger)" }}
              />
            )}
            <span className="text-base font-semibold text-primary">
              {isRunning && "Обновляем пул..."}
              {isDone && "Пул обновлён"}
              {isFailed && "Refill завершился с ошибкой"}
            </span>
          </div>
          <button
            onClick={onClose}
            disabled={isRunning}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors text-tertiary disabled:opacity-30"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {isRunning && (
            <div className="text-xs text-tertiary">
              Прошло: <span className="font-mono tabular-nums">{elapsedText}</span>
              {" — "}refill длится до 30-60 мин (8 регионов × ~5 мин на каждый)
            </div>
          )}

          {task.progress_text && (
            <div
              className="text-xs px-3 py-2 rounded"
              style={{
                background: "var(--color-bg-info)",
                color: "var(--color-text-info)",
              }}
            >
              {task.progress_text}
            </div>
          )}

          {task.progress_total > 0 && (
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
                    background: isFailed
                      ? "var(--color-text-danger)"
                      : "var(--color-accent)",
                  }}
                />
              </div>
            </div>
          )}

          {isDone && (
            <div className="space-y-2 text-sm">
              <Stat label="Verified добавлено" value={task.verified_added} />
              <Stat label="Отсеяно (открыли ИП)" value={task.egrul_rejected} />
              <Stat label="Отсеяно (не активны в НПД)" value={task.npd_rejected} />
              {task.revalidated_total > 0 && (
                <>
                  <Stat
                    label="Ревалидировано verified"
                    value={task.revalidated_total}
                  />
                  <Stat
                    label="Из них стали невалидны"
                    value={task.revalidated_invalidated}
                  />
                </>
              )}
            </div>
          )}

          {isFailed && task.error && (
            <div
              className="p-3 rounded-md text-sm"
              style={{
                background: "var(--color-bg-danger)",
                color: "var(--color-text-danger)",
                border: "0.5px solid var(--color-border-danger)",
              }}
            >
              {task.error}
            </div>
          )}
        </div>

        {!isRunning && (
          <div
            className="px-5 py-4 border-t flex justify-end"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderTopWidth: 0.5,
            }}
          >
            <button
              onClick={onClose}
              className="px-5 py-2 rounded-md text-sm font-medium text-white transition-colors"
              style={{ background: "var(--color-accent)" }}
            >
              Закрыть
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-tertiary">{label}</span>
      <span className="font-mono tabular-nums text-primary">{value}</span>
    </div>
  );
}

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("ru");
  } catch {
    return iso;
  }
}
