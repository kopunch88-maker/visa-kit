"use client";

import { useState } from "react";
import { Sparkles, Copy, Check } from "lucide-react";

/**
 * ApostilleEstimator (Pack 56) — внутренний калькулятор примерного номера
 * апостиля по дате получения. Без бэка: чистый клиентский расчёт.
 *
 * Номера сквозные по стране, но темп выдачи НЕ постоянный, поэтому —
 * кусочно-линейная аппроксимация по реальным якорным точкам:
 *   - между двумя известными номерами — по локальному темпу отрезка;
 *   - до самой ранней точки — по темпу первого отрезка;
 *   - после самой поздней — экстраполяция по свежему темпу
 *     (окно 2025-09-30 -> 2026-05-06 ~= 104.29 ном/день ~= 3175/мес).
 * Модель проходит ТОЧНО через каждую якорную точку.
 *
 * Это ОЦЕНКА «для внутренней кухни», не официальный номер.
 * Уточнение модели — добавляй новые пары [номер, "YYYY-MM-DD"] в ANCHORS
 * (строго по возрастанию даты).
 */

const ANCHORS: [number, string][] = [
  [140192, "2013-05-20"],
  [149323, "2013-12-23"],
  [177642, "2015-12-05"],
  [204661, "2017-06-26"],
  [235749, "2018-09-19"],
  [521993, "2019-12-23"],
  [801505, "2025-09-30"],
  [810946, "2026-01-22"],
  [823642, "2026-05-04"],
  [824241, "2026-05-06"],
];

const DAY_MS = 86_400_000;
const toDays = (iso: string) =>
  Math.round(new Date(iso + "T00:00:00").getTime() / DAY_MS);

const RECENT_FROM = ANCHORS[6];
const RECENT_TO = ANCHORS[ANCHORS.length - 1];
const RECENT_PER_DAY =
  (RECENT_TO[0] - RECENT_FROM[0]) /
  (toDays(RECENT_TO[1]) - toDays(RECENT_FROM[1]));

function estimateApostille(iso: string): number {
  const t = toDays(iso);
  const first = ANCHORS[0];
  const last = ANCHORS[ANCHORS.length - 1];

  if (t <= toDays(first[1])) {
    const [n0, d0] = first;
    const [n1, d1] = ANCHORS[1];
    const slope = (n1 - n0) / (toDays(d1) - toDays(d0));
    return Math.round(n0 + slope * (t - toDays(d0)));
  }
  if (t >= toDays(last[1])) {
    return Math.round(last[0] + RECENT_PER_DAY * (t - toDays(last[1])));
  }
  for (let i = 1; i < ANCHORS.length; i++) {
    const [na, da] = ANCHORS[i - 1];
    const [nb, db] = ANCHORS[i];
    const ta = toDays(da);
    const tb = toDays(db);
    if (t >= ta && t <= tb) {
      const slope = (nb - na) / (tb - ta);
      return Math.round(na + slope * (t - ta));
    }
  }
  return last[0];
}

export function ApostilleEstimator() {
  const [date, setDate] = useState<string>("");
  const [result, setResult] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  const generate = () => {
    if (!date) return;
    setResult(estimateApostille(date));
    setCopied(false);
  };

  const copy = async () => {
    if (result == null) return;
    try {
      await navigator.clipboard.writeText(String(result));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard недоступен */
    }
  };

  const inputStyle = {
    borderColor: "var(--color-border-tertiary)",
    borderWidth: 0.5,
    background: "var(--color-bg-primary)",
    color: "var(--color-text-primary)",
  } as const;

  return (
    <>
      <p className="text-xs text-tertiary">
        Примерный номер по дате получения — аппроксимация по реальным данным.
        Для внутренней кухни, не официальный номер.
      </p>

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-tertiary">Дата получения</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && generate()}
            className="text-sm px-2 py-1.5 rounded border"
            style={inputStyle}
          />
        </div>

        <button
          type="button"
          onClick={generate}
          disabled={!date}
          className="text-xs flex items-center gap-1 px-2.5 py-1.5 rounded text-primary border hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ borderColor: "var(--color-border-tertiary)" }}
        >
          <Sparkles className="w-3.5 h-3.5" />
          Сгенерировать
        </button>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-tertiary">Примерный номер</label>
          <div className="relative">
            <input
              readOnly
              value={result != null ? `№${result}` : ""}
              placeholder="№—"
              className="text-sm font-mono px-2 py-1.5 pr-8 rounded border w-36"
              style={inputStyle}
            />
            {result != null && (
              <button
                type="button"
                onClick={copy}
                title="Скопировать"
                className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-secondary"
                style={{
                  color: copied ? "#16a34a" : "var(--color-text-tertiary)",
                }}
              >
                {copied ? (
                  <Check className="w-3.5 h-3.5" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
