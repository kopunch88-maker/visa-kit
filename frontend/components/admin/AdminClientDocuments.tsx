"use client";

import { useEffect, useState } from "react";
import {
  Loader2, FileText, Image as ImageIcon, Download, RefreshCw,
  CheckCircle2, AlertCircle, Inbox, ExternalLink, Sparkles,
} from "lucide-react";
import {
  ClientDocument,
  ClientDocumentType,
  DOCUMENT_TYPE_LABELS,
  FIELD_LABELS,
  adminListClientDocuments,
  adminRecognizeClientDocument,
} from "@/lib/api";

interface Props {
  applicationId: number;
}

const SEX_LABELS: Record<string, string> = { H: "Мужской", M: "Женский" };
const DEGREE_LABELS: Record<string, string> = {
  bachelor: "Бакалавр",
  specialist: "Специалист",
  master: "Магистр",
  phd: "Кандидат / Доктор наук",
  secondary: "Среднее специальное",
};

function formatValue(field: string, value: any): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "sex" && SEX_LABELS[value]) return SEX_LABELS[value];
  if (field === "degree" && DEGREE_LABELS[value]) return DEGREE_LABELS[value];
  return String(value);
}

const STATUS_LABELS: Record<string, string> = {
  uploaded: "Загружен",
  ocr_pending: "Распознаётся...",
  ocr_done: "Распознан",
  ocr_failed: "Ошибка распознавания",
};

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  uploaded: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
  ocr_pending: { bg: "var(--color-bg-info)", text: "var(--color-text-info)" },
  ocr_done: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  ocr_failed: { bg: "var(--color-bg-danger)", text: "var(--color-text-danger)" },
};

