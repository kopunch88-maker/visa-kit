"use client";

import { useEffect, useState, useMemo } from "react";
import { X, Loader2, AlertCircle, Sparkles } from "lucide-react";
import {
  PositionResponse,
  CompanyResponse,
  getPosition,
  createPosition,
  updatePosition,
  // Pack 45.0 — LLM-генерация русских полей
  generatePositionRussian,
  // Pack 50.7-B — LLM-генерация цели командировки
  generateBusinessTripPurpose,
} from "@/lib/api";
// Pack 41.0 — Tech Opinion editing
import {
  TechOpinionSection,
  TechOpinionState,
  EMPTY_TECH_OPINION,
} from "./TechOpinionSection";

// Pack 20.1: метки уровней
const LEVEL_OPTIONS: { value: number; label: string; description: string }[] = [
  { value: 1, label: "Junior", description: "Начинающий специалист, до 1 года опыта" },
  { value: 2, label: "Middle", description: "Самостоятельный специалист, 1+ год опыта" },
  { value: 3, label: "Senior", description: "Эксперт, наставник, 5+ лет опыта" },
  { value: 4, label: "Lead", description: "Руководитель направления / команды" },
];

interface SpecialtyOption {
  id: number;
  code: string;
  name: string;
}

interface Props {
  positionId: number | null;
  companies: CompanyResponse[]; // legacy, не используется в Pack 20.1, но оставлен для сигнатуры
  // Pack 20.1: уже загруженные Position'ы из родителя — для извлечения списка специальностей
  allPositions?: PositionResponse[];
  onClose: () => void;
  onSaved: () => void;
}

