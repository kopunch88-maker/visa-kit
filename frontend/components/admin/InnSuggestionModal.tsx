"use client";

/**
 * Pack 17.3 — Модал «Сгенерировать ИНН».
 * Pack 18.1 — добавлен tier-fallback по регионам (бэкенд).
 * Pack 18.2 — live-проверка статуса НПД через ФНС API при «Принять».
 * Pack 18.6 — синхронизация с реальным API + два warning'а:
 *   - 🟡 жёлтая плашка fallback (ИНН выдан из другого региона из-за пустоты целевого)
 *   - 🟠 оранжевая плашка skipped_fns_unavailable (ФНС был недоступен, ручная проверка)
 *
 * Pack 28.2 Часть Б — поддержка TASK-режима:
 *   - Backend теперь возвращает union: { kind: "immediate", ... } | { kind: "task", task_id, ... }
 *   - При kind="task" модал показывает спиннер «Идёт поиск чистого самозанятого… (до 4 мин)»
 *     и поллит /admin/npd-pool/tasks/{task_id} каждые 3 сек
 *   - Когда task завершается с done — повторно зовём suggestInn → получаем immediate
 *   - Если task failed — показываем ошибку + кнопку «Попробовать ещё раз»
 *
 * Workflow:
 *  1. При открытии вызывает /inn-suggest
 *     → kind="immediate" → показываем кандидата (как раньше)
 *     → kind="task" → переходим в task-режим, поллим
 *  2. Менеджер видит ИНН, адрес, регион, дата НПД, ссылки на проверку
 *  3. Кнопки:
 *     - «Принять»     → /inn-accept → проверка через ФНС, закрывает модал
 *     - «Другой»      → повторный /inn-suggest
 *     - «Закрыть»     → закрывает без сохранения
 */

import { useEffect, useRef, useState } from "react";
import {
  X,
  Loader2,
  Sparkles,
  AlertCircle,
  AlertTriangle,
  WifiOff,
  Check,
  RefreshCw,
  ExternalLink,
  MapPin,
  Calendar,
  Info,
  Search,
} from "lucide-react";
import {
  suggestInn,
  acceptInn,
  getNpdPoolTask,
  InnSuggestionResponse,
  InnSuggestionImmediate,
  InnAcceptResult,
  NpdRefillTask,
} from "@/lib/api";

interface Props {
  applicantId: number;
  /**
   * Pack 17.3 deprecated — оставлен в Props чтобы не править ApplicantDrawer.tsx.
   */
  hadAddressBefore: boolean;
  onClose: () => void;
  onAccepted: () => void;
}

// Pack 28.2: интервал поллинга task'а
const TASK_POLL_INTERVAL_MS = 3000;
// Максимум 6 минут поллинга (refill длится 4-5 мин, запас на rate-limit ФНС)
const TASK_POLL_MAX_MS = 6 * 60 * 1000;

