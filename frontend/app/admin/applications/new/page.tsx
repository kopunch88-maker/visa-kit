"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, X } from "lucide-react";
import { createApplication, ApplicationType, APPLICATION_TYPE_BADGE } from "@/lib/api";

export default function NewApplicationPage() {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [submissionDate, setSubmissionDate] = useState("");
  const [applicantEmail, setApplicantEmail] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Pack 50.0-C3 + fix1 — модалка выбора типа заявки
  // Открывается СРАЗУ при заходе на страницу (первое действие менеджера).
  const [showTypeModal, setShowTypeModal] = useState(true);
  // Запомненный тип — выставляется в handleInitialTypeSelected.
  const [selectedType, setSelectedType] = useState<ApplicationType | null>(null);

  // Pack 50.0-C3 fix1 — открыть модалку при заходе (на случай если
  // useState(true) был перебит каким-то ре-рендером, плюс прозрачно отражает намерение).
  useEffect(() => {
    if (!selectedType) {
      setShowTypeModal(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Pack 50.0-C3 fix1 — закрытие модалки без выбора → редирект на /admin
  function handleModalClose() {
    if (!selectedType) {
      // менеджер передумал создавать заявку — возвращаем в список
      router.push("/admin");
      return;
    }
    // тип уже выбран ранее — просто закрываем (менеджер открывал чтобы посмотреть/изменить)
    setShowTypeModal(false);
  }

  // Pack 50.0-C3 fix1 — выбор типа в модалке (первое окно).
  // Только запоминаем тип и закрываем модалку, форма становится доступной.
  function handleInitialTypeSelected(type: ApplicationType) {
    setSelectedType(type);
    setShowTypeModal(false);
  }

  // Pack 50.0-C3 fix1 — submit формы → создание заявки с уже выбранным типом.
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedType) {
      // защита: на форму ничего не нажмётся без выбранного типа,
      // но на всякий случай открываем модалку повторно.
      setShowTypeModal(true);
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const created = await createApplication({
        notes: notes || undefined,
        submission_date: submissionDate || undefined,
        applicant_email: applicantEmail || undefined,
        application_type: selectedType,
      });
      router.push(`/admin/applications/${created.id}`);
    } catch (e) {
      setError((e as Error).message);
      setCreating(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <button
        onClick={() => router.push("/admin")}
        className="text-sm text-tertiary hover:text-primary flex items-center gap-1 mb-4 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Назад к списку
      </button>

      <div
        className="bg-primary rounded-xl border p-6"
        style={{
          borderColor: "var(--color-border-tertiary)",
          borderWidth: 0.5,
        }}
      >
        <h1 className="text-xl font-semibold text-primary mb-1">
          Создать новую заявку
        </h1>
        <p className="text-sm text-tertiary mb-4">
          После создания вы получите магическую ссылку для отправки клиенту.
        </p>

        {/* Pack 50.0-C3 fix1 — индикатор выбранного типа + кнопка изменить */}
        {selectedType && (
          <div
            className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg mb-5"
            style={{
              background: selectedType === "EMPLOYMENT" ? "#fef3c7" : "var(--color-bg-secondary)",
              border: selectedType === "EMPLOYMENT" ? "1px solid #eab308" : "0.5px solid var(--color-border-tertiary)",
            }}
          >
            <div className="text-sm font-medium" style={{ color: selectedType === "EMPLOYMENT" ? "#92400e" : "var(--color-text-primary)" }}>
              {APPLICATION_TYPE_BADGE[selectedType].emoji} Тип заявки: {APPLICATION_TYPE_BADGE[selectedType].label}
            </div>
            <button
              type="button"
              onClick={() => setShowTypeModal(true)}
              className="text-xs text-tertiary hover:text-primary transition-colors underline"
            >
              изменить
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-secondary mb-1.5">
              Заметка о клиенте
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Например: Алиев Джафар, рекомендация от Иванова"
              className="w-full px-3 py-2 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
              style={{
                borderColor: "var(--color-border-secondary)",
                borderWidth: 0.5,
              }}
            />
            <p className="text-xs text-tertiary mt-1">
              Чтобы потом можно было найти заявку в списке
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-secondary mb-1.5">
              Email клиента (опционально)
            </label>
            <input
              type="email"
              value={applicantEmail}
              onChange={(e) => setApplicantEmail(e.target.value)}
              placeholder="ivanov@example.com"
              className="w-full px-3 py-2 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
              style={{
                borderColor: "var(--color-border-secondary)",
                borderWidth: 0.5,
              }}
            />
            <p className="text-xs text-tertiary mt-1">
              Для метаданных. Пока письма не отправляются автоматически.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-secondary mb-1.5">
              Планируемая дата подачи в UGE
            </label>
            <input
              type="date"
              value={submissionDate}
              onChange={(e) => setSubmissionDate(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
              style={{
                borderColor: "var(--color-border-secondary)",
                borderWidth: 0.5,
              }}
            />
            <p className="text-xs text-tertiary mt-1">
              Опционально. Можно установить позже на странице заявки.
            </p>
          </div>

          {error && (
            <div className="text-sm text-danger bg-danger p-3 rounded-md">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => router.push("/admin")}
              className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={creating}
              className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 transition-colors flex items-center gap-2"
              style={{ background: "var(--color-accent)" }}
            >
              {creating ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                "Создать заявку"
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Pack 50.0-C3 — модалка выбора типа заявки */}
      {showTypeModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.45)" }}
          onClick={handleModalClose}
        >
          <div
            className="bg-primary rounded-xl border p-6 w-full max-w-md shadow-xl"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-1">
              <h2 className="text-lg font-semibold text-primary">
                Тип заявки на визу
              </h2>
              <button
                onClick={handleModalClose}
                className="text-tertiary hover:text-primary transition-colors"
                title="Закрыть"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm text-tertiary mb-5">
              Выбери тип. От этого зависит набор документов и пакет, который будем готовить.
            </p>

            <div className="space-y-3">
              <button
                type="button"
                onClick={() => handleInitialTypeSelected("SELF_EMPLOYED")}
                className="w-full text-left px-4 py-4 rounded-lg border transition-colors hover:bg-secondary"
                style={{
                  borderColor: "var(--color-border-tertiary)",
                  borderWidth: 0.5,
                }}
              >
                <div className="text-base font-semibold text-primary mb-0.5">
                  🆔 Самозанятый
                </div>
                <div className="text-xs text-tertiary">
                  Клиент работает по ГПХ с заказчиком, оформлен как самозанятый (НПД).
                  Договор оказания услуг, акты, счета, НПД-справка.
                </div>
              </button>

              <button
                type="button"
                onClick={() => handleInitialTypeSelected("EMPLOYMENT")}
                className="w-full text-left px-4 py-4 rounded-lg border-2 transition-colors"
                style={{
                  borderColor: "#eab308",
                  background: "#fef3c7",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = "#fde68a";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = "#fef3c7";
                }}
              >
                <div className="text-base font-semibold mb-0.5" style={{ color: "#92400e" }}>
                  💼 Найм
                </div>
                <div className="text-xs" style={{ color: "#78350f" }}>
                  Клиент работает по трудовому договору с работодателем.
                  Расчётные листки, 2-НДФЛ, ЭТК, свидетельство об отъезде из СФР.
                </div>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