export function AdminClientDocuments({ applicationId }: Props) {
  const [documents, setDocuments] = useState<ClientDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recognizingId, setRecognizingId] = useState<number | null>(null);

  async function load() {
    setError(null);
    try {
      const docs = await adminListClientDocuments(applicationId);
      setDocuments(docs);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  async function handleRecognize(docId: number) {
    setRecognizingId(docId);
    setError(null);
    try {
      const updated = await adminRecognizeClientDocument(applicationId, docId);
      setDocuments((prev) => prev.map((d) => (d.id === docId ? updated : d)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRecognizingId(null);
    }
  }

  return (
    <div
      className="bg-primary rounded-xl border p-5"
      style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h3 className="text-base font-semibold text-primary mb-0.5">
            Документы клиента
          </h3>
          <div className="text-xs text-tertiary">
            Загружено клиентом через личный кабинет
          </div>
        </div>
        <button
          onClick={() => {
            setLoading(true);
            load();
          }}
          disabled={loading}
          className="text-xs px-2.5 py-1 rounded-md border text-secondary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderWidth: 0.5,
          }}
          title="Обновить список"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          Обновить
        </button>
      </div>

      {error && (
        <div
          className="mb-3 p-3 rounded-md text-sm flex gap-2 items-start"
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

      {loading && documents.length === 0 ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-tertiary" />
        </div>
      ) : documents.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          {documents.map((doc) => (
            <DocumentCard
              key={doc.id}
              doc={doc}
              isRecognizing={recognizingId === doc.id}
              onRecognize={() => handleRecognize(doc.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}


function EmptyState() {
  return (
    <div
      className="rounded-md p-6 text-center"
      style={{
        background: "var(--color-bg-secondary)",
        border: "0.5px dashed var(--color-border-secondary)",
      }}
    >
      <Inbox className="w-8 h-8 text-tertiary mx-auto mb-2" />
      <div className="text-sm text-secondary mb-1">Документов нет</div>
      <div className="text-xs text-tertiary">
        Клиент пропустил Шаг 0 «Документы» или ещё не зашёл в кабинет
      </div>
    </div>
  );
}


function DocumentCard({
  doc,
  isRecognizing,
  onRecognize,
}: {
  doc: ClientDocument;
  isRecognizing: boolean;
  onRecognize: () => void;
}) {
  const statusColor = STATUS_COLORS[doc.status] || STATUS_COLORS.uploaded;
  const isImage = doc.content_type.startsWith("image/");
  const fileSizeKB = Math.round(doc.file_size / 1024);
  const docTypeLabel =
    DOCUMENT_TYPE_LABELS[doc.doc_type as ClientDocumentType] || doc.doc_type;

  // Список распознанных полей с непустыми значениями
  const parsedFields = Object.entries(doc.parsed_data || {}).filter(
    ([_, v]) => v !== null && v !== undefined && v !== "",
  );

  // Apostille — особый случай: parsed_data пустой по дизайну
  const isApostille = doc.doc_type === "diploma_apostille";

  return (
    <div
      className="rounded-md p-3 flex gap-3"
      style={{
        border: "0.5px solid var(--color-border-tertiary)",
        background: "var(--color-bg-primary)",
      }}
    >
      {/* Превью */}
      <div
        className="w-24 h-24 flex-shrink-0 rounded-md overflow-hidden flex items-center justify-center"
        style={{
          background: "var(--color-bg-secondary)",
          border: "0.5px solid var(--color-border-secondary)",
        }}
      >
        {isImage && doc.download_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <a
            href={doc.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full h-full block"
            title="Открыть в полном размере"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={doc.download_url}
              alt={docTypeLabel}
              className="w-full h-full object-cover"
            />
          </a>
        ) : (
          <FileText className="w-8 h-8 text-tertiary" />
        )}
      </div>

      {/* Содержимое */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span className="text-sm font-medium text-primary">{docTypeLabel}</span>
          <span
            className="text-xs px-2 py-0.5 rounded-full inline-flex items-center gap-1"
            style={{ background: statusColor.bg, color: statusColor.text }}
          >
            {doc.status === "ocr_pending" && (
              <Loader2 className="w-3 h-3 animate-spin" />
            )}
            {doc.status === "ocr_done" && <CheckCircle2 className="w-3 h-3" />}
            {doc.status === "ocr_failed" && <AlertCircle className="w-3 h-3" />}
            {STATUS_LABELS[doc.status] || doc.status}
          </span>
          {doc.applied_to_applicant && (
            <span
              className="text-xs px-2 py-0.5 rounded-full inline-flex items-center gap-1"
              style={{
                background: "var(--color-bg-success)",
                color: "var(--color-text-success)",
              }}
              title="Распознанные данные применены к анкете клиента"
            >
              <Sparkles className="w-3 h-3" />
              Применено
            </span>
          )}
        </div>

        <div className="text-xs text-tertiary mb-2 truncate">
          {doc.file_name} · {fileSizeKB} КБ
        </div>

        {/* Распознанные поля (если есть) */}
        {doc.status === "ocr_done" && parsedFields.length > 0 && !isApostille && (
          <details className="mb-2">
            <summary
              className="text-xs cursor-pointer hover:text-primary"
              style={{ color: "var(--color-text-info)" }}
            >
              Распознанные поля ({parsedFields.length})
            </summary>
            <dl className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-1 text-xs">
              {parsedFields.map(([key, value]) => (
                <div key={key} className="flex gap-1.5">
                  <dt className="text-tertiary">
                    {FIELD_LABELS[key] || key}:
                  </dt>
                  <dd className="text-secondary break-words">
                    {formatValue(key, value)}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        )}

        {/* Apostille — только notice */}
        {isApostille && doc.status === "ocr_done" && (
          <div className="text-xs text-tertiary italic mb-2">
            Апостиль распознавать не нужно — файл сохранён для подачи
          </div>
        )}

        {/* OCR error */}
        {doc.status === "ocr_failed" && doc.ocr_error && (
          <div
            className="text-xs mb-2 p-2 rounded"
            style={{
              background: "var(--color-bg-danger)",
              color: "var(--color-text-danger)",
            }}
          >
            {doc.ocr_error}
          </div>
        )}

        {/* Действия */}
        <div className="flex flex-wrap gap-1.5">
          {doc.download_url && (
            <a
              href={doc.download_url}
              target="_blank"
              rel="noopener noreferrer"
              download={doc.file_name}
              className="text-xs px-2.5 py-1 rounded-md border text-secondary hover:bg-secondary transition-colors flex items-center gap-1"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
            >
              <Download className="w-3 h-3" />
              {isImage ? "Скачать фото" : "Скачать"}
            </a>
          )}

          {doc.has_original && doc.original_download_url && (
            <a
              href={doc.original_download_url}
              target="_blank"
              rel="noopener noreferrer"
              download={doc.original_file_name || undefined}
              className="text-xs px-2.5 py-1 rounded-md border text-secondary hover:bg-secondary transition-colors flex items-center gap-1"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
              title="Оригинальный PDF файл (для отправки в финальную инстанцию)"
            >
              <FileText className="w-3 h-3" />
              Скачать оригинал PDF
            </a>
          )}

          {!isApostille &&
            (doc.status === "ocr_failed" || doc.status === "uploaded") && (
              <button
                onClick={onRecognize}
                disabled={isRecognizing}
                className="text-xs px-2.5 py-1 rounded-md text-white disabled:opacity-50 transition-colors flex items-center gap-1"
                style={{ background: "var(--color-accent)" }}
                title="Запустить OCR для этого документа"
              >
                {isRecognizing ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Распознаём...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3 h-3" />
                    {doc.status === "ocr_failed" ? "Попробовать снова" : "Распознать"}
                  </>
                )}
              </button>
            )}

          {doc.status === "ocr_done" && !isApostille && (
            <button
              onClick={onRecognize}
              disabled={isRecognizing}
              className="text-xs px-2.5 py-1 rounded-md border text-tertiary hover:bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
              title="Распознать заново"
            >
              {isRecognizing ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <RefreshCw className="w-3 h-3" />
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
