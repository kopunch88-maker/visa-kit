"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Loader2,
  ArrowLeft,
  FileCheck2,
  AlertCircle,
  UploadCloud,
  Play,
  RefreshCw,
  ShieldCheck,
  Download,
} from "lucide-react";
import {
  getApplication,
  listFinalSubmissionDocuments,
  uploadFinalSubmissionDocuments,
  deleteFinalSubmissionDocument,
  replaceFinalSubmissionDocument,
  updateFinalSubmissionDocumentCategory,
  // Pack 39.0-E2
  runFinalSubmissionAudit,
  listFinalSubmissionAuditReports,
  getFinalSubmissionAuditReport,
  downloadFinalSubmissionAuditReportDocx,
  FINAL_AUDIT_CATEGORY_LABELS,
  type FinalSubmissionDocument,
  type FinalSubmissionDocCategory,
  type FinalSubmissionUploadResponse,
  type FinalSubmissionAuditReportWithFindings,
  type FinalSubmissionCategory,
  type FinalSubmissionFinding,
} from "@/lib/api";
import { FinalSubmissionDropZone } from "@/components/admin/FinalSubmissionDropZone";
import { FinalSubmissionDocumentCard } from "@/components/admin/FinalSubmissionDocumentCard";
import { FinalSubmissionVerdictBanner } from "@/components/admin/FinalSubmissionVerdictBanner";
import { FinalSubmissionFindingCard } from "@/components/admin/FinalSubmissionFindingCard";

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

  // Pack 39.0-E2: текущий отчёт аудита
  const [currentReport, setCurrentReport] =
    useState<FinalSubmissionAuditReportWithFindings | null>(null);
  const [startingAudit, setStartingAudit] = useState(false);
  const [downloadingDocx, setDownloadingDocx] = useState(false);

  // Pack 39.0-F: скачать DOCX
  async function handleDownloadDocx() {
    if (!currentReport) return;
    setDownloadingDocx(true);
    try {
      await downloadFinalSubmissionAuditReportDocx(currentReport.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloadingDocx(false);
    }
  }

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

        // Pack 39.0-E2: загрузить последний отчёт (если есть)
        try {
          const reports = await listFinalSubmissionAuditReports(app.applicant_id);
          if (!cancelled && reports.length > 0) {
            const latest = await getFinalSubmissionAuditReport(reports[0].id);
            if (!cancelled) setCurrentReport(latest);
          }
        } catch {
          // тихо игнорируем — нет отчётов это нормально
        }
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

  // Pack 39.0-E2: polling прогона аудита (если is_running=true)
  useEffect(() => {
    if (!currentReport || !currentReport.is_running) return;
    const interval = setInterval(async () => {
      try {
        const updated = await getFinalSubmissionAuditReport(currentReport.id);
        setCurrentReport(updated);
        if (!updated.is_running) {
          clearInterval(interval);
        }
      } catch {
        // тихо
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [currentReport?.id, currentReport?.is_running]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pack 39.0-E2: запустить аудит
  async function handleRunAudit() {
    if (applicantId === null) return;
    setStartingAudit(true);
    setError(null);
    try {
      const { report_id } = await runFinalSubmissionAudit(applicantId, applicationId);
      const fresh = await getFinalSubmissionAuditReport(report_id);
      setCurrentReport(fresh);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStartingAudit(false);
    }
  }

  // Pack 39.0-E2: перечитать текущий отчёт (после acknowledge/dismiss)
  async function reloadReport() {
    if (!currentReport) return;
    try {
      const fresh = await getFinalSubmissionAuditReport(currentReport.id);
      setCurrentReport(fresh);
    } catch (e) {
      setError((e as Error).message);
    }
  }

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

          {/* Pack 39.0-F: кнопка скачивания DOCX */}
          {currentReport &&
            !currentReport.is_running &&
            !currentReport.error && (
              <button
                onClick={handleDownloadDocx}
                disabled={downloadingDocx}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50 flex-shrink-0"
                style={{
                  background: "var(--color-bg-primary)",
                  color: "var(--color-text-secondary)",
                  border: "1px solid var(--color-border-secondary)",
                }}
                title="Скачать отчёт в формате Word (.docx)"
              >
                {downloadingDocx ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Download className="w-4 h-4" />
                )}
                Скачать DOCX
              </button>
            )}

          {/* Pack 39.0-E2: компактная кнопка прогона в хедере */}
          {documents.length > 0 && (
            <button
              onClick={handleRunAudit}
              disabled={startingAudit || (currentReport?.is_running ?? false)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 flex-shrink-0"
              style={{ background: "var(--color-accent)" }}
              title="Запустить новый прогон проверки"
            >
              {startingAudit || currentReport?.is_running ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : currentReport ? (
                <RefreshCw className="w-4 h-4" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {currentReport ? "Новый прогон" : "Запустить проверку"}
            </button>
          )}
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

            {/* Pack 39.0-E2: блок отчёта под списком документов */}
            {documents.length > 0 && (
              <div className="mt-8">
                {!currentReport ? (
                  <div
                    className="rounded-lg p-8 text-center"
                    style={{
                      background: "var(--color-bg-primary)",
                      border: "1px solid var(--color-border-tertiary)",
                    }}
                  >
                    <ShieldCheck
                      className="w-12 h-12 mx-auto mb-3"
                      style={{ color: "var(--color-accent)" }}
                    />
                    <h2
                      className="text-lg font-semibold mb-2"
                      style={{ color: "var(--color-text-primary)" }}
                    >
                      Запустить финальную проверку
                    </h2>
                    <p
                      className="text-sm mb-4 max-w-xl mx-auto"
                      style={{ color: "var(--color-text-secondary)" }}
                    >
                      AI-инспектор симулирует приём документов в консульстве:
                      сверит ФИО, даты, суммы, реквизиты компании, переводы
                      jurada и поищет хвосты прошлых клиентов в шаблонах.
                    </p>
                    <button
                      onClick={handleRunAudit}
                      disabled={startingAudit}
                      className="inline-flex items-center gap-2 px-6 py-3 rounded-md text-white font-medium disabled:opacity-50"
                      style={{ background: "var(--color-accent)" }}
                    >
                      {startingAudit ? (
                        <Loader2 className="w-5 h-5 animate-spin" />
                      ) : (
                        <Play className="w-5 h-5" />
                      )}
                      Запустить проверку
                    </button>
                    <p
                      className="text-xs mt-3"
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      Занимает 30-90 секунд. Стоимость ~$0.10.
                    </p>
                  </div>
                ) : currentReport.is_running ? (
                  <div
                    className="rounded-lg p-8 text-center"
                    style={{
                      background: "var(--color-bg-info)",
                      border: "1px solid var(--color-border-info)",
                    }}
                  >
                    <Loader2
                      className="w-12 h-12 mx-auto mb-3 animate-spin"
                      style={{ color: "var(--color-text-info)" }}
                    />
                    <h2
                      className="text-lg font-semibold mb-1"
                      style={{ color: "var(--color-text-info)" }}
                    >
                      Проверка идёт...
                    </h2>
                    <p
                      className="text-sm"
                      style={{ color: "var(--color-text-info)" }}
                    >
                      AI-инспектор анализирует пакет. Это займёт 30-90 секунд.
                    </p>
                  </div>
                ) : currentReport.error ? (
                  <div
                    className="rounded-lg p-6"
                    style={{
                      background: "var(--color-bg-danger)",
                      border: "1px solid var(--color-border-secondary)",
                    }}
                  >
                    <h2
                      className="text-lg font-semibold mb-2 flex items-center gap-2"
                      style={{ color: "var(--color-text-danger)" }}
                    >
                      <AlertCircle className="w-5 h-5" /> Ошибка проверки
                    </h2>
                    <p
                      className="text-sm whitespace-pre-wrap font-mono"
                      style={{ color: "var(--color-text-danger)" }}
                    >
                      {currentReport.error}
                    </p>
                    <button
                      onClick={handleRunAudit}
                      disabled={startingAudit}
                      className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-md text-white text-sm font-medium disabled:opacity-50"
                      style={{ background: "var(--color-text-danger)" }}
                    >
                      <RefreshCw className="w-4 h-4" /> Попробовать снова
                    </button>
                  </div>
                ) : (
                  <>
                    <FinalSubmissionVerdictBanner report={currentReport} />
                    {currentReport.findings.length === 0 ? (
                      <div
                        className="rounded-lg p-6 text-center"
                        style={{
                          background: "var(--color-bg-success)",
                          border: "1px solid var(--color-border-success)",
                        }}
                      >
                        <p
                          className="text-sm"
                          style={{ color: "var(--color-text-success)" }}
                        >
                          AI-инспектор не нашёл замечаний. Пакет готов к подаче.
                        </p>
                      </div>
                    ) : (
                      <FindingsByCategory
                        findings={currentReport.findings}
                        documents={currentReport.documents}
                        onResolved={reloadReport}
                      />
                    )}
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ====================================================================
// Pack 39.0-E2 — Группировка findings по категориям A-H
// ====================================================================

function FindingsByCategory({
  findings,
  documents,
  onResolved,
}: {
  findings: FinalSubmissionFinding[];
  documents: FinalSubmissionDocument[];
  onResolved: () => void;
}) {
  const docDownloadUrls: Record<string, string | null> = {};
  for (const d of documents) {
    docDownloadUrls[d.original_filename] = d.download_url;
  }

  const grouped: Record<string, FinalSubmissionFinding[]> = {};
  for (const f of findings) {
    if (!grouped[f.category]) grouped[f.category] = [];
    grouped[f.category].push(f);
  }

  const order: FinalSubmissionCategory[] = [
    "A_identity",
    "B_numeric",
    "C_dates",
    "D_company",
    "E_translation",
    "F_completeness",
    "G_quality",
    "H_stale",
  ];

  return (
    <div className="space-y-6">
      {order.map((cat) => {
        const items = grouped[cat];
        if (!items || items.length === 0) return null;
        const sorted = [...items].sort((a, b) => {
          const sevOrder = { critical: 0, warning: 1, info: 2 };
          const sevDiff = sevOrder[a.severity] - sevOrder[b.severity];
          if (sevDiff !== 0) return sevDiff;
          return a.sort_order - b.sort_order;
        });
        return (
          <section key={cat}>
            <h3
              className="text-sm font-semibold uppercase tracking-wide mb-2 flex items-center gap-2"
              style={{ color: "var(--color-text-secondary)" }}
            >
              {FINAL_AUDIT_CATEGORY_LABELS[cat]}
              <span
                className="text-xs font-normal"
                style={{ color: "var(--color-text-tertiary)" }}
              >
                ({sorted.length})
              </span>
            </h3>
            <div className="space-y-2">
              {sorted.map((f) => (
                <FinalSubmissionFindingCard
                  key={f.id}
                  finding={f}
                  docDownloadUrls={docDownloadUrls}
                  onResolved={onResolved}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
