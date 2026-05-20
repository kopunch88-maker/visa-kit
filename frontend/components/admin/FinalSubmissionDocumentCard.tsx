"use client";

import { useState, useRef } from "react";
import {
  FileText,
  Download,
  Trash2,
  RefreshCw,
  Edit3,
  Check,
  X,
  Loader2,
  Sparkles,
  User,
  Image as ImageIcon,
  FileArchive,
  AlertCircle,
} from "lucide-react";
import {
  FinalSubmissionDocument,
  FinalSubmissionDocCategory,
  FINAL_DOC_CATEGORY_LABELS,
} from "@/lib/api";

interface Props {
  doc: FinalSubmissionDocument;
  onDelete: (hard: boolean) => void;
  onReplace: (file: File, keepCategory: boolean) => void;
  onCategoryChange: (category: FinalSubmissionDocCategory) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(mime: string, filename: string) {
  if (mime.startsWith("image/")) return ImageIcon;
  if (mime === "application/zip" || filename.endsWith(".zip")) return FileArchive;
  return FileText;
}

export function FinalSubmissionDocumentCard({
  doc,
  onDelete,
  onReplace,
  onCategoryChange,
}: Props) {
  const [editingCategory, setEditingCategory] = useState(false);
  const [pendingCategory, setPendingCategory] = useState<FinalSubmissionDocCategory | null>(null);
  const [busy, setBusy] = useState(false);
  const replaceInputRef = useRef<HTMLInputElement>(null);

  const Icon = fileIcon(doc.mime_type, doc.original_filename);
  const isProcessing = doc.doc_category === null && doc.extraction_method === null;
  const categoryLabel = doc.doc_category
    ? FINAL_DOC_CATEGORY_LABELS[doc.doc_category]
    : null;

  async function saveCategory() {
    if (!pendingCategory) return;
    setBusy(true);
    try {
      await onCategoryChange(pendingCategory);
      setEditingCategory(false);
      setPendingCategory(null);
    } finally {
      setBusy(false);
    }
  }

  function handleReplaceClick() {
    replaceInputRef.current?.click();
  }

  function handleReplaceFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const keepCategory = confirm(
      "Сохранить текущую категорию документа?\n\n" +
        "OK — оставить ту же категорию.\n" +
        "Отмена — AI определит категорию заново."
    );
    onReplace(file, keepCategory);
    if (replaceInputRef.current) replaceInputRef.current.value = "";
  }

