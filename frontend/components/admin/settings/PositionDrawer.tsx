"use client";

import { useEffect, useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import {
  PositionResponse,
  CompanyResponse,
  getPosition,
  createPosition,
  updatePosition,
} from "@/lib/api";

interface Props {
  positionId: number | null;
  companies: CompanyResponse[];
  onClose: () => void;
  onSaved: () => void;
}

export function PositionDrawer({ positionId, companies, onClose, onSaved }: Props) {
  const isNew = positionId === null;
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [companyId, setCompanyId] = useState<number | "">("");
  const [titleRu, setTitleRu] = useState("");
  const [titleEs, setTitleEs] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [dutiesText, setDutiesText] = useState(""); // в текстовом виде по строке
  const [tagsText, setTagsText] = useState(""); // через запятую
  const [profileDescription, setProfileDescription] = useState("");

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    if (isNew) return;
    (async () => {
      try {
        const data = await getPosition(positionId!);
        setCompanyId(data.company_id);
        setTitleRu(data.title_ru);
        setTitleEs(data.title_es || "");
        setSalary(data.salary_rub_default || "");
        setDutiesText((data.duties || []).join("\n"));
        setTagsText((data.tags || []).join(", "));
        setProfileDescription(data.profile_description || "");
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [positionId, isNew]);

  async function handleSave() {
    setError(null);
    if (!companyId || !titleRu || !titleEs || !salary) {
      setError("Заполните: Компания, Название (рус и исп), Зарплата");
      return;
    }

    // Парсим duties и tags
    const duties = dutiesText.split("\n").map((s) => s.trim()).filter(Boolean);
    const tags = tagsText.split(",").map((s) => s.trim()).filter(Boolean);

    setSaving(true);
    try {
      const payload = {
        company_id: companyId as number,
        title_ru: titleRu,
        title_es: titleEs,
        salary_rub_default: salary as number,
        duties,
        tags,
        profile_description: profileDescription,
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
      <div className="fixed right-0 top-0 h-screen w-full sm:w-[600px] bg-primary z-40 shadow-2xl overflow-y-auto"
        style={{ borderLeft: "0.5px solid var(--color-border-tertiary)" }}>
        <div className="sticky top-0 bg-primary border-b px-5 py-4 flex items-center justify-between z-10"
          style={{ borderColor: "var(--color-border-tertiary)", borderBottomWidth: 0.5 }}>
          <h2 className="text-lg font-semibold text-primary">
            {isNew ? "Новая должность" : `Должность #${positionId}`}
          </h2>
          <button onClick={onClose} className="p-1 rounded-md text-tertiary hover:text-primary hover:bg-secondary">
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
          </div>
        ) : (
          <>
            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Компания <span className="text-danger">*</span>
                </label>
                <select value={companyId}
                  onChange={(e) => setCompanyId(e.target.value ? parseInt(e.target.value, 10) : "")}
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}>
                  <option value="">— выберите —</option>
                  {companies.filter((c) => c.is_active).map((c) => (
                    <option key={c.id} value={c.id}>{c.short_name}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">
                    Название (рус) <span className="text-danger">*</span>
                  </label>
                  <input type="text" value={titleRu} onChange={(e) => setTitleRu(e.target.value)}
                    placeholder="инженер-геодезист (камеральщик)"
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-secondary mb-1">
                    Название (исп) <span className="text-danger">*</span>
                  </label>
                  <input type="text" value={titleEs} onChange={(e) => setTitleEs(e.target.value)}
                    placeholder="ingeniero topógrafo (gabinete)"
                    className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                    style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Стандартная зарплата ₽/мес <span className="text-danger">*</span>
                </label>
                <input type="number" value={salary}
                  onChange={(e) => setSalary(e.target.value ? Number(e.target.value) : "")}
                  placeholder="300000"
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Обязанности (по одной на строку)
                </label>
                <textarea value={dutiesText} onChange={(e) => setDutiesText(e.target.value)}
                  rows={6}
                  placeholder={"Выполнение топографо-геодезических работ\nКамеральная обработка результатов\nСоздание и обновление топографических планов"}
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary resize-y font-mono"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
                <p className="text-xs text-tertiary mt-1">
                  Эти пункты попадут в договор и акты. Сейчас: {dutiesText.split("\n").filter((s) => s.trim()).length} шт.
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Теги для LLM-матчинга (через запятую)
                </label>
                <input type="text" value={tagsText} onChange={(e) => setTagsText(e.target.value)}
                  placeholder="геодезия, топография, автокад, инженерное образование"
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
                <p className="text-xs text-tertiary mt-1">
                  Помогают Claude рекомендовать эту должность подходящим кандидатам
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-secondary mb-1">
                  Описание для LLM (как выглядит идеальный кандидат)
                </label>
                <textarea value={profileDescription}
                  onChange={(e) => setProfileDescription(e.target.value)}
                  rows={4}
                  placeholder="Инженерные специальности с акцентом на геодезию и топографию. Нужен релевантный диплом или 5+ лет опыта."
                  className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary resize-y"
                  style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }} />
              </div>

              {error && (
                <div className="bg-danger text-danger text-sm p-3 rounded-md flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>{error}</div>
                </div>
              )}
            </div>

            <div className="sticky bottom-0 bg-primary border-t px-5 py-3 flex justify-end gap-2"
              style={{ borderColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}>
              <button onClick={onClose}
                className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary"
                style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}>
                Отмена
              </button>
              <button onClick={handleSave} disabled={saving}
                className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 flex items-center gap-2"
                style={{ background: "var(--color-accent)" }}>
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Сохранить"}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}
