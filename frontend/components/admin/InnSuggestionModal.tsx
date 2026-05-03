"use client";

/**
 * Pack 17.3 — Модал «Сгенерировать ИНН».
 *
 * Workflow:
 *  1. При открытии автоматически вызывает /inn-suggest → показывает кандидата
 *  2. Менеджер видит: ИНН, ФИО из реестра, адрес, дата НПД, ссылки на проверку
 *  3. Кнопки:
 *     - «Принять»     → /inn-accept → закрывает модал, обновляет родителя
 *     - «Другой»      → повторный /inn-suggest (ещё кандидат)
 *     - «Закрыть»     → закрывает без сохранения
 *
 * Что сохраняется в applicant при «Принять»:
 *  - inn
 *  - inn_registration_date (estimated_npd_start)
 *  - inn_kladr_code (target_kladr_code)
 *  - inn_source = "auto-generated"
 *  - home_address — ТОЛЬКО если он был сгенерирован (не было в БД)
 */

import { useEffect, useState } from "react";
import {
  X,
  Loader2,
  Sparkles,
  AlertCircle,
  Check,
  RefreshCw,
  ExternalLink,
  MapPin,
  User,
  Calendar,
  Info,
} from "lucide-react";
import {
  suggestInn,
  acceptInn,
  InnSuggestionResponse,
} from "@/lib/api";

interface Props {
  applicantId: number;
  hadAddressBefore: boolean;  // у applicant.home_address был валидный текст до открытия модала
  onClose: () => void;
  onAccepted: () => void;     // вызывается после успешного accept
}

export function InnSuggestionModal({
  applicantId,
  hadAddressBefore,
  onClose,
  onAccepted,
}: Props) {
  const [suggestion, setSuggestion] = useState<InnSuggestionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Загружаем кандидата при открытии и по кнопке «Другой»
  useEffect(() => {
    loadSuggestion();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  async function loadSuggestion() {
    setLoading(true);
    setError(null);
    try {
      const data = await suggestInn(applicantId);
      setSuggestion(data);
    } catch (e) {
      setError((e as Error).message);
      setSuggestion(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleAccept() {
    if (!suggestion) return;
    setAccepting(true);
    setError(null);
    try {
      await acceptInn(applicantId, {
        inn: suggestion.inn,
        inn_registration_date: suggestion.estimated_npd_start || null,
        // home_address передаём ТОЛЬКО если он был сгенерирован
        // (если был у applicant — оставляем тот, что в БД, не трогаем)
        home_address: suggestion.address_was_generated
          ? suggestion.home_address
          : null,
        region_kladr_code: suggestion.target_kladr_code,
      });
      onAccepted();
    } catch (e) {
      setError((e as Error).message);
      setAccepting(false);
    }
  }

  function handleAnother() {
    setAttempt((n) => n + 1);
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
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

          {loading && (
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

          {!loading && suggestion && (
            <>
              {/* Карточка кандидата */}
              <div
                className="p-4 rounded-md space-y-3"
                style={{
                  background: "var(--color-bg-secondary)",
                  border: "0.5px solid var(--color-border-secondary)",
                }}
              >
                {/* ИНН — крупно */}
                <div>
                  <div className="text-xs uppercase tracking-wide text-tertiary mb-1">
                    ИНН
                  </div>
                  <div className="text-2xl font-mono font-semibold text-primary tracking-wide">
                    {suggestion.inn}
                  </div>
                </div>

                {/* ФИО из реестра (для проверки в Яндексе) */}
                {suggestion.full_name_rmsp && (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-tertiary mb-1 flex items-center gap-1">
                      <User className="w-3 h-3" />
                      ФИО в реестре ФНС (НЕ используется в документах)
                    </div>
                    <div className="text-sm text-secondary">
                      {suggestion.full_name_rmsp}
                    </div>
                  </div>
                )}

                {/* Дата начала НПД */}
                {suggestion.estimated_npd_start && (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-tertiary mb-1 flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      Дата начала статуса НПД (ориентировочно)
                    </div>
                    <div className="text-sm text-primary">
                      {formatDate(suggestion.estimated_npd_start)}
                    </div>
                  </div>
                )}

                {/* Адрес */}
                <div>
                  <div className="text-xs uppercase tracking-wide text-tertiary mb-1 flex items-center gap-1">
                    <MapPin className="w-3 h-3" />
                    Адрес проживания
                    {suggestion.address_was_generated ? (
                      <span
                        className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                        style={{
                          background: "var(--color-bg-warning)",
                          color: "var(--color-text-warning)",
                        }}
                      >
                        СГЕНЕРИРОВАН
                      </span>
                    ) : (
                      <span
                        className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                        style={{
                          background: "var(--color-bg-info)",
                          color: "var(--color-text-info)",
                        }}
                      >
                        ИЗ ПРОФИЛЯ
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-primary">{suggestion.home_address}</div>
                </div>

                {/* Регион + объяснение */}
                <div
                  className="text-xs p-2 rounded flex gap-1.5 items-start"
                  style={{
                    background: "var(--color-bg-info)",
                    color: "var(--color-text-info)",
                  }}
                >
                  <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-medium">{suggestion.target_region_name}</span>
                    {" — "}
                    {suggestion.region_pick_explanation}
                  </div>
                </div>
              </div>

              {/* Ссылки на проверку «не светится ли» */}
              <div className="space-y-2">
                <div className="text-xs uppercase tracking-wide text-tertiary">
                  Ручная проверка перед принятием
                </div>
                <div className="flex flex-col sm:flex-row gap-2">
                  <a
                    href={suggestion.yandex_search_url}
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
                    Яндекс по ИНН и ФИО
                  </a>
                  <a
                    href={suggestion.rusprofile_url}
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

              {hadAddressBefore && suggestion.address_was_generated && (
                <div
                  className="p-3 rounded-md text-xs flex gap-2 items-start"
                  style={{
                    background: "var(--color-bg-warning)",
                    color: "var(--color-text-warning)",
                    border: "0.5px solid var(--color-border-warning)",
                  }}
                >
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>
                    У клиента в карточке был указан адрес, но регион из него не
                    распознан. Используется новый сгенерированный адрес —
                    <b> текущий адрес в карточке будет перезаписан</b> при принятии.
                  </span>
                </div>
              )}
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
            disabled={loading || accepting || !suggestion}
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
              Отмена
            </button>
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
          </div>
        </div>
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  // 2024-05-15 -> 15.05.2024
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${m[3]}.${m[2]}.${m[1]}`;
}
