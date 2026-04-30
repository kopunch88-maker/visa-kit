"use client";

import { StepHeader, FileDropzone, Callout } from "@/components/ui/Form";

export function StepDocuments() {
  return (
    <div>
      <StepHeader
        title="Документы"
        subtitle="Сканы документов которые нужно приложить к заявке."
      />

      <div className="space-y-5">
        <Callout type="warning">
          Загрузка файлов через интерфейс пока в разработке. Сейчас вышлите
          сканы менеджеру по почте — он приложит их к вашей заявке вручную.
        </Callout>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
            Паспорт
          </h3>
          <div className="space-y-3">
            <FileDropzone
              label="Скан главной страницы паспорта"
              hint="Цветной скан, JPG / PNG / PDF"
            />
            <FileDropzone
              label="Скан страницы с штампом последнего въезда"
              hint="Если есть текущая шенгенская виза"
            />
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
            Образование
          </h3>
          <FileDropzone
            label="Сканы дипломов"
            hint="Все дипломы и приложения. Желательно с апостилем"
          />
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
            Прочее
          </h3>
          <div className="space-y-3">
            <FileDropzone
              label="Справка о несудимости с апостилем"
              hint="Не старше 3 месяцев на дату подачи"
            />
            <FileDropzone
              label="Фото 3.5 × 4.5 см на белом фоне"
              hint="Формат JPG, цветное"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
