"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Loader2,
  ArrowLeft,
  FileCheck2,
  AlertCircle,
  UploadCloud,
} from "lucide-react";
import {
  getApplication,
  listFinalSubmissionDocuments,
  uploadFinalSubmissionDocuments,
  deleteFinalSubmissionDocument,
  replaceFinalSubmissionDocument,
  updateFinalSubmissionDocumentCategory,
  type FinalSubmissionDocument,
  type FinalSubmissionDocCategory,
  type FinalSubmissionUploadResponse,
} from "@/lib/api";
import { FinalSubmissionDropZone } from "@/components/admin/FinalSubmissionDropZone";
import { FinalSubmissionDocumentCard } from "@/components/admin/FinalSubmissionDocumentCard";

/**
 * Pack 39.0-E1 — страница финальной проверки физических документов.
 *
 * Маршрут: /admin/applications/[id]/final-check
 *
 * Логика:
 * 1. По id заявки получаем applicant_id через getApplication.
 * 2. Грузим список активных документов клиента.
 * 3. Drag&drop зона: загрузить N файлов (multipart, ZIP распаковывается).
 * 4. Polling каждые 5 секунд — extraction крутится в фоне, doc_category появится позже.
 * 5. Inline-edit категории на каждой карточке.
 * 6. Кнопки: скачать, заменить (UploadFile), удалить (soft).
 *
 * Pack 39.0-E2 (next): добавит кнопку "Запустить финальную проверку" + страницу findings.
 */
