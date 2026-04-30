"use client";

import { TextInput, SelectInput, StepHeader } from "@/components/ui/Form";
import { ApplicantData, NATIONALITY_OPTIONS } from "@/lib/api";

interface Props {
  data: ApplicantData;
  onChange: (next: Partial<ApplicantData>) => void;
}

export function StepAddress({ data, onChange }: Props) {
  return (
    <div>
      <StepHeader
        title="Адрес и контакты"
        subtitle="Текущий адрес проживания и контактные данные."
      />

      <div className="space-y-5">
        <TextInput
          label="Адрес проживания"
          required
          value={data.home_address || ""}
          onChange={(e) => onChange({ home_address: e.target.value })}
          placeholder="352919, Краснодарский край, г. Армавир, ул. 11-я Линия, д. 31, кв. 2"
          hint="С индексом, городом и полным адресом"
        />

        <SelectInput
          label="Страна проживания"
          required
          value={data.home_country || ""}
          onChange={(e) => onChange({ home_country: e.target.value })}
          options={NATIONALITY_OPTIONS}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <TextInput
            type="email"
            label="Email"
            required
            value={data.email || ""}
            onChange={(e) => onChange({ email: e.target.value })}
            placeholder="ivanov@example.com"
            hint="На этот адрес отправим уведомления"
          />
          <TextInput
            type="tel"
            label="Телефон"
            required
            value={data.phone || ""}
            onChange={(e) => onChange({ phone: e.target.value })}
            placeholder="+34 627 901 730"
            hint="С кодом страны"
          />
        </div>
      </div>
    </div>
  );
}