  return (
    <div
      className="rounded-lg p-3 transition-colors"
      style={{
        background: "var(--color-bg-primary)",
        border: "1px solid var(--color-border-tertiary)",
      }}
    >
      <div className="flex items-start gap-3">
        {/* Иконка типа файла */}
        <div
          className="flex-shrink-0 w-10 h-10 rounded-md flex items-center justify-center"
          style={{ background: "var(--color-bg-tertiary)" }}
        >
          <Icon
            className="w-5 h-5"
            style={{ color: "var(--color-text-secondary)" }}
          />
        </div>

        {/* Body */}
        <div className="flex-1 min-w-0">
          {/* Имя файла + размер */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <h3
              className="text-sm font-medium truncate"
              style={{ color: "var(--color-text-primary)" }}
              title={doc.original_filename}
            >
              {doc.original_filename}
            </h3>
            <span
              className="text-xs flex-shrink-0"
              style={{ color: "var(--color-text-tertiary)" }}
            >
              {formatBytes(doc.file_size_bytes)}
              {doc.page_count ? ` · ${doc.page_count} стр.` : ""}
            </span>
          </div>

          {/* Категория + extraction info */}
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            {isProcessing ? (
              <span
                className="text-xs inline-flex items-center gap-1.5 px-2 py-0.5 rounded"
                style={{
                  background: "var(--color-bg-info)",
                  color: "var(--color-text-info)",
                }}
              >
                <Loader2 className="w-3 h-3 animate-spin" />
                AI анализирует...
              </span>
            ) : editingCategory ? (
              <div className="flex items-center gap-1">
                <select
                  value={pendingCategory || doc.doc_category || "other"}
                  onChange={(e) =>
                    setPendingCategory(e.target.value as FinalSubmissionDocCategory)
                  }
                  className="text-xs px-2 py-0.5 rounded border"
                  style={{
                    background: "var(--color-bg-primary)",
                    color: "var(--color-text-primary)",
                    borderColor: "var(--color-border-secondary)",
                  }}
                >
                  {(Object.keys(FINAL_DOC_CATEGORY_LABELS) as FinalSubmissionDocCategory[]).map((cat) => (
                    <option key={cat} value={cat}>
                      {FINAL_DOC_CATEGORY_LABELS[cat]}
                    </option>
                  ))}
                </select>
                <button
                  onClick={saveCategory}
                  disabled={busy || !pendingCategory}
                  className="p-1 rounded disabled:opacity-50"
                  style={{ color: "var(--color-text-success)" }}
                  title="Сохранить"
                >
                  {busy ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Check className="w-3.5 h-3.5" />
                  )}
                </button>
                <button
                  onClick={() => {
                    setEditingCategory(false);
                    setPendingCategory(null);
                  }}
                  className="p-1 rounded"
                  style={{ color: "var(--color-text-tertiary)" }}
                  title="Отмена"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <>
                <span
                  className="text-xs inline-flex items-center gap-1.5 px-2 py-0.5 rounded"
                  style={{
                    background:
                      doc.doc_category_source === "manual"
                        ? "var(--color-bg-success)"
                        : "var(--color-bg-info)",
                    color:
                      doc.doc_category_source === "manual"
                        ? "var(--color-text-success)"
                        : "var(--color-text-info)",
                  }}
                  title={
                    doc.doc_category_source === "manual"
                      ? "Категория выставлена менеджером вручную"
                      : `AI · уверенность ${doc.doc_category_confidence || "?"}`
                  }
                >
                  {doc.doc_category_source === "manual" ? (
                    <User className="w-3 h-3" />
                  ) : (
                    <Sparkles className="w-3 h-3" />
                  )}
                  {categoryLabel || "не определена"}
                  {doc.doc_category_source !== "manual" && doc.doc_category_confidence && (
                    <span className="opacity-70">
                      · {Math.round(parseFloat(doc.doc_category_confidence) * 100)}%
                    </span>
                  )}
                </span>
                <button
                  onClick={() => {
                    setPendingCategory(doc.doc_category || "other");
                    setEditingCategory(true);
                  }}
                  className="p-0.5 rounded hover:bg-secondary"
                  style={{ color: "var(--color-text-tertiary)" }}
                  title="Исправить категорию"
                >
                  <Edit3 className="w-3 h-3" />
                </button>
              </>
            )}

            {doc.extraction_method && (
              <span
                className="text-xs inline-flex items-center px-1.5 py-0.5 rounded font-mono"
                style={{
                  background: "var(--color-bg-secondary)",
                  color: "var(--color-text-tertiary)",
                }}
                title="Метод извлечения текста"
              >
                {doc.extraction_method}
              </span>
            )}
          </div>

          {/* Дата загрузки */}
          <p
            className="text-xs mt-1.5"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            Загружено: {new Date(doc.uploaded_at).toLocaleString("ru-RU")}
          </p>
        </div>

        {/* Действия */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {doc.download_url && (
            <a
              href={doc.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded hover:bg-secondary"
              style={{ color: "var(--color-text-secondary)" }}
              title="Открыть/скачать"
            >
              <Download className="w-4 h-4" />
            </a>
          )}
          <button
            onClick={handleReplaceClick}
            className="p-1.5 rounded hover:bg-secondary"
            style={{ color: "var(--color-text-secondary)" }}
            title="Заменить новой версией"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <input
            ref={replaceInputRef}
            type="file"
            className="hidden"
            onChange={handleReplaceFile}
          />
          <button
            onClick={() => onDelete(false)}
            className="p-1.5 rounded hover:bg-secondary"
            style={{ color: "var(--color-text-danger)" }}
            title="Удалить (soft — файл останется в истории)"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
