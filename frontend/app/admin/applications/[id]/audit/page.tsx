"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Loader2,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  ArrowLeft,
  Play,
  RefreshCw,
  ShieldCheck,
  Clock,
  DollarSign,
} from "lucide-react";
import {
  AuditReport,
  AuditReportWithFindings,
  AuditFinding,
  AuditVerdict,
  AuditCategory,
  AUDIT_CATEGORY_LABELS,
  AUDIT_VERDICT_LABELS,
  runAudit,
  listAuditReports,
  getAuditReport,
} from "@/lib/api";
import { AuditFindingCard } from "@/components/admin/AuditFindingCard";

/**
 * Pack 37.0-D — страница аудита пакета документов.
 *
 * Маршрут: /admin/applications/[id]/audit
 *
 * Логика:
 * 1. При открытии — грузит список прогонов (listAuditReports).
 * 2. Если есть активный (is_running=true) — выбирает его + запускает polling.
 * 3. Если нет прогонов вообще — показывает большую кнопку «Запустить проверку».
 * 4. После завершения прогона — показывает светофор + summary + findings.
 * 5. Polling каждые 2 секунды пока is_running=true.
 *
 * Pack 37.0-C: фикс finding обновляет только БД. Пакет 16 файлов нужно
 * пересобирать отдельно (кнопка «Сгенерировать пакет» на главной странице
 * заявки или в ApplicantDrawer).
 */

const VERDICT_STYLES = {
  PASS: {
    bg: "bg-green-50",
    border: "border-green-300",
    text: "text-green-900",
    icon: CheckCircle2,
    iconColor: "text-green-600",
  },
  WARN: {
    bg: "bg-amber-50",
    border: "border-amber-300",
    text: "text-amber-900",
    icon: AlertTriangle,
    iconColor: "text-amber-600",
  },
  FAIL: {
    bg: "bg-red-50",
    border: "border-red-300",
    text: "text-red-900",
    icon: AlertOctagon,
    iconColor: "text-red-600",
  },
} as const;

