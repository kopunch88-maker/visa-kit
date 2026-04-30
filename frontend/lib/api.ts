/**
 * Pack 8.7 — добавлены:
 * - patchApplication(): partial-update заявки
 * - CRUD endpoints для справочников
 * - Расширенные типы CompanyResponse / PositionResponse и т.д.
 *
 * Pack 13.0b — добавлены:
 * - Типы ClientDocument / ClientDocumentType / ClientDocumentStatus
 * - uploadDocument / getMyDocuments / deleteDocument / recognizeDocument
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ============================================================================
// Types
// ============================================================================

export type ApplicantData = {
  last_name_native?: string;
  first_name_native?: string;
  middle_name_native?: string;
  last_name_latin?: string;
  first_name_latin?: string;
  birth_date?: string;
  birth_place_latin?: string;
  nationality?: string;
  sex?: string;
  marital_status?: string;
  father_name_latin?: string;
  mother_name_latin?: string;
  passport_number?: string;
  passport_issue_date?: string;
  passport_issuer?: string;
  inn?: string;
  home_address?: string;
  home_country?: string;
  email?: string;
  phone?: string;
  education?: any[];
  work_history?: any[];
  languages?: string[];
};

export type ApplicantResponse = ApplicantData & {
  id: number;
  full_name_native: string;
  initials_native: string;
};

export type ApplicationResponse = {
  id: number;
  reference: string;
  status: string;
  status_notes?: string;
  internal_notes?: string;
  business_rule_problems?: string[];
  client_access_token?: string;
  applicant_id?: number;
  company_id?: number;
  position_id?: number;
  representative_id?: number;
  spain_address_id?: number;
  contract_number?: string;
  contract_sign_date?: string;
  contract_end_date?: string;
  contract_sign_city?: string;
  salary_rub?: number;
  submission_date?: string;
  payments_period_months?: number;
  recommendation_snapshot?: any;
  tasa_nrc?: string;
  created_at?: string;
  // Pack 10
  is_archived?: boolean;
  archived_at?: string;
  can_be_archived?: boolean;
  // Pack 10.1
  applicant_name_native?: string;
  applicant_name_latin?: string;
};

// Pack 13: типы документов клиента
export type ClientDocumentType =
  | "passport_internal_main"
  | "passport_internal_address"
  | "passport_foreign"
  | "diploma_main"
  | "diploma_apostille"
  | "other";

export type ClientDocumentStatus =
  | "uploaded"
  | "ocr_pending"
  | "ocr_done"
  | "ocr_failed";

export type ClientDocument = {
  id: number;
  doc_type: ClientDocumentType;
  file_name: string;
  file_size: number;
  content_type: string;
  status: ClientDocumentStatus;
  parsed_data: Record<string, any>;
  ocr_error?: string;
  ocr_completed_at?: string;
  applied_to_applicant: boolean;
  created_at: string;
  download_url?: string;
};

// Полный тип Company
export type CompanyResponse = {
  id: number;
  short_name: string;
  full_name_ru: string;
  full_name_es: string;
  full_name?: string;
  inn?: string;
  kpp?: string;
  country?: string;
  tax_id_primary: string;
  tax_id_secondary?: string;
  legal_address: string;
  postal_address?: string;
  director_full_name_ru: string;
  director_full_name_genitive_ru: string;
  director_short_ru: string;
  director_position_ru: string;
  director_name_genitive?: string;
  bank_name: string;
  bank_account: string;
  bank_bic: string;
  bank_correspondent_account?: string;
  egryl_extract_date?: string;
  egryl_is_fresh?: boolean;
  is_active: boolean;
  notes?: string;
  application_count?: number;
};

export type PositionResponse = {
  id: number;
  company_id: number;
  company_short_name?: string;
  title_ru: string;
  title_es?: string;
  duties: string[];
  salary_rub_default: number;
  tags?: string[];
  profile_description?: string;
  description_ru?: string;
  is_active: boolean;
  application_count?: number;
};

export type RepresentativeResponse = {
  id: number;
  full_name?: string;
  first_name: string;
  last_name: string;
  nie: string;
  email: string;
  phone: string;
  address_street: string;
  address_number: string;
  address_floor?: string;
  address_zip: string;
  address_city: string;
  address_province: string;
  notes?: string;
  is_active: boolean;
  application_count?: number;
};

export type SpainAddressResponse = {
  id: number;
  street: string;
  number: string;
  floor?: string;
  zip: string;
  city: string;
  province: string;
  uge_office: string;
  label: string;
  notes?: string;
  is_active: boolean;
  address_line?: string;
  application_count?: number;
};

// ============================================================================
// JWT helpers
// ============================================================================

const TOKEN_KEY = "visa_kit_jwt";
const USER_KEY = "visa_kit_user";

export function saveToken(token: string, user: { email: string; name?: string }) {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getCurrentUser(): { email: string; name?: string } | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export function clearAuth() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function jsonHeaders(): HeadersInit {
  return { "Content-Type": "application/json", ...authHeaders() };
}

// ============================================================================
// Auth
// ============================================================================

export async function login(
  email: string,
  password: string,
): Promise<{ access_token: string; token_type: string; user: any }> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "Не удалось войти";
    try {
      const json = JSON.parse(text);
      message = json.detail || message;
    } catch {}
    throw new Error(message);
  }
  return res.json();
}

// ============================================================================
// Client portal
// ============================================================================

export async function getMyProfile(token: string): Promise<ApplicantResponse | null> {
  const res = await fetch(`${API_BASE_URL}/api/client/${token}/me`);
  if (!res.ok) {
    if (res.status === 404) throw new Error("Неверный или истёкший токен. Обратитесь к менеджеру.");
    throw new Error(`Ошибка ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function updateMyProfile(token: string, data: ApplicantData): Promise<ApplicantResponse> {
  const res = await fetch(`${API_BASE_URL}/api/client/${token}/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось сохранить: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function getMyApplication(token: string): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/client/${token}/application`);
  if (!res.ok) throw new Error(`Ошибка получения заявки: ${res.status}`);
  return res.json();
}

// ============================================================================
// Pack 13.0b: Client documents
// ============================================================================

/**
 * Получить список загруженных клиентом документов.
 */
