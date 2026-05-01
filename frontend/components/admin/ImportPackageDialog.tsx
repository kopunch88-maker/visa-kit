"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Loader2, X, Upload, FileText, AlertCircle, CheckCircle2,
  Sparkles, FileWarning, Package, ArrowLeft, Building2, AlertTriangle,
  SkipForward,
} from "lucide-react";
import {
  ClientDocumentType,
  DOCUMENT_TYPE_LABELS,
  ImportFileMeta,
  ImportSession,
  ImportFileAssignment,
  ImportFinalizeResult,
  ApplicationResponse,
  PendingCompanyData,
  CompanyCreatePayload,
  importPackageUpload,
  importPackageFinalize,
  importPackageFinalizeWithCompany,
  importPackageFinalizeSkipCompany,
  importPackageCancel,
} from "@/lib/api";
import {
  pdfToImagePages,
  PdfPagePreview,
} from "@/lib/pdfConverter";

interface Props {
  applications: ApplicationResponse[];
  onClose: () => void;
  onImported: (result: ImportFinalizeResult) => void;
}

type FileChoice = {
  fileId: string;
  docType: ClientDocumentType | "skip";
  pdfPage: number;
  pdfPagesPreviews?: PdfPagePreview[];
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
  { value: "egryl_extract", label: DOCUMENT_TYPE_LABELS.egryl_extract },
  { value: "diploma_main", label: DOCUMENT_TYPE_LABELS.diploma_main },
  { value: "diploma_apostille", label: DOCUMENT_TYPE_LABELS.diploma_apostille },
  { value: "other", label: DOCUMENT_TYPE_LABELS.other },
];

type Step = "upload" | "classify" | "company" | "submitting" | "done";

