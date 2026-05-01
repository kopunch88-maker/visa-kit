"use client";

import { useEffect, useState } from "react";
import {
  Loader2, X, Upload, FileText, AlertCircle, CheckCircle2,
  Sparkles, FileWarning, Package,
} from "lucide-react";
import {
  ClientDocumentType,
  DOCUMENT_TYPE_LABELS,
  ImportFileMeta,
  ImportSession,
  ImportFileAssignment,
  ImportFinalizeResult,
  ApplicationResponse,
  importPackageUpload,
  importPackageFinalize,
  importPackageCancel,
} from "@/lib/api";
import {
  pdfToImagePages,
  PdfPagePreview,
} from "@/lib/pdfConverter";

interface Props {
  applications: ApplicationResponse[]; // для выбора существующей заявки
  onClose: () => void;
  onImported: (result: ImportFinalizeResult) => void;
}

type FileChoice = {
  fileId: string;
  docType: ClientDocumentType | "skip";
  pdfPage: number; // 1-based, для PDF
  pdfPagesPreviews?: PdfPagePreview[]; // загружается лениво
  pdfLoading?: boolean;
  pdfError?: string;
};

const DOC_TYPE_OPTIONS: Array<{ value: ClientDocumentType | "skip"; label: string }> = [
  { value: "skip", label: "— Не использовать —" },
  { value: "passport_internal_main", label: DOCUMENT_TYPE_LABELS.passport_internal_main },
  { value: "passport_internal_address", label: DOCUMENT_TYPE_LABELS.passport_internal_address },
  { value: "passport_foreign", label: DOCUMENT_TYPE_LABELS.passport_foreign },
  { value: "passport_national", label: DOCUMENT_TYPE_LABELS.passport_national },
  { value: "residence_card", label: DOCUMENT_TYPE_LABELS.residence_card },
  { value: "criminal_record", label: DOCUMENT_TYPE_LABELS.criminal_record },
  { value: "diploma_main", label: DOCUMENT_TYPE_LABELS.diploma_main },
  { value: "diploma_apostille", label: DOCUMENT_TYPE_LABELS.diploma_apostille },
  { value: "other", label: DOCUMENT_TYPE_LABELS.other },
];

type Step = "upload" | "classify" | "submitting" | "done";

