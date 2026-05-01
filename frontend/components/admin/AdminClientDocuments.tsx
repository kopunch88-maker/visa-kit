"use client";

import { useEffect, useState } from "react";
import {
  Loader2, FileText, Image as ImageIcon, Download, RefreshCw,
  CheckCircle2, AlertCircle, Inbox, ExternalLink, Sparkles,
  X, FileWarning,
} from "lucide-react";
import {
  ClientDocument,
  ClientDocumentType,
  DOCUMENT_TYPE_LABELS,
  FIELD_LABELS,
  adminListClientDocuments,
  adminRecognizeClientDocument,
} from "@/lib/api";
import { pdfToImagePages, PdfPagePreview } from "@/lib/pdfConverter";

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
  const [pageSelectorDoc, setPageSelectorDoc] = useState<ClientDocument | null>(null);

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

  // Простое распознавание (для не-PDF или когда страница не нужна)
  async function handleRecognizeSimple(docId: number) {
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

  // Распознавание с выбранной страницей PDF
  async function handleRecognizeWithPage(docId: number, pageNum: number) {
    setRecognizingId(docId);
    setError(null);
    try {
      const updated = await adminRecognizeClientDocument(applicationId, docId, pageNum);
      setDocuments((prev) => prev.map((d) => (d.id === docId ? updated : d)));
      setPageSelectorDoc(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRecognizingId(null);
    }
  }

  // Обработчик клика по «Распознать» / «↻»: для PDF — открыть пикер страниц, иначе сразу
  function handleRecognizeClick(doc: ClientDocument) {
    if (doc.has_original && doc.original_download_url) {
      // Это PDF, у которого есть оригинал. Открываем выбор страницы.
      setPageSelectorDoc(doc);
    } else {
      // Не-PDF или PDF без оригинала — стандартный путь
      handleRecognizeSimple(doc.id);
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
            Загружено клиентом через личный кабинет или импортом пакета
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
              onRecognize={() => handleRecognizeClick(doc)}
            />
          ))}
        </div>
      )}

      {/* Pack 14b+c finishing: модалка выбора страницы PDF */}
      {pageSelectorDoc && (
        <PdfPageSelector
          doc={pageSelectorDoc}
          isRecognizing={recognizingId === pageSelectorDoc.id}
          onClose={() => setPageSelectorDoc(null)}
          onSelect={(page) => handleRecognizeWithPage(pageSelectorDoc.id, page)}
        />
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

  const parsedFields = Object.entries(doc.parsed_data || {}).filter(
    ([_, v]) => v !== null && v !== undefined && v !== "",
  );

  const isApostille = doc.doc_type === "diploma_apostille";
  const isPdf = doc.has_original; // doc has original PDF saved

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

        {/* Распознанные поля */}
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

        {isApostille && doc.status === "ocr_done" && (
          <div className="text-xs text-tertiary italic mb-2">
            Апостиль распознавать не нужно — файл сохранён для подачи
          </div>
        )}

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
                title={
                  isPdf
                    ? "Открыть выбор страницы и распознать"
                    : "Запустить OCR для этого документа"
                }
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
                    {isPdf ? " (выбор стр.)" : ""}
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
              title={
                isPdf
                  ? "Распознать другую страницу PDF"
                  : "Распознать заново"
              }
            >
              {isRecognizing ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <>
                  <RefreshCw className="w-3 h-3" />
                  {isPdf && <span className="ml-1">Выбрать стр.</span>}
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


// =============================================================================
// PDF Page Selector Modal (Pack 14b+c finishing)
// =============================================================================

function PdfPageSelector({
  doc,
  isRecognizing,
  onClose,
  onSelect,
}: {
  doc: ClientDocument;
  isRecognizing: boolean;
  onClose: () => void;
  onSelect: (pageNum: number) => void;
}) {
  const [pages, setPages] = useState<PdfPagePreview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<number>(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function loadPages() {
      if (!doc.original_download_url) {
        setLoadError("Оригинальный PDF недоступен");
        setLoading(false);
        return;
      }
      try {
        const res = await fetch(doc.original_download_url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const result = await pdfToImagePages(blob, { dpi: 100, maxPages: 30 });
        if (!cancelled) {
          setPages(result);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError((e as Error).message);
          setLoading(false);
        }
      }
    }
    loadPages();
    return () => {
      cancelled = true;
    };
  }, [doc.original_download_url]);

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
            <FileText className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
            <span className="text-base font-semibold text-primary">
              Выбор страницы для распознавания
            </span>
          </div>
          <button
            onClick={onClose}
            disabled={isRecognizing}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors text-tertiary disabled:opacity-50"
            aria-label="Закрыть"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-5">
          <div className="text-xs text-tertiary mb-3">
            {doc.original_file_name || doc.file_name} · Кликните страницу с данными,
            затем «Распознать выбранную страницу».
          </div>

          {loading && (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
              <div className="text-sm text-tertiary">Конвертируем страницы PDF...</div>
            </div>
          )}

          {loadError && (
            <div
              className="p-3 rounded-md text-sm flex gap-2 items-start"
              style={{
                background: "var(--color-bg-danger)",
                color: "var(--color-text-danger)",
                border: "0.5px solid var(--color-border-danger)",
              }}
            >
              <FileWarning className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>Не удалось загрузить превью: {loadError}</span>
            </div>
          )}

          {pages && pages.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {pages.map((p) => {
                const selected = selectedPage === p.pageNum;
                return (
                  <button
                    key={p.pageNum}
                    onClick={() => setSelectedPage(p.pageNum)}
                    disabled={isRecognizing}
                    className="relative rounded-md overflow-hidden text-left transition-all disabled:opacity-50"
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
                      className="absolute bottom-0 left-0 right-0 px-2 py-1 text-xs font-medium text-center"
                      style={{
                        background: selected
                          ? "var(--color-accent)"
                          : "rgba(0,0,0,0.6)",
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

        {/* Footer */}
        <div
          className="px-5 py-4 border-t flex justify-between gap-3"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderTopWidth: 0.5,
          }}
        >
          <button
            onClick={onClose}
            disabled={isRecognizing}
            className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors disabled:opacity-50"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
          >
            Отмена
          </button>
          <button
            onClick={() => onSelect(selectedPage)}
            disabled={isRecognizing || loading || !pages}
            className="px-5 py-2 rounded-md text-sm font-medium text-white transition-colors flex items-center gap-2 disabled:opacity-50"
            style={{ background: "var(--color-accent)" }}
          >
            {isRecognizing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Распознаём страницу {selectedPage}...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Распознать страницу {selectedPage}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