export function ImportPackageDialog({ applications, onClose, onImported }: Props) {
  const [step, setStep] = useState<Step>("upload");
  const [error, setError] = useState<string | null>(null);
  const [importSession, setImportSession] = useState<ImportSession | null>(null);
  const [choices, setChoices] = useState<Record<string, FileChoice>>({});

  const [target, setTarget] = useState<"new" | "existing">("new");
  const [internalNotes, setInternalNotes] = useState("");
  const [existingApplicationId, setExistingApplicationId] = useState<number | null>(null);

  // Pack 14b — данные для второго шага (создание компании)
  const [pendingCompany, setPendingCompany] = useState<PendingCompanyData | null>(null);
  const [companyForm, setCompanyForm] = useState<CompanyCreatePayload | null>(null);

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

    setStep("submitting");
    try {
      const session = await importPackageUpload(file);
      setImportSession(session);

      // Pack 14c — Автоматически проставляем типы из ИИ-классификатора
      const initialChoices: Record<string, FileChoice> = {};
      session.files.forEach((f) => {
        let autoType: ClientDocumentType | "skip" = "skip";
        if (f.classified_type && f.classifier_confidence) {
          // Проставляем для high и medium (с пометкой)
          if (f.classifier_confidence === "high" || f.classifier_confidence === "medium") {
            autoType = f.classified_type;
          }
          // low — оставляем skip, менеджер выберет вручную
        }
        initialChoices[f.file_id] = {
          fileId: f.file_id,
          docType: autoType,
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
      const res = await fetch(file.preview_url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
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

  function buildAssignments(): ImportFileAssignment[] {
    if (!importSession) return [];
    return Object.values(choices).map((c) => {
      const file = importSession.files.find((f) => f.file_id === c.fileId);
      return {
        file_id: c.fileId,
        doc_type: c.docType,
        pdf_page: file?.is_pdf ? c.pdfPage : null,
      };
    });
  }

  async function handleFinalize() {
    if (!importSession) return;
    setError(null);

    const fileAssignments = buildAssignments();
    const usableCount = fileAssignments.filter((a) => a.doc_type !== "skip").length;
    if (usableCount === 0) {
      setError("Выберите тип хотя бы для одного документа.");
      return;
    }

    setStep("submitting");

    try {
      const result = await importPackageFinalize(importSession.session_id, {
        application_id: target === "existing" ? existingApplicationId : null,
        internal_notes: target === "new" ? internalNotes : null,
        files: fileAssignments,
        run_ocr: true,
      });

      // Pack 14b: если требуется создание компании из ЕГРЮЛ
      if (result.requires_company_creation && result.pending_company) {
        setPendingCompany(result.pending_company);
        // Предзаполняем форму данными из ЕГРЮЛ + склонениями директора
        const ocr = result.pending_company.ocr_data;
        const decl = result.pending_company.director_declensions;
        setCompanyForm({
          short_name: ocr.short_name_inferred || "",
          full_name_ru: ocr.full_name_ru || "",
          full_name_es: ocr.full_name_es || "",
          country: "RUS",
          tax_id_primary: ocr.inn || "",
          tax_id_secondary: ocr.kpp || null,
          legal_address: ocr.legal_address || "",
          postal_address: ocr.postal_address || null,
          director_full_name_ru: decl.nominative || ocr.director_full_name_ru || "",
          director_full_name_genitive_ru: decl.genitive || "",
          director_short_ru: decl.short_form || "",
          director_position_ru: ocr.director_position_ru || "Генерального директора",
          bank_name: ocr.bank_name || "",
          bank_account: ocr.bank_account || "",
          bank_bic: ocr.bank_bic || "",
          bank_correspondent_account: ocr.bank_correspondent_account || null,
          egryl_extract_date: ocr.egryl_extract_date || null,
          notes: null,
        });
        setStep("company");
        return;
      }

      // Иначе — заявка создана, закрываем
      setStep("done");
      setTimeout(() => {
        onImported(result);
      }, 1200);
    } catch (e) {
      setError((e as Error).message);
      setStep("classify");
    }
  }

  async function handleFinalizeWithCompany() {
    if (!importSession || !companyForm) return;
    setError(null);

    // Валидация — критичные поля
    const missing: string[] = [];
    if (!companyForm.short_name?.trim()) missing.push("Краткое название");
    if (!companyForm.full_name_ru?.trim()) missing.push("Полное название (рус)");
    if (!companyForm.full_name_es?.trim()) missing.push("Полное название (исп)");
    if (!companyForm.tax_id_primary?.trim()) missing.push("ИНН");
    if (!companyForm.legal_address?.trim()) missing.push("Юр. адрес");
    if (!companyForm.director_full_name_ru?.trim()) missing.push("ФИО директора");
    if (!companyForm.director_full_name_genitive_ru?.trim()) missing.push("ФИО директора (родительный)");
    if (!companyForm.director_short_ru?.trim()) missing.push("ФИО директора (короткая форма)");
    if (!companyForm.bank_name?.trim()) missing.push("Банк");
    if (!companyForm.bank_account?.trim()) missing.push("Расчётный счёт");
    if (!companyForm.bank_bic?.trim()) missing.push("БИК");

    if (missing.length > 0) {
      setError(`Заполните обязательные поля: ${missing.join(", ")}`);
      return;
    }

    setStep("submitting");

    try {
      const result = await importPackageFinalizeWithCompany(importSession.session_id, {
        company: companyForm,
        application_id: target === "existing" ? existingApplicationId : null,
        internal_notes: target === "new" ? internalNotes : null,
        files: buildAssignments(),
        run_ocr: true,
      });

      setStep("done");
      setTimeout(() => {
        onImported(result);
      }, 1200);
    } catch (e) {
      setError((e as Error).message);
      setStep("company");
    }
  }

  async function handleSkipCompany() {
    if (!importSession) return;
    setError(null);
    setStep("submitting");

    try {
      const result = await importPackageFinalizeSkipCompany(importSession.session_id, {
        application_id: target === "existing" ? existingApplicationId : null,
        internal_notes: target === "new" ? internalNotes : null,
        files: buildAssignments(),
        run_ocr: true,
      });

      setStep("done");
      setTimeout(() => {
        onImported(result);
      }, 1200);
    } catch (e) {
      setError((e as Error).message);
      setStep("company");
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
            {step === "company" ? (
              <Building2 className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
            ) : (
              <Package className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
            )}
            <span className="text-base font-semibold text-primary">
              {step === "company"
                ? "Создание компании из ЕГРЮЛ"
                : "Импорт пакета документов"}
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
              <div className="text-sm text-secondary font-medium">
                Распаковываем архив...
              </div>
              <div className="text-xs text-tertiary">
                Сейчас ИИ определит тип каждого документа
              </div>
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

          {step === "company" && companyForm && pendingCompany && (
            <CompanyFormStep
              companyForm={companyForm}
              setCompanyForm={setCompanyForm}
              pendingCompany={pendingCompany}
            />
          )}

          {step === "submitting" && importSession && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-secondary" />
              <div className="text-sm text-secondary font-medium">
                {pendingCompany
                  ? "Создаём компанию и заявку..."
                  : "Загружаем документы и распознаём..."}
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

        {step === "company" && (
          <div
            className="px-5 py-4 border-t flex justify-between gap-3 flex-wrap"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderTopWidth: 0.5,
            }}
          >
            <button
              onClick={() => {
                setPendingCompany(null);
                setCompanyForm(null);
                setStep("classify");
              }}
              className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center gap-1.5"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
            >
              <ArrowLeft className="w-4 h-4" />
              Назад
            </button>
            <div className="flex gap-2 ml-auto">
              <button
                onClick={handleSkipCompany}
                className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center gap-1.5"
                style={{
                  borderColor: "var(--color-border-tertiary)",
                  borderWidth: 0.5,
                }}
                title="Создать заявку без компании. ЕГРЮЛ-файл будет пропущен. Компанию можно будет добавить позже вручную."
              >
                <SkipForward className="w-4 h-4" />
                Пропустить компанию
              </button>
              <button
                onClick={handleFinalizeWithCompany}
                className="px-5 py-2 rounded-md text-sm font-medium text-white transition-colors flex items-center gap-2"
                style={{ background: "var(--color-accent)" }}
              >
                <Building2 className="w-4 h-4" />
                Создать компанию и заявку →
              </button>
            </div>
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
      className="rounded-lg p-10 text-center transition-colors"
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
      <Package className="w-12 h-12 mx-auto mb-3 text-tertiary" />
      <div className="text-base font-medium text-primary mb-1">
        Перетащите архив сюда
      </div>
      <div className="text-sm text-tertiary mb-4">
        ZIP или RAR с документами клиента (паспорт, ВНЖ, справки, диплом, ЕГРЮЛ)
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
        После загрузки ИИ определит тип каждого документа автоматически
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
  // Считаем сколько ЕГРЮЛ выбрано — предупреждаем если несколько
  const egrylCount = Object.values(choices).filter((c) => c.docType === "egryl_extract").length;

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
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-tertiary">
            Файлы из архива ({session.files.length})
          </div>
          <div className="text-xs text-tertiary flex items-center gap-1">
            <Sparkles className="w-3 h-3" />
            Типы определены ИИ — проверьте перед продолжением
          </div>
        </div>

        {egrylCount > 1 && (
          <div
            className="mb-3 p-3 rounded-md text-sm flex gap-2 items-start"
            style={{
              background: "var(--color-bg-warning)",
              color: "var(--color-text-warning)",
              border: "0.5px solid var(--color-border-warning)",
            }}
          >
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>
              Выбрано {egrylCount} файла как ЕГРЮЛ. Будет использован только первый.
              Остальные пометьте «— Не использовать —».
            </span>
          </div>
        )}

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

  const needPdfPages =
    file.is_pdf && choice.docType !== "skip" && !choice.pdfPagesPreviews && !choice.pdfLoading && !choice.pdfError;

  useEffect(() => {
    if (needPdfPages) {
      onLoadPdfPages();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needPdfPages]);

  // Pack 14c — индикатор уверенности классификатора
  const confidence = file.classifier_confidence;
  const confidenceLabel =
    confidence === "high" ? "ИИ уверен"
    : confidence === "medium" ? "ИИ не уверен — проверьте"
    : confidence === "low" ? "ИИ не смог определить"
    : null;
  const confidenceColor =
    confidence === "high" ? { bg: "var(--color-bg-success)", text: "var(--color-text-success)" }
    : confidence === "medium" ? { bg: "var(--color-bg-warning)", text: "var(--color-text-warning)" }
    : { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" };

  // Цвет рамки селекта зависит от confidence
  const selectBorderColor =
    choice.docType === "skip" ? "var(--color-border-tertiary)"
    : confidence === "medium" ? "var(--color-text-warning)"
    : "var(--color-accent)";

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
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-primary truncate">
              {file.name}
            </span>
            {confidenceLabel && (
              <span
                className="text-xs px-2 py-0.5 rounded-full inline-flex items-center gap-1"
                style={{
                  background: confidenceColor.bg,
                  color: confidenceColor.text,
                }}
              >
                <Sparkles className="w-3 h-3" />
                {confidenceLabel}
                {file.classifier_country ? ` (${file.classifier_country})` : ""}
              </span>
            )}
          </div>

          <div className="text-xs text-tertiary mb-2">
            {file.is_pdf ? "PDF" : file.extension.replace(".", "").toUpperCase()} ·{" "}
            {sizeMB} МБ
            {file.classifier_error ? ` · ИИ: ${file.classifier_error}` : ""}
          </div>

          <select
            value={choice.docType}
            onChange={(e) =>
              onDocTypeChange(e.target.value as ClientDocumentType | "skip")
            }
            className="px-2 py-1.5 rounded-md text-sm border w-full"
            style={{
              borderColor: selectBorderColor,
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


// =============================================================================
// Step 3: Company creation form (Pack 14b)
// =============================================================================

function CompanyFormStep({
  companyForm,
  setCompanyForm,
  pendingCompany,
}: {
  companyForm: CompanyCreatePayload;
  setCompanyForm: (c: CompanyCreatePayload) => void;
  pendingCompany: PendingCompanyData;
}) {
  function update<K extends keyof CompanyCreatePayload>(
    key: K,
    value: CompanyCreatePayload[K]
  ) {
    setCompanyForm({ ...companyForm, [key]: value });
  }

  const inputStyle = {
    borderColor: "var(--color-border-tertiary)",
    borderWidth: 0.5,
    background: "var(--color-bg-primary)",
    color: "var(--color-text-primary)",
  } as const;

  return (
    <div className="space-y-5">
      <div
        className="rounded-md p-3 text-sm flex gap-2 items-start"
        style={{
          background: "var(--color-bg-info)",
          color: "var(--color-text-info)",
          border: "0.5px solid var(--color-border-info)",
        }}
      >
        <Sparkles className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          <div className="font-medium mb-0.5">Данные распознаны из ЕГРЮЛ</div>
          <div className="text-xs">
            Проверьте поля, заполните недостающее (особенно банковские реквизиты)
            и нажмите «Создать компанию и заявку».
          </div>
        </div>
      </div>

      {/* Названия */}
      <FormSection title="Названия компании">
        <FormField
          label="Краткое название *"
          hint="Например: ИНЖГЕОСЕРВИС, СК10"
          value={companyForm.short_name}
          onChange={(v) => update("short_name", v)}
          placeholder={pendingCompany.ocr_data.short_name_inferred || ""}
        />
        <FormField
          label="Полное название (рус) *"
          value={companyForm.full_name_ru}
          onChange={(v) => update("full_name_ru", v)}
        />
        <FormField
          label="Полное название (исп) *"
          hint="Для документов в UGE"
          value={companyForm.full_name_es}
          onChange={(v) => update("full_name_es", v)}
        />
      </FormSection>

      {/* Идентификаторы */}
      <FormSection title="Регистрационные данные">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FormField
            label="ИНН *"
            value={companyForm.tax_id_primary}
            onChange={(v) => update("tax_id_primary", v)}
          />
          <FormField
            label="КПП"
            value={companyForm.tax_id_secondary || ""}
            onChange={(v) => update("tax_id_secondary", v || null)}
          />
        </div>
        {pendingCompany.ocr_data.ogrn && (
          <div className="text-xs text-tertiary mt-1">
            ОГРН (из выписки): {pendingCompany.ocr_data.ogrn}
          </div>
        )}
      </FormSection>

      {/* Адреса */}
      <FormSection title="Адреса">
        <FormField
          label="Юридический адрес *"
          value={companyForm.legal_address}
          onChange={(v) => update("legal_address", v)}
          textarea
        />
        <FormField
          label="Почтовый адрес"
          hint="Если отличается от юридического"
          value={companyForm.postal_address || ""}
          onChange={(v) => update("postal_address", v || null)}
          textarea
        />
      </FormSection>

      {/* Директор */}
      <FormSection title="Директор">
        <FormField
          label="ФИО директора (Им. падеж) *"
          value={companyForm.director_full_name_ru}
          onChange={(v) => update("director_full_name_ru", v)}
        />
        <FormField
          label="ФИО директора (Род. падеж) *"
          hint="Например: Иванова Сергея Петровича"
          value={companyForm.director_full_name_genitive_ru}
          onChange={(v) => update("director_full_name_genitive_ru", v)}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FormField
            label="Короткая форма *"
            hint="Например: Иванов С.П."
            value={companyForm.director_short_ru}
            onChange={(v) => update("director_short_ru", v)}
          />
          <FormField
            label="Должность (Род. падеж)"
            value={companyForm.director_position_ru || ""}
            onChange={(v) => update("director_position_ru", v)}
          />
        </div>

        {/* Все остальные склонения — для просмотра */}
        <details className="mt-2">
          <summary
            className="text-xs cursor-pointer hover:text-primary"
            style={{ color: "var(--color-text-info)" }}
          >
            Все склонения (сгенерированы ИИ)
          </summary>
          <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1 text-xs text-tertiary">
            <div>Им.: {pendingCompany.director_declensions.nominative}</div>
            <div>Род.: {pendingCompany.director_declensions.genitive}</div>
            <div>Дат.: {pendingCompany.director_declensions.dative}</div>
            <div>Вин.: {pendingCompany.director_declensions.accusative}</div>
            <div>Тв.: {pendingCompany.director_declensions.instrumental}</div>
            <div>Пр.: {pendingCompany.director_declensions.prepositional}</div>
          </div>
        </details>
      </FormSection>

      {/* Банк */}
      <FormSection
        title="Банковские реквизиты"
        warning={
          !companyForm.bank_name && !companyForm.bank_account
            ? "ЕГРЮЛ не всегда содержит банковские реквизиты — заполните вручную"
            : undefined
        }
      >
        <FormField
          label="Банк *"
          value={companyForm.bank_name}
          onChange={(v) => update("bank_name", v)}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FormField
            label="Расчётный счёт *"
            value={companyForm.bank_account}
            onChange={(v) => update("bank_account", v)}
          />
          <FormField
            label="БИК *"
            value={companyForm.bank_bic}
            onChange={(v) => update("bank_bic", v)}
          />
        </div>
        <FormField
          label="Корреспондентский счёт"
          value={companyForm.bank_correspondent_account || ""}
          onChange={(v) => update("bank_correspondent_account", v || null)}
        />
      </FormSection>

      {/* ЕГРЮЛ дата */}
      <FormSection title="Прочее">
        <FormField
          label="Дата выдачи ЕГРЮЛ"
          value={companyForm.egryl_extract_date || ""}
          onChange={(v) => update("egryl_extract_date", v || null)}
          placeholder="YYYY-MM-DD"
        />
      </FormSection>
    </div>
  );
}


function FormSection({
  title,
  warning,
  children,
}: {
  title: string;
  warning?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-md p-4"
      style={{
        background: "var(--color-bg-secondary)",
        border: "0.5px solid var(--color-border-secondary)",
      }}
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3">
        {title}
      </div>
      {warning && (
        <div
          className="mb-3 p-2 rounded-md text-xs flex gap-1.5 items-start"
          style={{
            background: "var(--color-bg-warning)",
            color: "var(--color-text-warning)",
          }}
        >
          <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
          <span>{warning}</span>
        </div>
      )}
      <div className="space-y-3">{children}</div>
    </div>
  );
}


function FormField({
  label,
  hint,
  value,
  onChange,
  placeholder,
  textarea,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  textarea?: boolean;
}) {
  const style = {
    borderColor: "var(--color-border-tertiary)",
    borderWidth: 0.5,
    background: "var(--color-bg-primary)",
    color: "var(--color-text-primary)",
  } as const;

  return (
    <div>
      <label className="block text-xs text-tertiary mb-1">{label}</label>
      {textarea ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={2}
          className="w-full px-2 py-1.5 rounded-md text-sm border"
          style={style}
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full px-2 py-1.5 rounded-md text-sm border"
          style={style}
        />
      )}
      {hint && <div className="text-xs text-tertiary mt-0.5">{hint}</div>}
    </div>
  );
}
