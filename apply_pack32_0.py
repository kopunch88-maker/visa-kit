"""
Pack 32.0 — карандаш для редактирования кандидата сразу при создании заявки.

Проблема:
  Когда менеджер создаёт пустую заявку через «+ Создать заявку», у неё
  applicant_id = NULL. В CandidateCard показывается «Ожидание данных от
  клиента» БЕЗ карандаша — менеджер не может вбить данные сам, ждёт пока
  клиент заполнит анкету.

Решение:
  1. Backend: новый endpoint POST /admin/applicants/for-application/{app_id}
     создаёт пустого Applicant с placeholder именами «—» (тот же приём,
     что в import_package.py:_auto_apply_ocr_to_applicant), привязывает
     application.applicant_id, возвращает _enrich(applicant).
     Идемпотентен: если applicant уже есть — возвращает существующего.

  2. Frontend lib/api.ts: новая функция createApplicantForApplication(appId).

  3. ApplicationDetail.tsx: карандаш показывается ВСЕГДА. Если applicant=null —
     по клику сначала создаём пустого, дожидаемся, перезагружаем, открываем Drawer.

  4. CandidateCard.tsx:
     - Кнопка «Изменить» (идентичная поздней) показывается всегда — onEdit
       приходит безусловно из ApplicationDetail.
     - Если applicant=null показывается тот же layout что и для созданного
       (просто все поля = «—»), вместо строки «Ожидание данных от клиента» —
       плейсхолдеры «—» в полях.

Файлы:
  backend/app/api/applicants.py             — добавляем endpoint в конец
  frontend/lib/api.ts                       — добавляем функцию
  frontend/components/admin/ApplicationDetail.tsx       — полная замена
  frontend/components/admin/cards/CandidateCard.tsx     — полная замена

Все frontend-файлы пишутся ПОЛНОСТЬЮ (Правило 5). Backend — точечная вставка
endpoint'а (он не пересекается с существующими).

Запуск (PowerShell, из D:\\VISA\\visa_kit):
    python apply_pack32_0.py
    git add backend/app/api/applicants.py frontend/lib/api.ts frontend/components/admin/ApplicationDetail.tsx frontend/components/admin/cards/CandidateCard.tsx
    git commit -m "Pack 32.0: empty applicant edit pencil"
    git push
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


# =============================================================================
# Helpers
# =============================================================================

def write_text(path: Path, text: str, label: str) -> None:
    """Записывает файл UTF-8 без BOM, с LF переводами строк."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"    [OK] {label}: {path}")


def assert_python_syntax(path: Path) -> None:
    """Правило 6 — проверка синтаксиса до отдачи."""
    src = path.read_text(encoding="utf-8")
    try:
        ast.parse(src)
    except SyntaxError as e:
        raise SystemExit(f"[FATAL] Python syntax error in {path}: {e}")


