"use client";

import { InputHTMLAttributes, SelectHTMLAttributes, forwardRef } from "react";

/**
 * Универсальный wrapper для полей формы — единый стиль для inputs/selects.
 * Цвета берутся из CSS-переменных (поддерживают тёмную тему).
 */

interface FieldProps {
  label?: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function Field({ label, hint, required, children, className = "" }: FieldProps) {
  return (
    <div className={`space-y-1.5 ${className}`}>
      {label && (
        <label className="block text-sm font-medium text-secondary">
          {label}
          {required && <span className="text-danger ml-1">*</span>}
        </label>
      )}
      {children}
      {hint && <p className="text-xs text-tertiary">{hint}</p>}
    </div>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  required?: boolean;
}

export const TextInput = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, required, className = "", ...props }, ref) => (
    <Field label={label} hint={hint} required={required}>
      <input
        ref={ref}
        className={`w-full px-3 py-2 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2 focus:ring-offset-0 transition-colors ${className}`}
        style={{
          borderColor: "var(--color-border-secondary)",
          borderWidth: 0.5,
        }}
        {...props}
      />
    </Field>
  ),
);
TextInput.displayName = "TextInput";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
  required?: boolean;
  options: Array<{ value: string; label: string }>;
  placeholder?: string;
}

export const SelectInput = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, hint, required, options, placeholder, className = "", ...props }, ref) => (
    <Field label={label} hint={hint} required={required}>
      <select
        ref={ref}
        className={`w-full px-3 py-2 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2 transition-colors ${className}`}
        style={{
          borderColor: "var(--color-border-secondary)",
          borderWidth: 0.5,
        }}
        {...props}
      >
        <option value="">{placeholder || "— выберите —"}</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </Field>
  ),
);
SelectInput.displayName = "SelectInput";


export function Callout({ children, type = "info" }: { children: React.ReactNode; type?: "info" | "warning" | "success" }) {
  const bgClass = type === "info" ? "bg-info" : type === "warning" ? "bg-warning" : "bg-success";
  const textClass = type === "info" ? "text-info" : type === "warning" ? "text-warning" : "text-success";
  return (
    <div className={`p-3 rounded-md text-sm ${bgClass} ${textClass}`}>
      {children}
    </div>
  );
}


export function StepHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-2xl font-semibold text-primary">{title}</h2>
      {subtitle && <p className="text-sm text-secondary mt-1">{subtitle}</p>}
    </div>
  );
}


/**
 * Заглушка загрузки файла. Не работает (нет backend для file upload), но
 * визуально показывает клиенту что нужно будет приложить.
 */
export function FileDropzone({ label, hint }: { label: string; hint?: string }) {
  return (
    <Field label={label} hint={hint}>
      <div
        className="rounded-md p-4 text-center cursor-not-allowed transition-colors"
        style={{
          borderWidth: 1,
          borderStyle: "dashed",
          borderColor: "var(--color-border-secondary)",
          background: "var(--color-bg-secondary)",
          opacity: 0.7,
        }}
        title="Загрузка файлов скоро будет доступна"
      >
        <div className="text-sm text-secondary">📎 Нажмите чтобы загрузить</div>
        <div className="text-xs text-tertiary mt-1">
          Загрузка файлов скоро будет доступна — пока вышлите менеджеру
        </div>
      </div>
    </Field>
  );
}


export function PrimaryButton({
  children,
  disabled,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className="px-4 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      style={{ background: "var(--color-accent)" }}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}


export function SecondaryButton({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className="px-4 py-2 rounded-md text-sm border bg-primary text-secondary hover:bg-secondary transition-colors"
      style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
      {...props}
    >
      {children}
    </button>
  );
}