export function InnSuggestionModal({
  applicantId,
  hadAddressBefore: _hadAddressBefore,
  onClose,
  onAccepted,
}: Props) {
  // immediate-result (когда suggest сразу нашёл verified)
  const [suggestion, setSuggestion] = useState<InnSuggestionImmediate | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [acceptResult, setAcceptResult] = useState<InnAcceptResult | null>(null);

  // Pack 28.2: task-режим
  const [task, setTask] = useState<NpdRefillTask | null>(null);
  const [taskRegionName, setTaskRegionName] = useState<string | null>(null);
  const [taskStartedAt, setTaskStartedAt] = useState<number | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    loadSuggestion();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  // Очистка поллинга при закрытии модала
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  async function loadSuggestion() {
    setLoading(true);
    setError(null);
    setTask(null);
    setTaskRegionName(null);
    setTaskStartedAt(null);
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    try {
      const data: InnSuggestionResponse = await suggestInn(applicantId);

      if (data.kind === "immediate") {
        // Сразу нашли verified — показываем как раньше
        setSuggestion(data);
        setLoading(false);
      } else if (data.kind === "task") {
        // Пул пуст — стартанул refill task, поллим
        setSuggestion(null);
        setTaskRegionName(data.region_name);
        setTaskStartedAt(Date.now());
        setLoading(false); // спиннер теперь не общий, а в блоке task
        startPollingTask(data.task_id);
      }
    } catch (e) {
      setError((e as Error).message);
      setSuggestion(null);
      setLoading(false);
    }
  }

  function startPollingTask(taskId: number) {
    let elapsed = 0;

    const poll = async () => {
      try {
        const t = await getNpdPoolTask(taskId);
        setTask(t);

        if (t.status === "done") {
          // Refill завершился. Повторно зовём suggestInn — получим immediate.
          if (pollTimerRef.current) {
            clearTimeout(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          // Маленькая задержка чтобы UI успел показать «Готово» прежде чем повторный suggest
          await new Promise((r) => setTimeout(r, 500));
          // Повторный suggest
          try {
            const data = await suggestInn(applicantId);
            if (data.kind === "immediate") {
              setSuggestion(data);
              setTask(null);
              setTaskRegionName(null);
            } else {
              // Маловероятно но возможно — пул опять пуст, опять task
              setError(
                "После пополнения пула в регионе всё ещё нет verified. Возможно, refill не нашёл подходящих кандидатов. Попробуйте «Другой кандидат».",
              );
            }
          } catch (e) {
            setError(`Не удалось получить кандидата после пополнения: ${(e as Error).message}`);
          }
          return;
        }

        if (t.status === "failed") {
          if (pollTimerRef.current) {
            clearTimeout(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          setError(
            t.error || "Не удалось пополнить пул самозанятых. Попробуйте «Другой кандидат» или попозже.",
          );
          return;
        }

        // pending или running — продолжаем поллинг
        elapsed = taskStartedAt ? Date.now() - taskStartedAt : 0;
        if (elapsed > TASK_POLL_MAX_MS) {
          if (pollTimerRef.current) {
            clearTimeout(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          setError(
            "Поиск длится слишком долго (> 6 мин). Закройте модал и попробуйте позже — refill в фоне продолжится.",
          );
          return;
        }

        pollTimerRef.current = setTimeout(poll, TASK_POLL_INTERVAL_MS);
      } catch (e) {
        // Не валим UI на сетевой ошибке — пробуем ещё раз
        console.error("[InnSuggestionModal] poll error:", e);
        pollTimerRef.current = setTimeout(poll, TASK_POLL_INTERVAL_MS);
      }
    };

    pollTimerRef.current = setTimeout(poll, TASK_POLL_INTERVAL_MS);
  }

  async function handleAccept() {
    if (!suggestion) return;
    setAccepting(true);
    setError(null);
    setAcceptResult(null);
    try {
      const result = await acceptInn(applicantId, {
        inn: suggestion.inn,
        inn_registration_date: suggestion.inn_registration_date || null,
        home_address: suggestion.home_address || null,
        kladr_code: suggestion.kladr_code || null,
        inn_source: "npd_pool", // Pack 28.2: новые ИНН из npd_candidate
      });
      setAcceptResult(result);

      // skipped_fns_unavailable — НЕ закрываем модал, показываем оранжевый warning
      if (result.npd_check_status === "skipped_fns_unavailable") {
        setAccepting(false);
        return;
      }

      // confirmed / skipped_already_checked / skipped_recently_verified — закрываем
      onAccepted();
    } catch (e) {
      setError((e as Error).message);
      setAccepting(false);
    }
  }

  function handleAnother() {
    setAcceptResult(null);
    setError(null);
    setAttempt((n) => n + 1);
  }

  // Прогресс task'а в процентах (для возможной полосы прогресса)
  const taskProgressPct = task && task.progress_total > 0
    ? Math.min(100, Math.round((task.progress_current / task.progress_total) * 100))
    : 0;

  // Elapsed time текстом для UI
  const elapsedSec = taskStartedAt
    ? Math.floor((Date.now() - taskStartedAt) / 1000)
    : 0;
  const elapsedText = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, "0")}`;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={task ? undefined : onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-auto rounded-lg flex flex-col"
        style={{
          background: "var(--color-bg-primary)",
          border: "0.5px solid var(--color-border-tertiary)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b sticky top-0"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderBottomWidth: 0.5,
            background: "var(--color-bg-primary)",
          }}
        >
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
            <span className="text-base font-semibold text-primary">
              Генерация ИНН самозанятого
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors text-tertiary"
            disabled={accepting}
            aria-label="Закрыть"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 p-5 space-y-4">
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

          {loading && !task && (
            <div
              className="p-6 rounded-md flex items-center justify-center gap-2 text-sm text-tertiary"
              style={{
                background: "var(--color-bg-secondary)",
                border: "0.5px solid var(--color-border-secondary)",
              }}
            >
              <Loader2 className="w-4 h-4 animate-spin" />
              Подбираем кандидата из реестра самозанятых...
            </div>
          )}

          {/* Pack 28.2: task-режим — спиннер с прогрессом */}
          {task && (
            <div
              className="p-6 rounded-md space-y-4"
              style={{
                background: "var(--color-bg-secondary)",
                border: "0.5px solid var(--color-border-secondary)",
              }}
            >
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Search className="w-6 h-6" style={{ color: "var(--color-accent)" }} />
                  <Loader2
                    className="w-6 h-6 animate-spin absolute inset-0"
                    style={{ color: "var(--color-accent)", opacity: 0.4 }}
                  />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-primary">
                    Идёт поиск чистого самозанятого…
                  </div>
                  <div className="text-xs text-tertiary mt-0.5">
                    до 4 минут — проверяем кандидатов через ЕГРЮЛ и ФНС НПД
                  </div>
                </div>
                <div className="text-sm font-mono text-tertiary tabular-nums">
                  {elapsedText}
                </div>
              </div>

              {taskRegionName && (
                <div className="text-xs text-tertiary">
                  Регион: <span className="text-secondary">{taskRegionName}</span>
                </div>
              )}

              {task.progress_text && (
                <div className="text-xs text-secondary px-3 py-2 rounded"
                     style={{ background: "var(--color-bg-info)", color: "var(--color-text-info)" }}>
                  <Info className="w-3 h-3 inline mr-1.5 -mt-0.5" />
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
                        width: `${taskProgressPct}%`,
                        background: "var(--color-accent)",
                      }}
                    />
                  </div>
                </div>
              )}

              <div className="text-[11px] text-tertiary leading-relaxed">
                Поиск идёт в фоне через rmsp-pp.nalog.ru → ЕГРЮЛ → ФНС НПД API.
                ФНС ограничивает запросы (2/мин), поэтому на проверку каждого кандидата
                нужно ~30 сек. Можно закрыть модал — refill продолжится в фоне,
                и следующая попытка для этого региона будет мгновенной.
              </div>
            </div>
          )}

          {!loading && !task && suggestion && (
            <>
              {/* 🟡 fallback warning (для immediate-результата) */}
              {suggestion.fallback_used && (
                <div
                  className="p-3 rounded-md text-sm flex gap-2 items-start"
                  style={{
                    background: "var(--color-bg-warning)",
                    color: "var(--color-text-warning)",
                    border: "0.5px solid var(--color-border-warning)",
                  }}
                >
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <div className="font-medium">
                      ИНН выдан из региона <b>{suggestion.region_name}</b>
                      {suggestion.requested_region_name && (
                        <> вместо <b>{suggestion.requested_region_name}</b></>
                      )}
                    </div>
                    <div className="text-xs">
                      {fallbackReasonExplain(suggestion.fallback_reason)}
                      {" "}
                      Адрес тоже сгенерирован под фактический регион — он будет
                      записан в карточку клиента при принятии.
                    </div>
                  </div>
                </div>
              )}

              {/* Карточка кандидата */}
              <div
                className="p-4 rounded-md space-y-3"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "0.5px solid var(--color-border-secondary)",
                }}
              >
                <div>
                  <div className="text-xs uppercase tracking-wide text-tertiary mb-1">
                    ИНН
                  </div>
                  <div className="text-2xl font-mono font-semibold text-primary tracking-wide">
                    {suggestion.inn}
                  </div>
                </div>

                {suggestion.inn_registration_date && (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-tertiary mb-1 flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      Дата регистрации как самозанятого
                    </div>
                    <div className="text-sm text-primary">
                      {formatDate(suggestion.inn_registration_date)}
                    </div>
                  </div>
                )}

                <div>
                  <div className="text-xs uppercase tracking-wide text-tertiary mb-1 flex items-center gap-1">
                    <MapPin className="w-3 h-3" />
                    Адрес проживания
                  </div>
                  <div className="text-sm text-primary">{suggestion.home_address}</div>
                </div>

                <div
                  className="text-xs p-2 rounded flex gap-1.5 items-start"
                  style={{
                    background: "var(--color-bg-info)",
                    color: "var(--color-text-info)",
                  }}
                >
                  <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-medium">{suggestion.region_name}</span>
                    {" — "}
                    {sourceExplain(suggestion.source)}
                  </div>
                </div>
              </div>

              {/* 🟠 ФНС unavailable warning */}
              {acceptResult?.npd_check_status === "skipped_fns_unavailable" && (
                <div
                  className="p-3 rounded-md text-sm space-y-2"
                  style={{
                    background: "var(--color-bg-warning)",
                    color: "var(--color-text-warning)",
                    border: "0.5px solid var(--color-border-warning)",
                  }}
                >
                  <div className="flex gap-2 items-start">
                    <WifiOff className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-medium mb-0.5">
                        ФНС API временно недоступен
                      </div>
                      <div className="text-xs">
                        {acceptResult.npd_check_message ||
                          "ИНН сохранён без проверки актуальности статуса НПД. " +
                            "Рекомендуем проверить вручную перед выдачей справки."}
                      </div>
                    </div>
                  </div>
                  {acceptResult.manual_check_url && (
                    <a
                      href={acceptResult.manual_check_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
                      style={{
                        background: "var(--color-text-warning)",
                        color: "var(--color-bg-warning)",
                      }}
                    >
                      <ExternalLink className="w-3 h-3" />
                      Открыть проверку на сайте ФНС
                    </a>
                  )}
                </div>
              )}

              {/* Ссылки на проверку */}
              <div className="space-y-2">
                <div className="text-xs uppercase tracking-wide text-tertiary">
                  Ручная проверка перед принятием
                </div>
                <div className="flex flex-col sm:flex-row gap-2">
                  <a
                    href={`https://yandex.ru/search/?text=${encodeURIComponent(suggestion.inn)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm border transition-colors hover:bg-secondary"
                    style={{
                      borderColor: "var(--color-border-tertiary)",
                      borderWidth: 0.5,
                      color: "var(--color-text-primary)",
                    }}
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    Яндекс по ИНН
                  </a>
                  <a
                    href={`https://www.rusprofile.ru/search?query=${encodeURIComponent(suggestion.inn)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm border transition-colors hover:bg-secondary"
                    style={{
                      borderColor: "var(--color-border-tertiary)",
                      borderWidth: 0.5,
                      color: "var(--color-text-primary)",
                    }}
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    Rusprofile
                  </a>
                </div>
                <p className="text-[11px] text-tertiary">
                  Откройте обе ссылки и проверьте: не упоминается ли этот ИНН в
                  публичных источниках (новости, форумы, скандалы). Если всё чисто
                  — нажмите «Принять».
                </p>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div
          className="px-5 py-4 border-t flex justify-between gap-3 sticky bottom-0"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderTopWidth: 0.5,
            background: "var(--color-bg-primary)",
          }}
        >
          <button
            onClick={handleAnother}
            disabled={loading || accepting || !!task}
            className="px-4 py-2 rounded-md text-sm border text-secondary disabled:opacity-40 hover:bg-secondary transition-colors flex items-center gap-1.5"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Другой кандидат
          </button>

          <div className="flex gap-2">
            <button
              onClick={onClose}
              disabled={accepting}
              className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
            >
              {task ? "Закрыть (refill продолжится)" : "Отмена"}
            </button>
            {acceptResult?.npd_check_status === "skipped_fns_unavailable" ? (
              <button
                onClick={onAccepted}
                className="px-5 py-2 rounded-md text-sm font-medium text-white transition-colors flex items-center gap-2"
                style={{ background: "var(--color-accent)" }}
              >
                <Check className="w-4 h-4" />
                Готово, закрыть
              </button>
            ) : (
              <button
                onClick={handleAccept}
                disabled={loading || accepting || !suggestion}
                className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-2"
                style={{ background: "var(--color-accent)" }}
              >
                {accepting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Сохраняем...
                  </>
                ) : (
                  <>
                    <Check className="w-4 h-4" />
                    Принять
                  </>
                )}
              </button>
            )}
          </div>
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

function fallbackReasonExplain(reason: string | null): string {
  switch (reason) {
    case "no_free_in_target_region":
      return "В целевом регионе закончились свободные ИНН — взяли из соседнего (по диаспоре).";
    case "no_free_in_target_or_diaspora":
      return "В целевом регионе и регионах диаспоры свободных ИНН не осталось — взяли московский (safety net).";
    default:
      return "ИНН подобран из другого региона.";
  }
}

function sourceExplain(source: string): string {
  switch (source) {
    case "home_address":
      return "регион распознан из адреса проживания клиента";
    case "contract_city":
      return "регион взят из города подписания договора";
    case "company_address":
      return "регион взят из юридического адреса компании-заказчика";
    case "diaspora":
      return "регион выбран случайно из диаспоры по гражданству клиента";
    case "fallback_moscow":
      return "регион не определён — выбрана Москва (safety net)";
    default:
      return `источник: ${source}`;
  }
}
