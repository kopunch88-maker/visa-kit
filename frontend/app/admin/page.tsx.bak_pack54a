"use client";

import { useEffect, useState, useMemo, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, Search, Loader2, Settings, Archive, Package, Trash2 } from "lucide-react";
import {
  listApplications,
  ApplicationResponse,
  STATUS_TABS,
} from "@/lib/api";
import { ApplicationsList, type SortMode } from "@/components/admin/ApplicationsList";
import { ApplicationDetail } from "@/components/admin/ApplicationDetail";
import { ImportPackageDialog } from "@/components/admin/ImportPackageDialog";

function AdminPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("id");

  const [applications, setApplications] = useState<ApplicationResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("all");
  const [showPaid, setShowPaid] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  // Pack 34.3 — режим сортировки списка (default / alphabet / submission_date)
  // Сохраняется в localStorage чтобы выбор менеджера переживал перезагрузку.
  const [sortMode, setSortMode] = useState<SortMode>(() => {
    if (typeof window === "undefined") return "default";
    const saved = window.localStorage.getItem("visa-kit-sort-mode");
    if (saved === "default" || saved === "alphabet" || saved === "submission_date") {
      return saved;
    }
    return "default";
  });

  // Pack 34.3 — persist sortMode в localStorage при смене
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("visa-kit-sort-mode", sortMode);
  }, [sortMode]);
  const [mainTab, setMainTab] = useState<"applications" | "filed">("applications");
    const [showImportDialog, setShowImportDialog] = useState(false);

  async function loadApplications() {
    setError(null);
    try {
      const apps = await listApplications();
      setApplications(apps);
    } catch (e) {
      const msg = (e as Error).message;
      if (msg.includes("Требуется вход") || msg.includes("401")) {
        router.replace("/admin/login");
        return;
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadApplications();
    const interval = setInterval(loadApplications, 30000);
    return () => clearInterval(interval);
  }, []);

  const tabCounts = useMemo(() => {
    const counts: Record<string, number> = { all: applications.length };
    STATUS_TABS.forEach((tab) => {
      if (tab.id === "all") return;
      counts[tab.id] = applications.filter((a) => tab.statuses.includes(a.status)).length;
    });
    counts["paid"] = applications.filter((a) => a.is_paid).length;
    return counts;
  }, [applications]);

  const filteredApplications = useMemo(() => {
    let filtered = mainTab === "filed"
      ? applications.filter((a) => a.is_filed)
      : applications.filter((a) => !a.is_filed);
    const tab = STATUS_TABS.find((t) => t.id === activeTab);
    if (tab && tab.statuses.length > 0) {
      filtered = filtered.filter((a) => tab.statuses.includes(a.status));
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      filtered = filtered.filter(
        (a) =>
          a.reference.toLowerCase().includes(q) ||
          (a.internal_notes || "").toLowerCase().includes(q),
      );
    }
    return filtered;
  }, [applications, activeTab, searchQuery, mainTab]);

  useEffect(() => {
    if (!selectedId && filteredApplications.length > 0 && !loading) {
      router.replace(`/admin?id=${filteredApplications[0].id}`);
    }
  }, [selectedId, filteredApplications, loading, router]);

  function handleSelectApplication(id: number) {
    router.push(`/admin?id=${id}`);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-tertiary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-6">
        <div className="bg-danger text-danger p-4 rounded-md">{error}</div>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 py-4">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex gap-1">
          {([["applications", "Заявки"], ["filed", "Поданы"]] as const).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setMainTab(id)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                mainTab === id ? "text-primary" : "text-secondary hover:bg-secondary"
              }`}
              style={mainTab === id ? { background: "var(--color-bg-secondary)" } : {}}
            >
              {label}
              <span className="ml-1.5 text-xs text-tertiary">
                {id === "filed"
                  ? applications.filter((a) => a.is_filed).length
                  : applications.filter((a) => !a.is_filed).length}
              </span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push("/admin/archive")}
            className="px-3 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center gap-1.5"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            title="Архив завершённых заявок"
          >
            <Archive className="w-4 h-4" />
            Архив
          </button>
          <button
            onClick={() => router.push("/admin/trash")}
            className="px-3 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center gap-1.5"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            title="Корзина завершённых заявок"
          >
            <Trash2 className="w-4 h-4" />
            Корзина
          </button>
          <button
            onClick={() => router.push("/admin/settings")}
            className="px-3 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center gap-1.5"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            title="Управление компаниями, должностями, представителями, адресами"
          >
            <Settings className="w-4 h-4" />
            Настройки
          </button>

          {/* Pack 14a — Импорт пакета документов */}
          <button
            onClick={() => setShowImportDialog(true)}
            className="px-3 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center gap-1.5"
            style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            title="Загрузить ZIP/RAR с документами клиента — система распакует, распознает и создаст заявку"
          >
            <Package className="w-4 h-4" />
            Импорт пакета
          </button>

          <button
            onClick={() => router.push("/admin/applications/new")}
            className="px-4 py-2 rounded-md text-sm font-medium text-white flex items-center gap-2 transition-colors"
            style={{ background: "var(--color-accent)" }}
          >
            <Plus className="w-4 h-4" />
            Создать заявку
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-4">
        <div className="flex flex-col gap-3 min-h-0">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-tertiary" />
            <input
              type="text"
              placeholder="Поиск по ФИО, паспорту, ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
              style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            />
          </div>

          <div className="flex flex-wrap gap-1.5 text-xs">
            {STATUS_TABS.map((tab) => {
              const isActive = tab.id === activeTab;
              const count = tabCounts[tab.id] || 0;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${
                    isActive ? "text-primary font-medium" : "text-secondary hover:bg-secondary"
                  }`}
                  style={isActive ? { background: "var(--color-bg-secondary)" } : {}}
                >
                  {tab.label} <span className="text-tertiary ml-0.5">{count}</span>
                </button>
              );
            })}
            <button
              onClick={() => setShowPaid(!showPaid)}
              className={`px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${
                showPaid ? "text-primary font-medium" : "text-secondary hover:bg-secondary"
              }`}
              style={showPaid ? { background: "rgba(34, 197, 94, 0.15)", color: "#22c55e" } : {}}
            >
              $ Оплачен <span className="text-tertiary ml-0.5">{tabCounts["paid"] || 0}</span>
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
          </div>

          {/* Pack 34.3 — переключатель сортировки */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-tertiary mr-1">Сортировка:</span>
            {[
              { id: "default" as const, label: "По умолчанию" },
              { id: "alphabet" as const, label: "А → Я" },
              { id: "submission_date" as const, label: "По дате подачи" },
            ].map((opt) => {
              const isActive = opt.id === sortMode;
              return (
                <button
                  key={opt.id}
                  onClick={() => setSortMode(opt.id)}
                  className={`px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${
                    isActive ? "text-primary font-medium" : "text-secondary hover:bg-secondary"
                  }`}
                  style={isActive ? { background: "var(--color-bg-secondary)" } : {}}
                  title={
                    opt.id === "default"
                      ? "Огонь и чемодан сверху, новые снизу"
                      : opt.id === "alphabet"
                      ? "Внутри групп — по алфавиту"
                      : "Внутри групп — ближайшая дата подачи выше"
                  }
                >
                  {opt.label}
                </button>
              );
            })}
          </div>

          <ApplicationsList
            applications={filteredApplications}
            selectedId={selectedId ? parseInt(selectedId) : null}
            onSelect={handleSelectApplication}
            sortMode={sortMode}
          />
        </div>

        <div className="min-h-0">
          {selectedId ? (
            <ApplicationDetail
              key={selectedId}
              applicationId={parseInt(selectedId)}
              onUpdated={loadApplications}
            />
          ) : (
            <div
              className="bg-primary rounded-xl border p-12 text-center text-tertiary"
              style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            >
              {applications.length === 0
                ? "Создайте первую заявку — кнопка справа сверху"
                : "Выберите заявку слева, чтобы увидеть детали"}
            </div>
          )}
        </div>
      </div>

      {/* Pack 14a — диалог импорта пакета */}
      {showImportDialog && (
        <ImportPackageDialog
          applications={applications}
          onClose={() => setShowImportDialog(false)}
          onImported={(result) => {
            setShowImportDialog(false);
            loadApplications();
            // Переходим на созданную заявку
            router.push(`/admin?id=${result.application_id}`);
          }}
        />
      )}
    </div>
  );
}

export default function AdminPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-tertiary" />
        </div>
      }
    >
      <AdminPageContent />
    </Suspense>
  );
}
