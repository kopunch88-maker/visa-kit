"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";
import { createApplication } from "@/lib/api";

export default function NewApplicationPage() {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [submissionDate, setSubmissionDate] = useState("");
  const [applicantEmail, setApplicantEmail] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);

    try {
      const created = await createApplication({
        notes: notes || undefined,
        submission_date: submissionDate || undefined,
        applicant_email: applicantEmail || undefined,
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
        <p className="text-sm text-tertiary mb-6">
          После создания вы получите магическую ссылку для отправки клиенту.
        </p>

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
    </div>
  );
}
