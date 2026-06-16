"use client";

import { useEffect, useState } from "react";
// Pack 37.0-D — навигация на страницу аудита
import { useRouter } from "next/navigation";
import { ExternalLink, Loader2, Copy, Check, Link2, ShieldCheck, FileCheck2, RefreshCw } from "lucide-react";
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
  // Pack 50.0-C4
  changeApplicationType,
  APPLICATION_TYPE_BADGE,
  ApplicationType,
} from "@/lib/api";
import { CandidateCard } from "./cards/CandidateCard";
import { CompanyCard } from "./cards/CompanyCard";
import { SubmissionCard } from "./cards/SubmissionCard";
import { TieCard } from "./cards/TieCard";  // Pack 36.1
import { CitaCard } from "./cards/CitaCard";  // Pack 56.1
// Pack 32.1 — блок заметок по клиенту
import { NotesCard } from "./cards/NotesCard";
import { BusinessChecksBlock } from "./BusinessChecksBlock";
import { DocumentsGrid } from "./DocumentsGrid";
import { CompanyContractDrawer } from "./CompanyContractDrawer";
import { SubmissionDrawer } from "./SubmissionDrawer";
import { TieDrawer } from "./TieDrawer";  // Pack 36.1
import { CitaDrawer } from "./CitaDrawer";  // Pack 56.2
import { ApplicantDrawer } from "./ApplicantDrawer";
import { StatusDropdown } from "./StatusDropdown";
import { ArchiveButton, ArchiveBanner } from "./ArchiveButton";
// Pack 30.0
import { toggleFiled } from "@/lib/api";
import { UrgentToggleButton } from "./UrgentToggleButton";
import { PaidToggleButton } from "./PaidToggleButton";
import { ReadyForPickupToggleButton } from "./ReadyForPickupToggleButton";
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
  // Pack 37.0-D — router для перехода на страницу аудита
  const router = useRouter();

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
  const [showTieDrawer, setShowTieDrawer] = useState(false);  // Pack 36.1
  const [showApplicantDrawer, setShowApplicantDrawer] = useState(false);
  const [showCitaDrawer, setShowCitaDrawer] = useState(false);  // Pack 56.2
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
      // Pack 36.1 — статус "Подана" автоматически ставит флаг is_filed
      if (newStatus === "submitted" && !application.is_filed) {
        await toggleFiled(application.id);
      } else if (newStatus !== "submitted" && application.is_filed) {
        await toggleFiled(application.id);
      }
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
  // isPlaceholderApplicant — Pack 50.38-D-fix: placeholder только если
  // И native, И latin пустые/«—». Иностранец (native=«—», latin валиден)
  // НЕ placeholder — заголовок должен показать latin, не заметки.
  const _nativeIsPlaceholder =
    !applicant ||
    ((applicant.last_name_native || "").trim() === "—" &&
     (applicant.first_name_native || "").trim() === "—") ||
    (!(applicant.last_name_native || "").trim() &&
     !(applicant.first_name_native || "").trim());
  const _latinValid =
    !!applicant &&
    !!applicant.last_name_latin &&
    !!applicant.first_name_latin &&
    applicant.last_name_latin !== "—" &&
    applicant.first_name_latin !== "—";
  // Полностью фейковая запись — нет ни native, ни latin
  const isPlaceholderApplicant = _nativeIsPlaceholder && !_latinValid;
  const fullNameLatin = _latinValid
    ? `${applicant!.last_name_latin} ${applicant!.first_name_latin}`
    : null;
  // Заголовок: native ФИО → latin ФИО → заметки → "Без имени"
  const fullNameRu =
    (!_nativeIsPlaceholder && applicant?.full_name_native) ||
    fullNameLatin ||
    application.internal_notes ||
    "Без имени";

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
              <PaidToggleButton application={application} onChanged={handleArchiveChanged} />
              <ReadyForPickupToggleButton application={application} onChanged={handleArchiveChanged} />
              <button
                onClick={async () => {
                  try {
                    await toggleFiled(application.id);
                    // Pack 36.2 — синхронизируем статус с флагом
                    if (!application.is_filed && application.status !== "submitted") {
                      await updateStatus(applicationId, "submitted");
                    } else if (application.is_filed && application.status === "submitted") {
                      await updateStatus(applicationId, "drafts_generated");
                    }
                    await loadAll(); onUpdated();
                  }
                  catch (e) { alert(`Ошибка: ${(e as Error).message}`); }
                }}
                className="px-2.5 py-1 rounded-md text-xs font-semibold transition-colors"
                style={application.is_filed
                  ? { background: "#eab308", color: "#fff" }
                  : { background: "var(--color-bg-secondary)", color: "var(--color-text-secondary)", border: "0.5px solid var(--color-border-tertiary)" }
                }
                title={application.is_filed ? "Снять отметку «Подан»" : "Отметить как поданную"}
              >
                {application.is_filed ? "✓ Подан" : "Подан"}
              </button>
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
              {/* Pack 50.0-C4 — badge типа заявки (НАЙМ; для самозанятого скрыт) */}
              {application.application_type && APPLICATION_TYPE_BADGE[application.application_type]?.show && (
                <>
                  <span className="text-tertiary">·</span>
                  <span
                    className="inline-block px-2 py-0.5 rounded text-xs font-semibold"
                    style={{ background: "#fef3c7", color: "#92400e" }}
                    title="Тип заявки: найм по трудовому договору"
                  >
                    {APPLICATION_TYPE_BADGE[application.application_type].emoji} {APPLICATION_TYPE_BADGE[application.application_type].label}
                  </span>
                </>
              )}
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

            {/* Pack 32.2 — заметки по клиенту, размещены под мета-строкой */}
            <div className="mt-3">
              <NotesCard application={application} onSaved={loadAll} />
            </div>
          </div>

          <div className="flex flex-col items-stretch gap-2 min-w-[260px]">
            <StatusDropdown
              currentStatus={application.status}
              onChange={handleStatusChange}
            />

            {/* Pack 50.0-C4 — кнопка «Сменить тип заявки» (Самозанятый ↔ Найм) */}
            <button
              onClick={async () => {
                const current = application.application_type || "SELF_EMPLOYED";
                const target: ApplicationType = current === "EMPLOYMENT" ? "SELF_EMPLOYED" : "EMPLOYMENT";
                const currentLabel = APPLICATION_TYPE_BADGE[current].label;
                const targetLabel = APPLICATION_TYPE_BADGE[target].label;

                // 1-е подтверждение — сценарий
                const ok1 = window.confirm(
                  `Сменить тип заявки: ${currentLabel} → ${targetLabel}?\n\n` +
                  `БУДЕТ УДАЛЕНО:\n` +
                  `• Все сгенерированные документы (DOCX/PDF) из R2 и БД\n\n` +
                  `БУДЕТ СБРОШЕНО (в NULL):\n` +
                  `• Компания, должность, реквизиты договора\n` +
                  `• Зарплата, письмо работодателя, исх. №\n` +
                  `• Все настройки банковской выписки\n` +
                  `• Tech opinion override, NRC квитанции\n\n` +
                  `Сканы клиента (паспорт, диплом, апостили) НЕ удаляются.\n` +
                  `Статус будет сброшен в «Ожидание данных».`
                );
                if (!ok1) return;

                // 2-е подтверждение — финальное
                const ok2 = window.confirm(
                  `Точно сменить тип на ${targetLabel}?\n\nЭто действие НЕОБРАТИМО.`
                );
                if (!ok2) return;

                try {
                  await changeApplicationType(application.id, target);
                  await loadAll();
                  onUpdated();
                } catch (e) {
                  alert(`Не удалось сменить тип: ${(e as Error).message}`);
                }
              }}
              className="px-3 py-1.5 rounded-md text-sm border text-secondary hover:bg-secondary transition-colors flex items-center justify-center gap-1.5"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
              title="Сменить тип заявки между Самозанятый и Найм. Это удалит сгенерированные документы и сбросит реквизиты."
            >
              <RefreshCw className="w-4 h-4" />
              Сменить тип заявки
            </button>

            {/* Pack 39.0-E1 — финальная проверка физических документов */}
            <button
              onClick={() => window.open(`/admin/applications/${application.id}/final-check`, '_blank')}
              className="px-3 py-1.5 rounded-md text-sm font-medium text-white flex items-center justify-center gap-1.5 transition-colors"
              style={{
                background: "#0ea5e9",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "#0284c7";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "#0ea5e9";
              }}
              title="Загрузка физических документов клиента и финальная проверка пакета перед подачей"
            >
              <FileCheck2 className="w-4 h-4" />
              📋 Финальная проверка
            </button>
            {/* Pack 37.0-D — кнопка ИИ-аудита пакета документов */}
            <button
              onClick={() => router.push(`/admin/applications/${application.id}/audit`)}
              className="px-3 py-1.5 rounded-md text-sm font-medium text-white flex items-center justify-center gap-1.5 transition-colors"
              style={{
                background: "#2563eb",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "#1d4ed8";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "#2563eb";
              }}
              title="ИИ-симуляция приёма документов в консульстве — последняя проверка перед подачей"
            >
              <ShieldCheck className="w-4 h-4" />
              🛂 Симуляция приёма документов
            </button>

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
        {/* Pack 36.1 — карточка TIE с NIE и датой отпечатков */}
        <TieCard
          application={application}
          onEdit={() => setShowTieDrawer(true)}
        />
      </div>

      {/* Pack 56.1 — плашка «Ситы» (перед чек-листом) */}
      {applicant && (
        <CitaCard
          applicant={applicant}
          application={application}
          onEdit={() => setShowCitaDrawer(true)}
          onChanged={loadAll}
        />
      )}

      <BusinessChecksBlock
        application={application}
        applicant={applicant}
        company={company}
      />
      <AdminClientDocuments applicationId={application.id} />
      {isAssigned && <DocumentsGrid applicationId={application.id} companyId={application.company_id} applicationType={application.application_type} />}
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

      {showTieDrawer && (
        <TieDrawer
          application={application}
          onClose={() => setShowTieDrawer(false)}
          onSaved={() => {
            setShowTieDrawer(false);
            onChanged();
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

      {/* Pack 56.2 — отдельный дровер «Ситы» */}
      {showCitaDrawer && applicant && (
        <CitaDrawer
          applicant={applicant}
          application={application}
          onClose={() => setShowCitaDrawer(false)}
          onSaved={() => {
            setShowCitaDrawer(false);
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