def patch_backend_applicants(repo_root: Path) -> None:
    """
    Backend: добавляем endpoint POST /for-application/{app_id} в applicants.py.
    Точечная вставка через append — endpoint не пересекается с существующим
    кодом, и его легко удалить откатом коммита.
    """
    path = repo_root / "backend" / "app" / "api" / "applicants.py"
    if not path.exists():
        raise SystemExit(f"[FATAL] not found: {path}")

    text = path.read_text(encoding="utf-8")

    # Если уже применено — пропускаем (Правило 33: маркер должен быть уникален).
    marker = "# Pack 32.0 — POST /for-application/{app_id}"
    if marker in text:
        print("    [SKIP] applicants.py: Pack 32.0 endpoint уже добавлен")
        return

    # Импорт Application понадобится для нового endpoint'а — добавим если ещё нет.
    if "from app.models import Applicant" in text and "Application" not in text.split(
        "from app.models import Applicant"
    )[1].split("\n")[0]:
        text = text.replace(
            "from app.models import Applicant",
            "from app.models import Applicant, Application",
            1,
        )
        print("    [OK] applicants.py: Application добавлен в импорт из app.models")

    new_endpoint = '''


# ============================================================================
# Pack 32.0 — POST /for-application/{app_id}
# ============================================================================
# Создаёт пустого Applicant'а с placeholder ФИО «—» и привязывает к указанной
# Application. Используется когда менеджер хочет начать редактировать карточку
# кандидата СРАЗУ после создания пустой заявки, не дожидаясь пока клиент
# заполнит анкету через свой кабинет.
#
# Если у application уже есть applicant_id — возвращает существующего (идемпотентно).
# Placeholder'ы тот же приём что в import_package.py:_auto_apply_ocr_to_applicant
# (NOT NULL constraint на имена, но реальные данные пока неизвестны).

@router.post("/for-application/{app_id}", status_code=201)
def create_empty_applicant_for_application(
    app_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    """
    Создать пустого Applicant'а для заявки если у неё ещё нет applicant_id.

    Возвращает _enrich(applicant) — тот же формат, что GET /admin/applicants/{id},
    чтобы фронт мог сразу подсунуть результат в стейт без дополнительного
    refetch'а.
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    # Идемпотентность — если applicant уже привязан, вернём его.
    if application.applicant_id:
        existing = session.get(Applicant, application.applicant_id)
        if existing:
            return _enrich(existing, session)
        # applicant_id указывает на удалённую запись — отвяжем и пересоздадим.
        application.applicant_id = None

    # Placeholder'ы для NOT NULL имён. Менеджер потом перезапишет через
    # PATCH /admin/applicants/{id} (тот же ApplicantDrawer).
    applicant = Applicant(
        last_name_native="—",
        first_name_native="—",
        last_name_latin="—",
        first_name_latin="—",
    )
    session.add(applicant)
    session.flush()
    session.refresh(applicant)

    application.applicant_id = applicant.id
    session.add(application)

    session.commit()
    session.refresh(applicant)

    return _enrich(applicant, session)
'''

    text = text.rstrip() + new_endpoint + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"    [OK] applicants.py: endpoint Pack 32.0 добавлен ({path})")
    assert_python_syntax(path)


# =============================================================================
# Frontend lib/api.ts — точечная вставка функции
# =============================================================================

def patch_frontend_api(repo_root: Path) -> None:
    path = repo_root / "frontend" / "lib" / "api.ts"
    if not path.exists():
        raise SystemExit(f"[FATAL] not found: {path}")

    text = path.read_text(encoding="utf-8")
    marker = "// Pack 32.0 — createApplicantForApplication"
    if marker in text:
        print("    [SKIP] api.ts: Pack 32.0 функция уже добавлена")
        return

    # Якорь — вставим после getApplicantById (логичное место).
    anchor = (
        'export async function getApplicantById(id: number): Promise<ApplicantResponse> {\n'
        '  const res = await fetch(`${API_BASE_URL}/api/admin/applicants/${id}`, '
        '{ headers: authHeaders() });\n'
        '  if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);\n'
        '  return res.json();\n'
        '}'
    )

    if anchor not in text:
        # Fallback: ищем функцию по имени и вставляем сразу после её закрывающей скобки.
        # Защита от изменений форматирования.
        idx = text.find("export async function getApplicantById")
        if idx == -1:
            raise SystemExit(
                "[FATAL] api.ts: getApplicantById не найден — "
                "нужно вставить createApplicantForApplication вручную"
            )
        # Найдём первую "}\n" после idx — конец функции.
        end_idx = text.find("\n}\n", idx)
        if end_idx == -1:
            raise SystemExit("[FATAL] api.ts: не нашёл конец getApplicantById")
        insertion_point = end_idx + len("\n}\n")
    else:
        insertion_point = text.find(anchor) + len(anchor) + 1  # +1 = newline

    new_fn = '''
// Pack 32.0 — createApplicantForApplication
// Создаёт пустого Applicant'а с placeholder ФИО «—» и привязывает к application.
// Возвращает enriched dict (тот же формат что getApplicantById).
// Идемпотентно: если applicant уже есть у заявки — вернёт существующего.
export async function createApplicantForApplication(
  appId: number,
): Promise<ApplicantResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/for-application/${appId}`,
    { method: "POST", headers: authHeaders() },
  );
  if (!res.ok) {
    throw new Error(`Не удалось создать кандидата: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

'''

    text = text[:insertion_point] + new_fn + text[insertion_point:]
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"    [OK] api.ts: createApplicantForApplication добавлена")


# =============================================================================
# Frontend ApplicationDetail.tsx — ПОЛНАЯ ЗАМЕНА
# =============================================================================

