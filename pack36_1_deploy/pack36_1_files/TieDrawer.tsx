"use client";

import { useState, useEffect } from "react";
import { X, Loader2, AlertCircle, CreditCard } from "lucide-react";
import { ApplicationResponse, patchApplication } from "@/lib/api";

interface Props {
  application: ApplicationResponse;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Pack 36.1 — drawer для редактирования NIE и даты отпечатков.
 * Используется TieCard.onEdit.
 */
export function TieDrawer({ application, onClose, onSaved }: Props) {
  const [nie, setNie] = useState<string>(application.nie || "");
  const [fingerprintDate, setFingerprintDate] = useState<string>(
    application.fingerprint_date || ""
  );

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  // Простая валидация NIE: буква + 6-7 цифр + буква. Z3751311Q.
  const nieClean = nie.replace(/[\s-]/g, "").toUpperCase();
  const nieValid =
    nieClean === "" ||
    /^[XYZ]?\d{6,8}[A-Z]$/.test(nieClean);

  async function handleSave() {
    setSaveError(null);
    if (!nieValid) {
      setSaveError(
        "NIE некорректный. Формат: Z3751311Q (буква + цифры + буква)."
      );
      return;
    }
    setSaving(true);
    try {
      await patchApplication(application.id, {
        nie: nieClean || undefined,
        fingerprint_date: fingerprintDate || undefined,
      } as any);
      onSaved();
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-30" onClick={onClose} />
      <div
        className="fixed right-0 top-0 h-screen w-full sm:w-[500px] bg-primary z-40 shadow-2xl overflow-y-auto"
        style={{ borderLeft: "0.5px solid var(--color-border-tertiary)" }}
      >
        <div
          className="sticky top-0 bg-primary border-b px-5 py-4 flex items-center justify-between z-10"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderBottomWidth: 0.5,
          }}
        >
          <h2 className="text-lg font-semibold text-primary flex items-center gap-2">
            <CreditCard className="w-5 h-5" />
            Карта TIE · #{application.reference}
          </h2>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-tertiary hover:text-primary hover:bg-secondary"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div className="bg-secondary rounded-md p-3 text-xs text-secondary">
            Заполняется после одобрения заявления MI-T и получения уведомления
            от полиции с номером NIE. Дата отпечатков — день визита заявителя
            в комиссариат для биометрии (она же ставится как дата подписи в
            формах MI-TIE и EX-17).
          </div>

          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              N.I.E
            </label>
            <input
              type="text"
              value={nie}
              onChange={(e) => setNie(e.target.value.toUpperCase())}
              placeholder="Z3751311Q"
              className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary font-mono focus:outline-none focus:ring-2"
              style={{
                borderColor: nieValid
                  ? "var(--color-border-secondary)"
                  : "var(--color-danger)",
                borderWidth: 0.5,
              }}
            />
            <p className="text-xs text-tertiary mt-1">
              Формат: буква + 6-8 цифр + буква. Пример: Z3751311Q
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              Дата отпечатков
            </label>
            <input
              type="date"
              value={fingerprintDate}
              onChange={(e) => setFingerprintDate(e.target.value)}
              className="w-full px-2 py-1.5 text-sm rounded-md border bg-primary text-primary focus:outline-none focus:ring-2"
              style={{
                borderColor: "var(--color-border-secondary)",
                borderWidth: 0.5,
              }}
            />
            <p className="text-xs text-tertiary mt-1">
              Эта дата подставится в формы MI-TIE и EX-17 как дата подписи
              ("BARCELONA, a 20 de JUNIO de 2026")
            </p>
          </div>

          {saveError && (
            <div className="bg-danger text-danger text-sm p-3 rounded-md flex items-start gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>{saveError}</div>
            </div>
          )}
        </div>

        <div
          className="sticky bottom-0 bg-primary border-t px-5 py-3 flex justify-end gap-2"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderTopWidth: 0.5,
          }}
        >
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
          >
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !nieValid}
            className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 flex items-center gap-2"
            style={{ background: "var(--color-accent)" }}
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Сохранить"}
          </button>
        </div>
      </div>
    </>
  );
}