export default function FinalCheckPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const applicationId = parseInt(params.id, 10);

  const [applicantId, setApplicantId] = useState<number | null>(null);
  const [applicantName, setApplicantName] = useState<string>("");
  const [documents, setDocuments] = useState<FinalSubmissionDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<FinalSubmissionUploadResponse | null>(null);

  // 1. Initial load: applicant_id + documents
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const app = await getApplication(applicationId);
        if (cancelled) return;
        if (!app.applicant_id) {
          setError("В заявке не указан клиент (applicant_id)");
          return;
        }
        setApplicantId(app.applicant_id);
        setApplicantName(`Заявка ${app.reference} · Клиент #${app.applicant_id}`);
        const docs = await listFinalSubmissionDocuments(app.applicant_id);
        if (cancelled) return;
        setDocuments(docs);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applicationId]);

  // 2. Polling каждые 5 сек — extraction в фоне обновит doc_category/extracted_text
  useEffect(() => {
    if (applicantId === null) return;
    // Если все документы уже имеют категорию — polling не нужен
    const allClassified = documents.every(
      (d) => d.doc_category !== null && d.extraction_method !== null
    );
    if (allClassified && documents.length > 0) return;

    const interval = setInterval(async () => {
      try {
        const docs = await listFinalSubmissionDocuments(applicantId);
        setDocuments(docs);
      } catch {
        // Тихо пропускаем — следующий тик попробует снова
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [applicantId, documents]);

  // Обновить документы вручную
  const reload = useCallback(async () => {
    if (applicantId === null) return;
    try {
      const docs = await listFinalSubmissionDocuments(applicantId);
      setDocuments(docs);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [applicantId]);

  // Upload handler
  async function handleUpload(files: File[]) {
    if (applicantId === null) return;
    setUploading(true);
    setError(null);
    setUploadResult(null);
    try {
      const result = await uploadFinalSubmissionDocuments(
        applicantId,
        files,
        applicationId
      );
      setUploadResult(result);
      // Обновим список
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  // Delete handler
  async function handleDelete(docId: number, hard: boolean) {
    if (applicantId === null) return;
    const confirmText = hard
      ? "Удалить файл навсегда (вместе с R2)?"
      : "Скрыть документ из списка? Файл останется в истории.";
    if (!confirm(confirmText)) return;
    try {
      await deleteFinalSubmissionDocument(applicantId, docId, hard);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // Replace handler
  async function handleReplace(docId: number, newFile: File, keepCategory: boolean) {
    if (applicantId === null) return;
    try {
      await replaceFinalSubmissionDocument(applicantId, docId, newFile, keepCategory);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // Category change handler
  async function handleCategoryChange(
    docId: number,
    category: FinalSubmissionDocCategory
  ) {
    if (applicantId === null) return;
    try {
      await updateFinalSubmissionDocumentCategory(applicantId, docId, category);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--color-bg-tertiary)" }}>
      <div className="max-w-5xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() =>
                router.push(`/admin?id=${applicationId}`)
              }
              className="p-2 rounded-md hover:bg-secondary"
              style={{ color: "var(--color-text-secondary)" }}
              title="Вернуться к заявке"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1
                className="text-xl font-bold flex items-center gap-2"
                style={{ color: "var(--color-text-primary)" }}
              >
                <FileCheck2 className="w-6 h-6" style={{ color: "var(--color-accent)" }} />
                Финальная проверка
              </h1>
              <p className="text-xs" style={{ color: "var(--color-text-tertiary)" }}>
                Заявка #{applicationId}
                {applicantName ? ` · ${applicantName}` : ""}
              </p>
            </div>
          </div>
        </div>

        {/* Глобальная ошибка */}
        {error && (
          <div
            className="px-4 py-3 rounded-md mb-4 text-sm flex items-start gap-2"
            style={{
              background: "var(--color-bg-danger)",
              color: "var(--color-text-danger)",
              border: "1px solid var(--color-border-secondary)",
            }}
          >
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Загрузка */}
        {loading ? (
          <div
            className="flex items-center justify-center py-20"
            style={{ color: "var(--color-text-secondary)" }}
          >
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Загрузка...
          </div>
        ) : (
          <>
            {/* Drop zone */}
            <FinalSubmissionDropZone
              uploading={uploading}
              onUpload={handleUpload}
            />

            {/* Результат последней загрузки */}
            {uploadResult && (
              <div className="mt-3 mb-4">
                {uploadResult.uploaded.length > 0 && (
                  <div
                    className="text-sm px-3 py-2 rounded-md mb-2"
                    style={{
                      background: "var(--color-bg-success)",
                      color: "var(--color-text-success)",
                    }}
                  >
                    ✓ Загружено: {uploadResult.uploaded.length}{" "}
                    {uploadResult.uploaded.length === 1 ? "файл" : "файла(ов)"}
                  </div>
                )}
                {uploadResult.skipped_duplicates.length > 0 && (
                  <div
                    className="text-sm px-3 py-2 rounded-md mb-2"
                    style={{
                      background: "var(--color-bg-warning)",
                      color: "var(--color-text-warning)",
                    }}
                  >
                    ⚠ Дубли (уже загружены ранее):{" "}
                    {uploadResult.skipped_duplicates.join(", ")}
                  </div>
                )}
                {uploadResult.errors.length > 0 && (
                  <div
                    className="text-sm px-3 py-2 rounded-md"
                    style={{
                      background: "var(--color-bg-danger)",
                      color: "var(--color-text-danger)",
                    }}
                  >
                    ✗ Ошибки:
                    <ul className="list-disc list-inside mt-1">
                      {uploadResult.errors.map((e, i) => (
                        <li key={i}>
                          <span className="font-mono">{e.filename}</span>: {e.error}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Список документов */}
            <div className="mt-6">
              <div className="flex items-center justify-between mb-3">
                <h2
                  className="text-sm font-semibold uppercase tracking-wide"
                  style={{ color: "var(--color-text-secondary)" }}
                >
                  Документы клиента ({documents.length})
                </h2>
              </div>

              {documents.length === 0 ? (
                <div
                  className="rounded-lg p-12 text-center"
                  style={{
                    background: "var(--color-bg-primary)",
                    border: "1px dashed var(--color-border-secondary)",
                  }}
                >
                  <UploadCloud
                    className="w-12 h-12 mx-auto mb-3"
                    style={{ color: "var(--color-text-tertiary)" }}
                  />
                  <p style={{ color: "var(--color-text-secondary)" }}>
                    Загрузите физические документы клиента — паспорт, договор, акты,
                    переводы jurada, апостили и т.д.
                  </p>
                  <p
                    className="text-xs mt-2"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    AI автоматически определит категорию каждого документа за 10-30
                    секунд после загрузки.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <FinalSubmissionDocumentCard
                      key={doc.id}
                      doc={doc}
                      onDelete={(hard) => handleDelete(doc.id, hard)}
                      onReplace={(file, keep) => handleReplace(doc.id, file, keep)}
                      onCategoryChange={(cat) => handleCategoryChange(doc.id, cat)}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
