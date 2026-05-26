"use client";

// Pack 41.0-D — секция управления несколькими паспортами клиента.
// Backend стандарт: applicant.passports[] (JSONB-массив), плюс
// applicant.passport_id_for_ru_docs для выбора паспорта в русских документах.

import { useState } from "react";
import { Loader2, Plus, Trash2, Sparkles, Wand2 } from "lucide-react";
import type { PassportRecord } from "@/lib/api";
import { resolvePassportIssuerRu } from "@/lib/api";

type PassportTypeValue = "RU_INTERNAL" | "RU_FOREIGN" | "FOREIGN" | "";

const PASSPORT_TYPE_OPTIONS: Array<{ value: PassportTypeValue; label: string }> = [
  { value: "", label: "— Не определён —" },
  { value: "FOREIGN", label: "Иностранный (FOREIGN)" },
  { value: "RU_FOREIGN", label: "Загранпаспорт РФ" },
  { value: "RU_INTERNAL", label: "Паспорт РФ (внутренний)" },
];

interface Props {
  passports: PassportRecord[];
  setPassports: (next: PassportRecord[]) => void;
  passportIdForRuDocs: string | null;
  setPassportIdForRuDocs: (id: string | null) => void;
  nationality: string;
}

function shortUid(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(4)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function makeNewPassport(): PassportRecord {
  return {
    id: `p_${shortUid()}`,
    number: "",
    issue_date: null,
    expiry_date: null,
    issuer: null,
    issuer_ru: null,
    passport_type: null,
    is_primary: false,
    notes: null,
    source: "manual",
  };
}

function passportTypeBadgeColor(type: string | null | undefined): string {
  switch (type) {
    case "RU_INTERNAL":
      return "bg-amber-100 text-amber-800";
    case "RU_FOREIGN":
      return "bg-blue-100 text-blue-800";
    case "FOREIGN":
      return "bg-emerald-100 text-emerald-800";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

function sourceBadgeColor(source: string | null | undefined): string {
  switch (source) {
    case "ocr":
      return "bg-purple-100 text-purple-700";
    case "manual":
      return "bg-slate-100 text-slate-700";
    case "legacy_backfill":
      return "bg-orange-100 text-orange-700";
    default:
      return "bg-slate-100 text-slate-500";
  }
}

export function PassportsSection({
  passports,
  setPassports,
  passportIdForRuDocs,
  setPassportIdForRuDocs,
  nationality,
}: Props) {
  const [resolvingForId, setResolvingForId] = useState<string | null>(null);

  const handleAdd = () => {
    setPassports([...passports, makeNewPassport()]);
  };

  const handleDelete = (id: string) => {
    if (!window.confirm("Удалить этот паспорт?")) return;
    const next = passports.filter((p) => p.id !== id);
    setPassports(next);
    if (passportIdForRuDocs === id) {
      setPassportIdForRuDocs(null);
    }
  };

  const handleUpdate = (id: string, patch: Partial<PassportRecord>) => {
    const next = passports.map((p) => (p.id === id ? { ...p, ...patch } : p));
    setPassports(next);
  };

  const handleResolveIssuerRu = async (rec: PassportRecord) => {
    if (!rec.issuer || !rec.issuer.trim()) {
      window.alert("Сначала укажи «Кем выдан» (англ./исп.)");
      return;
    }
    setResolvingForId(rec.id);
    try {
      const response = await resolvePassportIssuerRu(rec.issuer, nationality || null);
      if (response?.resolved) {
        handleUpdate(rec.id, { issuer_ru: response.resolved });
      } else {
        window.alert("Не удалось определить русское название");
      }
    } catch (err) {
      console.error("Pack 41.0-D resolvePassportIssuerRu failed:", err);
      window.alert("Ошибка при определении русского названия");
    } finally {
      setResolvingForId(null);
    }
  };

  const ruInternal = passports.find((p) => p.passport_type === "RU_INTERNAL");
  const showUseRuInternalHint =
    ruInternal && passportIdForRuDocs !== ruInternal.id;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-900">Паспорта</h3>
        <button
          type="button"
          onClick={handleAdd}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md
                     border border-slate-300 bg-white text-slate-900 hover:bg-slate-50"
        >
          <Plus className="w-4 h-4" />
          Добавить паспорт
        </button>
      </div>

      {passports.length === 0 && (
        <div className="text-sm text-slate-500 italic px-4 py-6 border border-dashed
                        border-slate-300 rounded-md text-center">
          Нет паспортов. Они появятся после OCR или нажми «Добавить паспорт».
        </div>
      )}

      {passports.map((rec) => (
        <div
          key={rec.id}
          className="border border-slate-200 rounded-lg p-4 space-y-3 bg-white"
        >
          <div className="flex items-center gap-2 flex-wrap">
            {rec.is_primary && (
              <span className="inline-flex items-center px-2 py-0.5 text-xs
                              font-semibold rounded-full bg-green-100 text-green-800">
                🟢 PRIMARY
              </span>
            )}
            <span className={`inline-flex items-center px-2 py-0.5 text-xs
                              font-medium rounded-full ${passportTypeBadgeColor(rec.passport_type)}`}>
              {rec.passport_type || "тип не задан"}
            </span>
            <span className={`inline-flex items-center px-2 py-0.5 text-xs
                              font-medium rounded-full ${sourceBadgeColor(rec.source)}`}>
              {rec.source || "manual"}
            </span>
            {passportIdForRuDocs === rec.id && (
              <span className="inline-flex items-center px-2 py-0.5 text-xs
                              font-semibold rounded-full bg-amber-100 text-amber-800">
                🇷🇺 ДЛЯ РУС. ДОКОВ
              </span>
            )}
            <div className="flex-1" />
            <button
              type="button"
              onClick={() => handleDelete(rec.id)}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md
                         text-red-700 hover:bg-red-50"
              title="Удалить паспорт"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Удалить
            </button>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-slate-700">
                  Номер паспорта
                </label>
                <input
                  type="text"
                  value={rec.number}
                  onChange={(e) => handleUpdate(rec.id, { number: e.target.value })}
                  placeholder="BD1825376 или 4612 978898"
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2
                             text-sm placeholder-slate-400 focus:border-slate-500 focus:outline-none"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-slate-700">
                  Тип
                </label>
                <select
                  value={rec.passport_type || ""}
                  onChange={(e) =>
                    handleUpdate(rec.id, {
                      passport_type: (e.target.value as PassportTypeValue) || null,
                    })
                  }
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2
                             text-sm focus:border-slate-500 focus:outline-none"
                >
                  {PASSPORT_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-slate-700">
                  Дата выдачи
                </label>
                <input
                  type="date"
                  value={rec.issue_date || ""}
                  onChange={(e) =>
                    handleUpdate(rec.id, { issue_date: e.target.value || null })
                  }
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2
                             text-sm focus:border-slate-500 focus:outline-none"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-slate-700">
                  Дата окончания
                  {rec.passport_type === "RU_INTERNAL" && (
                    <span className="ml-1 text-xs text-slate-400">(не нужно для RU_INTERNAL)</span>
                  )}
                </label>
                <input
                  type="date"
                  value={rec.expiry_date || ""}
                  onChange={(e) =>
                    handleUpdate(rec.id, { expiry_date: e.target.value || null })
                  }
                  disabled={rec.passport_type === "RU_INTERNAL"}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2
                             text-sm focus:border-slate-500 focus:outline-none
                             disabled:bg-slate-50 disabled:text-slate-400"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-slate-700">
                Кем выдан (англ./исп./нац.)
              </label>
              <input
                type="text"
                value={rec.issuer || ""}
                onChange={(e) =>
                  handleUpdate(rec.id, { issuer: e.target.value || null })
                }
                placeholder="Ministry of Internal Affairs / Pasaporta Republikës..."
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2
                           text-sm placeholder-slate-400 focus:border-slate-500 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-slate-700">
                Кем выдан (рус., для договора)
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={rec.issuer_ru || ""}
                  onChange={(e) =>
                    handleUpdate(rec.id, { issuer_ru: e.target.value || null })
                  }
                  placeholder="МВД Албании / посольством КНР в России"
                  className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2
                             text-sm placeholder-slate-400 focus:border-slate-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => handleResolveIssuerRu(rec)}
                  disabled={resolvingForId === rec.id}
                  className="text-xs px-2.5 py-1 rounded-md text-white transition-colors
                             flex items-center gap-1 whitespace-nowrap disabled:opacity-50"
                  style={{ background: "var(--color-accent, #475569)" }}
                  title="Сгенерировать на основе английского варианта и гражданства"
                >
                  {resolvingForId === rec.id ? (
                    <>
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Резолв...
                    </>
                  ) : (
                    <>
                      <Wand2 className="w-3 h-3" />
                      Резолв
                    </>
                  )}
                </button>
              </div>
            </div>

            {rec.notes && (
              <div className="text-xs text-slate-500 italic">
                Заметка: {rec.notes}
              </div>
            )}
          </div>
        </div>
      ))}

      {passports.length > 0 && (
        <div className="border-t border-slate-200 pt-4 space-y-2">
          <label className="block text-sm font-medium text-slate-700">
            🇷🇺 Паспорт для русских документов
          </label>
          <div className="flex gap-2 items-center">
            <select
              value={passportIdForRuDocs || ""}
              onChange={(e) => setPassportIdForRuDocs(e.target.value || null)}
              className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2
                         text-sm focus:border-slate-500 focus:outline-none"
            >
              <option value="">— Автоматически (primary) —</option>
              {passports.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.number || "(без номера)"} · {p.passport_type || "—"}
                  {p.is_primary ? " · primary" : ""}
                </option>
              ))}
            </select>
            {showUseRuInternalHint && ruInternal && (
              <button
                type="button"
                onClick={() => setPassportIdForRuDocs(ruInternal.id)}
                className="inline-flex items-center gap-1 px-3 py-2 text-xs rounded-md
                           bg-amber-50 border border-amber-300 text-amber-900 hover:bg-amber-100
                           whitespace-nowrap"
                title="Для российских клиентов в русских документах нужен внутренний паспорт РФ"
              >
                <Sparkles className="w-3 h-3" />
                Использовать внутренний РФ
              </button>
            )}
          </div>
          <p className="text-xs text-slate-500">
            <strong>01_Договор.docx</strong> — подставляется выбранный паспорт
            (для любого клиента, любой тип паспорта; договор может быть на
            старый паспорт исторически).
            <br />
            <strong>10_Выписка.docx</strong> — выбранный паспорт подставляется
            ТОЛЬКО для русских клиентов (nationality=RUS) и ТОЛЬКО если выбран
            внутренний паспорт РФ. Для иностранцев и в остальных кейсах →
            primary (самый свежий).
            <br />
            Остальные документы (акты, счета, НПД, апостиль, испанские формы)
            → всегда primary.
          </p>
        </div>
      )}
    </div>
  );
}