export function PositionDrawer({ positionId, allPositions = [], onClose, onSaved }: Props) {
  const isNew = positionId === null;
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pack 20.1: новые поля вместо company_id
  const [primarySpecialtyId, setPrimarySpecialtyId] = useState<number | "">("");
  const [level, setLevel] = useState<number | "">("");

  const [titleRu, setTitleRu] = useState("");
  const [titleRuGenitive, setTitleRuGenitive] = useState("");
  const [titleEs, setTitleEs] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [dutiesText, setDutiesText] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [profileDescription, setProfileDescription] = useState("");
  // Pack 41.0 — Tech Opinion state (12 полей в одном объекте)
  const [techOpinion, setTechOpinion] = useState<TechOpinionState>(EMPTY_TECH_OPINION);
  // Pack 50.7-D2 — цель командировки для Приказа Т-9 (найм)
  const [businessTripPurpose, setBusinessTripPurpose] = useState("");
  const [generatingBusinessTripPurpose, setGeneratingBusinessTripPurpose] = useState(false);

  // Pack 20.1: извлекаем уникальные specialty из уже загруженных Position'ов
  const specialtyOptions = useMemo<SpecialtyOption[]>(() => {
    const seen = new Map<number, SpecialtyOption>();
    for (const p of allPositions) {
      const sid = (p as any).primary_specialty_id;
      const code = (p as any).specialty_code;
      const name = (p as any).specialty_name;
      if (sid && code && name && !seen.has(sid)) {
        seen.set(sid, { id: sid, code, name });
      }
    }
    return Array.from(seen.values()).sort((a, b) => a.code.localeCompare(b.code));
  }, [allPositions]);

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    if (isNew) return;
    (async () => {
      try {
        const data = await getPosition(positionId!);
        setPrimarySpecialtyId((data as any).primary_specialty_id ?? "");
        setLevel((data as any).level ?? "");
        setTitleRu(data.title_ru);
        setTitleRuGenitive((data as any).title_ru_genitive ?? "");
        setTitleEs(data.title_es || "");
        setSalary(data.salary_rub_default || "");
        setDutiesText((data.duties || []).join("\n"));
        setTagsText((data.tags || []).join(", "));
        setProfileDescription(data.profile_description || "");
        // Pack 41.0 — загружаем tech_opinion (поля могут отсутствовать)
        const d: any = data;
        setTechOpinion({
          international_analog_ru: d.international_analog_ru || "",
          international_analog_es: d.international_analog_es || "",
          description_ru: d.tech_opinion_description_ru || "",
          description_es: d.tech_opinion_description_es || "",
          tools_ru: d.tech_opinion_tools_ru || [],
          tools_es: d.tech_opinion_tools_es || [],
          steps_ru: d.tech_opinion_steps_ru || [],
          steps_es: d.tech_opinion_steps_es || [],
          grounds_ru: d.tech_opinion_grounds_ru || [],
          grounds_es: d.tech_opinion_grounds_es || [],
          contract_clause_ru: d.tech_opinion_contract_clause_ru || "",
          contract_clause_es: d.tech_opinion_contract_clause_es || "",
        });
        // Pack 50.7-D2 — цель командировки
        setBusinessTripPurpose(d.business_trip_purpose || "");
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [positionId, isNew]);

  // ====== Pack 45.0: LLM-генерация русских полей ======
  const [generatingAll, setGeneratingAll] = useState(false);
  const canGenerateAll =
    titleRu.trim().length > 0 &&
    titleEs.trim().length > 0 &&
    primarySpecialtyId !== "" &&
    level !== "" &&
    !generatingAll;

  async function handleGenerateAll() {
    if (!canGenerateAll) return;

    // Проверка непустоты RU-полей
    const hasFilledRu =
      dutiesText.trim().length > 0 ||
      tagsText.trim().length > 0 ||
      profileDescription.trim().length > 0 ||
      techOpinion.description_ru.trim().length > 0 ||
      techOpinion.tools_ru.length > 0 ||
      techOpinion.steps_ru.length > 0 ||
      techOpinion.grounds_ru.length > 0 ||
      techOpinion.contract_clause_ru.trim().length > 0 ||
      techOpinion.international_analog_ru.trim().length > 0;

    if (hasFilledRu) {
      const ok = window.confirm(
        "Все русские поля (обязанности, теги, описание, техническое заключение) будут перезаписаны генерацией из LLM. Продолжить?"
      );
      if (!ok) return;
    }

    setError(null);
    setGeneratingAll(true);
    try {
      const result = await generatePositionRussian({
        title_ru: titleRu,
        title_es: titleEs,
        primary_specialty_id: primarySpecialtyId as number,
        level: level as number,
        title_ru_genitive: titleRuGenitive || null,
        profile_description_existing: profileDescription || null,
        salary_rub_default: (salary as number) || null,
      });
      // Заполняем верхние поля
      setDutiesText(result.duties.join("\n"));
      setTagsText(result.tags.join(", "));
      setProfileDescription(result.profile_description);
      // Заполняем tech_opinion RU-поля (ES не трогаем — для них отдельная кнопка)
      setTechOpinion((prev) => ({
        ...prev,
        international_analog_ru: result.international_analog_ru,
        description_ru: result.tech_opinion_description_ru,
        tools_ru: result.tech_opinion_tools_ru,
        steps_ru: result.tech_opinion_steps_ru,
        grounds_ru: result.tech_opinion_grounds_ru,
        contract_clause_ru: result.tech_opinion_contract_clause_ru,
      }));
    } catch (e) {
      setError("Не удалось сгенерировать: " + ((e as Error).message || "ошибка LLM"));
    } finally {
      setGeneratingAll(false);
    }
  }

  // ====== Pack 50.7-D2: LLM-генерация цели командировки ======
  async function handleGenerateBusinessTripPurpose() {
    if (isNew) {
      setError("Сначала сохрани должность — нужен ID для генерации цели командировки");
      return;
    }
    if (!titleRu.trim()) {
      setError("Заполните русское название должности перед генерацией");
      return;
    }
    if (businessTripPurpose.trim().length > 0) {
      const ok = window.confirm(
        "Текущая цель командировки будет перезаписана генерацией из LLM. Продолжить?"
      );
      if (!ok) return;
    }
    setError(null);
    setGeneratingBusinessTripPurpose(true);
    try {
      const result = await generateBusinessTripPurpose(positionId!);
      setBusinessTripPurpose(result.business_trip_purpose);
    } catch (e) {
      setError("Не удалось сгенерировать цель командировки: " + ((e as Error).message || "ошибка LLM"));
    } finally {
      setGeneratingBusinessTripPurpose(false);
    }
  }

  async function handleSave() {
    setError(null);
    if (!titleRu || !titleEs || !salary) {
      setError("Заполните: Название (рус и исп), Зарплата");
      return;
    }

    const duties = dutiesText.split("\n").map((s) => s.trim()).filter(Boolean);
    const tags = tagsText.split(",").map((s) => s.trim()).filter(Boolean);

    setSaving(true);
    try {
      const payload: any = {
        title_ru: titleRu,
        title_ru_genitive: titleRuGenitive || null,
        title_es: titleEs,
        salary_rub_default: salary as number,
        primary_specialty_id: primarySpecialtyId || null,
        level: level || null,
        duties,
        tags,
        profile_description: profileDescription,
        // Pack 41.0 — tech_opinion поля (12 шт.)
        international_analog_ru: techOpinion.international_analog_ru || null,
        international_analog_es: techOpinion.international_analog_es || null,
        tech_opinion_description_ru: techOpinion.description_ru || null,
        tech_opinion_description_es: techOpinion.description_es || null,
        tech_opinion_tools_ru: techOpinion.tools_ru.length ? techOpinion.tools_ru : null,
        tech_opinion_tools_es: techOpinion.tools_es.length ? techOpinion.tools_es : null,
        tech_opinion_steps_ru: techOpinion.steps_ru.length ? techOpinion.steps_ru : null,
        tech_opinion_steps_es: techOpinion.steps_es.length ? techOpinion.steps_es : null,
        tech_opinion_grounds_ru: techOpinion.grounds_ru.length ? techOpinion.grounds_ru : null,
        tech_opinion_grounds_es: techOpinion.grounds_es.length ? techOpinion.grounds_es : null,
        tech_opinion_contract_clause_ru: techOpinion.contract_clause_ru || null,
        tech_opinion_contract_clause_es: techOpinion.contract_clause_es || null,
        // Pack 50.7-D2 — цель командировки для Приказа Т-9
        business_trip_purpose: businessTripPurpose.trim() || null,
      };
      if (isNew) {
        await createPosition(payload);
      } else {
        await updatePosition(positionId!, payload);
      }
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-30" onClick={onClose} />
      <div
        className="fixed right-0 top-0 h-screen w-full sm:w-[600px] bg-primary z-40 shadow-2xl overflow-y-auto"
        style={{ borderLeft: "0.5px solid var(--color-border-tertiary)" }}
      >
        <div
          className="sticky top-0 bg-primary border-b px-5 py-4 flex items-center justify-between z-10"
          style={{ borderColor: "var(--color-border-tertiary)", borderBottomWidth: 0.5 }}
        >
          <h2 className="text-lg font-semibold text-primary">
            {isNew ? "Новая должность" : `Должность #${positionId}`}
          </h2>
          <div className="flex items-center gap-2">
            {/* Pack 45.0 — кнопка генерации всех русских полей через LLM */}
            <button
              type="button"
              onClick={handleGenerateAll}
              disabled={!canGenerateAll}
              title={
                !titleRu.trim() || !titleEs.trim() || primarySpecialtyId === "" || level === ""
                  ? "Сначала заполни: Специальность, Уровень, Название (рус), Название (исп)"
                  : "Сгенерировать все русские поля через LLM (~30-50 сек): обязанности, теги, описание, тех. заключение"
              }
              className="text-xs flex items-center gap-1 px-2.5 py-1.5 rounded text-primary border hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            >
              {generatingAll ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Генерация...
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  Сгенерировать всё
                </>
              )}
            </button>
            <button
              onClick={onClose}
              className="p-1 rounded-md text-tertiary hover:text-primary hover:bg-secondary"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
          </div>
        ) : (
          <>
            <div className="px-5 py-4 space-y-4">
              {/* Pack 20.1: Специальность + Уровень — две колонки */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">
                    Специальность (ОКСО)
                  </label>
                  <select
                    value={primarySpecialtyId}
                    onChange={(e) =>
                      setPrimarySpecialtyId(e.target.value ? parseInt(e.target.value, 10) : "")
                    }
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  >
                    <option value="">— без специальности —</option>
                    {specialtyOptions.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.code} {s.name}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-tertiary mt-1">
                    Используется для подбора work_history (Pack 20.3)
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">Уровень</label>
                  <select
                    value={level}
                    onChange={(e) =>
                      setLevel(e.target.value ? parseInt(e.target.value, 10) : "")
                    }
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  >
                    <option value="">— не указан —</option>
                    {LEVEL_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        L{opt.value} {opt.label}
                      </option>
                    ))}
                  </select>
                  {level && typeof level === "number" && (
                    <p className="text-xs text-tertiary mt-1">
                      {LEVEL_OPTIONS.find((o) => o.value === level)?.description}
                    </p>
                  )}
                </div>
              </div>

              {/* Названия — 2 колонки */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">
                    Название (рус) <span className="text-danger">*</span>
                  </label>
                  <input
                    type="text"
                    value={titleRu}
                    onChange={(e) => setTitleRu(e.target.value)}
                    placeholder="Инженер-проектировщик"
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">
                    Название (исп) <span className="text-danger">*</span>
                  </label>
                  <input
                    type="text"
                    value={titleEs}
                    onChange={(e) => setTitleEs(e.target.value)}
                    placeholder="ingeniero proyectista"
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  />
                </div>
              </div>

              {/* Pack 20.1: title_ru_genitive — отдельным полем */}
              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Название в родительном падеже (рус)
                </label>
                <input
                  type="text"
                  value={titleRuGenitive}
                  onChange={(e) => setTitleRuGenitive(e.target.value)}
                  placeholder="инженера-проектировщика"
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                />
                <p className="text-xs text-tertiary mt-1">
                  Используется в договорах и актах: «...на должность инженера-проектировщика»
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Стандартная зарплата ₽/мес <span className="text-danger">*</span>
                </label>
                <input
                  type="number"
                  value={salary}
                  onChange={(e) => setSalary(e.target.value ? Number(e.target.value) : "")}
                  placeholder="240000"
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                />
                <p className="text-xs text-tertiary mt-1">
                  Среднерыночная для уровня; реальная в заявке указывается отдельно
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Обязанности (по одной на строку)
                </label>
                <textarea
                  value={dutiesText}
                  onChange={(e) => setDutiesText(e.target.value)}
                  rows={10}
                  placeholder={
                    "Разработка отдельных листов и узлов рабочей документации в AutoCAD\n" +
                    "Моделирование строительных конструкций в Autodesk Revit\n" +
                    "Сбор и систематизация исходных данных для проектирования"
                  }
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary resize-y font-mono"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                />
                <p className="text-xs text-tertiary mt-1">
                  Эти пункты попадут в договор, акты и резюме. Сейчас:{" "}
                  {dutiesText.split("\n").filter((s) => s.trim()).length} шт.
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Теги для LLM-матчинга (через запятую)
                </label>
                <input
                  type="text"
                  value={tagsText}
                  onChange={(e) => setTagsText(e.target.value)}
                  placeholder="проектирование, AutoCAD, Revit, BIM, ПГС"
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Описание для LLM (как выглядит идеальный кандидат)
                </label>
                <textarea
                  value={profileDescription}
                  onChange={(e) => setProfileDescription(e.target.value)}
                  rows={4}
                  placeholder="Junior-инженер-проектировщик в строительной/проектной организации. Работает под руководством ведущего/главного специалиста, выполняет разделы рабочей документации в AutoCAD/Revit."
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary resize-y"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                />
              </div>

              {/* Pack 41.0 — Техническое заключение */}
              {/* Pack 43.0 — positionId передан для кнопки "Сгенерировать испанский" */}
              <TechOpinionSection
                value={techOpinion}
                onChange={setTechOpinion}
                positionId={positionId}
              />

              {/* Pack 50.7-D2 — Цель командировки для Приказа Т-9 (найм) */}
              <div className="border-t pt-4" style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-medium text-secondary">
                    💼 Цель командировки <span className="text-tertiary font-normal">(для Приказа Т-9 при найме)</span>
                  </label>
                  <button
                    type="button"
                    onClick={handleGenerateBusinessTripPurpose}
                    disabled={isNew || generatingBusinessTripPurpose || !titleRu.trim()}
                    title={
                      isNew
                        ? "Сначала сохрани должность"
                        : !titleRu.trim()
                        ? "Заполни русское название"
                        : "Сгенерировать через LLM по сохранённым полям"
                    }
                    className="px-2 py-1 text-xs rounded-md border flex items-center gap-1 hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                  >
                    {generatingBusinessTripPurpose ? (
                      <>
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Генерация...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3 h-3" />
                        Сгенерировать
                      </>
                    )}
                  </button>
                </div>
                <textarea
                  value={businessTripPurpose}
                  onChange={(e) => setBusinessTripPurpose(e.target.value)}
                  rows={3}
                  placeholder="напр. «мониторинга изменений в законодательстве и нормативах в ЕС, особенностей внешнеторговой деятельности с контрагентами»"
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary resize-y"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
                />
                <p className="text-[10px] text-tertiary mt-1">
                  Текст в родительном падеже (после «с целью...»). Подставляется в Т-9 при найме.
                  Можно переопределить для конкретной заявки в поле «Цель командировки (override)».
                </p>
              </div>

              {error && (
                <div className="bg-danger text-danger text-sm p-3 rounded-md flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>{error}</div>
                </div>
              )}
            </div>

            <div
              className="sticky bottom-0 bg-primary border-t px-5 py-3 flex justify-end gap-2"
              style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}
            >
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary"
                style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
              >
                Отмена
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 flex items-center gap-2"
                style={{ background: "var(--color-accent)" }}
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Сохранить"}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}
