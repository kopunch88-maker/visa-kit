"use client";

import { useEffect, useState, useRef } from "react";
import { Loader2, X, Upload, Camera, CheckCircle2, AlertCircle, Sparkles } from "lucide-react";
import {
  ClientDocument,
  ClientDocumentType,
  DOCUMENT_TYPE_LABELS,
  getMyDocuments,
  uploadDocument,
  deleteDocument,
} from "@/lib/api";
import { StepHeader } from "@/components/ui/Form";

interface Props {
  token: string;
  onSkip?: () => void;
  onContinue?: () => void;
}

// Слоты документов в нужном порядке
const SLOTS: Array<{
  type: ClientDocumentType;
  title: string;
  description: string;
  hint: string;
}> = [
  {
    type: "passport_internal_main",
    title: "Паспорт РФ — главная страница",
    description: "Разворот с фотографией и ФИО",
    hint: "Сделайте фото первой страницы паспорта (с фото). Нужно для извлечения ФИО, даты рождения, серии и номера.",
  },
  {
    type: "passport_internal_address",
    title: "Паспорт РФ — страница прописки",
    description: "Страница 5 — где штамп о регистрации",
    hint: "Сделайте фото страницы с пропиской. Нужно для извлечения адреса регистрации.",
  },
  {
    type: "passport_foreign",
    title: "Загранпаспорт",
    description: "Страница с фотографией и данными",
    hint: "Главный разворот загранпаспорта. Нужны латинские ФИО, номер, срок действия.",
  },
  {
    type: "diploma_main",
    title: "Диплом — основная страница",
    description: "Лист с указанием ВУЗа и специальности",
    hint: "Скан или фото диплома. Нужны название ВУЗа, год выпуска, специальность.",
  },
  {
    type: "diploma_apostille",
    title: "Диплом — апостиль",
    description: "Страница с апостилем",
    hint: "Если апостиль на отдельном листе или странице.",
  },
];

export function StepDocuments({ token, onSkip, onContinue }: Props) {
  const [documents, setDocuments] = useState<ClientDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Загружаем существующие документы
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

  // Найти документ по типу
  const findDoc = (type: ClientDocumentType) =>
    documents.find((d) => d.doc_type === type);

  async function handleUpload(type: ClientDocumentType, file: File) {
    setError(null);
    try {
      const newDoc = await uploadDocument(token, type, file);
      // Заменяем в стейте — если был такой же тип, заменяется
      setDocuments((prev) => [
        ...prev.filter((d) => d.doc_type !== type),
        newDoc,
      ]);
    } catch (e) {
      setError((e as Error).message);
      throw e; // пробрасываем чтобы слот мог обработать локально
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

  function handleRecognize() {
    // Pack 13.0b — заглушка
    alert(
      "Функция распознавания будет доступна в следующем обновлении.\n\n" +
      "Сейчас вы можете загрузить документы, а затем заполнить анкету вручную.\n" +
      "Менеджер увидит ваши сканы и сможет с ними сверяться при оформлении."
    );
  }

  const uploadedCount = documents.length;

  if (loading) {
    return (
      <div className="flex justify-center items-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-secondary" />
      </div>
    );
  }

  return (
    <div>
      <StepHeader
        title="Документы"
        subtitle="Загрузите фотографии документов — мы автоматически заполним анкету за вас. Этот шаг можно пропустить."
      />

      {error && (
        <div
          className="mb-4 p-3 rounded-md text-sm"
          style={{
            background: "var(--color-bg-danger)",
            color: "var(--color-text-danger)",
            border: "0.5px solid var(--color-border-danger)",
          }}
        >
          {error}
        </div>
      )}

      {/* Информационная плашка */}
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
          паспортов и диплома — анкета заполнится автоматически. Вы сможете проверить и
          поправить любые поля. Если документов под рукой нет — нажмите «Пропустить» и
          заполните вручную.
        </div>
      </div>

      {/* Слоты документов */}
      <div className="space-y-3">
        {SLOTS.map((slot) => (
          <DocumentSlot
            key={slot.type}
            slot={slot}
            doc={findDoc(slot.type)}
            onUpload={(file) => handleUpload(slot.type, file)}
            onDelete={(docId) => handleDelete(docId)}
          />
        ))}
      </div>

      {/* Кнопки внизу */}
      <div
        className="mt-8 pt-6 border-t border-tertiary flex flex-col sm:flex-row gap-3 justify-between"
        style={{ borderTopWidth: 0.5 }}
      >
        <button
          onClick={onSkip}
          className="px-5 py-2.5 rounded-md text-sm border border-tertiary text-secondary hover:bg-secondary transition-colors"
          style={{ borderWidth: 0.5 }}
        >
          Пропустить → заполнить вручную
        </button>

        <button
          onClick={handleRecognize}
          disabled={uploadedCount === 0}
          className="px-5 py-2.5 rounded-md text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          style={{ background: "var(--color-accent)" }}
        >
          <Sparkles className="w-4 h-4" />
          {uploadedCount === 0
            ? "Загрузите хотя бы один документ"
            : `Распознать всё (${uploadedCount}) и заполнить анкету →`}
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
  };
  doc?: ClientDocument;
  onUpload: (file: File) => Promise<void>;
  onDelete: (docId: number) => void;
}

function DocumentSlot({ slot, doc, onUpload, onDelete }: DocumentSlotProps) {
  const [uploading, setUploading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setLocalError(null);

    // Базовая валидация на фронте
    const MAX_SIZE = 10 * 1024 * 1024; // 10 МБ
    const MIN_SIZE = 100 * 1024; // 100 КБ

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
    e.target.value = ""; // reset чтобы можно было выбрать тот же файл
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

  // Если документ загружен — показываем превью
  if (doc) {
    const isImage = doc.content_type.startsWith("image/");
    const fileSizeKB = Math.round(doc.file_size / 1024);

    return (
      <div
        className="rounded-lg border border-tertiary p-3 flex gap-3 items-start"
        style={{
          borderWidth: 0.5,
          background: "var(--color-bg-primary)",
        }}
      >
        {/* Превью или иконка */}
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
              {doc.content_type.split("/")[1].toUpperCase()}
            </div>
          )}
        </div>

        {/* Описание */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: "var(--color-text-success)" }} />
            <span className="text-sm font-medium text-primary truncate">
              {slot.title}
            </span>
          </div>
          <div className="text-xs text-tertiary mt-1 truncate">
            {doc.file_name} · {fileSizeKB} КБ
          </div>
          <div className="flex gap-2 mt-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="text-xs px-2.5 py-1 rounded-md border border-tertiary text-secondary hover:bg-secondary disabled:opacity-50 transition-colors"
              style={{ borderWidth: 0.5 }}
            >
              {uploading ? <Loader2 className="w-3 h-3 animate-spin" /> : "Заменить"}
            </button>
            <button
              onClick={() => onDelete(doc.id)}
              disabled={uploading}
              className="text-xs px-2.5 py-1 rounded-md text-danger hover:bg-secondary disabled:opacity-50 transition-colors"
            >
              Удалить
            </button>
          </div>
        </div>

        {/* Hidden inputs */}
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

  // Если документа нет — показываем зону загрузки
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
