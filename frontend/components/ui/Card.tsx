"use client";

import { HTMLAttributes } from "react";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";

export function Card({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-slate-200 bg-white shadow-sm",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}


/**
 * Заглушка загрузки файла. Не работает (нет backend для file upload), но
 * визуально показывает клиенту что нужно будет приложить.
 *
 * Когда сделаем file upload — заменим эту заглушку на реальный uploader.
 */
export function FileUploadStub({
  label,
  hint,
}: {
  label: string;
  hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className="flex items-center justify-center w-full">
        <div
          className={cn(
            "flex flex-col items-center justify-center w-full h-28",
            "border-2 border-slate-200 border-dashed rounded-lg bg-slate-50",
            "cursor-not-allowed opacity-70",
          )}
          title="Загрузка файлов скоро будет доступна"
        >
          <Upload className="w-6 h-6 text-slate-400 mb-1" />
          <p className="text-xs text-slate-500">Загрузка скоро будет доступна</p>
          <p className="text-xs text-slate-400">Пока вышлите файл менеджеру</p>
        </div>
      </div>
      {hint && <p className="text-sm text-slate-500">{hint}</p>}
    </div>
  );
}
