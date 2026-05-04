"use client";

/**
 * Pack 17.3 — Модал «Сгенерировать ИНН».
 * Pack 18.1 — добавлен tier-fallback по регионам (бэкенд).
 * Pack 18.2 — live-проверка статуса НПД через ФНС API при «Принять».
 * Pack 18.6 — синхронизация с реальным API + два warning'а:
 *   - 🟡 жёлтая плашка fallback (ИНН выдан из другого региона из-за пустоты целевого)
 *   - 🟠 оранжевая плашка skipped_fns_unavailable (ФНС был недоступен, ручная проверка)
 *   - убраны мёртвые блоки (full_name_rmsp / address_was_generated / region_pick_explanation)
 *   - URL Яндекс/Rusprofile теперь генерируются на фронте из ИНН
 *   - Фикс payload accept: `kladr_code` вместо несуществующего `region_kladr_code`
 *
 * Workflow:
 *  1. При открытии автоматически вызывает /inn-suggest → показывает кандидата
 *  2. Менеджер видит: ИНН, адрес, регион, дата НПД, ссылки на проверку
 *     + жёлтый warning если был fallback на другой регион
 *  3. Кнопки:
 *     - «Принять»     → /inn-accept → проверка через ФНС, закрывает модал
 *                       (если ФНС вернул skipped — показываем оранжевый warning
 *                        и НЕ закрываем модал, менеджер может перепринять)
 *     - «Другой»      → повторный /inn-suggest (ещё кандидат)
 *     - «Закрыть»     → закрывает без сохранения
 */

import { useEffect, useState } from "react";
import {
  X,
  Loader2,
  Sparkles,
  AlertCircle,
  AlertTriangle, // Pack 18.6: жёлтая плашка fallback
  WifiOff,       // Pack 18.6: оранжевая плашка ФНС-недоступен
  Check,
  RefreshCw,
  ExternalLink,
  MapPin,
  Calendar,
  Info,
} from "lucide-react";
import {
  suggestInn,
  acceptInn,
  InnSuggestionResponse,
  InnAcceptResult,
} from "@/lib/api";

interface Props {
  applicantId: number;
  /**
   * Pack 17.3: был флаг что у applicant был адрес ДО открытия модалки.
   * Pack 18.6: больше не используется — раньше сравнивали с suggestion.address_was_generated,
   * но бэкенд это поле не шлёт. Оставлен в Props чтобы не править ApplicantDrawer.tsx.
   */
  hadAddressBefore: boolean;
  onClose: () => void;
  onAccepted: () => void;     // вызывается после успешного accept
}

export function InnSuggestionModal({
  applicantId,
  hadAddressBefore: _hadAddressBefore, // Pack 18.6: deprecated, см. Props
  onClose,
  onAccepted,
}: Props) {
  const [suggestion, setSuggestion] = useState<InnSuggestionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  // Pack 18.6: результат accept'а — для показа оранжевого warning'а если ФНС был недоступен
  const [acceptResult, setAcceptResult] = useState<InnAcceptResult | null>(null);

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
    setAcceptResult(null);
    try {
      // Pack 18.6 fixes vs Pack 17.3:
      //   - kladr_code (не region_kladr_code — pydantic игнорировал это имя)
      //   - inn_registration_date из реального поля (не estimated_npd_start)
      //   - home_address передаём всегда (раньше только при address_was_generated,
      //     но бэк это поле не шлёт). Бэк сам решает писать ли home_address —
      //     см. inn_generation.py inn_accept(): if payload.home_address: applicant.home_address = ...
      //     То есть для applicant с уже заполненным адресом он ВСЁ РАВНО будет перезаписан
      //     значением из suggestion. Это намеренно: home_address из suggestion согласован с
      //     ИНН (тот же регион), а старый адрес applicant'а мог быть из другого региона.
      const result = await acceptInn(applicantId, {
        inn: suggestion.inn,
        inn_registration_date: suggestion.inn_registration_date || null,
        home_address: suggestion.home_address || null,
        kladr_code: suggestion.kladr_code || null,
        inn_source: "registry_snrip",
      });
      setAcceptResult(result);

      // Pack 18.6: если ФНС был недоступен — НЕ закрываем модал, показываем
      // оранжевый warning + ссылку manual_check_url. Менеджер сам решает
      // перепринять (нажать «Другой») или закрыть модал.
      if (result.npd_check_status === "skipped_fns_unavailable") {
        setAccepting(false);
        return;
      }

      // Успех (confirmed или skipped_already_checked) — закрываем
      onAccepted();
    } catch (e) {
      // 409 от бэка: ФНС подтвердил отзыв НПД — кандидат помечен is_invalid,
      // менеджер должен жать «Другой кандидат». Бэк присылает понятный текст ошибки.
      setError((e as Error).message);
      setAccepting(false);
    }
  }

  function handleAnother() {
    setAcceptResult(null); // Pack 18.6: сбрасываем оранжевый warning при смене кандидата
    setError(null);
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
              {/* Pack 18.6: 🟡 жёлтая плашка fallback — выводим ПЕРВОЙ чтобы менеджер
                  заметил что регион подменён до того как смотрит на адрес */}
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
                      ИНН выдан из региона{" "}
                      <b>{suggestion.region_name}</b>
                      {suggestion.requested_region_name && (
                        <>
                          {" "}вместо{" "}
                          <b>{suggestion.requested_region_name}</b>
                        </>
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
                {/* ИНН — крупно */}
                <div>
                  <div className="text-xs uppercase tracking-wide text-tertiary mb-1">
                    ИНН
                  </div>
                  <div className="text-2xl font-mono font-semibold text-primary tracking-wide">
                    {suggestion.inn}
                  </div>
                </div>

                {/* Дата начала НПД (Pack 18.6: правильное поле inn_registration_date) */}
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

                {/* Адрес (Pack 18.6: убрана badge СГЕНЕРИРОВАН/ИЗ ПРОФИЛЯ —
                    бэкенд не шлёт address_was_generated, всё равно сравнить не с чем) */}
                <div>
                  <div className="text-xs uppercase tracking-wide text-tertiary mb-1 flex items-center gap-1">
                    <MapPin className="w-3 h-3" />
                    Адрес проживания
                  </div>
                  <div className="text-sm text-primary">{suggestion.home_address}</div>
                </div>

                {/* Регион + источник выбора (Pack 18.6: region_name из реального поля,
                    region_pick_explanation бэкенд не шлёт — заменён на расшифровку source) */}
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

              {/* Pack 18.6: 🟠 оранжевая плашка — ФНС был недоступен при принятии.
                  Показываем после accept'а если backend вернул skipped_fns_unavailable.
                  Менеджер должен зайти по ссылке и проверить вручную. */}
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

              {/* Ссылки на проверку «не светится ли»
                  Pack 18.6: URL генерируются на фронте из ИНН (бэкенд эти поля не шлёт).
                  Без full_name (мы его и не показываем — см. убранный блок выше). */}
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
            {/* Pack 18.6: после skipped_fns_unavailable accept уже произошёл на бэке.
                Меняем «Принять» на «Готово, закрыть» — он просто триггерит onAccepted
                (родитель перезагрузит applicant'а). */}
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
  // 2024-05-15 -> 15.05.2024
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${m[3]}.${m[2]}.${m[1]}`;
}

// Pack 18.6: расшифровка fallback_reason из бэкенда (см. inn_generator/pipeline.py).
// Значения формирует pick_candidate_with_fallback() — два варианта.
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

// Pack 18.6: расшифровка поля source из бэкенда — откуда был взят регион для подбора.
// Значения см. inn_generator/pipeline.py (resolve_target_region).
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
