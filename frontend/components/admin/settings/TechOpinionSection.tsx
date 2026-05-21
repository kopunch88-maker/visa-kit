"use client";

/**
 * Pack 41.0 — TechOpinionSection
 *
 * Sub-компонент PositionDrawer для редактирования 12 полей tech_opinion:
 * - international_analog (RU/ES)
 * - tech_opinion_description (RU/ES) — длинный текст
 * - tech_opinion_tools (RU/ES) — список { name, purpose }
 * - tech_opinion_steps (RU/ES) — список { title, body }
 * - tech_opinion_grounds (RU/ES) — список строк
 * - tech_opinion_contract_clause (RU/ES) — короткий текст
 *
 * UI:
 *  - Collapsible section (свёрнута по умолчанию, если контент пуст)
 *  - Tabs RU / ES — общий уровень для всех полей
 *  - Для tools/steps/grounds — динамические списки с + Добавить / × Удалить
 *  - Стили соответствуют PositionDrawer (var(--color-*), text-secondary, etc.)
 */

import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight, Plus, X } from "lucide-react";

// ====== Типы ======

export interface ToolItem {
  name: string;
  purpose: string;
}
export interface StepItem {
  title: string;
  body: string;
}

export interface TechOpinionState {
  international_analog_ru: string;
  international_analog_es: string;
  description_ru: string;
  description_es: string;
  tools_ru: ToolItem[];
  tools_es: ToolItem[];
  steps_ru: StepItem[];
  steps_es: StepItem[];
  grounds_ru: string[];
  grounds_es: string[];
  contract_clause_ru: string;
  contract_clause_es: string;
}

export const EMPTY_TECH_OPINION: TechOpinionState = {
  international_analog_ru: "",
  international_analog_es: "",
  description_ru: "",
  description_es: "",
  tools_ru: [],
  tools_es: [],
  steps_ru: [],
  steps_es: [],
  grounds_ru: [],
  grounds_es: [],
  contract_clause_ru: "",
  contract_clause_es: "",
};

interface Props {
  value: TechOpinionState;
  onChange: (next: TechOpinionState) => void;
}

// ====== Хелперы для immutable-обновления списков ======

function updateAt<T>(arr: T[], idx: number, patch: Partial<T>): T[] {
  return arr.map((item, i) =>
    i === idx ? { ...item, ...patch } : item
  );
}

function removeAt<T>(arr: T[], idx: number): T[] {
  return arr.filter((_, i) => i !== idx);
}

// ====== Главный компонент ======