APPLICATION_DETAIL_TSX = '''"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Loader2, Copy, Check, Link2 } from "lucide-react";
import {
  getApplication,
  getApplicantById,
  // Pack 32.0 — создание пустого кандидата по клику карандаша
  createApplicantForApplication,
  ApplicationResponse,
  ApplicantResponse,
  STATUS_LABELS,
  getClientLink,
  listCompanies,
  listPositions,
  listRepresentatives,
  listSpainAddresses,
  CompanyResponse,
  PositionResponse,
  RepresentativeResponse,
  SpainAddressResponse,
  updateStatus,
} from "@/lib/api";
import { CandidateCard } from "./cards/CandidateCard";
import { CompanyCard } from "./cards/CompanyCard";
import { SubmissionCard } from "./cards/SubmissionCard";
import { BusinessChecksBlock } from "./BusinessChecksBlock";
import { DocumentsGrid } from "./DocumentsGrid";
import { CompanyContractDrawer } from "./CompanyContractDrawer";
import { SubmissionDrawer } from "./SubmissionDrawer";
import { ApplicantDrawer } from "./ApplicantDrawer";
import { StatusDropdown } from "./StatusDropdown";
import { ArchiveButton, ArchiveBanner } from "./ArchiveButton";
// Pack 30.0
import { UrgentToggleButton } from "./UrgentToggleButton";
// Pack 27.0 — кнопка удаления в корзину
import { DeleteButton } from "./DeleteButton";
import { AdminClientDocuments } from "./AdminClientDocuments";
import { TranslationPanel } from "./TranslationPanel";

interface Props {
  applicationId: number;
  onUpdated: () => void;
}

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  draft: { bg: "var(--color-bg-secondary)", text: "var(--color-text-tertiary)" },
  awaiting_data: { bg: "var(--color-bg-warning)", text: "var(--color-text-warning)" },
  ready_to_assign: { bg: "var(--color-bg-info)", text: "var(--color-text-info)" },
  assigned: { bg: "var(--color-bg-info)", text: "var(--color-text-info)" },
  drafts_generated: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  submitted: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  approved: { bg: "var(--color-bg-success)", text: "var(--color-text-success)" },
  rejected: { bg: "var(--color-bg-danger)", text: "var(--color-text-danger)" },
  needs_followup: { bg: "var(--color-bg-warning)", text: "var(--color-text-warning)" },
};

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  if (hours < 24) return `${hours} ч назад`;
  if (days === 1) return "вчера";
  return `${days} дн назад`;
}

export function ApplicationDetail({ applicationId, onUpdated }: Props) {
  const [application, setApplication] = useState<ApplicationResponse | null>(null);
  const [applicant, setApplicant] = useState<ApplicantResponse | null>(null);
  const [companies, setCompanies] = useState<CompanyResponse[]>([]);
  const [positions, setPositions] = useState<PositionResponse[]>([]);
  const [representatives, setRepresentatives] = useState<RepresentativeResponse[]>([]);
  const [addresses, setAddresses] = useState<SpainAddressResponse[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showCompanyDrawer, setShowCompanyDrawer] = useState(false);
  const [showSubmissionDrawer, setShowSubmissionDrawer] = useState(false);
  const [showApplicantDrawer, setShowApplicantDrawer] = useState(false);
  // Pack 32.0 — спиннер пока создаём пустого кандидата
  const [creatingApplicant, setCreatingApplicant] = useState(false);

  async function loadAll() {
    setError(null);
    try {
      const app = await getApplication(applicationId);
      setApplication(app);

      const promises: Promise<any>[] = [];
      if (app.applicant_id) {
        promises.push(
          getApplicantById(app.applicant_id)
            .then(setApplicant)
            .catch((e) => console.warn("applicant load failed:", e)),
        );
      } else {
        setApplicant(null);
      }
      if (companies.length === 0) {
        promises.push(listCompanies().then((r) => setCompanies(r.filter((x) => x.is_active))));
        promises.push(listPositions().then((r) => setPositions(r.filter((x) => x.is_active))));
        promises.push(listRepresentatives().then((r) => setRepresentatives(r.filter((x) => x.is_active))));
        promises.push(listSpainAddresses().then((r) => setAddresses(r.filter((x) => x.is_active))));
      }
      await Promise.all(promises);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    loadAll();
  }, [applicationId]);

  async function handleCopyLink() {
    if (!application?.client_access_token) return;
    const link = getClientLink(application.client_access_token);
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = link;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function handleOpenAsClient() {
    if (!application?.client_access_token) return;
    window.open(getClientLink(application.client_access_token), "_blank");
  }

  async function handleStatusChange(newStatus: string) {
    try {
      await updateStatus(applicationId, newStatus);
      await loadAll();
      onUpdated();
    } catch (e) {
      alert(`Не удалось изменить статус: ${(e as Error).message}`);
    }
  }

  async function handleArchiveChanged() {
    await loadAll();
    onUpdated();
  }

  // Pack 32.0 — клик по карандашу в карточке «Кандидат».
  // Если applicant ещё не создан — сначала создаём пустого с placeholder «—»,
  // после чего открываем Drawer для редактирования. Если уже создан — просто
  // открываем Drawer.
  async function handleEditApplicant() {
    if (applicant) {
      setShowApplicantDrawer(true);
      return;
    }
    if (!application) return;
    setCreatingApplicant(true);
    try {
      const created = await createApplicantForApplication(application.id);
      setApplicant(created);
      // Перезагрузим application чтобы у него обновилось applicant_id.
      const app = await getApplication(application.id);
      setApplication(app);
      setShowApplicantDrawer(true);
      onUpdated();
    } catch (e) {
      alert(`Не удалось создать кандидата: ${(e as Error).message}`);
    } finally {
      setCreatingApplicant(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
      </div>
    );
  }

  if (error || !application) {
    return (
      <div
        className="bg-primary rounded-xl border p-6"
        style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
      >
        <div className="text-sm text-danger">{error || "Заявка не найдена"}</div>
      </div>
    );
  }

  const company = companies.find((c) => c.id === application.company_id);
  const position = positions.find((p) => p.id === application.position_id);
  const representative = representatives.find((r) => r.id === application.representative_id);
  const address = addresses.find((a) => a.id === application.spain_address_id);

  const isAssigned = !!application.company_id;
  const statusColors = STATUS_COLORS[application.status] || STATUS_COLORS.draft;

  // Двуязычное ФИО.
  // Pack 32.0: если applicant создан с placeholder'ами «—» — не показываем
  // эту фейковую запись в шапке заявки, fallback на internal_notes.
  const isPlaceholderApplicant =
    !!applicant &&
    (applicant.last_name_native || "").trim() === "—" &&
    (applicant.first_name_native || "").trim() === "—";

  const fullNameRu =
    (!isPlaceholderApplicant && applicant?.full_name_native) ||
    application.internal_notes ||
    "Без имени";
  const fullNameLatin =
    !isPlaceholderApplicant &&
    applicant?.last_name_latin &&
    applicant?.first_name_latin &&
    applicant.last_name_latin !== "—" &&
    applicant.first_name_latin !== "—"
      ? `${applicant.last_name_latin} ${applicant.first_name_latin}`
      : null;

  return (
    <div className="space-y-4">
      {application.is_archived && (
        <ArchiveBanner application={application} onChanged={handleArchiveChanged} />
      )}

      {/* Шапка заявки */}
      <div
        className="bg-primary rounded-xl border p-5"
        style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
      >
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-0">
            {/* Pack 30.0 — огонёк рядом с именем клиента */}
            <div className="flex items-center gap-2 mb-0.5">
              <UrgentToggleButton application={application} onChanged={handleArchiveChanged} />
              <h2 className="text-2xl font-bold text-primary leading-tight">
                {fullNameRu}
              </h2>
            </div>
            {fullNameLatin && (
              <div className="text-sm text-tertiary uppercase tracking-wide mb-2">
                {fullNameLatin}
              </div>
            )}
            <div className="flex items-center gap-2 flex-wrap text-sm">
              <span className="text-tertiary font-mono">#{application.reference}</span>
              <span className="text-tertiary">·</span>
              <span
                className="inline-block px-2 py-0.5 rounded text-xs font-medium"
                style={{ background: statusColors.bg, color: statusColors.text }}
              >
                {STATUS_LABELS[application.status] || application.status}
              </span>
              <span className="text-tertiary">·</span>
              <span className="text-tertiary text-xs">
                обновлено {formatRelativeTime(application.created_at)}
              </span>
            </div>
          </div>

          <div className="flex flex-col items-stretch gap-2 min-w-[260px]">
            <StatusDropdown
              currentStatus={application.status}
              onChange={handleStatusChange}
            />

            <button
              onClick={handleCopyLink}
              className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center justify-center gap-1.5"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
              title="Скопировать magic-link для входа клиента в его кабинет"
            >
              {copied ? (
                <>
                  <Check className="w-4 h-4 text-success" />
                  Ссылка скопирована
                </>
              ) : (
                <>
                  <Link2 className="w-4 h-4" />
                  Копировать ссылку для клиента
                </>
              )}
            </button>

            <button
              onClick={handleOpenAsClient}
              className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center justify-center gap-1.5"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
              title="Открыть кабинет клиента в новой вкладке"
            >
              <ExternalLink className="w-4 h-4" />
              Открыть как клиент
            </button>

            <ArchiveButton application={application} onChanged={handleArchiveChanged} />
            {/* Pack 27.0 - удаление в корзину */}
            <DeleteButton
              application={application}
              onDeleted={() => {
                // Pack 27.0 — после удаления сначала снять выбор (URL без id),
                // потом обновить список. useEffect в page.tsx выберет первую активную.
                if (typeof window !== "undefined") {
                  window.history.replaceState(null, "", "/admin");
                }
                if (onUpdated) onUpdated();
              }}
            />
          </div>
        </div>
      </div>

      {/* Сетка карточек: 1 кандидат сверху, 2 (компания + подача) ниже */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pack 32.0 — onEdit передаётся всегда: handleEditApplicant сам решит,
            создавать пустого applicant'а или сразу открывать Drawer. */}
        <CandidateCard
          applicant={applicant}
          application={application}
          onEdit={handleEditApplicant}
          editLoading={creatingApplicant}
        />
        <CompanyCard
          company={company}
          position={position}
          application={application}
          onEdit={() => setShowCompanyDrawer(true)}
        />
        <SubmissionCard
          application={application}
          representative={representative}
          address={address}
          onEdit={() => setShowSubmissionDrawer(true)}
        />
      </div>

      <BusinessChecksBlock
        application={application}
        applicant={applicant}
        company={company}
      />
      <AdminClientDocuments applicationId={application.id} />
      {isAssigned && <DocumentsGrid applicationId={application.id} companyId={application.company_id} />}
      {isAssigned && <TranslationPanel applicationId={application.id} />}

      {!isAssigned && applicant && (
        <div
          className="bg-primary rounded-xl border p-5 text-center"
          style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
        >
          <p className="text-sm text-tertiary mb-3">Заявка ещё не распределена</p>
          <div className="flex items-center justify-center gap-2 flex-wrap">
            <button
              onClick={() => setShowCompanyDrawer(true)}
              className="px-4 py-2 rounded-md text-sm font-medium text-white"
              style={{ background: "var(--color-accent)" }}
            >
              Указать компанию и договор
            </button>
            <button
              onClick={() => setShowSubmissionDrawer(true)}
              className="px-4 py-2 rounded-md text-sm border text-secondary hover:bg-secondary"
              style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
            >
              Указать подачу
            </button>
          </div>
        </div>
      )}

      {/* Drawers */}
      {showCompanyDrawer && (
        <CompanyContractDrawer
          application={application}
          applicant={applicant}
          companies={companies}
          positions={positions}
          onClose={() => setShowCompanyDrawer(false)}
          onSaved={() => {
            setShowCompanyDrawer(false);
            loadAll();
            onUpdated();
          }}
        />
      )}

      {showSubmissionDrawer && (
        <SubmissionDrawer
          application={application}
          representatives={representatives}
          addresses={addresses}
          onClose={() => setShowSubmissionDrawer(false)}
          onSaved={() => {
            setShowSubmissionDrawer(false);
            loadAll();
            onUpdated();
          }}
        />
      )}

      {/* Pack 14 finishing — drawer для редактирования Applicant */}
      {showApplicantDrawer && applicant && (
        <ApplicantDrawer
          applicant={applicant}
          application={application}
          onApplicationSaved={loadAll}
          onClose={() => setShowApplicantDrawer(false)}
          onSaved={() => {
            setShowApplicantDrawer(false);
            loadAll();
            onUpdated();
          }}
        />
      )}
    </div>
  );
}
'''


