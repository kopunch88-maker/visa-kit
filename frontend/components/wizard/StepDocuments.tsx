
"use client";

import { useEffect, useState, useRef } from "react";
import { Loader2, Upload, Camera, CheckCircle2, AlertCircle, Sparkles, AlertTriangle, FileText, Download } from "lucide-react";
import {
  ClientDocument,
  ClientDocumentType,
  ApplyPreview,
  ApplyOptions,
  FIELD_LABELS,
  getMyDocuments,
  uploadDocument,
  deleteDocument,
  recognizeDocument,
  previewApplyDocuments,
  applyDocumentsToApplicant,
} from "@/lib/api";
import { isPdfFile, isHeicFile } from "@/lib/pdfConverter";
import { StepHeader } from "@/components/ui/Form";
import { PdfPageSelector } from "./PdfPageSelector";

interface Props {
  token: string;
  onSkip?: () => void;
  onContinue?: () => void;
}

const SLOTS: Array<{
  type: ClientDocumentType;
  title: string;
  description: string;
  hint: string;
  ocrEnabled: boolean;
}> = [
  {
    type: "passport_internal_main",
    title: "Паспорт РФ — главная страница",
    description: "Разворот с фотографией и ФИО",
    hint: "Сделайте фото первой страницы паспорта (с фото). Извлекаем ФИО, дату рождения, серию и номер.",
    ocrEnabled: true,
  },
  {
    type: "passport_internal_address",
    title: "Паспорт РФ — страница прописки",
    description: "Страница 5 — где штамп о регистрации",
    hint: "Сделайте фото страницы с пропиской. Извлекаем адрес регистрации.",
    ocrEnabled: true,
  },
  {
    type: "passport_foreign",
    title: "Загранпаспорт",
    description: "Страница с фотографией и данными",
    hint: "Главный разворот загранпаспорта. Извлекаем латинские ФИО, номер, срок действия.",
    ocrEnabled: true,
  },
  {
    type: "diploma_main",
    title: "Диплом — основная страница",
    description: "Лист с указанием ВУЗа и специальности",
    hint: "Скан или фото диплома. Извлекаем название ВУЗа, год выпуска, специальность.",
    ocrEnabled: true,
  },
  {
    type: "diploma_apostille",
    title: "Диплом — апостиль",
    description: "Страница с апостилем",
    hint: "Если апостиль на отдельном листе. Сохраняется для подачи в UGE.",
    ocrEnabled: false,
  },
];

