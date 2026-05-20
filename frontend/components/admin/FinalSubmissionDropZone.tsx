"use client";

import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { UploadCloud, Loader2, FileText } from "lucide-react";

interface Props {
  uploading: boolean;
  onUpload: (files: File[]) => void;
}

const SUPPORTED_EXTENSIONS = [
  ".pdf",
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".heic",
  ".heif",
  ".zip",
  ".docx",
];

export function FinalSubmissionDropZone({ uploading, onUpload }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDragEnter(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    if (!uploading) setDragOver(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    // Игнорируем dragleave когда уходим на дочерний элемент
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDragOver(false);
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (uploading) return;

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      onUpload(files);
    }
  }

  function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) onUpload(files);
    // Сброс инпута чтобы можно было выбрать тот же файл ещё раз
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      className="rounded-lg p-8 text-center transition-colors cursor-pointer"
      style={{
        background: dragOver
          ? "var(--color-bg-info)"
          : "var(--color-bg-primary)",
        border: `2px dashed ${
          dragOver ? "var(--color-accent)" : "var(--color-border-secondary)"
        }`,
      }}
      onClick={() => !uploading && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={SUPPORTED_EXTENSIONS.join(",")}
        onChange={handleFileSelect}
        className="hidden"
        disabled={uploading}
      />

      {uploading ? (
        <>
          <Loader2
            className="w-10 h-10 mx-auto mb-3 animate-spin"
            style={{ color: "var(--color-accent)" }}
          />
          <p
            className="text-sm font-medium"
            style={{ color: "var(--color-text-primary)" }}
          >
            Загрузка файлов...
          </p>
          <p
            className="text-xs mt-1"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            Дождитесь окончания, после загрузки AI определит категории документов
            в фоне (10-30 сек)
          </p>
        </>
      ) : (
        <>
          <UploadCloud
            className="w-10 h-10 mx-auto mb-3"
            style={{
              color: dragOver
                ? "var(--color-accent)"
                : "var(--color-text-tertiary)",
            }}
          />
          <p
            className="text-sm font-medium"
            style={{ color: "var(--color-text-primary)" }}
          >
            {dragOver
              ? "Отпустите файлы для загрузки"
              : "Перетащите файлы сюда или кликните для выбора"}
          </p>
          <p
            className="text-xs mt-1"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            PDF, JPG, PNG, WEBP, HEIC, DOCX, ZIP · до 200 МБ на файл · ZIP
            распаковывается автоматически
          </p>
          <div
            className="flex items-center justify-center gap-1 mt-2 text-xs"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            <FileText className="w-3 h-3" />
            Дубли (одинаковые файлы) пропускаются автоматически
          </div>
        </>
      )}
    </div>
  );
}