export async function getMyDocuments(token: string): Promise<ClientDocument[]> {
  const res = await fetch(`${API_BASE_URL}/api/client/${token}/documents`);
  if (!res.ok) {
    throw new Error(`Не удалось получить документы: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

/**
 * Загрузить документ. Если такого типа уже есть — заменяется.
 *
 * @param token - токен клиентского доступа
 * @param docType - тип документа (passport_internal_main и т.д.)
 * @param file - File объект из <input type="file">
 */
export async function uploadDocument(
  token: string,
  docType: ClientDocumentType,
  file: File,
): Promise<ClientDocument> {
  const formData = new FormData();
  formData.append("doc_type", docType);
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/client/${token}/documents/upload`, {
    method: "POST",
    body: formData,
    // Note: НЕ ставим Content-Type — браузер сам выставит multipart/form-data с boundary
  });

  if (!res.ok) {
    const errText = await res.text();
    let errMessage = `Ошибка загрузки (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      errMessage = errJson.detail || errMessage;
    } catch {
      // оставляем дефолт
    }
    throw new Error(errMessage);
  }

  return res.json();
}

/**
 * Удалить загруженный документ.
 */
export async function deleteDocument(
  token: string,
  docId: number,
): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/client/${token}/documents/${docId}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    throw new Error(`Не удалось удалить документ: ${res.status} ${await res.text()}`);
  }
}

/**
 * Запустить OCR для документа.
 *
 * Pack 13.0b: возвращает 501 (заглушка).
 * Pack 13.1: реальное распознавание.
 */
export async function recognizeDocument(
  token: string,
  docId: number,
): Promise<ClientDocument> {
  const res = await fetch(
    `${API_BASE_URL}/api/client/${token}/documents/${docId}/recognize`,
    { method: "POST" },
  );
  if (!res.ok) {
    throw new Error(`Не удалось распознать: ${res.status}`);
  }
  return res.json();
}

// ============================================================================
// Admin Applications
// ============================================================================

export async function listApplications(
  status?: string,
  archived: boolean = false,
): Promise<ApplicationResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/admin/applications`);
  if (status) url.searchParams.set("status", status);
  if (archived) url.searchParams.set("archived", "true");
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) {
    if (res.status === 401) throw new Error("Требуется вход");
    throw new Error(`Ошибка ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function getApplication(id: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${id}`, { headers: authHeaders() });
  if (!res.ok) {
    if (res.status === 401) throw new Error("Требуется вход");
    throw new Error(`Ошибка ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function createApplication(payload: {
  notes?: string;
  applicant_email?: string;
  submission_date?: string;
}): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Не удалось создать: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function getApplicantById(id: number): Promise<ApplicantResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applicants/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function requestRecommendation(appId: number): Promise<any> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${appId}/recommendation`,
    { method: "POST", headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`Ошибка рекомендации: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function patchApplication(
  appId: number,
  patch: Partial<{
    company_id: number;
    position_id: number;
    representative_id: number;
    spain_address_id: number;
    contract_number: string;
    contract_sign_date: string;
    contract_sign_city: string;
    contract_end_date: string;
    salary_rub: number;
    submission_date: string;
    payments_period_months: number;
    internal_notes: string;
  }>,
): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}`, {
    method: "PATCH", headers: jsonHeaders(), body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`Не удалось обновить: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function assignApplication(
  appId: number,
  payload: {
    company_id: number;
    position_id: number;
    representative_id: number;
    spain_address_id: number;
    contract_number: string;
    contract_sign_date: string;
    contract_sign_city: string;
    contract_end_date?: string;
    salary_rub: number;
    submission_date?: string;
    payments_period_months?: number;
  },
): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/assign`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Не удалось распределить: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function updateStatus(
  appId: number, newStatus: string, notes?: string,
): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/status`, {
    method: "POST", headers: jsonHeaders(),
    body: JSON.stringify({ new_status: newStatus, notes }),
  });
  if (!res.ok) throw new Error(`Не удалось изменить статус: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function archiveApplication(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/archive`, {
    method: "POST", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось архивировать: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function unarchiveApplication(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/unarchive`, {
    method: "POST", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось вернуть из архива: ${res.status} ${await res.text()}`);
  return res.json();
}

// ============================================================================
// Catalogs — Companies
// ============================================================================

export async function listCompanies(includeInactive = false): Promise<CompanyResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/admin/companies`);
  if (includeInactive) url.searchParams.set("include_inactive", "true");
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) throw new Error(`Companies: ${res.status}`);
  return res.json();
}

export async function getCompany(id: number): Promise<CompanyResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/companies/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Company: ${res.status}`);
  return res.json();
}

export async function createCompany(data: Partial<CompanyResponse>): Promise<CompanyResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/companies`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось создать компанию: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function updateCompany(id: number, data: Partial<CompanyResponse>): Promise<CompanyResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/companies/${id}`, {
    method: "PATCH", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось обновить компанию: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function deleteCompany(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/admin/companies/${id}`, {
    method: "DELETE", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось удалить: ${res.status}`);
}

// ============================================================================
// Catalogs — Positions
// ============================================================================

export async function listPositions(companyId?: number, includeInactive = false): Promise<PositionResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/admin/positions`);
  if (companyId) url.searchParams.set("company_id", String(companyId));
  if (includeInactive) url.searchParams.set("include_inactive", "true");
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) throw new Error(`Positions: ${res.status}`);
  return res.json();
}

export async function getPosition(id: number): Promise<PositionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/positions/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Position: ${res.status}`);
  return res.json();
}

export async function createPosition(data: Partial<PositionResponse>): Promise<PositionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/positions`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось создать должность: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function updatePosition(id: number, data: Partial<PositionResponse>): Promise<PositionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/positions/${id}`, {
    method: "PATCH", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось обновить должность: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function deletePosition(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/admin/positions/${id}`, {
    method: "DELETE", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось удалить: ${res.status}`);
}

// ============================================================================
// Catalogs — Representatives
// ============================================================================

export async function listRepresentatives(includeInactive = false): Promise<RepresentativeResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/admin/representatives`);
  if (includeInactive) url.searchParams.set("include_inactive", "true");
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) throw new Error(`Representatives: ${res.status}`);
  return res.json();
}

export async function getRepresentative(id: number): Promise<RepresentativeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/representatives/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Representative: ${res.status}`);
  return res.json();
}

export async function createRepresentative(data: Partial<RepresentativeResponse>): Promise<RepresentativeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/representatives`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось создать представителя: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function updateRepresentative(id: number, data: Partial<RepresentativeResponse>): Promise<RepresentativeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/representatives/${id}`, {
    method: "PATCH", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось обновить представителя: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function deleteRepresentative(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/admin/representatives/${id}`, {
    method: "DELETE", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось удалить: ${res.status}`);
}

// ============================================================================
// Catalogs — Spain Addresses
// ============================================================================

export async function listSpainAddresses(includeInactive = false): Promise<SpainAddressResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/admin/spain-addresses`);
  if (includeInactive) url.searchParams.set("include_inactive", "true");
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) throw new Error(`Spain addresses: ${res.status}`);
  return res.json();
}

