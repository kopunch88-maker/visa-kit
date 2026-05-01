"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Loader2, Copy, Check, Link2 } from "lucide-react";
import {
  getApplication,
  getApplicantById,
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

  // Двуязычное ФИО
  const fullNameRu = applicant?.full_name_native || application.internal_notes || "Без имени";
  const fullNameLatin =
    applicant?.last_name_latin && applicant?.first_name_latin
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
            <h2 className="text-2xl font-bold text-primary mb-0.5 leading-tight">
              {fullNameRu}
            </h2>
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
          </div>
        </div>
      </div>

      {/* Сетка карточек: 1 кандидат сверху, 2 (компания + подача) ниже */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <CandidateCard
          applicant={applicant}
          application={application}
          onEdit={applicant ? () => setShowApplicantDrawer(true) : undefined}
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
      {isAssigned && <DocumentsGrid applicationId={application.id} />}
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