export function ImportPackageDialog({ applications, onClose, onImported }: Props) {
  const [step, setStep] = useState<Step>("upload");
  const [error, setError] = useState<string | null>(null);
  const [archive, setArchive] = useState<File | null>(null);
  const [importSession, setImportSession] = useState<ImportSession | null>(null);
  const [choices, setChoices] = useState<Record<string, FileChoice>>({});

  // Куда привязываем — новая заявка или существующая
  const [target, setTarget] = useState<"new" | "existing">("new");
  const [internalNotes, setInternalNotes] = useState("");
  const [existingApplicationId, setExistingApplicationId] = useState<number | null>(null);

  // Авто-отмена при закрытии диалога
  useEffect(() => {
    return () => {
      if (importSession?.session_id && step !== "done") {
        importPackageCancel(importSession.session_id).catch(() => {});
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importSession?.session_id]);

  async function handleArchiveSelected(file: File) {
    setError(null);

    const ext = file.name.toLowerCase().split(".").pop();
    if (ext !== "zip" && ext !== "rar") {
      setError("Поддерживаются только архивы ZIP и RAR.");
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      setError("Архив слишком большой. Максимум 100 МБ.");
      return;
    }

    setArchive(file);
    setStep("submitting");

    try {
      const session = await importPackageUpload(file);
      setImportSession(session);

      // Инициализируем choices: по умолчанию "skip" для всех
      const initialChoices: Record<string, FileChoice> = {};
      session.files.forEach((f) => {
        initialChoices[f.file_id] = {
          fileId: f.file_id,
          docType: "skip",
          pdfPage: 1,
        };
      });
      setChoices(initialChoices);
      setStep("classify");
    } catch (e) {
      setError((e as Error).message);
      setStep("upload");
    }
  }

  async function handleLoadPdfPages(file: ImportFileMeta) {
    if (!file.is_pdf || !file.preview_url) return;

    setChoices((prev) => ({
      ...prev,
      [file.file_id]: {
        ...prev[file.file_id],
        pdfLoading: true,
        pdfError: undefined,
      },
    }));

    try {
      // Скачиваем PDF blob
      const res = await fetch(file.preview_url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();

      // Конвертируем все страницы (макс 10) в превью
      const pages = await pdfToImagePages(blob, { dpi: 100, maxPages: 10 });

      setChoices((prev) => ({
        ...prev,
        [file.file_id]: {
          ...prev[file.file_id],
          pdfPagesPreviews: pages,
          pdfLoading: false,
        },
      }));
    } catch (e) {
      setChoices((prev) => ({
        ...prev,
        [file.file_id]: {
          ...prev[file.file_id],
          pdfLoading: false,
          pdfError: (e as Error).message,
        },
      }));
    }
  }

  function setDocType(fileId: string, docType: ClientDocumentType | "skip") {
    setChoices((prev) => ({
      ...prev,
      [fileId]: { ...prev[fileId], docType },
    }));
  }

  function setPdfPage(fileId: string, page: number) {
    setChoices((prev) => ({
      ...prev,
      [fileId]: { ...prev[fileId], pdfPage: page },
    }));
  }

  async function handleFinalize() {
    if (!importSession) return;
    setError(null);
    setStep("submitting");

    const fileAssignments: ImportFileAssignment[] = Object.values(choices).map((c) => {
      const file = importSession.files.find((f) => f.file_id === c.fileId);
      return {
        file_id: c.fileId,
        doc_type: c.docType,
        pdf_page: file?.is_pdf ? c.pdfPage : null,
      };
    });

    // Хотя бы один документ должен быть выбран
    const usableCount = fileAssignments.filter((a) => a.doc_type !== "skip").length;
    if (usableCount === 0) {
      setError("Выберите тип хотя бы для одного документа.");
      setStep("classify");
      return;
    }

    try {
      const result = await importPackageFinalize(importSession.session_id, {
        application_id: target === "existing" ? existingApplicationId : null,
        internal_notes: target === "new" ? internalNotes : null,
        files: fileAssignments,
        run_ocr: true,
      });
      setStep("done");
      // Покажем результат и через 2 секунды закроем
      setTimeout(() => {
        onImported(result);
      }, 1200);
    } catch (e) {
      setError((e as Error).message);
      setStep("classify");
    }
  }

  async function handleCancel() {
    if (importSession?.session_id) {
      try {
        await importPackageCancel(importSession.session_id);
      } catch {}
    }
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.5)" }}
    >
      <div
        className="rounded-xl max-w-4xl w-full max-h-[92vh] overflow-hidden flex flex-col"
        style={{
          background: "var(--color-bg-primary)",
          border: "0.5px solid var(--color-border-secondary)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderBottomWidth: 0.5,
          }}
        >
          <div className="flex items-center gap-2">
            <Package className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
            <span className="text-base font-semibold text-primary">
              Импорт пакета документов
            </span>
          </div>
          <button
            onClick={handleCancel}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors text-tertiary"
            disabled={step === "submitting"}
            aria-label="Закрыть"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-5">
          {error && (
            <div
              className="mb-4 p-3 rounded-md text-sm flex gap-2 items-start"
              style={{
                background: "var(--color-bg-danger)",
                color: "var(--color-text-danger)",
                border: "0.5px solid var(--color-border-danger)",
              }}
            >
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {step === "upload" && (
            <UploadStep onFileSelected={handleArchiveSelected} />
          )}

          {step === "submitting" && !importSession && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-secondary" />
              <div className="text-sm text-tertiary">Распаковываем архив...</div>
            </div>
          )}

          {step === "classify" && importSession && (
            <ClassifyStep
              session={importSession}
              choices={choices}
              setDocType={setDocType}
              setPdfPage={setPdfPage}
              loadPdfPages={handleLoadPdfPages}
              target={target}
              setTarget={setTarget}
              internalNotes={internalNotes}
              setInternalNotes={setInternalNotes}
              existingApplicationId={existingApplicationId}
              setExistingApplicationId={setExistingApplicationId}
              applications={applications}
            />
          )}

          {step === "submitting" && importSession && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-secondary" />
              <div className="text-sm text-secondary font-medium">
                Загружаем документы и распознаём...
              </div>
              <div className="text-xs text-tertiary">
                Это может занять до минуты
              </div>
            </div>
          )}

          {step === "done" && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <div
                className="w-16 h-16 rounded-full flex items-center justify-center"
                style={{ background: "var(--color-bg-success)" }}
              >
                <CheckCircle2
                  className="w-10 h-10"
                  style={{ color: "var(--color-text-success)" }}
                />
              </div>
              <div className="text-sm text-primary font-medium">
                Импорт завершён успешно
              </div>
              <div className="text-xs text-tertiary">Открываем заявку...</div>
            </div>
          )}
        </div>

        {/* Footer */}
        {step === "classify" && importSession && (
          <div
            className="px-5 py-4 border-t flex justify-between gap-3"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderTopWidth: 0.5,
            }}
          >
            <button
              onClick={handleCancel}
              className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
            >
              Отмена
            </button>
            <button
              onClick={handleFinalize}
              className="px-5 py-2 rounded-md text-sm font-medium text-white transition-colors flex items-center gap-2"
              style={{ background: "var(--color-accent)" }}
            >
              <Sparkles className="w-4 h-4" />
              Распознать и создать заявку →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


// =============================================================================
// Step 1: Upload archive
// =============================================================================

function UploadStep({ onFileSelected }: { onFileSelected: (file: File) => void }) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useState<HTMLInputElement | null>(null)[0];

  function handleSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) onFileSelected(f);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFileSelected(f);
  }

  return (
    <div
      className="rounded-lg border-dashed p-10 text-center transition-colors"
      style={{
        borderWidth: 1.5,
        borderStyle: "dashed",
        borderColor: dragOver
          ? "var(--color-accent)"
          : "var(--color-border-secondary)",
        background: dragOver ? "var(--color-bg-secondary)" : "transparent",
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setDragOver(false);
      }}
      onDrop={handleDrop}
    >
      <Package
        className="w-12 h-12 mx-auto mb-3 text-tertiary"
        style={{ color: "var(--color-text-tertiary)" }}
      />
      <div className="text-base font-medium text-primary mb-1">
        Перетащите архив сюда
      </div>
      <div className="text-sm text-tertiary mb-4">
        ZIP или RAR с документами клиента (паспорт, ВНЖ, справки, диплом)
      </div>
      <label
        className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white cursor-pointer transition-colors"
        style={{ background: "var(--color-accent)" }}
      >
        <Upload className="w-4 h-4" />
        Выбрать архив
        <input
          type="file"
          accept=".zip,.rar,application/zip,application/x-zip-compressed,application/x-rar-compressed,application/vnd.rar"
          onChange={handleSelect}
          className="hidden"
        />
      </label>
      <div className="mt-4 text-xs text-tertiary">
        Макс. размер архива: 100 МБ. Внутри: PDF, JPEG, PNG, WebP, HEIC.
      </div>
    </div>
  );
}