# =============================================================================
# Frontend CandidateCard.tsx — ПОЛНАЯ ЗАМЕНА
# =============================================================================

CANDIDATE_CARD_TSX = '''"use client";

import { User, Pencil, Loader2 } from "lucide-react";
import { ApplicantResponse, ApplicationResponse } from "@/lib/api";

interface Props {
  applicant: ApplicantResponse | null;
  application: ApplicationResponse;
  onEdit?: () => void;
  // Pack 32.0 — спиннер пока родитель создаёт пустого applicant'а на бэке
  editLoading?: boolean;
}

// ISO 3166-1 alpha-3 → русское название (топ-страны для DN-визы и СНГ)
const COUNTRY_LABELS: Record<string, string> = {
  RUS: "Россия",
  UKR: "Украина",
  BLR: "Беларусь",
  KAZ: "Казахстан",
  AZE: "Азербайджан",
  ARM: "Армения",
  GEO: "Грузия",
  TJK: "Таджикистан",
  UZB: "Узбекистан",
  KGZ: "Кыргызстан",
  TKM: "Туркменистан",
  MDA: "Молдова",
  TUR: "Турция",
  ISR: "Израиль",
  POL: "Польша",
  DEU: "Германия",
  CZE: "Чехия",
  ESP: "Испания",
  ITA: "Италия",
  HUN: "Венгрия",
  PRT: "Португалия",
  GRC: "Греция",
  FRA: "Франция",
  GBR: "Великобритания",
  USA: "США",
  CAN: "Канада",
  SRB: "Сербия",
  MNE: "Черногория",
  THA: "Таиланд",
  ARE: "ОАЭ",
};

function formatCountry(code: string | null | undefined): string {
  if (!code) return "—";
  const upper = code.toUpperCase();
  return COUNTRY_LABELS[upper] || upper;
}

// Pack 32.0 — определяет, является ли запись "только что созданным placeholder'ом"
// (имена «—»). Нужно чтобы не считать иностранцем у которого пустые русские
// ФИО (там реальная latin есть).
function isPlaceholder(applicant: ApplicantResponse | null): boolean {
  if (!applicant) return false;
  const ln = (applicant.last_name_native || "").trim();
  const fn = (applicant.first_name_native || "").trim();
  return ln === "—" && fn === "—";
}

export function CandidateCard({ applicant, application, onEdit, editLoading }: Props) {
  // Pack 14 — подсказка для иностранцев у которых пустое русское ФИО.
  // Pack 32.0: для свежесозданного placeholder'а подсказка не нужна.
  const needsRussianName =
    applicant &&
    !isPlaceholder(applicant) &&
    (!applicant.last_name_native?.trim() || !applicant.first_name_native?.trim()) &&
    applicant.last_name_latin &&
    applicant.first_name_latin &&
    applicant.last_name_latin !== "—" &&
    applicant.first_name_latin !== "—";

  // Pack 32.0 — показываем поля карточки даже когда applicant=null или
  // placeholder, просто с прочерками. Это даёт менеджеру визуальную
  // согласованность и пустую структуру для редактирования.
  const placeholder = !applicant || isPlaceholder(applicant);

  // Удобные геттеры с прочерками вместо пустых значений.
  const passportValue = (() => {
    if (!applicant || !applicant.passport_number) return "—";
    return `${applicant.passport_number} (${applicant.nationality || "?"})`;
  })();

  const birthValue = (() => {
    if (!applicant || !applicant.birth_date) return "—";
    const d = new Date(applicant.birth_date).toLocaleDateString("ru");
    return applicant.birth_place_latin
      ? `${d}, ${applicant.birth_place_latin}`
      : d;
  })();

  const contactsValue = (() => {
    if (!applicant) return "—";
    if (!applicant.email && !applicant.phone) return "—";
    return `${applicant.email || ""}${applicant.phone ? ` · ${applicant.phone}` : ""}`;
  })();

  return (
    <div
      className="bg-primary rounded-xl border p-4"
      style={{
        borderColor: "var(--color-border-tertiary)",
        borderWidth: 0.5,
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-tertiary flex items-center gap-1.5">
          <User className="w-3.5 h-3.5" />
          Кандидат
        </h3>
        {/* Pack 32.0 — кнопка «Изменить» показывается ВСЕГДА если onEdit задан,
            даже когда applicant ещё не создан. Родитель сам решает что делать
            (создать пустого + открыть Drawer, либо просто открыть). */}
        {onEdit && (
          <button
            onClick={onEdit}
            disabled={editLoading}
            className="text-xs px-2 py-1 rounded-md hover:bg-secondary transition-colors flex items-center gap-1 disabled:opacity-50 disabled:cursor-wait"
            style={{ color: "var(--color-text-info)" }}
            title="Редактировать данные кандидата"
          >
            {editLoading ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Pencil className="w-3 h-3" />
            )}
            Изменить
          </button>
        )}
      </div>

      <div className="space-y-2">
        {/* Pack 14 — предупреждение если у иностранца нет русского имени */}
        {needsRussianName && (
          <div
            className="mb-2 p-2 rounded text-xs flex gap-1.5 items-start"
            style={{
              background: "var(--color-bg-warning)",
              color: "var(--color-text-warning)",
              border: "0.5px solid var(--color-border-warning)",
            }}
          >
            <Pencil className="w-3 h-3 flex-shrink-0 mt-0.5" />
            <div>
              В договоре будет латиница. Нажмите <b>«Изменить»</b> и впишите русские ФИО.
            </div>
          </div>
        )}

        <Field label="Паспорт" value={passportValue} muted={placeholder} />
        <Field label="Родился" value={birthValue} muted={placeholder} />

        {applicant && applicant.nationality ? (
          <Field
            label="Гражданство"
            value={`${formatCountry(applicant.nationality)} (${applicant.nationality})`}
          />
        ) : (
          <Field label="Гражданство" value="—" muted={placeholder} />
        )}
        {applicant && applicant.home_country ? (
          <Field
            label="Живёт в"
            value={`${formatCountry(applicant.home_country)} (${applicant.home_country})`}
          />
        ) : (
          <Field label="Живёт в" value="—" muted={placeholder} />
        )}
        {applicant && applicant.home_address ? (
          <Field label="Адрес" value={applicant.home_address} />
        ) : (
          <Field label="Адрес" value="—" muted={placeholder} />
        )}

        <Field label="Контакты" value={contactsValue} muted={placeholder} />
        {applicant && applicant.inn ? (
          <Field label="ИНН" value={applicant.inn} />
        ) : (
          <Field label="ИНН" value="—" muted={placeholder} />
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  muted,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div>
      <div className="text-[11px] text-tertiary">{label}</div>
      <div
        className={
          muted ? "text-sm text-tertiary break-words" : "text-sm text-primary break-words"
        }
      >
        {value}
      </div>
    </div>
  );
}
'''


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    repo_root = Path.cwd()
    print(f"== Pack 32.0 ==")
    print(f"   repo: {repo_root}")
    print()

    # 1. Backend
    print("[1/4] backend/app/api/applicants.py — добавляем endpoint")
    patch_backend_applicants(repo_root)
    print()

    # 2. Frontend api.ts
    print("[2/4] frontend/lib/api.ts — добавляем createApplicantForApplication")
    patch_frontend_api(repo_root)
    print()

    # 3. ApplicationDetail.tsx — full replacement
    print("[3/4] frontend/components/admin/ApplicationDetail.tsx — полная замена")
    write_text(
        repo_root / "frontend" / "components" / "admin" / "ApplicationDetail.tsx",
        APPLICATION_DETAIL_TSX,
        "ApplicationDetail.tsx",
    )
    print()

    # 4. CandidateCard.tsx — full replacement
    print("[4/4] frontend/components/admin/cards/CandidateCard.tsx — полная замена")
    write_text(
        repo_root / "frontend" / "components" / "admin" / "cards" / "CandidateCard.tsx",
        CANDIDATE_CARD_TSX,
        "CandidateCard.tsx",
    )
    print()

    print("== DONE ==")
    print()
    print("Дальше:")
    print("    git add backend/app/api/applicants.py \\")
    print("            frontend/lib/api.ts \\")
    print("            frontend/components/admin/ApplicationDetail.tsx \\")
    print("            frontend/components/admin/cards/CandidateCard.tsx")
    print('    git commit -m "Pack 32.0: empty applicant edit pencil"')
    print("    git push")
    print()
    print("Railway пересоберёт backend за ~1-2 мин, Vercel — frontend за ~30-60 сек.")
    print()
    print("Тест:")
    print("  1. Открой любую заявку с пустым кандидатом (например #2026-0029)")
    print("  2. В карточке «Кандидат» появится «Изменить» с карандашиком")
    print("  3. Клик → создастся applicant с «—», откроется Drawer")
    print("  4. Заполни данные и сохрани")
    return 0


if __name__ == "__main__":
    sys.exit(main())