export function TechOpinionSection({ value, onChange }: Props) {
  // Считаем заполненность для бейджа
  const isFilled = useMemo(() => {
    return (
      value.description_ru.trim().length > 50 ||
      value.description_es.trim().length > 50
    );
  }, [value.description_ru, value.description_es]);

  // Свёрнута по умолчанию если пустая
  const [expanded, setExpanded] = useState(isFilled);
  const [lang, setLang] = useState<"ru" | "es">("ru");

  // Локальные шорткаты для обновления
  const set = (patch: Partial<TechOpinionState>) =>
    onChange({ ...value, ...patch });

  // ----- Геттеры по текущему языку -----
  const intlAnalog =
    lang === "ru" ? value.international_analog_ru : value.international_analog_es;
  const setIntlAnalog = (v: string) =>
    set(lang === "ru" ? { international_analog_ru: v } : { international_analog_es: v });

  const description = lang === "ru" ? value.description_ru : value.description_es;
  const setDescription = (v: string) =>
    set(lang === "ru" ? { description_ru: v } : { description_es: v });

  const tools = lang === "ru" ? value.tools_ru : value.tools_es;
  const setTools = (next: ToolItem[]) =>
    set(lang === "ru" ? { tools_ru: next } : { tools_es: next });

  const steps = lang === "ru" ? value.steps_ru : value.steps_es;
  const setSteps = (next: StepItem[]) =>
    set(lang === "ru" ? { steps_ru: next } : { steps_es: next });

  const grounds = lang === "ru" ? value.grounds_ru : value.grounds_es;
  const setGrounds = (next: string[]) =>
    set(lang === "ru" ? { grounds_ru: next } : { grounds_es: next });

  const contractClause =
    lang === "ru" ? value.contract_clause_ru : value.contract_clause_es;
  const setContractClause = (v: string) =>
    set(lang === "ru" ? { contract_clause_ru: v } : { contract_clause_es: v });

  // ====== Render ======

  const borderStyle = {
    borderColor: "var(--color-border-secondary)",
    borderWidth: 0.5,
  };
  const inputCls =
    "w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2";
  const textareaCls = inputCls + " resize-y";
  const labelCls = "block text-xs font-medium text-secondary mb-1";

  return (
    <div
      className="rounded-md border"
      style={{
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
    >
      {/* Header / Collapse toggle */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2.5 flex items-center justify-between hover:bg-secondary"
      >
        <div className="flex items-center gap-2">
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-tertiary" />
          ) : (
            <ChevronRight className="w-4 h-4 text-tertiary" />
          )}
          <span className="text-sm font-medium text-primary">
            Техническое заключение (Pack 40.0)
          </span>
          {isFilled && (
            <span
              className="text-xs px-1.5 py-0.5 rounded"
              style={{
                background: "var(--color-accent)",
                color: "white",
                fontSize: "10px",
              }}
            >
              ✓ заполнено
            </span>
          )}
        </div>
        <span className="text-xs text-tertiary">
          {lang.toUpperCase()} • 17_Техническое_заключение.docx
        </span>
      </button>

      {!expanded ? null : (
        <div className="px-3 pb-4 pt-1 space-y-4">
          {/* ────── Language tabs ────── */}
          <div className="flex gap-1 border-b" style={borderStyle}>
            <button
              type="button"
              onClick={() => setLang("ru")}
              className={`px-3 py-1.5 text-xs font-medium ${
                lang === "ru"
                  ? "border-b-2 text-primary"
                  : "text-tertiary hover:text-secondary"
              }`}
              style={
                lang === "ru"
                  ? { borderBottomColor: "var(--color-accent)", borderBottomWidth: 2 }
                  : undefined
              }
            >
              🇷🇺 Русский
            </button>
            <button
              type="button"
              onClick={() => setLang("es")}
              className={`px-3 py-1.5 text-xs font-medium ${
                lang === "es"
                  ? "border-b-2 text-primary"
                  : "text-tertiary hover:text-secondary"
              }`}
              style={
                lang === "es"
                  ? { borderBottomColor: "var(--color-accent)", borderBottomWidth: 2 }
                  : undefined
              }
            >
              🇪🇸 Español
            </button>
          </div>

          {/* ────── 1. International analog ────── */}
          <div>
            <label className={labelCls}>
              Международный аналог должности
            </label>
            <input
              type="text"
              value={intlAnalog}
              onChange={(e) => setIntlAnalog(e.target.value)}
              placeholder={
                lang === "ru"
                  ? "data analyst или business intelligence analyst"
                  : "data analyst o business intelligence analyst"
              }
              className={inputCls}
              style={borderStyle}
            />
            <p className="text-xs text-tertiary mt-1">
              Используется в §1 заключения: «должность аналогична позиции ... в международной практике»
            </p>
          </div>

          {/* ────── 2. Description ────── */}
          <div>
            <label className={labelCls}>
              Описание деятельности (раздел 1) <span className="text-danger">*</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={6}
              placeholder={
                lang === "ru"
                  ? "сбор и подготовка данных из различных источников (SQL, REST API, CSV-выгрузки); построение аналитических отчётов..."
                  : "recopilación y preparación de datos de diversas fuentes; construcción de informes analíticos..."
              }
              className={textareaCls}
              style={borderStyle}
            />
            <p className="text-xs text-tertiary mt-1">
              {description.length} симв. (рекомендуется 400-600).
              {description.trim().length > 0 && description.trim().length < 50 && (
                <span className="text-danger ml-1">
                  Слишком коротко — будет выглядеть как заглушка
                </span>
              )}
            </p>
          </div>

          {/* ────── 3. Tools (динамический список) ────── */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className={labelCls + " mb-0"}>
                Инструменты (раздел 2) — {tools.length} шт.
              </label>
              <button
                type="button"
                onClick={() =>
                  setTools([...tools, { name: "", purpose: "" }])
                }
                className="text-xs flex items-center gap-1 px-2 py-1 rounded hover:bg-secondary text-tertiary hover:text-primary"
              >
                <Plus className="w-3 h-3" />
                Добавить
              </button>
            </div>
            <div className="space-y-2">
              {tools.length === 0 && (
                <div className="text-xs text-tertiary italic px-2 py-3 text-center border border-dashed rounded" style={borderStyle}>
                  Нет инструментов. Добавь хотя бы 3-5.
                </div>
              )}
              {tools.map((tool, idx) => (
                <div
                  key={idx}
                  className="rounded-md border p-2 space-y-1.5 bg-primary"
                  style={borderStyle}
                >
                  <div className="flex items-start gap-2">
                    <div className="flex-1 space-y-1.5">
                      <input
                        type="text"
                        value={tool.name}
                        onChange={(e) =>
                          setTools(updateAt(tools, idx, { name: e.target.value }))
                        }
                        placeholder={
                          lang === "ru"
                            ? "name: SQL (PostgreSQL, ClickHouse, BigQuery)"
                            : "name: SQL (PostgreSQL, ClickHouse, BigQuery)"
                        }
                        className={inputCls}
                        style={borderStyle}
                      />
                      <input
                        type="text"
                        value={tool.purpose}
                        onChange={(e) =>
                          setTools(updateAt(tools, idx, { purpose: e.target.value }))
                        }
                        placeholder={
                          lang === "ru"
                            ? "purpose: запросы к хранилищам данных"
                            : "purpose: consultas a almacenes de datos"
                        }
                        className={inputCls}
                        style={borderStyle}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => setTools(removeAt(tools, idx))}
                      className="p-1 rounded text-tertiary hover:text-danger hover:bg-secondary mt-0.5"
                      title="Удалить инструмент"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ────── 4. Steps (динамический список) ────── */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className={labelCls + " mb-0"}>
                Шаги рабочего процесса (раздел 3) — {steps.length} шт.
              </label>
              <button
                type="button"
                onClick={() =>
                  setSteps([...steps, { title: "", body: "" }])
                }
                className="text-xs flex items-center gap-1 px-2 py-1 rounded hover:bg-secondary text-tertiary hover:text-primary"
              >
                <Plus className="w-3 h-3" />
                Добавить
              </button>
            </div>
            <div className="space-y-2">
              {steps.length === 0 && (
                <div className="text-xs text-tertiary italic px-2 py-3 text-center border border-dashed rounded" style={borderStyle}>
                  Нет шагов. Рекомендуется 6-8 шагов рабочего процесса.
                </div>
              )}
              {steps.map((step, idx) => (
                <div
                  key={idx}
                  className="rounded-md border p-2 space-y-1.5 bg-primary"
                  style={borderStyle}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-xs text-tertiary mt-2 font-mono">
                      {idx + 1}.
                    </span>
                    <div className="flex-1 space-y-1.5">
                      <input
                        type="text"
                        value={step.title}
                        onChange={(e) =>
                          setSteps(updateAt(steps, idx, { title: e.target.value }))
                        }
                        placeholder={
                          lang === "ru"
                            ? "title: Получение задачи от заказчика"
                            : "title: Recepción de la tarea del cliente"
                        }
                        className={inputCls}
                        style={borderStyle}
                      />
                      <textarea
                        value={step.body}
                        onChange={(e) =>
                          setSteps(updateAt(steps, idx, { body: e.target.value }))
                        }
                        rows={2}
                        placeholder={
                          lang === "ru"
                            ? "body: Заказчик направляет запрос на анализ через Jira..."
                            : "body: El cliente envía la solicitud vía Jira..."
                        }
                        className={textareaCls}
                        style={borderStyle}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => setSteps(removeAt(steps, idx))}
                      className="p-1 rounded text-tertiary hover:text-danger hover:bg-secondary mt-0.5"
                      title="Удалить шаг"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ────── 5. Grounds (список строк) ────── */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className={labelCls + " mb-0"}>
                Основания дистанционности (раздел 4) — {grounds.length} шт.
              </label>
              <button
                type="button"
                onClick={() => setGrounds([...grounds, ""])}
                className="text-xs flex items-center gap-1 px-2 py-1 rounded hover:bg-secondary text-tertiary hover:text-primary"
              >
                <Plus className="w-3 h-3" />
                Добавить
              </button>
            </div>
            <div className="space-y-2">
              {grounds.length === 0 && (
                <div className="text-xs text-tertiary italic px-2 py-3 text-center border border-dashed rounded" style={borderStyle}>
                  Нет оснований. Рекомендуется 2-3 основания.
                </div>
              )}
              {grounds.map((ground, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="text-xs text-tertiary mt-2">•</span>
                  <textarea
                    value={ground}
                    onChange={(e) =>
                      setGrounds(
                        grounds.map((g, i) => (i === idx ? e.target.value : g))
                      )
                    }
                    rows={2}
                    placeholder={
                      lang === "ru"
                        ? "Все данные хранятся в облачных хранилищах и доступны через защищённое VPN-соединение..."
                        : "Todos los datos se almacenan en cloud y son accesibles vía VPN..."
                    }
                    className={textareaCls + " flex-1"}
                    style={borderStyle}
                  />
                  <button
                    type="button"
                    onClick={() => setGrounds(removeAt(grounds, idx))}
                    className="p-1 rounded text-tertiary hover:text-danger hover:bg-secondary mt-0.5"
                    title="Удалить основание"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* ────── 6. Contract clause ────── */}
          <div>
            <label className={labelCls}>
              Пункт договора о дистанционности
            </label>
            <textarea
              value={contractClause}
              onChange={(e) => setContractClause(e.target.value)}
              rows={3}
              placeholder={
                lang === "ru"
                  ? "Услуги по сбору, обработке и визуализации данных оказываются исключительно дистанционно..."
                  : "Los servicios se prestan exclusivamente a distancia mediante medios electrónicos..."
              }
              className={textareaCls}
              style={borderStyle}
            />
            <p className="text-xs text-tertiary mt-1">
              Цитируется в §4 заключения как доказательство дистанционности из договора
            </p>
          </div>

          <div
            className="mt-3 text-xs text-tertiary p-2 rounded bg-secondary"
            style={{ background: "var(--color-bg-tertiary, transparent)" }}
          >
            💡 Контент попадает в документ <span className="font-mono">17_Техническое_заключение.docx</span>.
            Заполни обе вкладки (RU и ES) — RU попадает на первую страницу,
            ES на вторую (для подачи в испанский консулат).
          </div>
        </div>
      )}
    </div>
  );
}