export default function AuditPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const applicationId = parseInt(params.id, 10);

  const [reports, setReports] = useState<AuditReport[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [report, setReport] = useState<AuditReportWithFindings | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Загрузка списка прогонов
  const loadReports = useCallback(async () => {
    try {
      const data = await listAuditReports(applicationId);
      setReports(data);
      if (data.length > 0 && selectedReportId === null) {
        // По умолчанию — последний прогон
        setSelectedReportId(data[0].id);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [applicationId, selectedReportId]);

  // Загрузка полного отчёта
  const loadReport = useCallback(async (id: number) => {
    try {
      const data = await getAuditReport(id);
      setReport(data);
      return data;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }, []);

  // Первичная загрузка
  useEffect(() => {
    setLoading(true);
    loadReports().finally(() => setLoading(false));
  }, [loadReports]);

  // Загрузка выбранного прогона
  useEffect(() => {
    if (selectedReportId === null) {
      setReport(null);
      return;
    }
    loadReport(selectedReportId);
  }, [selectedReportId, loadReport]);

  // Polling если прогон активен
  useEffect(() => {
    if (!report || !report.is_running) return;

    const interval = setInterval(async () => {
      const updated = await loadReport(report.id);
      if (updated && !updated.is_running) {
        clearInterval(interval);
        // Обновим список (summary_counts в этом отчёте поменялся)
        loadReports();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [report?.id, report?.is_running, loadReport, loadReports]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleStartAudit() {
    setStarting(true);
    setError(null);
    try {
      const res = await runAudit(applicationId);
      // Обновим список и переключимся на новый прогон
      await loadReports();
      setSelectedReportId(res.report_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  // Сгруппированные findings по категориям, чтобы UI был структурированным
  const findingsByCategory = useMemo(() => {
    if (!report) return {} as Record<AuditCategory, AuditFinding[]>;
    const grouped: Record<string, AuditFinding[]> = {};
    for (const f of report.findings) {
      if (!grouped[f.category]) grouped[f.category] = [];
      grouped[f.category].push(f);
    }
    return grouped as Record<AuditCategory, AuditFinding[]>;
  }, [report]);

  const counts = report?.summary_counts as
    | (Record<string, number> & { _llm_summary?: string })
    | undefined;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push(`/admin/applications/${applicationId}`)}
              className="p-2 hover:bg-gray-200 rounded-md text-gray-600"
              title="Вернуться к заявке"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                🛂 Симуляция приёма документов
              </h1>
              <p className="text-xs text-gray-500">Заявка #{applicationId}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {reports.length > 0 && (
              <select
                value={selectedReportId ?? ""}
                onChange={(e) => setSelectedReportId(parseInt(e.target.value, 10))}
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm bg-white"
              >
                {reports.map((r) => (
                  <option key={r.id} value={r.id}>
                    Прогон #{r.id} от {new Date(r.started_at).toLocaleString("ru-RU")}
                    {r.is_running ? " (выполняется...)" : ""}
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={handleStartAudit}
              disabled={starting || report?.is_running}
              className="inline-flex items-center gap-2 px-4 py-2 bg-accent text-white text-sm font-medium rounded-md hover:opacity-90 disabled:opacity-50"
            >
              {starting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : reports.length === 0 ? (
                <Play className="w-4 h-4" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              {reports.length === 0 ? "Запустить проверку" : "Новый прогон"}
            </button>
          </div>
        </div>

        {/* Ошибка глобальная */}
        {error && (
          <div className="bg-red-50 border border-red-300 text-red-900 px-4 py-3 rounded-md mb-4 text-sm">
            {error}
          </div>
        )}

        {/* Загрузка */}
        {loading && (
          <div className="flex items-center justify-center py-20 text-gray-500">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Загрузка...
          </div>
        )}

        {/* Нет прогонов — приглашение запустить */}
        {!loading && reports.length === 0 && (
          <div className="bg-white border border-gray-200 rounded-lg p-12 text-center">
            <ShieldCheck className="w-16 h-16 mx-auto text-gray-300 mb-4" />
            <h2 className="text-lg font-semibold text-gray-900 mb-2">
              Проверка пакета документов перед подачей
            </h2>
            <p className="text-sm text-gray-600 max-w-xl mx-auto mb-6">
              ИИ-аудитор имитирует приём документов в консульстве: сверяет ФИО, даты, паспортные данные,
              реквизиты компании, суммы в договоре, актах, счетах и банковской выписке.
              Это последняя проверка перед подачей — от её результата зависит успех заявки.
            </p>
            <button
              onClick={handleStartAudit}
              disabled={starting}
              className="inline-flex items-center gap-2 px-6 py-3 bg-accent text-white font-medium rounded-md hover:opacity-90 disabled:opacity-50"
            >
              {starting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
              Запустить первую проверку
            </button>
            <p className="text-xs text-gray-400 mt-3">Занимает 30-90 секунд</p>
          </div>
        )}

        {/* Активный прогон в процессе */}
        {report && report.is_running && (
          <div className="bg-blue-50 border border-blue-300 rounded-lg p-8 text-center">
            <Loader2 className="w-12 h-12 mx-auto text-blue-600 animate-spin mb-4" />
            <h2 className="text-lg font-semibold text-blue-900 mb-2">
              Проверка выполняется...
            </h2>
            <p className="text-sm text-blue-700 mb-1">
              ИИ-аудитор анализирует пакет документов. Это займёт 30-90 секунд.
            </p>
            <p className="text-xs text-blue-600">
              Начато: {new Date(report.started_at).toLocaleString("ru-RU")}
            </p>
          </div>
        )}

        {/* Ошибка прогона */}
        {report && !report.is_running && report.error && (
          <div className="bg-red-50 border border-red-300 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-red-900 mb-2 flex items-center gap-2">
              <AlertOctagon className="w-5 h-5" /> Ошибка проверки
            </h2>
            <p className="text-sm text-red-800 whitespace-pre-wrap font-mono">{report.error}</p>
            <button
              onClick={handleStartAudit}
              disabled={starting}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700"
            >
              <RefreshCw className="w-4 h-4" /> Попробовать снова
            </button>
          </div>
        )}

        {/* Готовый отчёт */}
        {report && !report.is_running && !report.error && (
          <>
            {/* Светофор + метаданные */}
            <VerdictBanner report={report} />

            {/* Summary cards */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <SummaryCard
                label="Критично"
                value={counts?.critical ?? 0}
                resolved={counts?.accepted ?? 0}
                color="red"
              />
              <SummaryCard
                label="Предупреждений"
                value={counts?.warning ?? 0}
                resolved={0}
                color="amber"
              />
              <SummaryCard
                label="Замечаний"
                value={counts?.info ?? 0}
                resolved={0}
                color="blue"
              />
            </div>

            {/* Резюме от ИИ */}
            {counts?._llm_summary && (
              <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4">
                <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Резюме от ИИ</h3>
                <p className="text-sm text-gray-800 whitespace-pre-wrap">
                  {counts._llm_summary as string}
                </p>
              </div>
            )}

            {/* Метаданные прогона */}
            <div className="flex items-center gap-4 text-xs text-gray-500 mb-6 flex-wrap">
              {report.duration_ms !== null && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {(report.duration_ms / 1000).toFixed(1)} сек
                </span>
              )}
              {report.cost_usd !== null && (
                <span className="inline-flex items-center gap-1">
                  <DollarSign className="w-3.5 h-3.5" />
                  {report.cost_usd}
                </span>
              )}
              {report.model_used && (
                <span className="inline-flex items-center gap-1">
                  Модель: <code className="bg-gray-100 px-1.5 py-0.5 rounded">{report.model_used}</code>
                </span>
              )}
              <span>Найдено всего: {report.findings.length}</span>
            </div>

            {/* Findings — без findings показываем «всё ок», иначе по категориям */}
            {report.findings.length === 0 ? (
              <div className="bg-green-50 border border-green-300 rounded-lg p-8 text-center">
                <CheckCircle2 className="w-16 h-16 mx-auto text-green-600 mb-3" />
                <h3 className="text-lg font-semibold text-green-900 mb-1">
                  Пакет готов к подаче
                </h3>
                <p className="text-sm text-green-800">
                  ИИ-аудитор не нашёл несоответствий. Можно подавать документы.
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {(
                  ["identity", "financial", "company", "education", "spain_pack", "formal"] as AuditCategory[]
                ).map((cat) => {
                  const items = findingsByCategory[cat];
                  if (!items || items.length === 0) return null;
                  return (
                    <section key={cat}>
                      <h3 className="text-sm font-semibold text-gray-700 uppercase mb-2 flex items-center gap-2">
                        {AUDIT_CATEGORY_LABELS[cat]}
                        <span className="text-xs text-gray-400 font-normal">
                          ({items.length})
                        </span>
                      </h3>
                      <div className="space-y-2">
                        {items.map((f) => (
                          <AuditFindingCard
                            key={f.id}
                            finding={f}
                            onResolved={() => {
                              // Перечитать отчёт после accept/dismiss/manual-fix
                              loadReport(report.id);
                            }}
                          />
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ====================================================================
// Подкомпоненты
// ====================================================================

function VerdictBanner({ report }: { report: AuditReportWithFindings }) {
  const v = VERDICT_STYLES[report.verdict];
  const Icon = v.icon;

  return (
    <div className={`${v.bg} ${v.border} border-2 rounded-lg p-5 mb-4`}>
      <div className="flex items-center gap-4">
        <Icon className={`w-12 h-12 ${v.iconColor}`} />
        <div className="flex-1">
          <div className={`text-2xl font-bold ${v.text}`}>
            {AUDIT_VERDICT_LABELS[report.verdict]}
          </div>
          <div className={`text-sm ${v.text} opacity-80 mt-0.5`}>
            {report.verdict === "FAIL" &&
              "Найдены критические несоответствия. Исправьте их перед подачей."}
            {report.verdict === "WARN" &&
              "Найдены предупреждения. Подача возможна, но с риском вопросов от консульства."}
            {report.verdict === "PASS" &&
              "Пакет соответствует требованиям консульства. Можно подавать."}
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  resolved,
  color,
}: {
  label: string;
  value: number;
  resolved: number;
  color: "red" | "amber" | "blue";
}) {
  const colorClasses = {
    red: { bg: "bg-red-50", border: "border-red-200", text: "text-red-700", num: "text-red-900" },
    amber: {
      bg: "bg-amber-50",
      border: "border-amber-200",
      text: "text-amber-700",
      num: "text-amber-900",
    },
    blue: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700", num: "text-blue-900" },
  }[color];

  return (
    <div className={`${colorClasses.bg} ${colorClasses.border} border rounded-lg p-3`}>
      <div className={`text-xs font-medium ${colorClasses.text} uppercase mb-1`}>{label}</div>
      <div className="flex items-baseline gap-2">
        <span className={`text-3xl font-bold ${colorClasses.num}`}>{value}</span>
        {resolved > 0 && (
          <span className="text-xs text-gray-500">из них решено: {resolved}</span>
        )}
      </div>
    </div>
  );
}
