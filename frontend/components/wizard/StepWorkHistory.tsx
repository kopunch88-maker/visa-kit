"use client";

import { Plus, Trash2, X } from "lucide-react";
import { TextInput, StepHeader, SecondaryButton } from "@/components/ui/Form";
import { ApplicantData } from "@/lib/api";

interface Props {
  data: ApplicantData;
  onChange: (next: Partial<ApplicantData>) => void;
}

export function StepWorkHistory({ data, onChange }: Props) {
  const workHistory = data.work_history || [];

  function updateJob(idx: number, field: string, value: string | string[]) {
    const next = [...workHistory];
    next[idx] = { ...next[idx], [field]: value };
    onChange({ work_history: next });
  }

  function addJob() {
    onChange({
      work_history: [
        ...workHistory,
        { period_start: "", period_end: "", company: "", position: "", duties: [] },
      ],
    });
  }

  function removeJob(idx: number) {
    onChange({ work_history: workHistory.filter((_, i) => i !== idx) });
  }

  function addDuty(jobIdx: number) {
    const next = [...workHistory];
    next[jobIdx] = { ...next[jobIdx], duties: [...(next[jobIdx].duties || []), ""] };
    onChange({ work_history: next });
  }

  function updateDuty(jobIdx: number, dutyIdx: number, value: string) {
    const next = [...workHistory];
    const duties = [...(next[jobIdx].duties || [])];
    duties[dutyIdx] = value;
    next[jobIdx] = { ...next[jobIdx], duties };
    onChange({ work_history: next });
  }

  function removeDuty(jobIdx: number, dutyIdx: number) {
    const next = [...workHistory];
    const duties = (next[jobIdx].duties || []).filter((_, i) => i !== dutyIdx);
    next[jobIdx] = { ...next[jobIdx], duties };
    onChange({ work_history: next });
  }

  return (
    <div>
      <StepHeader
        title="Опыт работы"
        subtitle="Места работы за последние ~10 лет, начиная с самого недавнего."
      />

      <div className="space-y-4">
        {workHistory.length === 0 && (
          <p className="text-sm text-tertiary italic">
            Пока ни одной записи. Нажмите «Добавить место работы».
          </p>
        )}

        {workHistory.map((job, idx) => (
          <div
            key={idx}
            className="rounded-lg p-4 space-y-3 border"
            style={{
              background: "var(--color-bg-secondary)",
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
          >
            <div className="flex justify-between items-start">
              <h3 className="text-sm font-semibold text-secondary">
                Место работы #{idx + 1}
              </h3>
              <button
                onClick={() => removeJob(idx)}
                className="p-1.5 rounded text-tertiary hover:bg-tertiary transition-colors"
                title="Удалить"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <TextInput
                label="Период с"
                value={job.period_start || ""}
                onChange={(e) => updateJob(idx, "period_start", e.target.value)}
                placeholder="Сентябрь 2025"
              />
              <TextInput
                label="Период по"
                value={job.period_end || ""}
                onChange={(e) => updateJob(idx, "period_end", e.target.value)}
                placeholder="по настоящее время"
              />
            </div>

            <TextInput
              label="Название компании"
              value={job.company || ""}
              onChange={(e) => updateJob(idx, "company", e.target.value)}
              placeholder="ООО «Строительная компания «СК10»"
            />

            <TextInput
              label="Должность"
              value={job.position || ""}
              onChange={(e) => updateJob(idx, "position", e.target.value)}
              placeholder="Инженер-геодезист (камеральщик)"
            />

            <div>
              <label className="block text-sm font-medium text-secondary mb-2">
                Обязанности
              </label>
              <div className="space-y-2">
                {(job.duties || []).map((duty, dutyIdx) => (
                  <div key={dutyIdx} className="flex gap-2">
                    <input
                      className="flex-1 px-3 py-2 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
                      style={{
                        borderColor: "var(--color-border-secondary)",
                        borderWidth: 0.5,
                      }}
                      value={duty}
                      onChange={(e) => updateDuty(idx, dutyIdx, e.target.value)}
                      placeholder="Например: Камеральная обработка результатов измерений"
                    />
                    <button
                      onClick={() => removeDuty(idx, dutyIdx)}
                      className="p-2 rounded text-tertiary hover:bg-tertiary transition-colors"
                      title="Удалить"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                <SecondaryButton onClick={() => addDuty(idx)} type="button">
                  <Plus className="w-4 h-4 inline mr-1" />
                  Добавить обязанность
                </SecondaryButton>
              </div>
            </div>
          </div>
        ))}

        <SecondaryButton onClick={addJob} type="button">
          <Plus className="w-4 h-4 inline mr-1" />
          Добавить место работы
        </SecondaryButton>

        <div
          className="border-t pt-5 mt-6"
          style={{ borderTopColor: "var(--color-border-tertiary)", borderTopWidth: 0.5 }}
        >
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
            Иностранные языки
          </h3>
          <TextInput
            label="Языки (через запятую)"
            value={(data.languages || []).join(", ")}
            onChange={(e) =>
              onChange({
                languages: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            placeholder="Русский — родной, Английский B1, Испанский A2"
            hint="Перечислите через запятую"
          />
        </div>
      </div>
    </div>
  );
}
