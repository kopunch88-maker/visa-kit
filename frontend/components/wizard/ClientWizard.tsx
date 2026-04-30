"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, Moon, Sun, Lock } from "lucide-react";
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
  { id: "personal", title: "Личные данные", subtitle: "ФИО, дата рождения" },
  { id: "passport", title: "Паспорт", subtitle: "Номер, родители, ИНН" },
  { id: "address", title: "Адрес и контакты", subtitle: "Где живёте, как связаться" },
  { id: "education", title: "Образование", subtitle: "Учебные заведения" },
  { id: "work", title: "Опыт работы", subtitle: "Для резюме на испанском" },
  { id: "docs", title: "Документы", subtitle: "Сканы паспорта, дипломов" },
];

interface Props {
  token: string;
}

export function ClientWizard({ token }: Props) {
  const [data, setData] = useState<ApplicantData>({});
  const [currentStep, setCurrentStep] = useState(0);
  // maxReachedStep — самый дальний шаг, до которого клиент когда-либо доходил.
  // Все шаги <= maxReachedStep — кликабельны. Шаги > maxReachedStep заблокированы.
  const [maxReachedStep, setMaxReachedStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [appReference, setAppReference] = useState<string>("");
  const [appStatus, setAppStatus] = useState<string>("");
  const [theme, setTheme] = useState<"light" | "dark">("light");

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
          // Восстанавливаем какие шаги были пройдены раньше
          const completed = new Set<number>();
          if (profile.last_name_native && profile.first_name_native) completed.add(0);
          if (profile.passport_number) completed.add(1);
          if (profile.home_address && profile.email) completed.add(2);
          if (profile.education && profile.education.length > 0) completed.add(3);
          if (profile.work_history && profile.work_history.length > 0) completed.add(4);
          setCompletedSteps(completed);
          // Самый дальний пройденный шаг + 1 (чтобы можно было идти дальше)
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

  async function handleStepClick(idx: number) {
    if (idx === currentStep) return;
    // Блокируем переход на шаги которых ещё не достигали
    if (idx > maxReachedStep) return;
    await saveProgress();
    setCurrentStep(idx);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

async function handleNext() {
    const ok = await saveProgress();
    if (!ok) return;

    // Если последний шаг — ничего не делаем, останемся на нём
    if (currentStep >= STEPS.length - 1) return;

    // Переключаемся на следующий шаг
    const nextStep = currentStep + 1;
    setMaxReachedStep((prev) => Math.max(prev, nextStep));
    setCurrentStep(nextStep);
    window.scrollTo({ top: 0, behavior: "smooth" });
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
    <div className="min-h-screen bg-tertiary py-6 px-4">
      <div className="max-w-5xl mx-auto">
        {/* Шапка */}
        <div
          className="bg-primary rounded-xl border border-tertiary px-5 py-4 mb-4 flex items-center justify-between"
          style={{ borderWidth: 0.5 }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-semibold"
              style={{ background: "var(--color-accent)" }}
            >
              V
            </div>
            <div>
              <div className="text-sm font-semibold text-primary">
                Visa kit · Digital nomad España
              </div>
              <div className="text-xs text-tertiary">
                Заявка #{appReference} · {STATUS_LABELS[appStatus] || appStatus}
              </div>
            </div>
          </div>

          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="text-sm px-3 py-1.5 rounded-md border border-tertiary text-secondary hover:bg-secondary transition-colors flex items-center gap-2"
            style={{ borderWidth: 0.5 }}
          >
            {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
          </button>
        </div>

        {/* Основная зона */}
        <div
          className="bg-primary rounded-xl border border-tertiary overflow-hidden flex"
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
              {error && (
                <div className="text-xs text-danger">{error}</div>
              )}
            </div>
          </aside>

          <main className="flex-1 p-6 md:p-8 overflow-x-auto">
            {currentStep === 0 && (
              <StepPersonalInfo data={data} onChange={updateData} />
            )}
            {currentStep === 1 && (
              <StepPassport data={data} onChange={updateData} />
            )}
            {currentStep === 2 && (
              <StepAddress data={data} onChange={updateData} />
            )}
            {currentStep === 3 && (
              <StepEducation data={data} onChange={updateData} />
            )}
            {currentStep === 4 && (
              <StepWorkHistory data={data} onChange={updateData} />
            )}
            {currentStep === 5 && <StepDocuments />}

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
                  "Сохранить и продолжить →"
                )}
              </button>
            </div>
          </main>
        </div>

        <div className="text-center text-xs text-tertiary mt-4">
          Visa kit · Если есть вопросы — свяжитесь с менеджером
        </div>
      </div>
    </div>
  );
}