// =============================================================================
// Step 2: Classify each file
// =============================================================================

function ClassifyStep({
  session,
  choices,
  setDocType,
  setPdfPage,
  loadPdfPages,
  target,
  setTarget,
  internalNotes,
  setInternalNotes,
  existingApplicationId,
  setExistingApplicationId,
  applications,
}: {
  session: ImportSession;
  choices: Record<string, FileChoice>;
  setDocType: (fileId: string, docType: ClientDocumentType | "skip") => void;
  setPdfPage: (fileId: string, page: number) => void;
  loadPdfPages: (file: ImportFileMeta) => void;
  target: "new" | "existing";
  setTarget: (t: "new" | "existing") => void;
  internalNotes: string;
  setInternalNotes: (s: string) => void;
  existingApplicationId: number | null;
  setExistingApplicationId: (id: number | null) => void;
  applications: ApplicationResponse[];
}) {
  return (
    <div className="space-y-5">
      {/* Куда импортируем */}
      <div
        className="rounded-md p-4"
        style={{
          background: "var(--color-bg-secondary)",
          border: "0.5px solid var(--color-border-secondary)",
        }}
      >
        <div className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-2">
          Куда импортируем
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <label
            className="flex-1 rounded-md p-3 cursor-pointer transition-colors"
            style={{
              borderWidth: target === "new" ? 1.5 : 0.5,
              borderStyle: "solid",
              borderColor:
                target === "new"
                  ? "var(--color-accent)"
                  : "var(--color-border-secondary)",
              background:
                target === "new" ? "var(--color-bg-primary)" : "transparent",
            }}
          >
            <div className="flex items-center gap-2">
              <input
                type="radio"
                checked={target === "new"}
                onChange={() => setTarget("new")}
              />
              <span className="text-sm font-medium text-primary">
                Создать новую заявку
              </span>
            </div>
            {target === "new" && (
              <input
                type="text"
                value={internalNotes}
                onChange={(e) => setInternalNotes(e.target.value)}
                placeholder="Внутренняя заметка (видна только менеджерам)"
                className="mt-2 w-full px-2 py-1.5 rounded-md text-sm border"
                style={{
                  borderColor: "var(--color-border-tertiary)",
                  borderWidth: 0.5,
                  background: "var(--color-bg-primary)",
                  color: "var(--color-text-primary)",
                }}
              />
            )}
          </label>

          <label
            className="flex-1 rounded-md p-3 cursor-pointer transition-colors"
            style={{
              borderWidth: target === "existing" ? 1.5 : 0.5,
              borderStyle: "solid",
              borderColor:
                target === "existing"
                  ? "var(--color-accent)"
                  : "var(--color-border-secondary)",
              background:
                target === "existing"
                  ? "var(--color-bg-primary)"
                  : "transparent",
            }}
          >
            <div className="flex items-center gap-2">
              <input
                type="radio"
                checked={target === "existing"}
                onChange={() => setTarget("existing")}
              />
              <span className="text-sm font-medium text-primary">
                Привязать к существующей
              </span>
            </div>
            {target === "existing" && (
              <select
                value={existingApplicationId || ""}
                onChange={(e) =>
                  setExistingApplicationId(
                    e.target.value ? parseInt(e.target.value) : null
                  )
                }
                className="mt-2 w-full px-2 py-1.5 rounded-md text-sm border"
                style={{
                  borderColor: "var(--color-border-tertiary)",
                  borderWidth: 0.5,
                  background: "var(--color-bg-primary)",
                  color: "var(--color-text-primary)",
                }}
              >
                <option value="">— Выберите заявку —</option>
                {applications.map((a) => (
                  <option key={a.id} value={a.id}>
                    #{a.reference}
                    {a.applicant_name_native
                      ? ` — ${a.applicant_name_native}`
                      : a.internal_notes
                      ? ` — ${a.internal_notes}`
                      : ""}
                  </option>
                ))}
              </select>
            )}
          </label>
        </div>
      </div>

      {/* Файлы */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-2">
          Файлы из архива ({session.files.length})
        </div>
        <div className="text-xs text-tertiary mb-3">
          Выберите тип каждого документа. Лишние оставьте «Не использовать».
        </div>

        <div className="space-y-2">
          {session.files.map((file) => (
            <FileRow
              key={file.file_id}
              file={file}
              choice={choices[file.file_id]}
              onDocTypeChange={(t) => setDocType(file.file_id, t)}
              onPdfPageChange={(p) => setPdfPage(file.file_id, p)}
              onLoadPdfPages={() => loadPdfPages(file)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}


function FileRow({
  file,
  choice,
  onDocTypeChange,
  onPdfPageChange,
  onLoadPdfPages,
}: {
  file: ImportFileMeta;
  choice: FileChoice;
  onDocTypeChange: (t: ClientDocumentType | "skip") => void;
  onPdfPageChange: (page: number) => void;
  onLoadPdfPages: () => void;
}) {
  const sizeMB = (file.size / 1024 / 1024).toFixed(1);

  // Загружаем превью PDF когда менеджер выбрал тип (не "skip")
  const needPdfPages =
    file.is_pdf && choice.docType !== "skip" && !choice.pdfPagesPreviews && !choice.pdfLoading && !choice.pdfError;

  useEffect(() => {
    if (needPdfPages) {
      onLoadPdfPages();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needPdfPages]);

  return (
    <div
      className="rounded-md p-3"
      style={{
        border: "0.5px solid var(--color-border-tertiary)",
        background: "var(--color-bg-primary)",
      }}
    >
      <div className="flex gap-3 items-start">
        {/* Иконка / превью */}
        <div
          className="w-16 h-16 flex-shrink-0 rounded-md overflow-hidden flex items-center justify-center"
          style={{
            background: "var(--color-bg-secondary)",
            border: "0.5px solid var(--color-border-secondary)",
          }}
        >
          {file.is_pdf ? (
            <FileText className="w-6 h-6 text-tertiary" />
          ) : file.preview_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <a href={file.preview_url} target="_blank" rel="noopener noreferrer">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={file.preview_url}
                alt={file.name}
                className="w-full h-full object-cover"
              />
            </a>
          ) : (
            <FileText className="w-6 h-6 text-tertiary" />
          )}
        </div>

        {/* Данные */}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-primary truncate">
            {file.name}
          </div>
          <div className="text-xs text-tertiary mb-2">
            {file.is_pdf ? "PDF" : file.extension.replace(".", "").toUpperCase()} ·{" "}
            {sizeMB} МБ
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            {/* Селект типа */}
            <select
              value={choice.docType}
              onChange={(e) =>
                onDocTypeChange(e.target.value as ClientDocumentType | "skip")
              }
              className="px-2 py-1.5 rounded-md text-sm border flex-1"
              style={{
                borderColor:
                  choice.docType === "skip"
                    ? "var(--color-border-tertiary)"
                    : "var(--color-accent)",
                borderWidth: 0.5,
                background: "var(--color-bg-primary)",
                color: "var(--color-text-primary)",
              }}
            >
              {DOC_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* PDF page picker */}
          {file.is_pdf && choice.docType !== "skip" && (
            <div className="mt-3">
              <div className="text-xs text-tertiary mb-1.5">
                Какую страницу PDF использовать:
              </div>
              {choice.pdfLoading && (
                <div className="flex items-center gap-2 text-xs text-tertiary">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Конвертируем PDF...
                </div>
              )}
              {choice.pdfError && (
                <div
                  className="text-xs flex items-start gap-1.5"
                  style={{ color: "var(--color-text-danger)" }}
                >
                  <FileWarning className="w-3 h-3 flex-shrink-0 mt-0.5" />
                  <span>
                    Не удалось показать превью: {choice.pdfError}. Будет
                    использована страница {choice.pdfPage}.
                  </span>
                </div>
              )}
              {choice.pdfPagesPreviews && choice.pdfPagesPreviews.length > 0 && (
                <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                  {choice.pdfPagesPreviews.map((p) => {
                    const selected = choice.pdfPage === p.pageNum;
                    return (
                      <button
                        key={p.pageNum}
                        onClick={() => onPdfPageChange(p.pageNum)}
                        className="relative rounded-md overflow-hidden text-left transition-all"
                        style={{
                          borderWidth: selected ? 2 : 0.5,
                          borderStyle: "solid",
                          borderColor: selected
                            ? "var(--color-accent)"
                            : "var(--color-border-secondary)",
                          background: "var(--color-bg-secondary)",
                        }}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={p.dataUrl}
                          alt={`Стр. ${p.pageNum}`}
                          className="w-full h-auto block"
                          style={{ aspectRatio: `${p.width}/${p.height}` }}
                        />
                        <div
                          className="absolute bottom-0 left-0 right-0 px-1.5 py-0.5 text-xs font-medium text-center"
                          style={{
                            background: selected
                              ? "var(--color-accent)"
                              : "rgba(0,0,0,0.5)",
                            color: "white",
                          }}
                        >
                          Стр. {p.pageNum}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
