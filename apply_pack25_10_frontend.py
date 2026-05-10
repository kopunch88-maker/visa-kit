"""
Pack 25.10 — Frontend для управления банковской выпиской.

Добавляет в ApplicantDrawer:
- Date-picker «Дата формирования выписки» (привязан к application.bank_statement_date)
- Кнопка ✨ Auto — подставляет today - 8 дней
- Кнопка «Перегенерировать выписку» с confirm-диалогом

Также добавляет 2 функции в lib/api.ts:
- regenerateBankTransactions(appId) — POST /api/admin/applications/{id}/bank-transactions/generate

Запуск:
    cd D:\\VISA\\visa_kit\\frontend
    python ..\\apply_pack25_10_frontend.py

(Скрипт можно положить в корень проекта или в backend/, главное — указать абсолютный путь.)
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Найти frontend относительно текущей директории
ROOT_CANDIDATES = [
    Path.cwd() / "frontend",
    Path.cwd().parent / "frontend",
    Path.cwd(),
]
FRONTEND = None
for c in ROOT_CANDIDATES:
    if (c / "lib" / "api.ts").exists() and (c / "components" / "admin" / "ApplicantDrawer.tsx").exists():
        FRONTEND = c
        break

if FRONTEND is None:
    print("ERROR: не найден frontend/. Запускай из visa_kit/ или visa_kit/frontend/.")
    sys.exit(1)

print(f"frontend root: {FRONTEND}")

API_TS = FRONTEND / "lib" / "api.ts"
DRAWER_TSX = FRONTEND / "components" / "admin" / "ApplicantDrawer.tsx"

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
api_backup = API_TS.with_name(API_TS.name + f".bak_pre_pack25_10_{ts}")
drawer_backup = DRAWER_TSX.with_name(DRAWER_TSX.name + f".bak_pre_pack25_10_{ts}")
shutil.copy2(API_TS, api_backup)
shutil.copy2(DRAWER_TSX, drawer_backup)
print(f"[1/3] Бэкапы:")
print(f"      {api_backup.name}")
print(f"      {drawer_backup.name}")


# === 2. Patch api.ts — добавить regenerateBankTransactions ===
api_text = API_TS.read_text(encoding="utf-8")

api_addition = '''

// Pack 25.10 — Bank statement transactions
export interface BankTransactionItem {
  transaction_date: string;
  code: string;
  description: string;
  amount: string;
  currency: string;
}

export interface BankStatementResponse {
  application_id: number;
  period_start: string;
  period_end: string;
  opening_balance: string;
  total_income: string;
  total_expense: string;
  transaction_count: number;
  transactions: BankTransactionItem[];
}

/**
 * Перегенерирует банковские транзакции для заявки.
 * Использует application.bank_statement_date если он задан,
 * иначе — today - random(7..10).
 * ВАЖНО: перезаписывает существующий bank_transactions_override.
 */
export async function regenerateBankTransactions(
  appId: number
): Promise<BankStatementResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${appId}/bank-transactions/generate`,
    {
      method: "POST",
      headers: jsonHeaders(),
    }
  );
  if (!res.ok) throw new Error(`Failed to regenerate bank transactions: ${res.status}`);
  return res.json();
}

/**
 * Получить текущие банковские транзакции заявки (если override установлен).
 * Возвращает null если override пустой.
 */
export async function getBankTransactions(
  appId: number
): Promise<BankStatementResponse | null> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${appId}/bank-transactions`,
    { headers: authHeaders() }
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to fetch bank transactions: ${res.status}`);
  return res.json();
}
'''

if "regenerateBankTransactions" in api_text:
    print(f"[2/3] api.ts: regenerateBankTransactions уже есть — пропуск")
else:
    api_text = api_text.rstrip() + "\n" + api_addition
    API_TS.write_text(api_text, encoding="utf-8")
    print(f"[2/3] api.ts: добавлены regenerateBankTransactions, getBankTransactions, типы")


# === 3. Patch ApplicantDrawer.tsx ===
drawer_text = DRAWER_TSX.read_text(encoding="utf-8")
patches = 0

# 3a. Добавить импорты (FileText, Calendar, regenerateBankTransactions, ApplicationResponse, patchApplication)
old_import = '''import {
  ApplicantResponse,
  updateApplicant,
  transliterateLatToRu,
  BankResponse,
  listBanks,
  generateAccount,
  regenerateAddress, // Pack 18.8: перегенерация адреса
  regenerateEducation, // Pack 19.0: автогенерация образования
  regenerateWorkHistory, // Pack 19.1: автогенерация work_history
} from "@/lib/api";'''

new_import = '''import {
  ApplicantResponse,
  updateApplicant,
  transliterateLatToRu,
  BankResponse,
  listBanks,
  generateAccount,
  regenerateAddress, // Pack 18.8: перегенерация адреса
  regenerateEducation, // Pack 19.0: автогенерация образования
  regenerateWorkHistory, // Pack 19.1: автогенерация work_history
  // Pack 25.10 — банковская выписка
  ApplicationResponse,
  patchApplication,
  regenerateBankTransactions,
} from "@/lib/api";'''

if old_import in drawer_text:
    drawer_text = drawer_text.replace(old_import, new_import)
    patches += 1
    print(f"[3/3a] ApplicantDrawer: импорты обновлены")
else:
    # fallback — попробуем найти любой блок импортов из api и добавить туда
    import re
    m = re.search(r'} from "@/lib/api";', drawer_text)
    if m:
        # Добавим перед закрывающей скобкой
        old_close = '} from "@/lib/api";'
        new_close = '''  // Pack 25.10 — банковская выписка
  ApplicationResponse,
  patchApplication,
  regenerateBankTransactions,
} from "@/lib/api";'''
        drawer_text = drawer_text.replace(old_close, new_close, 1)
        patches += 1
        print(f"[3/3a] ApplicantDrawer: импорты обновлены (fallback)")
    else:
        print(f"[3/3a] [!] WARN: импорты api не найдены")


# 3b. Добавить иконку CalendarRange в lucide-react импорт
old_icons = '''import {
  X, Loader2, Sparkles, AlertCircle, Save, User, Wand2, Landmark,
  CheckCircle2, XCircle, MinusCircle, // Pack 18.5 — статус проверки ИНН через ФНС
  Trash2, Plus, // Pack 19.0.3 — управление записями education
} from "lucide-react";'''

new_icons = '''import {
  X, Loader2, Sparkles, AlertCircle, Save, User, Wand2, Landmark,
  CheckCircle2, XCircle, MinusCircle, // Pack 18.5 — статус проверки ИНН через ФНС
  Trash2, Plus, // Pack 19.0.3 — управление записями education
  FileText, RefreshCw, // Pack 25.10 — банковская выписка
} from "lucide-react";'''

if old_icons in drawer_text:
    drawer_text = drawer_text.replace(old_icons, new_icons)
    patches += 1
    print(f"[3/3b] ApplicantDrawer: иконки добавлены")
else:
    print(f"[3/3b] [!] WARN: блок иконок не найден")


# 3c. Расширить Props интерфейс — добавить опциональный application + onApplicationSaved
old_props = '''interface Props {
  applicant: ApplicantResponse;
  onClose: () => void;
  onSaved: () => void;
}'''

new_props = '''interface Props {
  applicant: ApplicantResponse;
  // Pack 25.10 — опционально: если передан, показывается секция «Банковская выписка»
  application?: ApplicationResponse;
  onApplicationSaved?: () => void;
  onClose: () => void;
  onSaved: () => void;
}'''

if old_props in drawer_text:
    drawer_text = drawer_text.replace(old_props, new_props)
    patches += 1
    print(f"[3/3c] ApplicantDrawer: Props расширен")
else:
    print(f"[3/3c] [!] WARN: интерфейс Props не найден")


# 3d. Расширить функциональную сигнатуру компонента
old_sig = 'export function ApplicantDrawer({ applicant, onClose, onSaved }: Props) {'
new_sig = 'export function ApplicantDrawer({ applicant, application, onApplicationSaved, onClose, onSaved }: Props) {'

if old_sig in drawer_text:
    drawer_text = drawer_text.replace(old_sig, new_sig)
    patches += 1
    print(f"[3/3d] ApplicantDrawer: сигнатура обновлена")
else:
    print(f"[3/3d] [!] WARN: сигнатура компонента не найдена")


# 3e. Добавить state и хелперы для банковской выписки (после useState'ов перед useEffect listBanks)
old_state_anchor = '''  // Pack 18.8: перегенерация адреса
  const [addressRegenerating, setAddressRegenerating] = useState(false);'''

new_state_anchor = '''  // Pack 18.8: перегенерация адреса
  const [addressRegenerating, setAddressRegenerating] = useState(false);

  // Pack 25.10 — банковская выписка
  const [bankStatementDate, setBankStatementDate] = useState<string>(
    (application as any)?.bank_statement_date || ""
  );
  const [bankRegenerating, setBankRegenerating] = useState(false);
  const hasOverride = !!(application as any)?.bank_transactions_override;'''

if old_state_anchor in drawer_text:
    drawer_text = drawer_text.replace(old_state_anchor, new_state_anchor)
    patches += 1
    print(f"[3/3e] ApplicantDrawer: state банковской выписки добавлен")
else:
    print(f"[3/3e] [!] WARN: якорь для state не найден (Pack 18.8 строка)")


# 3f. Добавить handler для перегенерации (перед handleSave)
old_save_anchor = '  async function handleSave() {'

new_save_handler = '''  // Pack 25.10 — кнопка ✨ Auto: today - 8 дней (середина диапазона 7..10)
  function handleAutoStatementDate() {
    const d = new Date();
    d.setDate(d.getDate() - 8);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    setBankStatementDate(`${yyyy}-${mm}-${dd}`);
  }

  // Pack 25.10 — перегенерировать банковскую выписку.
  // 1. Если есть существующий override — confirm.
  // 2. PATCH application с новой bank_statement_date (или null чтобы сбросить).
  // 3. POST bank-transactions/generate.
  async function handleRegenerateBankStatement() {
    if (!application) return;
    if (hasOverride) {
      const ok = window.confirm(
        "У этой заявки уже есть сохранённая выписка. " +
        "Все ручные правки транзакций будут потеряны. Продолжить?"
      );
      if (!ok) return;
    }
    setBankRegenerating(true);
    setError(null);
    try {
      // Сохраняем дату формирования (или null если поле пустое)
      const currentDate = (application as any).bank_statement_date || null;
      const newDate = bankStatementDate || null;
      if (currentDate !== newDate) {
        await patchApplication(application.id, {
          bank_statement_date: newDate,
        } as any);
      }
      // Перегенерируем транзакции
      await regenerateBankTransactions(application.id);
      // Сообщаем родителю что application изменился
      if (onApplicationSaved) onApplicationSaved();
    } catch (e) {
      setError(`Не удалось перегенерировать выписку: ${(e as Error).message}`);
    } finally {
      setBankRegenerating(false);
    }
  }

  async function handleSave() {'''

if old_save_anchor in drawer_text:
    drawer_text = drawer_text.replace(old_save_anchor, new_save_handler, 1)
    patches += 1
    print(f"[3/3f] ApplicantDrawer: handlers перегенерации добавлены")
else:
    print(f"[3/3f] [!] WARN: якорь handleSave не найден")


# 3g. Добавить секцию UI после секции «Банк» (после закрывающего </Section> у Pack 16 Банк)
# Якорь — конец секции Банк: ищем закрытие `Pack 16: Банк` Section'а
# Конкретный паттерн: } </Section> + следующий комментарий "Pack 18.9 — подписант апостиля"
old_ui_anchor = '''          {/* Pack 18.9 — подписант апостиля (опционально, по умолчанию Байрамов Н.А.) */}'''

new_ui_section = '''          {/* Pack 25.10 — Банковская выписка (показывается только если передан application) */}
          {application && (
            <Section
              title="Банковская выписка"
              icon={<FileText className="w-3.5 h-3.5" />}
            >
              <p className="text-xs text-tertiary mb-3">
                Дата формирования выписки. По умолчанию (если поле пустое) генератор
                ставит дату <strong>сегодня минус 7-10 дней</strong> — реалистично для подачи
                на визу. При желании можно задать конкретную дату.
              </p>

              <Field
                label="Дата формирования"
                value={bankStatementDate}
                onChange={setBankStatementDate}
                type="date"
                actionButton={
                  <button
                    type="button"
                    onClick={handleAutoStatementDate}
                    className="text-xs px-2.5 py-1 rounded-md text-white transition-colors flex items-center gap-1 whitespace-nowrap"
                    style={{ background: "var(--color-accent)" }}
                    title="Подставить сегодня минус 8 дней"
                  >
                    <Sparkles className="w-3 h-3" />
                    Auto
                  </button>
                }
              />
              <p className="text-[11px] text-tertiary mt-1">
                Период выписки = 3 месяца до этой даты, включая её.
                Например: 27.04.2026 → выписка 27.01.2026 — 27.04.2026.
              </p>

              <div className="pt-2">
                <button
                  type="button"
                  onClick={handleRegenerateBankStatement}
                  disabled={bankRegenerating}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm w-full justify-center"
                  style={{
                    background: "var(--color-bg-secondary)",
                    border: "1px solid var(--color-border-tertiary)",
                    color: "var(--color-text-primary)",
                  }}
                >
                  {bankRegenerating ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Перегенерируем...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      {hasOverride ? "Перегенерировать выписку" : "Сгенерировать выписку"}
                    </>
                  )}
                </button>
                <p className="text-[11px] text-tertiary mt-2">
                  {hasOverride
                    ? "⚠ Существующие транзакции будут перезаписаны"
                    : "Создаст черновик транзакций по текущим настройкам"}
                </p>
              </div>
            </Section>
          )}

          {/* Pack 18.9 — подписант апостиля (опционально, по умолчанию Байрамов Н.А.) */}'''

if old_ui_anchor in drawer_text:
    drawer_text = drawer_text.replace(old_ui_anchor, new_ui_section, 1)
    patches += 1
    print(f"[3/3g] ApplicantDrawer: UI секция «Банковская выписка» добавлена")
else:
    print(f"[3/3g] [!] WARN: якорь Pack 18.9 не найден — UI не добавлен")
    print(f"        Возможно текст комментария отличается. Поправь руками.")


DRAWER_TSX.write_text(drawer_text, encoding="utf-8")


print(f"\n=== Pack 25.10 frontend применён ({patches}/7 патчей) ===\n")

if patches < 7:
    print(f"[!] Не все патчи применились. Проверь warnings выше.")
    print(f"    Возможно файл уже изменён или комментарии в нём другие.")
    print(f"    Откат: Copy-Item -Force '{drawer_backup}' '{DRAWER_TSX}'")
    print(f"           Copy-Item -Force '{api_backup}' '{API_TS}'")

print()
print("СЛЕДУЮЩИЕ ШАГИ:")
print()
print("1. Найди где открывается ApplicantDrawer и передай туда application:")
print('   Get-ChildItem -Recurse -Path "D:\\VISA\\visa_kit\\frontend" -Include "*.tsx" |')
print('     Select-String -Pattern "<ApplicantDrawer" -Context 0,3 |')
print('     ForEach-Object { $_.ToString() }')
print()
print("   В местах вызова добавь props: application={application} onApplicationSaved={refreshApp}")
print("   Если application не передан — секция просто не показывается (безопасно).")
print()
print("2. Проверь:")
print("   cd D:\\VISA\\visa_kit\\frontend")
print("   npm run build")
print("   (или npm run dev и открой Drawer — посмотри на новую секцию внизу)")
print()
print("3. Если всё ок — пуш:")
print("   git add lib/api.ts components/admin/ApplicantDrawer.tsx <место_вызова_Drawer>.tsx")
print("   git commit -m 'Pack 25.10: bank statement date picker + regenerate button in ApplicantDrawer'")
print("   git push")
print()
print(f"Откат:")
print(f"  Copy-Item -Force '{drawer_backup}' '{DRAWER_TSX}'")
print(f"  Copy-Item -Force '{api_backup}' '{API_TS}'")
