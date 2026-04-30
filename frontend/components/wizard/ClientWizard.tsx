"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Loader2, Moon, Sun, Lock } from "lucide-react";
import { StepPersonalInfo } from "./StepPersonalInfo";
import { StepPassport } from "./StepPassport";
import { StepAddress } from "./StepAddress";
import { StepEducation } from "./StepEducation";
import { StepWorkHistory } from "./StepWorkHistory";
import { StepDocuments } from "./StepDocuments";
import {
  ApplicantData,
  getMyProfile,
  updateMyProfile,
  getMyApplication,
  STATUS_LABELS,
} from "@/lib/api";

const STEPS = [
  { id: "docs", title: "Документы", subtitle: "Сканы паспортов и диплома (опционально)" },
  { id: "personal", title: "Личные данные", subtitle: "ФИО, дата рождения" },
  { id: "passport", title: "Паспорт", subtitle: "Номер, родители, ИНН" },
  { id: "address", title: "Адрес и контакты", subtitle: "Где живёте, как связаться" },
  { id: "education", title: "Образование", subtitle: "Учебные заведения" },
  { id: "work", title: "Опыт работы", subtitle: "Для резюме на испанском" },
];

interface Props {
  token: string;
}

export function ClientWizard({ token }: Props) {
  const [data, setData] = useState<ApplicantData>({});
  const [currentStep, setCurrentStep] = useState(0);
  const [maxReachedStep, setMaxReachedStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [appReference, setAppReference] = useState<string>("");
  const [appStatus, setAppStatus] = useState<string>("");
  const [theme, setTheme] = useState<"light" | "dark">("light");

  const stepRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme === "dark" ? "dark" : "";
  }, [theme]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [profile, application] = await Promise.all([
          getMyProfile(token),
          getMyApplication(token),
        ]);
        if (!mounted) return;
        if (profile) {
          setData(profile);
          const completed = new Set<number>();
          if (profile.last_name_native && profile.first_name_native) completed.add(1);
          if (profile.passport_number) completed.add(2);
          if (profile.home_address && profile.email) completed.add(3);
          if (profile.education && profile.education.length > 0) completed.add(4);
          if (profile.work_history && profile.work_history.length > 0) completed.add(5);
          setCompletedSteps(completed);
          if (completed.size > 0) {
            const maxCompleted = Math.max(...Array.from(completed));
            setMaxReachedStep(Math.min(maxCompleted + 1, STEPS.length - 1));
          }
        }
        setAppReference(application.reference);
        setAppStatus(application.status);
        setLoading(false);
      } catch (e) {
        if (!mounted) return;
        setError((e as Error).message);
        setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [token]);

  function updateData(next: Partial<ApplicantData>) {
    setData((prev) => ({ ...prev, ...next }));
  }

  async function saveProgress() {
    if (currentStep === 0) {
      setCompletedSteps((prev) => new Set([...prev, 0]));
      return true;
    }

    setSaving(true);
    setError(null);
    try {
      const updated = await updateMyProfile(token, data);
      setData(updated);
      setSavedAt(new Date());
      setCompletedSteps((prev) => new Set([...prev, currentStep]));
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setSaving(false);
    }
  }

  function scrollToStep(idx: number) {
    if (typeof window !== "undefined" && window.innerWidth >= 768) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    setTimeout(() => {
      const el = stepRefs.current[idx];
      if (el) {
        const top = el.getBoundingClientRect().top + window.scrollY - 80;
        window.scrollTo({ top, behavior: "smooth" });
      }
    }, 50);
  }

  async function handleStepClick(idx: number) {
    if (idx === currentStep) return;
    if (idx > maxReachedStep) return;
    await saveProgress();
    setCurrentStep(idx);
    scrollToStep(idx);
  }

  async function handleNext() {
    const ok = await saveProgress();
    if (!ok) return;
    if (currentStep >= STEPS.length - 1) return;
    const nextStep = currentStep + 1;
    setMaxReachedStep((prev) => Math.max(prev, nextStep));
    setCurrentStep(nextStep);
    scrollToStep(nextStep);
  }

  // Pack 13.1: после применения OCR данных нужно перезагрузить профиль
  async function handleDocumentsContinue() {
    setCompletedSteps((prev) => new Set([...prev, 0]));
    setMaxReachedStep((prev) => Math.max(prev, 1));

    // Перезагружаем профиль чтобы подтянуть OCR-данные если они применились
    try {
      const profile = await getMyProfile(token);
      if (profile) {
        setData(profile);
        const completed = new Set<number>([0]);
        if (profile.last_name_native && profile.first_name_native) completed.add(1);
        if (profile.passport_number) completed.add(2);
        if (profile.home_address && profile.email) completed.add(3);
        if (profile.education && profile.education.length > 0) completed.add(4);
        if (profile.work_history && profile.work_history.length > 0) completed.add(5);
        setCompletedSteps(completed);
        const maxCompleted = Math.max(...Array.from(completed));
        setMaxReachedStep(Math.min(maxCompleted + 1, STEPS.length - 1));
      }
    } catch (e) {
      console.error("Failed to reload profile:", e);
    }

    setCurrentStep(1);
    scrollToStep(1);
  }

  function renderStepContent(idx: number) {
    if (idx === 0) {
      return (
        <StepDocuments
          token={token}
          onSkip={handleDocumentsContinue}
          onContinue={handleDocumentsContinue}
        />
      );
    }
    if (idx === 1) return <StepPersonalInfo data={data} onChange={updateData} />;
    if (idx === 2) return <StepPassport data={data} onChange={updateData} />;
    if (idx === 3) return <StepAddress data={data} onChange={updateData} />;
    if (idx === 4) return <StepEducation data={data} onChange={updateData} />;
    if (idx === 5) return <StepWorkHistory data={data} onChange={updateData} />;
    return null;
  }

  function renderNavButtons() {
    if (currentStep === 0) return null;

    return (
      <div
        className="mt-8 pt-6 border-t border-tertiary flex justify-between gap-3"
        style={{ borderTopWidth: 0.5 }}
      >
        <button
          onClick={() => handleStepClick(Math.max(0, currentStep - 1))}
          disabled={currentStep === 0 || saving}
          className="px-4 py-2 rounded-md text-sm border border-tertiary text-secondary hover:bg-secondary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          style={{ borderWidth: 0.5 }}
        >
          ← Назад
        </button>

        <button
          onClick={handleNext}
          disabled={saving}
          className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          style={{ background: "var(--color-accent)" }}
        >
          {saving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : currentStep === STEPS.length - 1 ? (
            "Сохранить"
          ) : (
            "Продолжить →"
          )}
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-screen bg-tertiary">
        <Loader2 className="w-8 h-8 animate-spin text-secondary" />
      </div>
    );
  }

  if (error && !data.last_name_native) {
    return (
      <div className="min-h-screen bg-tertiary flex items-center justify-center p-6">
        <div className="max-w-md p-8 rounded-xl bg-danger border border-secondary">
          <h1 className="text-xl font-semibold text-danger mb-2">Ошибка</h1>
          <p className="text-sm text-danger">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-tertiary py-4 px-3 md:py-6 md:px-4">
      <div className="max-w-5xl mx-auto">
        <div
          className="bg-primary rounded-xl border border-tertiary px-4 py-3 md:px-5 md:py-4 mb-4 flex items-center justify-between gap-3"
          style={{ borderWidth: 0.5 }}
        >
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div
              className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-semibold flex-shrink-0"
              style={{ background: "var(--color-accent)" }}
            >
              V
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-primary truncate">
                Visa kit · Digital nomad España
              </div>
              <div className="text-xs text-tertiary truncate">
                Заявка #{appReference} · {STATUS_LABELS[appStatus] || appStatus}
              </div>
            </div>
          </div>

          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="text-sm px-2.5 py-1.5 md:px-3 rounded-md border border-tertiary text-secondary hover:bg-secondary transition-colors flex items-center gap-2 flex-shrink-0"
            style={{ borderWidth: 0.5 }}
            aria-label={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
          >
            {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            <span className="hidden md:inline">
              {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            </span>
          </button>
        </div>

        <div className="md:hidden mb-3 px-1 min-h-[18px]">
          {saving && (
            <div className="text-xs text-tertiary flex items-center gap-2">
              <Loader2 className="w-3 h-3 animate-spin" />
              Сохраняется...
            </div>
          )}
          {savedAt && !saving && !error && (
            <div className="text-xs text-success">
              Сохранено в {savedAt.toLocaleTimeString("ru")}
            </div>
          )}
          {error && <div className="text-xs text-danger">{error}</div>}
        </div>

        <div
          className="hidden md:flex bg-primary rounded-xl border border-tertiary overflow-hidden"
          style={{ borderWidth: 0.5, minHeight: "70vh" }}
        >
          <aside
            className="w-72 border-r border-tertiary p-4 nav-scroll"
            style={{
              borderRightWidth: 0.5,
              background: "var(--color-bg-secondary)",
            }}
          >
            <div className="text-xs font-semibold uppercase tracking-wide text-tertiary mb-3 px-2">
              Шаги анкеты
            </div>
            <nav className="space-y-1">
              {STEPS.map((step, idx) => {
                const isActive = idx === currentStep;
                const isCompleted = completedSteps.has(idx);
                const isLocked = idx > maxReachedStep;

                return (
                  <button
                    key={step.id}
                    onClick={() => handleStepClick(idx)}
                    disabled={isLocked}
                    className={`w-full text-left px-3 py-2.5 rounded-md transition-colors flex items-start gap-3 ${
                      isLocked
                        ? "cursor-not-allowed opacity-40"
                        : isActive
                        ? "bg-primary"
                        : "hover:bg-tertiary cursor-pointer"
                    }`}
                    style={
                      isActive
                        ? {
                            boxShadow: "0 0 0 1px var(--color-border-secondary)",
                          }
                        : {}
                    }
                    title={isLocked ? "Сначала пройдите предыдущие шаги" : undefined}
                  >
                    <div className="flex-shrink-0 mt-0.5">
                      {isCompleted ? (
                        <div
                          className="w-5 h-5 rounded-full flex items-center justify-center"
                          style={{
                            background: "var(--color-text-success)",
                            color: "white",
                          }}
                        >
                          <Check className="w-3 h-3" />
                        </div>
                      ) : isActive ? (
                        <div
                          className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-semibold text-white"
                          style={{ background: "var(--color-accent)" }}
                        >
                          {idx + 1}
                        </div>
                      ) : isLocked ? (
                        <div
                          className="w-5 h-5 rounded-full flex items-center justify-center"
                          style={{
                            color: "var(--color-text-tertiary)",
                          }}
                        >
                          <Lock className="w-3 h-3" />
                        </div>
                      ) : (
                        <div
                          className="w-5 h-5 rounded-full border flex items-center justify-center text-xs"
                          style={{
                            borderColor: "var(--color-border-secondary)",
                            color: "var(--color-text-tertiary)",
                          }}
                        >
                          {idx + 1}
                        </div>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div
                        className={`text-sm font-medium ${
                          isActive ? "text-primary" : "text-secondary"
                        }`}
                      >
                        {step.title}
                      </div>
                      <div className="text-xs text-tertiary mt-0.5">
                        {step.subtitle}
                      </div>
                    </div>
                  </button>
                );
              })}
            </nav>

            <div className="mt-6 px-2">
              {saving && (
                <div className="text-xs text-tertiary flex items-center gap-2">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Сохраняется...
                </div>
              )}
              {savedAt && !saving && !error && (
                <div className="text-xs text-success">
                  Сохранено в {savedAt.toLocaleTimeString("ru")}
                </div>
              )}
              {error && <div className="text-xs text-danger">{error}</div>}
            </div>
          </aside>

          <main className="flex-1 p-6 md:p-8 overflow-x-auto">
            {renderStepContent(currentStep)}
            {renderNavButtons()}
          </main>
        </div>

        <div className="md:hidden space-y-3">
          {STEPS.map((step, idx) => {
            const isActive = idx === currentStep;
            const isCompleted = completedSteps.has(idx);
            const isLocked = idx > maxReachedStep;

            return (
              <div
                key={step.id}
                ref={(el) => {
                  stepRefs.current[idx] = el;
                }}
                className="bg-primary rounded-xl border border-tertiary overflow-hidden"
                style={{
                  borderWidth: 0.5,
                  boxShadow: isActive
                    ? "0 0 0 1px var(--color-border-secondary)"
                    : undefined,
                }}
              >
                <button
                  onClick={() => handleStepClick(idx)}
                  disabled={isLocked || isActive}
                  className={`w-full text-left px-4 py-3.5 flex items-center gap-3 transition-colors ${
                    isLocked
                      ? "cursor-not-allowed opacity-50"
                      : isActive
                      ? "cursor-default"
                      : "active:bg-secondary cursor-pointer"
                  }`}
                  title={isLocked ? "Сначала пройдите предыдущие шаги" : undefined}
                >
                  <div className="flex-shrink-0">
                    {isCompleted && !isActive ? (
                      <div
                        className="w-7 h-7 rounded-full flex items-center justify-center"
                        style={{
                          background: "var(--color-text-success)",
                          color: "white",
                        }}
                      >
                        <Check className="w-4 h-4" />
                      </div>
                    ) : isActive ? (
                      <div
                        className="w-7 h-7 rounded-full flex items-center justify-center text-sm font-semibold text-white"
                        style={{ background: "var(--color-accent)" }}
                      >
                        {idx + 1}
                      </div>
                    ) : isLocked ? (
                      <div
                        className="w-7 h-7 rounded-full flex items-center justify-center"
                        style={{ color: "var(--color-text-tertiary)" }}
                      >
                        <Lock className="w-4 h-4" />
                      </div>
                    ) : (
                      <div
                        className="w-7 h-7 rounded-full border flex items-center justify-center text-sm"
                        style={{
                          borderColor: "var(--color-border-secondary)",
                          color: "var(--color-text-tertiary)",
                        }}
                      >
                        {idx + 1}
                      </div>
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div
                      className={`text-base font-medium ${
                        isActive ? "text-primary" : "text-secondary"
                      }`}
                    >
                      {step.title}
                    </div>
                    {!isActive && (
                      <div className="text-xs text-tertiary mt-0.5">
                        {step.subtitle}
                      </div>
                    )}
                  </div>

                  {!isActive && !isLocked && (
                    <ChevronDown className="w-5 h-5 text-tertiary flex-shrink-0" />
                  )}
                </button>

                {isActive && (
                  <div className="px-4 pb-5 pt-1">
                    {renderStepContent(idx)}
                    {renderNavButtons()}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="text-center text-xs text-tertiary mt-4">
          Visa kit · Если есть вопросы — свяжитесь с менеджером
        </div>
      </div>
    </div>
  );
}
