"use client";

import { Plus, Trash2 } from "lucide-react";
import { TextInput, StepHeader, SecondaryButton } from "@/components/ui/Form";
import { ApplicantData } from "@/lib/api";

interface Props {
  data: ApplicantData;
  onChange: (next: Partial<ApplicantData>) => void;
}

export function StepEducation({ data, onChange }: Props) {
  const education = data.education || [];

  function updateItem(idx: number, field: string, value: string | number) {
    const next = [...education];
    next[idx] = { ...next[idx], [field]: value };
    onChange({ education: next });
  }

  function addItem() {
    onChange({
      education: [
        ...education,
        { institution: "", graduation_year: undefined, degree: "", specialty: "" },
      ],
    });
  }

  function removeItem(idx: number) {
    onChange({ education: education.filter((_, i) => i !== idx) });
  }

  return (
    <div>
      <StepHeader
        title="Образование"
        subtitle="Учебные заведения, начиная с самого недавнего."
      />

      <div className="space-y-4">
        {education.length === 0 && (
          <p className="text-sm text-tertiary italic">
            Пока ни одного учебного заведения. Нажмите «Добавить».
          </p>
        )}

        {education.map((edu, idx) => (
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
                Учебное заведение #{idx + 1}
              </h3>
              <button
                onClick={() => removeItem(idx)}
                className="p-1.5 rounded text-tertiary hover:bg-tertiary transition-colors"
                title="Удалить"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>

            <TextInput
              label="Название учебного заведения"
              value={edu.institution || ""}
              onChange={(e) => updateItem(idx, "institution", e.target.value)}
              placeholder="Ростовский государственный строительный университет"
            />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <TextInput
                type="number"
                label="Год окончания"
                value={edu.graduation_year || ""}
                onChange={(e) =>
                  updateItem(idx, "graduation_year", parseInt(e.target.value) || 0)
                }
                placeholder="2010"
                min="1950"
                max="2030"
              />
              <TextInput
                label="Степень"
                value={edu.degree || ""}
                onChange={(e) => updateItem(idx, "degree", e.target.value)}
                placeholder="Инженер / Бакалавр"
              />
              <TextInput
                label="Специальность"
                value={edu.specialty || ""}
                onChange={(e) => updateItem(idx, "specialty", e.target.value)}
                placeholder="Прикладная геодезия"
              />
            </div>
          </div>
        ))}

        <SecondaryButton onClick={addItem} type="button">
          <Plus className="w-4 h-4 inline mr-1" />
          Добавить учебное заведение
        </SecondaryButton>
      </div>
    </div>
  );
}