export async function getSpainAddress(id: number): Promise<SpainAddressResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/spain-addresses/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Spain address: ${res.status}`);
  return res.json();
}

export async function createSpainAddress(data: Partial<SpainAddressResponse>): Promise<SpainAddressResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/spain-addresses`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось создать адрес: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function updateSpainAddress(id: number, data: Partial<SpainAddressResponse>): Promise<SpainAddressResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/spain-addresses/${id}`, {
    method: "PATCH", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Не удалось обновить адрес: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function deleteSpainAddress(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/admin/spain-addresses/${id}`, {
    method: "DELETE", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось удалить: ${res.status}`);
}

// ============================================================================
// Constants
// ============================================================================

export const NATIONALITY_OPTIONS = [
  { value: "RUS", label: "Россия" },
  { value: "AZE", label: "Азербайджан" },
  { value: "KAZ", label: "Казахстан" },
  { value: "BLR", label: "Беларусь" },
  { value: "UKR", label: "Украина" },
  { value: "ARM", label: "Армения" },
  { value: "GEO", label: "Грузия" },
  { value: "UZB", label: "Узбекистан" },
  { value: "TJK", label: "Таджикистан" },
  { value: "KGZ", label: "Кыргызстан" },
];

export const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  awaiting_data: "Ожидание данных",
  ready_to_assign: "Готова к распределению",
  assigned: "Распределена",
  drafts_generated: "Документы готовы",
  at_translator: "У переводчика",
  awaiting_scans: "Ожидание сканов",
  awaiting_digital_sign: "Ожидание подписи",
  submitted: "Подана",
  approved: "Одобрена",
  rejected: "Отказ",
  needs_followup: "Требует доработки",
  hold: "На паузе",
  cancelled: "Отменена",
};

export const STATUS_TABS = [
  { id: "all", label: "Все", statuses: [] as string[] },
  { id: "awaiting", label: "Ждём данные", statuses: ["awaiting_data", "ready_to_assign"] },
  {
    id: "in_progress", label: "В работе",
    statuses: ["assigned", "drafts_generated", "at_translator", "awaiting_scans", "awaiting_digital_sign"],
  },
  { id: "submitted", label: "Поданы", statuses: ["submitted"] },
  { id: "approved", label: "Одобрены", statuses: ["approved"] },
  { id: "problems", label: "Проблемы", statuses: ["rejected", "needs_followup", "cancelled"] },
];

export function getClientLink(token: string): string {
  if (typeof window !== "undefined") return `${window.location.origin}/client/${token}`;
  return `/client/${token}`;
}

// Pack 13: метки типов документов клиента
export const DOCUMENT_TYPE_LABELS: Record<ClientDocumentType, string> = {
  passport_internal_main: "Паспорт РФ — главный разворот",
  passport_internal_address: "Паспорт РФ — страница прописки",
  passport_foreign: "Загранпаспорт",
  diploma_main: "Диплом — основная страница",
  diploma_apostille: "Диплом — апостиль",
  other: "Другой документ",
};