export function StepDocuments({ token, onSkip, onContinue }: Props) {
  const [documents, setDocuments] = useState<ClientDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recognizing, setRecognizing] = useState(false);
  const [recognizingDocId, setRecognizingDocId] = useState<number | null>(null);
  const [showReview, setShowReview] = useState(false);
  const [preview, setPreview] = useState<ApplyPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const docs = await getMyDocuments(token);
        if (!cancelled) {
          setDocuments(docs);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message);
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const findDoc = (type: ClientDocumentType) =>
    documents.find((d) => d.doc_type === type);

  async function handleUpload(
    type: ClientDocumentType,
    primaryFile: File,
    originalFile?: File | null,
  ) {
    setError(null);
    try {
      const newDoc = await uploadDocument(token, type, primaryFile, originalFile);
      setDocuments((prev) => [
        ...prev.filter((d) => d.doc_type !== type),
        newDoc,
      ]);
    } catch (e) {
      setError((e as Error).message);
      throw e;
    }
  }

  async function handleDelete(docId: number) {
    setError(null);
    try {
      await deleteDocument(token, docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleRecognizeAll() {
    if (documents.length === 0) return;

    setRecognizing(true);
    setError(null);

    const ocrEnabledTypes = SLOTS.filter((s) => s.ocrEnabled).map((s) => s.type);
    const docsToRecognize = documents.filter(
      (d) => ocrEnabledTypes.includes(d.doc_type) && d.status !== "ocr_done"
    );

    for (const doc of docsToRecognize) {
      setRecognizingDocId(doc.id);
      try {
        const updated = await recognizeDocument(token, doc.id);
        setDocuments((prev) =>
          prev.map((d) => (d.id === doc.id ? updated : d))
        );
      } catch (e) {
        console.error(`OCR failed for doc ${doc.id}:`, e);
        setDocuments((prev) =>
          prev.map((d) =>
            d.id === doc.id
              ? { ...d, status: "ocr_failed" as const, ocr_error: (e as Error).message }
              : d
          )
        );
      }
    }

    setRecognizingDocId(null);
    setRecognizing(false);

    const updated = await getMyDocuments(token);
    setDocuments(updated);

    const hasSuccessful = updated.some((d) => d.status === "ocr_done");
    if (!hasSuccessful) {
      setError(
        "Ни один документ не удалось распознать. Проверьте качество фотографий и попробуйте снова."
      );
      return;
    }

    setPreviewLoading(true);
    try {
      const p = await previewApplyDocuments(token);
      setPreview(p);
      setShowReview(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPreviewLoading(false);
    }
  }

  const uploadedCount = documents.length;

  if (loading) {
    return (
      <div className="flex justify-center items-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-secondary" />
      </div>
    );
  }

  if (showReview && preview) {
    return (
      <ReviewMode
        token={token}
        preview={preview}
        documents={documents}
        onConfirm={async (options) => {
          setError(null);
          try {
            await applyDocumentsToApplicant(token, options);
            onContinue?.();
          } catch (e) {
            setError((e as Error).message);
          }
        }}
        onBack={() => {
          setShowReview(false);
          setPreview(null);
        }}
        error={error}
      />
    );
  }

  return (
    <div>
      <StepHeader
        title="Документы"
        subtitle="Загрузите фотографии или сканы документов — мы автоматически заполним анкету за вас. Этот шаг можно пропустить."
      />

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

      <div
        className="mb-5 p-4 rounded-lg flex gap-3"
        style={{
          background: "var(--color-bg-secondary)",
          border: "0.5px solid var(--color-border-secondary)",
        }}
      >
        <Sparkles className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: "var(--color-accent)" }} />
        <div className="text-sm text-secondary">
          <strong className="text-primary">Магия автозаполнения:</strong> загрузите фото
          или PDF-сканы паспортов и диплома — мы их распознаем и заполним анкету за вас. Вы сможете
          проверить и поправить любые поля.
        </div>
      </div>

      <div className="space-y-3">
        {SLOTS.map((slot) => {
          const doc = findDoc(slot.type);
          const isThisRecognizing = recognizing && recognizingDocId === doc?.id;
          return (
            <DocumentSlot
              key={slot.type}
              slot={slot}
              doc={doc}
              isRecognizing={isThisRecognizing}
              onUpload={(primaryFile, originalFile) =>
                handleUpload(slot.type, primaryFile, originalFile)
              }
              onDelete={(docId) => handleDelete(docId)}
            />
          );
        })}
      </div>

      <div
        className="mt-8 pt-6 border-t border-tertiary flex flex-col sm:flex-row gap-3 justify-between"
        style={{ borderTopWidth: 0.5 }}
      >
        <button
          onClick={onSkip}
          disabled={recognizing || previewLoading}
          className="px-5 py-2.5 rounded-md text-sm border border-tertiary text-secondary hover:bg-secondary disabled:opacity-50 transition-colors"
          style={{ borderWidth: 0.5 }}
        >
          Пропустить → заполнить вручную
        </button>

        <button
          onClick={handleRecognizeAll}
          disabled={uploadedCount === 0 || recognizing || previewLoading}
          className="px-5 py-2.5 rounded-md text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          style={{ background: "var(--color-accent)" }}
        >
          {recognizing ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Распознаём...
            </>
          ) : previewLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Подготовка...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              {uploadedCount === 0
                ? "Загрузите хотя бы один документ"
                : `Распознать всё (${uploadedCount}) >`}
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// REVIEW MODE
// =============================================================================

interface ReviewProps {
  token: string;
  preview: ApplyPreview;
  documents: ClientDocument[];
  onConfirm: (options: ApplyOptions) => Promise<void>;
  onBack: () => void;
  error: string | null;
}

const SEX_LABELS: Record<string, string> = { H: "Мужской", M: "Женский" };
const DEGREE_LABELS: Record<string, string> = {
  bachelor: "Бакалавр", specialist: "Специалист", master: "Магистр",
  phd: "Кандидат / Доктор наук", secondary: "Среднее специальное",
};
const DOC_SECTION_TITLES: Record<ClientDocumentType, string> = {
  passport_internal_main: "Паспорт РФ — главная",
  passport_internal_address: "Паспорт РФ — прописка",
  passport_foreign: "Загранпаспорт",
  diploma_main: "Диплом",
  diploma_apostille: "Апостиль",
  other: "Другое",
};

function formatValue(field: string, value: any): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "sex" && SEX_LABELS[value as string]) return SEX_LABELS[value as string];
  if (field === "degree" && DEGREE_LABELS[value as string]) return DEGREE_LABELS[value as string];
  return String(value);
}

function ReviewMode({ token, preview, documents, onConfirm, onBack, error }: ReviewProps) {
  const [conflictChoices, setConflictChoices] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    preview.conflicts.forEach((c) => {
      initial[c.field] = false;
    });
    return initial;
  });

  const [educationAction, setEducationAction] = useState<"auto" | "skip" | "replace" | "add">(
    () => (preview.education?.type === "conflict" ? "skip" : "auto")
  );

  const [submitting, setSubmitting] = useState(false);

  const ocrFailedDocs = documents.filter((d) => d.status === "ocr_failed");

  async function handleConfirm() {
    setSubmitting(true);
    try {
      const overrides = Object.entries(conflictChoices)
        .filter(([_, useOcr]) => useOcr)
        .map(([field]) => field);
      await onConfirm({ overrides, education_action: educationAction });
    } finally {
      setSubmitting(false);
    }
  }

  const totalChanges =
    preview.auto_fill.length +
    Object.values(conflictChoices).filter((v) => v).length +
    (preview.education?.type === "auto_fill" ? 1 : 0) +
    (preview.education?.type === "conflict" && educationAction !== "skip" ? 1 : 0);

  return (
    <div>
      <StepHeader
        title="Что мы извлекли"
        subtitle="Проверьте распознанные данные и решите что использовать в анкете."
      />

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

      {preview.conflicts.length > 0 && (
        <div className="mb-6">
          <div
            className="p-4 rounded-lg mb-3"
            style={{
              background: "var(--color-bg-warning, var(--color-bg-secondary))",
              border: "0.5px solid var(--color-border-secondary)",
            }}
          >
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4" style={{ color: "var(--color-text-warning, var(--color-accent))" }} />
              <span className="text-sm font-semibold text-primary">
                Найдены различия — выберите что оставить
              </span>
            </div>
            <div className="text-xs text-tertiary">
              В этих полях ваши текущие данные отличаются от распознанных.
            </div>
          </div>

          <div className="space-y-3">
            {preview.conflicts.map((c) => {
              const useOcr = conflictChoices[c.field] || false;
              const fieldLabel = FIELD_LABELS[c.field] || c.field;

              return (
                <div
                  key={c.field}
                  className="rounded-lg p-3 border"
                  style={{
                    borderWidth: 0.5,
                    borderColor: "var(--color-border-secondary)",
                    background: "var(--color-bg-primary)",
                  }}
                >
                  <div className="text-xs font-semibold text-tertiary uppercase tracking-wide mb-2">
                    {fieldLabel}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <label
                      className="rounded-md p-3 cursor-pointer transition-colors"
                      style={{
                        borderWidth: useOcr ? 0.5 : 1.5,
                        borderStyle: "solid",
                        borderColor: useOcr ? "var(--color-border-secondary)" : "var(--color-accent)",
                        background: useOcr ? "var(--color-bg-primary)" : "var(--color-bg-secondary)",
                      }}
                    >
                      <div className="flex items-start gap-2">
                        <input
                          type="radio"
                          name={`conflict-${c.field}`}
                          checked={!useOcr}
                          onChange={() =>
                            setConflictChoices((prev) => ({ ...prev, [c.field]: false }))
                          }
                          className="mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs text-tertiary">Оставить как есть</div>
                          <div className="text-sm text-primary break-words">
                            {formatValue(c.field, c.current_value)}
                          </div>
                        </div>
                      </div>
                    </label>

                    <label
                      className="rounded-md p-3 cursor-pointer transition-colors"
                      style={{
                        borderWidth: useOcr ? 1.5 : 0.5,
                        borderStyle: "solid",
                        borderColor: useOcr ? "var(--color-accent)" : "var(--color-border-secondary)",
                        background: useOcr ? "var(--color-bg-secondary)" : "var(--color-bg-primary)",
                      }}
                    >
                      <div className="flex items-start gap-2">
                        <input
                          type="radio"
                          name={`conflict-${c.field}`}
                          checked={useOcr}
                          onChange={() =>
                            setConflictChoices((prev) => ({ ...prev, [c.field]: true }))
                          }
                          className="mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs text-tertiary">Из документа</div>
                          <div className="text-sm text-primary break-words">
                            {formatValue(c.field, c.ocr_value)}
                          </div>
                        </div>
                      </div>
                    </label>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {preview.education?.type === "conflict" && (
        <div className="mb-6">
          <div
            className="rounded-lg p-3 border"
            style={{
              borderWidth: 0.5,
              borderColor: "var(--color-border-secondary)",
              background: "var(--color-bg-primary)",
            }}
          >
            <div className="text-xs font-semibold text-tertiary uppercase tracking-wide mb-2">
              Образование
            </div>
            <div className="text-xs text-tertiary mb-3">
              У вас уже {preview.education.current_count > 1 ? `${preview.education.current_count} записи` : "1 запись"} об образовании.
              Что делать с распознанным дипломом ({(preview.education.ocr_value as any).institution || "—"})?
            </div>
            <div className="space-y-2">
              {(["skip", "add", "replace"] as const).map((action) => {
                const labels: Record<typeof action, { title: string; desc: string }> = {
                  skip: { title: "Не трогать", desc: "Оставить только мои существующие записи" },
                  add: { title: "Добавить", desc: "Добавить распознанный диплом к существующим записям" },
                  replace: { title: "Заменить", desc: "Удалить мои записи и оставить только распознанный диплом" },
                };
                const l = labels[action];
                const checked = educationAction === action;
                return (
                  <label
                    key={action}
                    className="rounded-md p-2.5 cursor-pointer transition-colors flex items-start gap-2"
                    style={{
                      borderWidth: checked ? 1.5 : 0.5,
                      borderStyle: "solid",
                      borderColor: checked ? "var(--color-accent)" : "var(--color-border-secondary)",
                      background: checked ? "var(--color-bg-secondary)" : "var(--color-bg-primary)",
                    }}
                  >
                    <input
                      type="radio"
                      name="edu-action"
                      checked={checked}
                      onChange={() => setEducationAction(action)}
                      className="mt-0.5"
                    />
                    <div>
                      <div className="text-sm font-medium text-primary">{l.title}</div>
                      <div className="text-xs text-tertiary">{l.desc}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {(preview.auto_fill.length > 0 || preview.education?.type === "auto_fill") && (
        <div className="mb-6">
          <div className="text-xs font-semibold text-tertiary uppercase tracking-wide mb-2">
            Автоматически заполнятся
          </div>
          <div
            className="rounded-lg p-3 border"
            style={{
              borderWidth: 0.5,
              borderColor: "var(--color-border-secondary)",
              background: "var(--color-bg-primary)",
            }}
          >
            <ul className="space-y-1.5">
              {preview.auto_fill.map((item) => (
                <li key={item.field} className="flex gap-2 text-sm">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: "var(--color-text-success)" }} />
                  <span className="flex-1 min-w-0">
                    <span className="text-tertiary">{FIELD_LABELS[item.field] || item.field}: </span>
                    <span className="text-primary break-words">{formatValue(item.field, item.ocr_value)}</span>
                  </span>
                </li>
              ))}
              {preview.education?.type === "auto_fill" && (
                <li className="flex gap-2 text-sm">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: "var(--color-text-success)" }} />
                  <span className="flex-1 min-w-0">
                    <span className="text-tertiary">Образование: </span>
                    <span className="text-primary break-words">
                      {(preview.education.ocr_value as any).institution || "—"}
                      {(preview.education.ocr_value as any).graduation_year &&
                        ` (${(preview.education.ocr_value as any).graduation_year})`}
                    </span>
                  </span>
                </li>
              )}
            </ul>
          </div>
        </div>
      )}

      {preview.same.length > 0 && (
        <div className="mb-6">
          <details>
            <summary className="text-xs text-tertiary cursor-pointer hover:text-secondary">
              Совпало с тем что вы ввели ({preview.same.length})
            </summary>
            <ul className="mt-2 space-y-1 pl-4">
              {preview.same.map((item) => (
                <li key={item.field} className="text-xs text-tertiary">
                  ? {FIELD_LABELS[item.field] || item.field}: {formatValue(item.field, item.value)}
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}

      {preview.auto_fill.length === 0 &&
       preview.conflicts.length === 0 &&
       !preview.education && (
        <div
          className="p-4 rounded-lg mb-4 text-sm"
          style={{
            background: "var(--color-bg-secondary)",
            border: "0.5px solid var(--color-border-secondary)",
          }}
        >
          Ничего нового из документов извлечь не удалось. Все поля у вас уже совпадают
          с распознанным. Можно продолжать заполнение анкеты.
        </div>
      )}

      {ocrFailedDocs.length > 0 && (
        <div className="mt-4 mb-4 space-y-2">
          {ocrFailedDocs.map((doc) => (
            <div
              key={doc.id}
              className="p-3 rounded-lg flex gap-2 items-start"
              style={{
                background: "var(--color-bg-danger)",
                border: "0.5px solid var(--color-border-danger)",
              }}
            >
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: "var(--color-text-danger)" }} />
              <div className="text-sm" style={{ color: "var(--color-text-danger)" }}>
                <strong>{DOC_SECTION_TITLES[doc.doc_type]}:</strong>{" "}
                не удалось распознать. {doc.ocr_error || "Попробуйте загрузить более чёткое фото."}
              </div>
            </div>
          ))}
        </div>
      )}

      <div
        className="mt-8 pt-6 border-t border-tertiary flex flex-col sm:flex-row gap-3 justify-between"
        style={{ borderTopWidth: 0.5 }}
      >
        <button
          onClick={onBack}
          disabled={submitting}
          className="px-5 py-2.5 rounded-md text-sm border border-tertiary text-secondary hover:bg-secondary disabled:opacity-50 transition-colors"
          style={{ borderWidth: 0.5 }}
        >
          ← Назад к загрузке
        </button>

        <button
          onClick={handleConfirm}
          disabled={submitting}
          className="px-5 py-2.5 rounded-md text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          style={{ background: "var(--color-accent)" }}
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Применяем...
            </>
          ) : (
            <>
              <CheckCircle2 className="w-4 h-4" />
              {totalChanges === 0
                ? "Продолжить >"
                : `Применить (${totalChanges}) и продолжить >`}
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// DocumentSlot — Pack 13.1.3: с поддержкой PDF
// =============================================================================

interface DocumentSlotProps {
  slot: {
    type: ClientDocumentType;
    title: string;
    description: string;
    hint: string;
    ocrEnabled: boolean;
  };
  doc?: ClientDocument;
  isRecognizing: boolean;
  onUpload: (primaryFile: File, originalFile?: File | null) => Promise<void>;
  onDelete: (docId: number) => void;
}

function DocumentSlot({ slot, doc, isRecognizing, onUpload, onDelete }: DocumentSlotProps) {
  const [uploading, setUploading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [pdfPickerFile, setPdfPickerFile] = useState<File | null>(null); // открыть PdfPageSelector?
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setLocalError(null);

    // PDF — открываем модалку выбора страницы (конвертация на клиенте)
    if (isPdfFile(file)) {
      const MAX_SIZE = 10 * 1024 * 1024;
      if (file.size > MAX_SIZE) {
        setLocalError("PDF слишком большой. Максимум 10 МБ.");
        return;
      }
      setPdfPickerFile(file);
      return;
    }

    // HEIC — пока не конвертируем на клиенте, отправляем как есть (backend конвертирует)
    if (isHeicFile(file)) {
      // У HEIC может быть проблема с отображением превью в браузере
      // Но загрузить и распознать — можно
    }

    const MAX_SIZE = 10 * 1024 * 1024;
    const MIN_SIZE = 100 * 1024;

    if (file.size > MAX_SIZE) {
      setLocalError("Файл слишком большой. Максимум 10 МБ.");
      return;
    }
    if (file.size < MIN_SIZE) {
      setLocalError("Файл слишком маленький. Сделайте более качественное фото.");
      return;
    }

    const allowedTypes = [
      "image/jpeg", "image/jpg", "image/png", "image/webp",
      "image/heic", "image/heif",
    ];
    if (!allowedTypes.includes(file.type)) {
      setLocalError(`Неподдерживаемый формат: ${file.type}.`);
      return;
    }

    setUploading(true);
    try {
      await onUpload(file, null);
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  // Результат выбора страницы PDF
  async function handlePdfPageSelected(primaryFile: File, originalFile: File) {
    setPdfPickerFile(null);
    setUploading(true);
    setLocalError(null);
    try {
      await onUpload(primaryFile, originalFile);
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  function handlePdfPickerCancel() {
    setPdfPickerFile(null);
  }

  function handleFileInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }
  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
  }
  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  // Если открыта модалка выбора PDF — рендерим её сверху
  const pdfPickerModal = pdfPickerFile ? (
    <PdfPageSelector
      pdfFile={pdfPickerFile}
      onSelect={handlePdfPageSelected}
      onCancel={handlePdfPickerCancel}
    />
  ) : null;

  if (doc) {
    const isImage = doc.content_type.startsWith("image/");
    const fileSizeKB = Math.round(doc.file_size / 1024);

    let statusBadge: React.ReactNode = null;
    if (isRecognizing || doc.status === "ocr_pending") {
      statusBadge = (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
              style={{ background: "var(--color-bg-secondary)", color: "var(--color-text-secondary)" }}>
          <Loader2 className="w-3 h-3 animate-spin" />
          Распознаём...
        </span>
      );
    } else if (doc.status === "ocr_done") {
      statusBadge = (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
              style={{ background: "var(--color-bg-success)", color: "var(--color-text-success)" }}>
          <CheckCircle2 className="w-3 h-3" />
          Распознано
        </span>
      );
    } else if (doc.status === "ocr_failed") {
      statusBadge = (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
              style={{ background: "var(--color-bg-danger)", color: "var(--color-text-danger)" }}>
          <AlertCircle className="w-3 h-3" />
          Ошибка
        </span>
      );
    }

    return (
      <>
        {pdfPickerModal}
        <div
          className="rounded-lg border border-tertiary p-3 flex gap-3 items-start"
          style={{ borderWidth: 0.5, background: "var(--color-bg-primary)" }}
        >
          <div
            className="w-20 h-20 flex-shrink-0 rounded-md overflow-hidden flex items-center justify-center"
            style={{
              background: "var(--color-bg-secondary)",
              border: "0.5px solid var(--color-border-secondary)",
            }}
          >
            {isImage && doc.download_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={doc.download_url}
                alt={slot.title}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="text-center text-tertiary text-xs p-2">
                ??<br />
                {doc.content_type.split("/")[1]?.toUpperCase() || "FILE"}
              </div>
            )}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: "var(--color-text-success)" }} />
              <span className="text-sm font-medium text-primary truncate">
                {slot.title}
              </span>
              {statusBadge}
              {doc.has_original && (
                <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
                      style={{ background: "var(--color-bg-secondary)", color: "var(--color-text-secondary)" }}>
                  <FileText className="w-3 h-3" />
                  PDF сохранён
                </span>
              )}
            </div>
            <div className="text-xs text-tertiary mt-1 truncate">
              {doc.file_name} · {fileSizeKB} КБ
            </div>
            {doc.has_original && doc.original_download_url && (
              <a
                href={doc.original_download_url}
                target="_blank"
                rel="noopener noreferrer"
                download={doc.original_file_name || undefined}
                className="text-xs mt-1 inline-flex items-center gap-1 hover:underline"
                style={{ color: "var(--color-accent)" }}
              >
                <Download className="w-3 h-3" />
                Скачать оригинал PDF
              </a>
            )}
            {doc.status === "ocr_failed" && doc.ocr_error && (
              <div className="text-xs mt-1" style={{ color: "var(--color-text-danger)" }}>
                {doc.ocr_error}
              </div>
            )}
            <div className="flex gap-2 mt-2">
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || isRecognizing}
                className="text-xs px-2.5 py-1 rounded-md border border-tertiary text-secondary hover:bg-secondary disabled:opacity-50 transition-colors"
                style={{ borderWidth: 0.5 }}
              >
                {uploading ? <Loader2 className="w-3 h-3 animate-spin" /> : "Заменить"}
              </button>
              <button
                onClick={() => onDelete(doc.id)}
                disabled={uploading || isRecognizing}
                className="text-xs px-2.5 py-1 rounded-md text-danger hover:bg-secondary disabled:opacity-50 transition-colors"
              >
                Удалить
              </button>
            </div>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf"
            onChange={handleFileInputChange}
            className="hidden"
          />
        </div>
      </>
    );
  }

  return (
    <>
      {pdfPickerModal}
      <div
        className="rounded-lg border-dashed p-4 transition-colors"
        style={{
          borderWidth: 1.5,
          borderStyle: "dashed",
          borderColor: dragOver ? "var(--color-accent)" : "var(--color-border-secondary)",
          background: dragOver ? "var(--color-bg-secondary)" : "var(--color-bg-primary)",
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="text-sm font-medium text-primary mb-1">{slot.title}</div>
        <div className="text-xs text-tertiary mb-3">{slot.description}</div>

        {localError && (
          <div className="text-xs mb-2 flex gap-1.5 items-start" style={{ color: "var(--color-text-danger)" }}>
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span>{localError}</span>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="text-xs px-3 py-1.5 rounded-md text-white disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{ background: "var(--color-accent)" }}
          >
            {uploading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Загружается...
              </>
            ) : (
              <>
                <Upload className="w-3.5 h-3.5" />
                Выбрать файл
              </>
            )}
          </button>

          <button
            onClick={() => cameraInputRef.current?.click()}
            disabled={uploading}
            className="text-xs px-3 py-1.5 rounded-md border border-tertiary text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
            style={{ borderWidth: 0.5 }}
          >
            <Camera className="w-3.5 h-3.5" />
            Снять камерой
          </button>
        </div>

        <div className="text-xs text-tertiary mt-2">
          {slot.hint} <span className="text-secondary">Можно загрузить PDF — выберете нужную страницу.</span>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf"
          onChange={handleFileInputChange}
          className="hidden"
        />
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFileInputChange}
          className="hidden"
        />
      </div>
    </>
  );
}



