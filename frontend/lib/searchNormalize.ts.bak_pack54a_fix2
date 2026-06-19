// Pack 54-A — нормализация поиска: регистр + транслит кириллица<->латиница.
// Приводит и запрос, и поля к одной канонической форме (lower-case латиница),
// чтобы ARDIT == Ardit == ardit == ардит.

const CYR2LAT: Record<string, string> = {
  щ: "shch", ж: "zh", ч: "ch", ш: "sh", ю: "yu", я: "ya",
  х: "kh", ц: "ts", ё: "e", й: "y",
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e",
  з: "z", и: "i", к: "k", л: "l", м: "m", н: "n",
  о: "o", п: "p", р: "r", с: "s", т: "t", у: "u",
  ф: "f", ы: "y", э: "e", ь: "", ъ: "",
};

// ЙЦУКЕН -> QWERTY (на случай "печатал не на той раскладке": фквше -> ardit)
const RU_KEYS = "йцукенгшщзхъфывапролджэячсмитьбю";
const EN_KEYS = "qwertyuiop[]asdfghjkl;'zxcvbnm,.";
const LAYOUT: Record<string, string> = {};
for (let i = 0; i < RU_KEYS.length; i++) {
  const r = RU_KEYS[i];
  const e = EN_KEYS[i];
  if (r && e) LAYOUT[r] = e;
}

export function normalizeForSearch(text: string | null | undefined): string {
  if (!text) return "";
  const lowered = text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "") // убрать диакритику (ñ é ç ...)
    .toLowerCase();
  let out = "";
  for (const ch of lowered) {
    const mapped = CYR2LAT[ch];
    if (mapped !== undefined) out += mapped;
    else if (/[a-z0-9]/.test(ch)) out += ch;
    else out += " ";
  }
  return out.replace(/\s+/g, " ").trim();
}

function layoutSwapped(text: string): string {
  let out = "";
  for (const ch of text.toLowerCase()) {
    const m = LAYOUT[ch];
    out += m !== undefined ? m : ch;
  }
  return out;
}

/**
 * true, если нормализованный запрос — подстрока нормализованного объединения
 * всех переданных полей. Передавай сюда ВСЕ поля сразу (имя native+latin,
 * номер заявки, заметки и т.д.).
 */
export function matchesSearch(
  query: string,
  ...fields: (string | null | undefined)[]
): boolean {
  const nq = normalizeForSearch(query);
  if (!nq) return true; // пустой запрос — пропускаем всё
  const haystack = normalizeForSearch(
    fields.filter((f) => f && f !== "—").join(" "),
  );
  if (!haystack) return false;
  if (haystack.includes(nq)) return true;
  // fallback: запрос мог быть набран в русской раскладке вместо английской
  const swapped = normalizeForSearch(layoutSwapped(query));
  return swapped.length > 0 && haystack.includes(swapped);
}
