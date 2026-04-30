"use client";

import { useEffect, useState, useRef } from "react";
import { Loader2, X, Upload, Camera, CheckCircle2, AlertCircle, Sparkles, FileSearch, AlertTriangle } from "lucide-react";
import {
  ClientDocument,
  ClientDocumentType,
  DOCUMENT_TYPE_LABELS,
  getMyDocuments,
  uploadDocument,
  deleteDocument,
  recognizeDocument,
  applyDocumentsToApplicant,
} from "@/lib/api";
import { StepHeader } from "@/components/ui/Form";

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
    ocrEnabled: false, // не распознаём, только хранение
  },
];

export function StepDocuments({ token, onSkip, onContinue }: Props) {
  const [documents, setDocuments] = useState<ClientDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recognizing, setRecognizing] = useState(false);
  const [recognizingDocId, setRecognizingDocId] = useState<number | null>(null);
  const [showReview, setShowReview] = useState(false);
  const [appliedFields, setAppliedFields] = useState<string[]>([]);

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

  async function handleUpload(type: ClientDocumentType, file: File) {
    setError(null);
    try {
      const newDoc = await uploadDocument(token, type, file);
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

    // Распознаём только те, у кого OCR ещё не делался или провалился
    // и тип поддерживает OCR
    const ocrEnabledTypes = SLOTS.filter((s) => s.ocrEnabled).map((s) => s.type);
    const docsToRecognize = documents.filter(
      (d) =>
        ocrEnabledTypes.includes(d.doc_type) &&
        d.status !== "ocr_done"
    );

    // Запускаем распознавание последовательно (избегаем rate limit)
    for (const doc of docsToRecognize) {
      setRecognizingDocId(doc.id);
      try {
        const updated = await recognizeDocument(token, doc.id);
        setDocuments((prev) =>
          prev.map((d) => (d.id === doc.id ? updated : d))
        );
      } catch (e) {
        // не останавливаемся — продолжаем со следующим документом
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

    // Проверяем результаты — есть ли успешные распознавания?
    const updated = await getMyDocuments(token);
    setDocuments(updated);

    const hasSuccessful = updated.some((d) => d.status === "ocr_done");
    if (hasSuccessful) {
      setShowReview(true);
    } else {
      setError(
        "Ни один документ не удалось распознать. Проверьте качество фотографий и попробуйте снова."
      );
    }
  }

  async function handleApplyAndContinue() {
    setError(null);
    try {
      const result = await applyDocumentsToApplicant(token);
      setAppliedFields(result.applied_fields);
      // Переход на следующий шаг (Личные данные)
      onContinue?.();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const uploadedCount = documents.length;
  const recognizedCount = documents.filter((d) => d.status === "ocr_done").length;
  const failedCount = documents.filter((d) => d.status === "ocr_failed").length;

  if (loading) {
    return (
      <div className="flex justify-center items-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-secondary" />
      </div>
    );
  }

  // === REVIEW MODE — показываем что распозналось ===
  if (showReview) {
    return (
      <ReviewMode
        documents={documents}
        onConfirm={handleApplyAndContinue}
        onBack={() => setShowReview(false)}
        error={error}
      />
    );
  }

  // === UPLOAD MODE ===
  return (
    <div>
      <StepHeader
        title="Документы"
        subtitle="Загрузите фотографии документов — мы автоматически заполним анкету за вас. Этот шаг можно пропустить."
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
          паспортов и диплома — мы их распознаем и заполним анкету за вас. Вы сможете
          проверить и поправить любые поля. Если документов под рукой нет — нажмите
          «Пропустить» и заполните вручную.
        </div>
      </div>

      <div className="space-y-3">
        {SLOTS.map((slot) => {
          const doc = findDoc(slot.type);
          const isThisRecognizing =
            recognizing && recognizingDocId === doc?.id;
          return (
            <DocumentSlot
              key={slot.type}
              slot={slot}
              doc={doc}
              isRecognizing={isThisRecognizing}
              onUpload={(file) => handleUpload(slot.type, file)}
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
          disabled={recognizing}
          className="px-5 py-2.5 rounded-md text-sm border border-tertiary text-secondary hover:bg-secondary disabled:opacity-50 transition-colors"
          style={{ borderWidth: 0.5 }}
        >
          Пропустить → заполнить вручную
        </button>

        <button
          onClick={handleRecognizeAll}
          disabled={uploadedCount === 0 || recognizing}
          className="px-5 py-2.5 rounded-md text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          style={{ background: "var(--color-accent)" }}
        >
          {recognizing ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Распознаём...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              {uploadedCount === 0
                ? "Загрузите хотя бы один документ"
                : `Распознать всё (${uploadedCount}) и заполнить анкету →`}
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// REVIEW MODE — показ распознанных полей перед применением
// =============================================================================

interface ReviewProps {
  documents: ClientDocument[];
  onConfirm: () => void;
  onBack: () => void;
  error: string | null;
}

const FIELD_LABELS: Record<string, string> = {
  // passport_internal_main
  last_name_native: "Фамилия (рус)",
  first_name_native: "Имя (рус)",
  middle_name_native: "Отчество",
  birth_date: "Дата рождения",
  birth_place_native: "Место рождения (рус)",
  sex: "Пол",
  passport_series: "Серия паспорта РФ",
  passport_number: "Номер паспорта",
  passport_issue_date: "Дата выдачи",
  passport_issuer: "Кем выдан",
  passport_issuer_code: "Код подразделения",
  // passport_internal_address
  registration_address: "Адрес регистрации",
  registration_date: "Дата регистрации",
  // passport_foreign
  last_name_latin: "Фамилия (лат)",
  first_name_latin: "Имя (лат)",
  birth_place_latin: "Место рождения (лат)",
  nationality: "Гражданство",
  passport_expiry_date: "Срок действия",
  // diploma
  institution: "Учебное заведение",
  graduation_year: "Год выпуска",
  degree: "Степень",
  specialty: "Специальность",
  diploma_number: "Номер диплома",
  diploma_series: "Серия диплома",
  issue_date: "Дата выдачи",
};

const SEX_LABELS: Record<string, string> = {
  H: "Мужской",
  M: "Женский",
};

const DEGREE_LABELS: Record<string, string> = {
  bachelor: "Бакалавр",
  specialist: "Специалист",
  master: "Магистр",
  phd: "Кандидат наук / Доктор наук",
  secondary: "Среднее специальное",
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
  if (field === "sex" && SEX_LABELS[value]) return SEX_LABELS[value];
  if (field === "degree" && DEGREE_LABELS[value]) return DEGREE_LABELS[value];
  return String(value);
}

function ReviewMode({ documents, onConfirm, onBack, error }: ReviewProps) {
  const ocrDoneDocs = documents.filter((d) => d.status === "ocr_done");
  const ocrFailedDocs = documents.filter((d) => d.status === "ocr_failed");

  return (
    <div>
      <StepHeader
        title="Что мы извлекли"
        subtitle="Проверьте распознанные данные. После подтверждения они появятся в полях анкеты — вы сможете их отредактировать."
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

      {/* Успешно распознанные */}
      {ocrDoneDocs.length > 0 && (
        <div className="space-y-4">
          {ocrDoneDocs.map((doc) => {
            const fields = Object.entries(doc.parsed_data || {}).filter(
              ([_, v]) => v !== null && v !== undefined && v !== ""
            );
            if (fields.length === 0 && doc.doc_type !== "diploma_apostille") {
              return (
                <div
                  key={doc.id}
                  className="p-4 rounded-lg border border-tertiary"
                  style={{ borderWidth: 0.5, background: "var(--color-bg-primary)" }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <AlertTriangle className="w-4 h-4" style={{ color: "var(--color-text-warning)" }} />
                    <span className="text-sm font-medium text-primary">
                      {DOC_SECTION_TITLES[doc.doc_type]}
                    </span>
                  </div>
                  <div className="text-xs text-tertiary">
                    Документ загружен, но ничего не удалось извлечь. Возможно фото плохого качества.
                  </div>
                </div>
              );
            }

            if (doc.doc_type === "diploma_apostille") {
              return (
                <div
                  key={doc.id}
                  className="p-4 rounded-lg border border-tertiary"
                  style={{ borderWidth: 0.5, background: "var(--color-bg-primary)" }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <CheckCircle2 className="w-4 h-4" style={{ color: "var(--color-text-success)" }} />
                    <span className="text-sm font-medium text-primary">
                      Апостиль сохранён
                    </span>
                  </div>
                  <div className="text-xs text-tertiary">
                    Файл будет приложен к заявке для подачи.
                  </div>
                </div>
              );
            }

            return (
              <div
                key={doc.id}
                className="p-4 rounded-lg border border-tertiary"
                style={{ borderWidth: 0.5, background: "var(--color-bg-primary)" }}
              >
                <div className="flex items-center gap-2 mb-3">
                  <FileSearch className="w-4 h-4" style={{ color: "var(--color-accent)" }} />
                  <span className="text-sm font-semibold text-primary">
                    {DOC_SECTION_TITLES[doc.doc_type]}
                  </span>
                </div>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  {fields.map(([key, value]) => (
                    <div key={key}>
                      <dt className="text-xs text-tertiary">
                        {FIELD_LABELS[key] || key}
                      </dt>
                      <dd className="text-primary">{formatValue(key, value)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            );
          })}
        </div>
      )}

      {/* Провалившиеся */}
      {ocrFailedDocs.length > 0 && (
        <div className="mt-4 space-y-2">
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

      {/* Информационная плашка */}
      <div
        className="mt-5 p-4 rounded-lg flex gap-3"
        style={{
          background: "var(--color-bg-secondary)",
          border: "0.5px solid var(--color-border-secondary)",
        }}
      >
        <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: "var(--color-text-success)" }} />
        <div className="text-sm text-secondary">
          После подтверждения распознанные поля появятся в анкете. Уже заполненные вами
          вручную поля <strong className="text-primary">не будут перезаписаны</strong>.
          Вы сможете отредактировать любое поле в следующих шагах.
        </div>
      </div>

      {/* Кнопки */}
      <div
        className="mt-8 pt-6 border-t border-tertiary flex flex-col sm:flex-row gap-3 justify-between"
        style={{ borderTopWidth: 0.5 }}
      >
        <button
          onClick={onBack}
          className="px-5 py-2.5 rounded-md text-sm border border-tertiary text-secondary hover:bg-secondary transition-colors"
          style={{ borderWidth: 0.5 }}
        >
          ← Назад к загрузке
        </button>

        <button
          onClick={onConfirm}
          disabled={ocrDoneDocs.length === 0}
          className="px-5 py-2.5 rounded-md text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          style={{ background: "var(--color-accent)" }}
        >
          <CheckCircle2 className="w-4 h-4" />
          Подтвердить и заполнить анкету →
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// DocumentSlot — слот для одного типа документа
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
  onUpload: (file: File) => Promise<void>;
  onDelete: (docId: number) => void;
}

function DocumentSlot({ slot, doc, isRecognizing, onUpload, onDelete }: DocumentSlotProps) {
  const [uploading, setUploading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setLocalError(null);

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
      "image/jpeg",
      "image/jpg",
      "image/png",
      "image/webp",
      "image/heic",
      "image/heif",
      "application/pdf",
    ];
    if (!allowedTypes.includes(file.type)) {
      setLocalError(`Неподдерживаемый формат: ${file.type}. Нужен JPEG, PNG или PDF.`);
      return;
    }

    setUploading(true);
    try {
      await onUpload(file);
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setUploading(false);
    }
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

  // Документ загружен — показываем превью + статус OCR
  if (doc) {
    const isImage = doc.content_type.startsWith("image/");
    const fileSizeKB = Math.round(doc.file_size / 1024);

    // Статус OCR
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
              📄<br />
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
          </div>
          <div className="text-xs text-tertiary mt-1 truncate">
            {doc.file_name} · {fileSizeKB} КБ
          </div>
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
    );
  }

  // Документа нет — зона загрузки
  return (
    <div
      className="rounded-lg border-dashed p-4 transition-colors"
      style={{
        borderWidth: 1.5,
        borderStyle: "dashed",
        borderColor: dragOver
          ? "var(--color-accent)"
          : "var(--color-border-secondary)",
        background: dragOver
          ? "var(--color-bg-secondary)"
          : "var(--color-bg-primary)",
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="text-sm font-medium text-primary mb-1">{slot.title}</div>
      <div className="text-xs text-tertiary mb-3">{slot.description}</div>

      {localError && (
        <div
          className="text-xs mb-2 flex gap-1.5 items-start"
          style={{ color: "var(--color-text-danger)" }}
        >
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

      <div className="text-xs text-tertiary mt-2">{slot.hint}</div>

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
  );
}
