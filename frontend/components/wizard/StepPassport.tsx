"use client";

import { TextInput, StepHeader, Callout } from "@/components/ui/Form";
import { ApplicantData } from "@/lib/api";

interface Props {
  data: ApplicantData;
  onChange: (next: Partial<ApplicantData>) => void;
}

export function StepPassport({ data, onChange }: Props) {
  return (
    <div>
      <StepHeader
        title="Паспортные данные"
        subtitle="Загранпаспорт с которым будете подавать заявку в Испанию."
      />

      <div className="space-y-5">
        <Callout type="info">
          Паспорт должен быть действителен ещё минимум 1 год от даты подачи.
        </Callout>

        <TextInput
          label="Номер загранпаспорта"
          required
          value={data.passport_number || ""}
          onChange={(e) =>
            onChange({ passport_number: e.target.value.toUpperCase() })
          }
          placeholder="C01366076"
          hint="Только цифры и буквы (без пробелов)"
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <TextInput
            type="date"
            label="Дата выдачи"
            value={data.passport_issue_date || ""}
            onChange={(e) => onChange({ passport_issue_date: e.target.value })}
          />
          <TextInput
            label="Кем выдан"
            value={data.passport_issuer || ""}
            onChange={(e) => onChange({ passport_issuer: e.target.value })}
            placeholder="МИД РФ / МИД Азербайджана"
          />
        </div>
      </div>
    </div>
  );
}