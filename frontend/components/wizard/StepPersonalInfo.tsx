
"use client";

import { useEffect, useRef } from "react";
import { TextInput, SelectInput, StepHeader } from "@/components/ui/Form";
import { ApplicantData, NATIONALITY_OPTIONS, COUNTRY_OPTIONS } from "@/lib/api";

interface Props {
  data: ApplicantData;
  onChange: (next: Partial<ApplicantData>) => void;
}

// === Транслитерация по ГОСТ Р 52535.1-2006 (загранпаспорт РФ с 2014) ===
const TRANSLIT_MAP: Record<string, string> = {
  а: "A", б: "B", в: "V", г: "G", д: "D", е: "E", ё: "E",
  ж: "ZH", з: "Z", и: "I", й: "I", к: "K", л: "L", м: "M",
  н: "N", о: "O", п: "P", р: "R", с: "S", т: "T", у: "U",
  ф: "F", х: "KH", ц: "TS", ч: "CH", ш: "SH", щ: "SHCH",
  ъ: "IE", ы: "Y", ь: "", э: "E", ю: "IU", я: "IA",
};

function transliterate(input: string): string {
  if (!input) return "";
  let result = "";
  for (const char of input.toLowerCase()) {
    if (TRANSLIT_MAP[char] !== undefined) {
      result += TRANSLIT_MAP[char];
    } else if (/[a-zA-Z0-9\s\-']/.test(char)) {
      result += char.toUpperCase();
    }
    // Игнорируем прочие символы (запятые, скобки и т.д.)
  }
  return result.toUpperCase();
}

export function StepPersonalInfo({ data, onChange }: Props) {
  // Запоминаем прошлые автотранслитерации, чтобы понимать —
  // редактировал клиент латинское поле или нет
  const lastAutoFill = useRef({
    last: "",
    first: "",
  });

  // Автозаполнение фамилии при изменении русского варианта
  useEffect(() => {
    const ru = data.last_name_native || "";
    const auto = transliterate(ru);
    const current = data.last_name_latin || "";
    // Заполняем автоматически если латинское поле пустое
    // или совпадает с прошлой автотранслитерацией (значит клиент не правил)
    if (!current || current === lastAutoFill.current.last) {
      if (auto !== current) {
        onChange({ last_name_latin: auto });
        lastAutoFill.current.last = auto;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.last_name_native]);

  useEffect(() => {
    const ru = data.first_name_native || "";
    const auto = transliterate(ru);
    const current = data.first_name_latin || "";
    if (!current || current === lastAutoFill.current.first) {
      if (auto !== current) {
        onChange({ first_name_latin: auto });
        lastAutoFill.current.first = auto;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.first_name_native]);

  return (
    <div>
      <StepHeader
        title="Личные данные"
        subtitle="Введите ФИО на русском — латинский вариант появится автоматически. Сверьте с вашим загранпаспортом."
      />

      <div className="space-y-5">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
            На русском
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <TextInput
              label="Фамилия"
              required
              value={data.last_name_native || ""}
              onChange={(e) => onChange({ last_name_native: e.target.value })}
              placeholder="Иванов"
            />
            <TextInput
              label="Имя"
              required
              value={data.first_name_native || ""}
              onChange={(e) => onChange({ first_name_native: e.target.value })}
              placeholder="Иван"
            />
            <TextInput
              label="Отчество"
              value={data.middle_name_native || ""}
              onChange={(e) => onChange({ middle_name_native: e.target.value })}
              placeholder="Иванович"
              hint="Если есть"
            />
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
            На латинице (как в загранпаспорте)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TextInput
              label="Last name (Surname)"
              required
              value={data.last_name_latin || ""}
              onChange={(e) => onChange({ last_name_latin: e.target.value.toUpperCase() })}
              placeholder="IVANOV"
              className="uppercase"
              hint="Сверьте с паспортом — иногда написание отличается"
            />
            <TextInput
              label="First name (Given name)"
              required
              value={data.first_name_latin || ""}
              onChange={(e) => onChange({ first_name_latin: e.target.value.toUpperCase() })}
              placeholder="IVAN"
              className="uppercase"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <TextInput
            type="date"
            label="Дата рождения"
            required
            value={data.birth_date || ""}
            onChange={(e) => onChange({ birth_date: e.target.value })}
          />
          <TextInput
            label="Место рождения (на латинице)"
            value={data.birth_place_latin || ""}
            onChange={(e) =>
              onChange({ birth_place_latin: e.target.value.toUpperCase() })
            }
            placeholder="MOSCOW"
            className="uppercase"
            hint="Город"
          />
          <SelectInput
            label="Страна рождения"
            value={data.birth_country || ""}
            onChange={(e) => onChange({ birth_country: e.target.value })}
            options={COUNTRY_OPTIONS}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SelectInput
            label="Гражданство"
            required
            value={data.nationality || ""}
            onChange={(e) => onChange({ nationality: e.target.value })}
            options={NATIONALITY_OPTIONS}
          />
          <SelectInput
            label="Пол"
            required
            value={data.sex || ""}
            onChange={(e) => onChange({ sex: e.target.value })}
            options={[
              { value: "H", label: "Мужской" },
              { value: "M", label: "Женский" },
            ]}
          />
          <SelectInput
            label="Семейное положение"
            value={data.marital_status || ""}
            onChange={(e) => onChange({ marital_status: e.target.value })}
            options={[
              { value: "S", label: "Не женат / не замужем" },
              { value: "C", label: "Женат / замужем" },
              { value: "D", label: "Разведён / разведена" },
              { value: "V", label: "Вдовец / вдова" },
            ]}
          />
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
            Родители
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TextInput
              label="Имя отца (на латинице)"
              value={data.father_name_latin || ""}
              onChange={(e) =>
                onChange({ father_name_latin: e.target.value.toUpperCase() })
              }
              placeholder="IVAN"
              className="uppercase"
              hint="Для испанской анкеты MI-T"
            />
            <TextInput
              label="Имя матери (на латинице)"
              value={data.mother_name_latin || ""}
              onChange={(e) =>
                onChange({ mother_name_latin: e.target.value.toUpperCase() })
              }
              placeholder="MARIA"
              className="uppercase"
              hint="Для испанской анкеты MI-T"
            />
          </div>
        </div>
      </div>
    </div>
  );
}


