
/**
 * Pack 8.7 — добавлены:
 * - patchApplication(): partial-update заявки
 * - CRUD endpoints для справочников
 *
 * Pack 13.0b — типы и функции для документов клиента
 * Pack 13.1 — реальный OCR
 * Pack 13.1.1 — preview-apply с конфликтами + overrides
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ============================================================================
// Types
// ============================================================================

// Pack 41.0-D — запись о паспорте в applicant.passports[]
export type PassportRecord = {
  id: string;
  number: string;
  issue_date?: string | null;
  expiry_date?: string | null;
  issuer?: string | null;
  issuer_ru?: string | null;
  passport_type?: "RU_INTERNAL" | "RU_FOREIGN" | "FOREIGN" | null;
  is_primary: boolean;
  notes?: string | null;
  source?: "ocr" | "manual" | "legacy_backfill" | null;
  created_at?: string;
  updated_at?: string;
};

export type ApplicantData = {
  last_name_native?: string;
  first_name_native?: string;
  middle_name_native?: string;
  last_name_latin?: string;
  first_name_latin?: string;
  birth_date?: string;
  birth_place_latin?: string;
  birth_country?: string;  // Pack 18.10 — ISO-3 страна рождения (отдельно от nationality)
  nationality?: string;
  sex?: string;
  marital_status?: string;
  father_name_latin?: string;
  mother_name_latin?: string;
  passport_number?: string;
  passport_issue_date?: string;
  passport_issuer?: string;
  // Pack 41.0-D — мультипаспорт на applicant
  passports?: PassportRecord[];
  passport_id_for_ru_docs?: string | null;
  inn?: string;
  // Pack 17 — INN auto-generation
  inn_registration_date?: string | null;
  inn_source?: string | null;
  inn_kladr_code?: string | null;
  // /Pack 17
  // Pack 18.5 — статус проверки ИНН через ФНС API (только в response GET /applicants/{id})
  npd_check_status?: "no_inn" | "verified" | "invalid" | "not_checked" | null;
  npd_last_check_at?: string | null;
  // /Pack 18.5
  // Pack 18.9 — переопределение подписанта апостиля (если null — дефолт Байрамова)
  apostille_signer_short?: string | null;
  apostille_signer_signature?: string | null;
  apostille_signer_position?: string | null;
  // /Pack 18.9
  // Pack 16 — банк
  bank_id?: number | null;
  bank_account?: string | null;
  bank_name?: string | null;
  bank_bic?: string | null;
  bank_correspondent_account?: string | null;
  // /Pack 16
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

// Pack 50.0-C1 — тип заявки (Самозанятый / Найм)
export type ApplicationType = "SELF_EMPLOYED" | "EMPLOYMENT";

export const APPLICATION_TYPE_LABELS: Record<ApplicationType, string> = {
  SELF_EMPLOYED: "САМОЗАНЯТЫЙ",
  EMPLOYMENT: "НАЙМ",
};

// Бейдж для шапок и карточек. Самозанятый не показывается (дефолт),
// для НАЙМа — яркий жёлтый бейдж с эмодзи.
export const APPLICATION_TYPE_BADGE: Record<ApplicationType, { emoji: string; label: string; show: boolean }> = {
  SELF_EMPLOYED: { emoji: "🆔", label: "САМОЗАНЯТЫЙ", show: false },
  EMPLOYMENT: { emoji: "💼", label: "НАЙМ", show: true },
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
  submission_city?: string;        // Pack 50.38-A — город подачи
  submission_province?: string;    // Pack 50.38-A — провинция подачи
  payments_period_months?: number;
  recommendation_snapshot?: any;
  tasa_nrc?: string;
  created_at?: string;
  is_archived?: boolean;
  archived_at?: string;
  can_be_archived?: boolean;
  // Pack 30.0
  is_urgent?: boolean;
  is_filed?: boolean;  // Pack 36.0
  is_paid?: boolean;   // Pack 38.1
  // Pack 36.1: TIE поля
  nie?: string;
  fingerprint_date?: string;
  applicant_name_native?: string;
  applicant_name_latin?: string;
  // Pack 50.0-C1 — тип заявки
  application_type?: ApplicationType;
};

export type ClientDocumentType =
  | "passport_internal_main"
  | "passport_internal_address"
  | "passport_foreign"
  // Pack 14a — для иностранных клиентов
  | "passport_national"
  | "residence_card"
  | "criminal_record"
  // Pack 14b — выписка из ЕГРЮЛ (документ компании)
  | "egryl_extract"
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

// Pack 13.1.1: типы для preview-apply
export type ApplyPreviewItem = {
  field: string;
  ocr_value?: any;
  current_value?: any;
  value?: any;
};

export type ApplyEducationInfo =
  | {
      type: "auto_fill";
      ocr_value: Record<string, any>;
    }
  | {
      type: "conflict";
      current_value: Record<string, any>;
      ocr_value: Record<string, any>;
      current_count: number;
    };

export type ApplyPreview = {
  auto_fill: ApplyPreviewItem[];
  conflicts: ApplyPreviewItem[];
  same: ApplyPreviewItem[];
  education: ApplyEducationInfo | null;
};

export type ApplyOptions = {
  overrides?: string[];
  education_action?: "auto" | "skip" | "replace" | "add";
};

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
  director_full_name_latin?: string | null;
  director_name_genitive?: string;
  bank_name: string;
  bank_account: string;
  bank_bic: string;
  bank_correspondent_account?: string;
  egryl_extract_date?: string;
  egryl_is_fresh?: boolean;
  contract_template_slug?: string | null;  // Pack 29.0
  is_active: boolean;
  notes?: string;
  application_count?: number;
};

export type PositionResponse = {
  id: number;
  company_id?: number;
  company_short_name?: string;
  primary_specialty_id?: number | null;
  level?: number | null;
  specialty_code?: string | null;
  specialty_name?: string | null;
  title_ru: string;
  title_ru_genitive?: string | null;
  title_es?: string;
  duties: string[];
  salary_rub_default: number;
  tags?: string[];
  profile_description?: string;
  description_ru?: string;
  is_active: boolean;
  application_count?: number;
  // Pack 40.0 / 41.0: tech_opinion поля
  international_analog_ru?: string | null;
  international_analog_es?: string | null;
  tech_opinion_description_ru?: string | null;
  tech_opinion_description_es?: string | null;
  tech_opinion_tools_ru?: Array<{ name: string; purpose: string }> | null;
  tech_opinion_tools_es?: Array<{ name: string; purpose: string }> | null;
  tech_opinion_steps_ru?: Array<{ title: string; body: string }> | null;
  tech_opinion_steps_es?: Array<{ title: string; body: string }> | null;
  tech_opinion_grounds_ru?: string[] | null;
  tech_opinion_grounds_es?: string[] | null;
  tech_opinion_contract_clause_ru?: string | null;
  tech_opinion_contract_clause_es?: string | null;
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
// Pack 13: Client documents
// ============================================================================

export async function getMyDocuments(token: string): Promise<ClientDocument[]> {
  const res = await fetch(`${API_BASE_URL}/api/client/${token}/documents`);
  if (!res.ok) {
    throw new Error(`Не удалось получить документы: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

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
  });

  if (!res.ok) {
    const errText = await res.text();
    let errMessage = `Ошибка загрузки (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      errMessage = errJson.detail || errMessage;
    } catch {}
    throw new Error(errMessage);
  }

  return res.json();
}

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

export async function recognizeDocument(
  token: string,
  docId: number,
): Promise<ClientDocument> {
  const res = await fetch(
    `${API_BASE_URL}/api/client/${token}/documents/${docId}/recognize`,
    { method: "POST" },
  );
  if (!res.ok) {
    const errText = await res.text();
    let errMessage = `Не удалось распознать (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      errMessage = errJson.detail || errMessage;
    } catch {}
    throw new Error(errMessage);
  }
  return res.json();
}

/**
 * Pack 13.1.1: предпросмотр применения OCR данных.
 * Возвращает:
 * - auto_fill: поля будут заполнены автоматически (были пустые)
 * - conflicts: поля с конфликтом — клиент должен выбрать
 * - same: поля совпадают
 * - education: отдельная инфо о дипломе
 */
export async function previewApplyDocuments(
  token: string,
): Promise<ApplyPreview> {
  const res = await fetch(
    `${API_BASE_URL}/api/client/${token}/documents/preview-apply`,
    { method: "POST" },
  );
  if (!res.ok) {
    const errText = await res.text();
    let errMessage = `Не удалось подготовить предпросмотр (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      errMessage = errJson.detail || errMessage;
    } catch {}
    throw new Error(errMessage);
  }
  return res.json();
}

/**
 * Pack 13.1.1: применить распознанные данные с опциональными overrides.
 *
 * options.overrides — список полей которые ТОЧНО перезаписать (конфликты)
 * options.education_action — что делать с образованием:
 *   "auto" (default) — добавить если пусто, иначе пропустить
 *   "replace" — заменить весь список одной записью из диплома
 *   "add" — добавить запись в существующий список
 *   "skip" — не трогать
 */
export async function applyDocumentsToApplicant(
  token: string,
  options?: ApplyOptions,
): Promise<{
  applied_fields: string[];
  applicant?: ApplicantResponse;
  message?: string;
}> {
  const res = await fetch(
    `${API_BASE_URL}/api/client/${token}/documents/apply-to-applicant`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options || {}),
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    let errMessage = `Не удалось применить данные (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      errMessage = errJson.detail || errMessage;
    } catch {}
    throw new Error(errMessage);
  }
  return res.json();
}

// ============================================================================

// ============================================================================
// Pack 13.2: Admin — Client documents
// ============================================================================

/**
 * Получить документы клиента (от имени менеджера).
 */
export async function adminListClientDocuments(
  applicationId: number,
): Promise<ClientDocument[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/client-documents`,
    { headers: authHeaders() },
  );
  if (!res.ok) {
    throw new Error(`Не удалось получить документы: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

/**
 * Запустить OCR заново для документа клиента (от имени менеджера).
 *
 * Pack 14b+c FIX: опциональный pageNum — если PDF, можно выбрать другую страницу.
 * Backend конвертирует выбранную страницу в новый JPEG, заменяет primary файл и распознаёт.
 */
export async function adminRecognizeClientDocument(
  applicationId: number,
  docId: number,
  pageNum?: number,
): Promise<ClientDocument> {
  const body = pageNum != null ? JSON.stringify({ page_num: pageNum }) : "{}";
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/client-documents/${docId}/recognize`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body,
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    let errMessage = `Не удалось распознать (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      errMessage = errJson.detail || errMessage;
    } catch {}
    throw new Error(errMessage);
  }
  return res.json();
}


// ============================================================================
// Pack 14a: Bulk import — пакет документов от менеджера
// ============================================================================

export type ImportFileMeta = {
  file_id: string;
  name: string;
  size: number;
  mime: string;
  extension: string;
  is_pdf: boolean;
  preview_url?: string;
  // Pack 14c — ИИ-классификация
  classified_type?: ClientDocumentType | null;
  classifier_confidence?: "high" | "medium" | "low" | null;
  classifier_country?: string | null;
  classifier_reasoning?: string | null;
  classifier_error?: string | null;
  // Pack 31.0
  classification_status?: "pending" | "done" | "error";
};

export type ImportSession = {
  session_id: string;
  archive_name: string;
  files: ImportFileMeta[];
  // Pack 31.0
  classification_done?: boolean;
};

export type ImportFileAssignment = {
  file_id: string;
  doc_type: ClientDocumentType | "skip";
  pdf_page?: number | null;
};

export type ImportFinalizeRequest = {
  application_id: number | null;
  internal_notes?: string | null;
  manager_text?: string;  // Pack 50.38-D4 — текст менеджера для автозаполнения
  files: ImportFileAssignment[];
  run_ocr: boolean;
  // Pack 50.0-C5 — тип заявки (только для target=new)
  application_type?: ApplicationType;
};

export type EgrylOcrData = {
  full_name_ru?: string | null;
  full_name_es?: string | null;
  short_name_inferred?: string | null;
  ogrn?: string | null;
  inn?: string | null;
  kpp?: string | null;
  legal_address?: string | null;
  postal_address?: string | null;
  director_full_name_ru?: string | null;
  director_position_ru?: string | null;
  bank_name?: string | null;
  bank_account?: string | null;
  bank_bic?: string | null;
  bank_correspondent_account?: string | null;
  egryl_extract_date?: string | null;
};

export type DirectorDeclensions = {
  nominative: string;
  genitive: string;
  dative: string;
  accusative: string;
  instrumental: string;
  prepositional: string;
  short_form: string;
};

export type PendingCompanyData = {
  ocr_data: EgrylOcrData;
  director_declensions: DirectorDeclensions;
  egryl_file_id: string;
  egryl_pdf_page?: number | null;
};

export type ImportFinalizeResult = {
  // Pack 14b — если ЕГРЮЛ найден но компании нет:
  requires_company_creation?: boolean;
  pending_company?: PendingCompanyData;
  session_id?: string;

  // Если всё ок (заявка создана):
  application_id?: number;
  application_reference?: string;
  documents_created?: number;
  company_attached?: { id: number; short_name: string } | null;
  ocr_results?: Array<{
    doc_id: number;
    doc_type: string;
    ok: boolean;
    error?: string;
    skipped?: boolean;
    fields?: string[];
  }>;
};

export type CompanyCreatePayload = {
  short_name: string;
  full_name_ru: string;
  full_name_es: string;
  country?: string;
  tax_id_primary: string;
  tax_id_secondary?: string | null;
  legal_address: string;
  postal_address?: string | null;
  director_full_name_ru: string;
  director_full_name_genitive_ru: string;
  director_short_ru: string;
  director_position_ru?: string;
  bank_name: string;
  bank_account: string;
  bank_bic: string;
  bank_correspondent_account?: string | null;
  egryl_extract_date?: string | null;
  notes?: string | null;
};

export type ImportFinalizeWithCompanyRequest = {
  company: CompanyCreatePayload;
  application_id: number | null;
  internal_notes?: string | null;
  manager_text?: string;  // Pack 50.38-D4 — текст менеджера для автозаполнения
  files: ImportFileAssignment[];
  run_ocr: boolean;
  // Pack 50.0-C5 — тип заявки (только для target=new)
  application_type?: ApplicationType;
};

/**
 * Загрузить архив (ZIP/RAR) — backend распакует и вернёт список файлов.
 */
export async function importPackageUpload(files: File[]): Promise<ImportSession> {
  // Pack 27.0: принимаем массив файлов. Для одного архива это [archive],
  // для набора одиночных файлов это [pdf, jpg, png, ...].
  // Backend сам разбирается какой это случай по расширениям.
  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }

  const res = await fetch(`${API_BASE_URL}/api/admin/import-package/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  });
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Ошибка загрузки архива (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

/**
 * Финализировать импорт — менеджер указал типы документов и заявку.
 */
export async function importPackageFinalize(
  sessionId: string,
  payload: ImportFinalizeRequest,
): Promise<ImportFinalizeResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/import-package/${sessionId}/finalize`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Ошибка импорта (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

/**
 * Финализация импорта с созданием новой компании из ЕГРЮЛ.
 * Используется когда первый /finalize вернул requires_company_creation=true.
 */
export async function importPackageFinalizeWithCompany(
  sessionId: string,
  payload: ImportFinalizeWithCompanyRequest,
): Promise<ImportFinalizeResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/import-package/${sessionId}/finalize/with-company`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Ошибка создания компании (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

/**
 * Финализация импорта БЕЗ компании — менеджер пропускает создание компании из ЕГРЮЛ.
 * Создаст заявку без company_id. ЕГРЮЛ-файлы будут пропущены.
 */
export async function importPackageFinalizeSkipCompany(
  sessionId: string,
  payload: ImportFinalizeRequest,
): Promise<ImportFinalizeResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/import-package/${sessionId}/finalize/skip-company`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Ошибка импорта без компании (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

/**
 * Отменить сессию импорта (удаляет временные файлы на сервере).
 */
export async function importPackageCancel(sessionId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/admin/import-package/${sessionId}/cancel`, {
    method: "POST",
    headers: authHeaders(),
  });
}

// Pack 31.0 — polling статуса классификации
export async function importPackageStatus(sessionId: string): Promise<ImportSession> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/import-package/${sessionId}/status`,
    { headers: authHeaders() },
  );
  if (!res.ok) {
    throw new Error(`importPackageStatus: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

// ============================================================================
// Pack 32.0 full — presigned PUT upload directly to R2
// ============================================================================

export type ImportPresignUpload = {
  file_id: string;
  name: string;
  size: number;
  mime: string;
  extension: string;
  temp_storage_key: string;
  upload_url: string;
};

export type ImportPresignBatchResponse = {
  session_id: string;
  uploads: ImportPresignUpload[];
};

export type PresignFileMeta = {
  name: string;
  size: number;
  mime: string;
};

/**
 * Pack 32.0: получить presigned PUT URLs для прямой загрузки файлов в R2
 * (минуя FastAPI/Railway). Возвращает session_id и массив upload_url'ов.
 */
export async function importPackagePresignBatch(
  files: PresignFileMeta[],
): Promise<ImportPresignBatchResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/import-package/presign-batch`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Ошибка presign (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

/**
 * Pack 32.0: финализирует upload — после того как фронт сам залил все файлы
 * напрямую в R2 через presigned URLs. Бэк проверяет что файлы на месте,
 * распаковывает архив (если был), и запускает фоновую классификацию.
 */
export async function importPackageFinalizeUploads(
  sessionId: string,
): Promise<ImportSession> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/import-package/${sessionId}/finalize-uploads`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Ошибка финализации загрузки (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

/**
 * Pack 32.0: PUT-загрузка одного файла прямо в R2 через presigned URL.
 * Возвращает Promise который резолвится при HTTP 200/201 от R2.
 * onProgress(0..1) — callback для прогресс-бара.
 *
 * Используем XMLHttpRequest (не fetch), потому что fetch не даёт
 * onprogress для upload-stream'а.
 */
export function uploadToR2WithProgress(
  uploadUrl: string,
  file: File,
  contentType: string,
  onProgress?: (fraction: number) => void,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl, true);
    xhr.setRequestHeader("Content-Type", contentType);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded / e.total);
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        if (onProgress) onProgress(1);
        resolve();
      } else {
        reject(new Error(`R2 PUT failed: ${xhr.status} ${xhr.statusText}`));
      }
    };

    xhr.onerror = () => {
      reject(new Error(`R2 PUT network error`));
    };

    xhr.onabort = () => {
      reject(new Error(`R2 PUT aborted`));
    };

    xhr.send(file);
  });
}


// Admin Applications
// ============================================================================

export async function listApplications(
  status?: string,
  archived: boolean = false,
  trash: boolean = false,
): Promise<ApplicationResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/admin/applications`);
  if (status) url.searchParams.set("status", status);
  if (archived) url.searchParams.set("archived", "true");
  if (trash) url.searchParams.set("trash", "true");
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
  // Pack 50.0-C1 — тип заявки (опционально, дефолт на бэке = SELF_EMPLOYED)
  application_type?: ApplicationType;
}): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Не удалось создать: ${res.status} ${await res.text()}`);
  return res.json();
}


/**
 * Pack 50.0-C1 — сменить тип заявки.
 * ВАЖНО: КАСКАД на бэке — удаляет все generated_document (R2 + БД),
 * сбрасывает company_id, position_id, contract_*, bank_* и др.,
 * сбрасывает статус в AWAITING_DATA. Двойной window.confirm() уже сделан
 * на стороне UI (см. ApplicationDetail.tsx, Pack 50.0-C4).
 */
export async function changeApplicationType(
  appId: number,
  newType: ApplicationType,
): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/change-type`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ application_type: newType }),
  });
  if (!res.ok) throw new Error(`Не удалось сменить тип: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function getApplicantById(id: number): Promise<ApplicantResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applicants/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);
  return res.json();
}

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


/**
 * Обновить данные кандидата (Applicant) от имени менеджера.
 * Pack 14 finishing: позволяет менеджеру вписать русские ФИО для иностранцев,
 * исправить гражданство и т.д.
 */
export async function updateApplicant(
  id: number,
  patch: Partial<{
    last_name_native: string;
    first_name_native: string;
    middle_name_native: string;
    last_name_latin: string;
    first_name_latin: string;
    nationality: string;
    sex: string;
    home_country: string;
    home_address: string;
    passport_number: string;
    passport_issue_date: string;
    passport_issuer: string;
    passport_issuer_ru: string;
    // Pack 41.0-D — multi-passport (опциональные, чтобы не ломать вызовы)
    passports?: PassportRecord[];
    passport_id_for_ru_docs?: string | null;
    birth_date: string;
    birth_place_latin: string;
    email: string;
    phone: string;
    inn: string;
    // Pack 17 — INN auto-generation
    inn_registration_date: string | null;
    inn_source: string | null;
    inn_kladr_code: string | null;
    // Pack 16 — банк
    bank_id: number | null;
    bank_account: string | null;
    bank_name: string | null;
    bank_bic: string | null;
    bank_correspondent_account: string | null;
  }>,
): Promise<ApplicantResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applicants/${id}`, {
    method: "PATCH",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Ошибка обновления (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}


/**
 * Pack 14 finishing — транслитерирует латинское ФИО в русский черновик.
 *
 * Используется в ApplicantDrawer — кнопка «? Транслитерировать с латиницы».
 * Возвращает черновик который менеджер может поправить.
 */
export async function transliterateLatToRu(
  lastNameLatin: string,
  firstNameLatin: string,
  nationality?: string,
): Promise<{
  last_name_native: string;
  first_name_native: string;
  warning: string;
}> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applicants/transliterate`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      last_name_latin: lastNameLatin,
      first_name_latin: firstNameLatin,
      nationality: nationality || null,
    }),
  });
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Ошибка транслитерации (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
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

// Pack 30.0
export async function toggleUrgent(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/toggle-urgent`, {
    method: "POST", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`toggle-urgent: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function togglePaid(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/toggle-paid`, {
    method: "POST", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`toggle-paid: ${res.status} ${await res.text()}`);
  return res.json();
}

// Pack 34.2 — переключить флаг "Готово, можно забирать"
export async function toggleReady(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/toggle-ready`, {
    method: "POST", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`toggle-ready: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function toggleFiled(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/toggle-filed`, {
    method: "POST", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`toggle-filed: ${res.status} ${await res.text()}`);
  return res.json();
}
// Pack 36.0 end

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
// Pack 29.0/29.4 — Contract templates
// ============================================================================

export type ContractTemplateOption = {
  slug: string;
  label: string;
  archetype: string;       // 'vozmezdnoe' | 'vozmezdnoe_hourly' | 'gph'
  description: string;
};

export async function listContractTemplates(): Promise<ContractTemplateOption[]> {
  const res = await fetch(`${API_BASE_URL}/api/admin/companies/contract-templates`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Contract templates: ${res.status}`);
  const data = await res.json();
  return data.templates;
}

// ============================================================================
// Pack 50.1-G — Шаблоны Трудового договора
// ============================================================================

export type EmploymentContractTemplateOption = {
  slug: string;
  label: string;
  archetype: string;       // всегда "employment" для шаблонов найма
  description: string;
};

export async function listEmploymentContractTemplates(): Promise<EmploymentContractTemplateOption[]> {
  const res = await fetch(`${API_BASE_URL}/api/admin/companies/employment-contract-templates`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Employment contract templates: ${res.status}`);
  const data = await res.json();
  return data.templates;
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
  // Постсоветское пространство (главная аудитория)
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
  { value: "MDA", label: "Молдова" },
  { value: "TKM", label: "Туркменистан" },
  { value: "EST", label: "Эстония" },
  { value: "LVA", label: "Латвия" },
  { value: "LTU", label: "Литва" },
  // Балканы
  { value: "MKD", label: "Северная Македония" },
  { value: "ALB", label: "Албания" },
  { value: "SRB", label: "Сербия" },
  { value: "BIH", label: "Босния и Герцеговина" },
  { value: "MNE", label: "Черногория" },
  // Другие
  { value: "TUR", label: "Турция" },
  { value: "ISR", label: "Израиль" },
  { value: "IRN", label: "Иран" },
];

// Pack 34.0 — полный мир (ISO 3166-1 alpha-3, ~195 стран).
// Алфавитно по русскому label.
// Используется в ApplicantDrawer (Гражданство, Страна жительства, Страна рождения)
// и StepPersonalInfo визарда (Страна рождения).
//
// ВНИМАНИЕ: бэкендные словари _NATIONALITY_GENITIVE_RU / _NATIONALITY_NOMINATIVE_RU
// (backend/app/templates_engine/context.py) и COUNTRY_NAMES_ES
// (backend/app/pdf_forms_engine/countries_es.py) покрывают ~60-80 стран.
// Если выбрана страна вне этих словарей — в договоре будет «Гражданин XYZ»
// (ISO-код), в MI-T испанское поле País останется пустым. Менеджер увидит
// дефект и поправит вручную, либо попросит расширить словари точечно.
export const COUNTRY_OPTIONS = [
  { value: "AUT", label: "Австрия" },
  { value: "AUS", label: "Австралия" },
  { value: "AZE", label: "Азербайджан" },
  { value: "ALB", label: "Албания" },
  { value: "DZA", label: "Алжир" },
  { value: "AGO", label: "Ангола" },
  { value: "AND", label: "Андорра" },
  { value: "ATG", label: "Антигуа и Барбуда" },
  { value: "ARG", label: "Аргентина" },
  { value: "ARM", label: "Армения" },
  { value: "AFG", label: "Афганистан" },
  { value: "BHS", label: "Багамы" },
  { value: "BGD", label: "Бангладеш" },
  { value: "BRB", label: "Барбадос" },
  { value: "BHR", label: "Бахрейн" },
  { value: "BLZ", label: "Белиз" },
  { value: "BLR", label: "Беларусь" },
  { value: "BEL", label: "Бельгия" },
  { value: "BEN", label: "Бенин" },
  { value: "BGR", label: "Болгария" },
  { value: "BOL", label: "Боливия" },
  { value: "BIH", label: "Босния и Герцеговина" },
  { value: "BWA", label: "Ботсвана" },
  { value: "BRA", label: "Бразилия" },
  { value: "BRN", label: "Бруней" },
  { value: "BFA", label: "Буркина-Фасо" },
  { value: "BDI", label: "Бурунди" },
  { value: "BTN", label: "Бутан" },
  { value: "VUT", label: "Вануату" },
  { value: "VAT", label: "Ватикан" },
  { value: "GBR", label: "Великобритания" },
  { value: "HUN", label: "Венгрия" },
  { value: "VEN", label: "Венесуэла" },
  { value: "TLS", label: "Восточный Тимор" },
  { value: "VNM", label: "Вьетнам" },
  { value: "GAB", label: "Габон" },
  { value: "HTI", label: "Гаити" },
  { value: "GUY", label: "Гайана" },
  { value: "GMB", label: "Гамбия" },
  { value: "GHA", label: "Гана" },
  { value: "GTM", label: "Гватемала" },
  { value: "GIN", label: "Гвинея" },
  { value: "GNB", label: "Гвинея-Бисау" },
  { value: "DEU", label: "Германия" },
  { value: "HND", label: "Гондурас" },
  { value: "GRD", label: "Гренада" },
  { value: "GRC", label: "Греция" },
  { value: "GEO", label: "Грузия" },
  { value: "DNK", label: "Дания" },
  { value: "COD", label: "ДР Конго" },
  { value: "DJI", label: "Джибути" },
  { value: "DMA", label: "Доминика" },
  { value: "DOM", label: "Доминиканская Республика" },
  { value: "EGY", label: "Египет" },
  { value: "ZMB", label: "Замбия" },
  { value: "ZWE", label: "Зимбабве" },
  { value: "ISR", label: "Израиль" },
  { value: "IND", label: "Индия" },
  { value: "IDN", label: "Индонезия" },
  { value: "JOR", label: "Иордания" },
  { value: "IRQ", label: "Ирак" },
  { value: "IRN", label: "Иран" },
  { value: "IRL", label: "Ирландия" },
  { value: "ISL", label: "Исландия" },
  { value: "ESP", label: "Испания" },
  { value: "ITA", label: "Италия" },
  { value: "YEM", label: "Йемен" },
  { value: "CPV", label: "Кабо-Верде" },
  { value: "KAZ", label: "Казахстан" },
  { value: "KHM", label: "Камбоджа" },
  { value: "CMR", label: "Камерун" },
  { value: "CAN", label: "Канада" },
  { value: "QAT", label: "Катар" },
  { value: "KEN", label: "Кения" },
  { value: "CYP", label: "Кипр" },
  { value: "KGZ", label: "Кыргызстан" },
  { value: "KIR", label: "Кирибати" },
  { value: "CHN", label: "Китай" },
  { value: "COL", label: "Колумбия" },
  { value: "COM", label: "Коморы" },
  { value: "COG", label: "Конго" },
  { value: "PRK", label: "Корея Северная" },
  { value: "KOR", label: "Корея Южная" },
  { value: "XKX", label: "Косово" },
  { value: "CRI", label: "Коста-Рика" },
  { value: "CIV", label: "Кот-д\'Ивуар" },
  { value: "CUB", label: "Куба" },
  { value: "KWT", label: "Кувейт" },
  { value: "LAO", label: "Лаос" },
  { value: "LVA", label: "Латвия" },
  { value: "LSO", label: "Лесото" },
  { value: "LBR", label: "Либерия" },
  { value: "LBN", label: "Ливан" },
  { value: "LBY", label: "Ливия" },
  { value: "LTU", label: "Литва" },
  { value: "LIE", label: "Лихтенштейн" },
  { value: "LUX", label: "Люксембург" },
  { value: "MUS", label: "Маврикий" },
  { value: "MRT", label: "Мавритания" },
  { value: "MDG", label: "Мадагаскар" },
  { value: "MWI", label: "Малави" },
  { value: "MYS", label: "Малайзия" },
  { value: "MLI", label: "Мали" },
  { value: "MDV", label: "Мальдивы" },
  { value: "MLT", label: "Мальта" },
  { value: "MAR", label: "Марокко" },
  { value: "MHL", label: "Маршалловы Острова" },
  { value: "MEX", label: "Мексика" },
  { value: "FSM", label: "Микронезия" },
  { value: "MOZ", label: "Мозамбик" },
  { value: "MDA", label: "Молдова" },
  { value: "MCO", label: "Монако" },
  { value: "MNG", label: "Монголия" },
  { value: "MMR", label: "Мьянма" },
  { value: "NAM", label: "Намибия" },
  { value: "NRU", label: "Науру" },
  { value: "NPL", label: "Непал" },
  { value: "NER", label: "Нигер" },
  { value: "NGA", label: "Нигерия" },
  { value: "NLD", label: "Нидерланды" },
  { value: "NIC", label: "Никарагуа" },
  { value: "NZL", label: "Новая Зеландия" },
  { value: "NOR", label: "Норвегия" },
  { value: "ARE", label: "ОАЭ" },
  { value: "OMN", label: "Оман" },
  { value: "PAK", label: "Пакистан" },
  { value: "PLW", label: "Палау" },
  { value: "PSE", label: "Палестина" },
  { value: "PAN", label: "Панама" },
  { value: "PNG", label: "Папуа — Новая Гвинея" },
  { value: "PRY", label: "Парагвай" },
  { value: "PER", label: "Перу" },
  { value: "POL", label: "Польша" },
  { value: "PRT", label: "Португалия" },
  { value: "RUS", label: "Россия" },
  { value: "RWA", label: "Руанда" },
  { value: "ROU", label: "Румыния" },
  { value: "SLV", label: "Сальвадор" },
  { value: "WSM", label: "Самоа" },
  { value: "SMR", label: "Сан-Марино" },
  { value: "STP", label: "Сан-Томе и Принсипи" },
  { value: "SAU", label: "Саудовская Аравия" },
  { value: "SWZ", label: "Эсватини" },
  { value: "MKD", label: "Северная Македония" },
  { value: "SYC", label: "Сейшелы" },
  { value: "SEN", label: "Сенегал" },
  { value: "VCT", label: "Сент-Винсент и Гренадины" },
  { value: "KNA", label: "Сент-Китс и Невис" },
  { value: "LCA", label: "Сент-Люсия" },
  { value: "SRB", label: "Сербия" },
  { value: "SGP", label: "Сингапур" },
  { value: "SYR", label: "Сирия" },
  { value: "SVK", label: "Словакия" },
  { value: "SVN", label: "Словения" },
  { value: "SLB", label: "Соломоновы Острова" },
  { value: "SOM", label: "Сомали" },
  { value: "SDN", label: "Судан" },
  { value: "SSD", label: "Южный Судан" },
  { value: "SUR", label: "Суринам" },
  { value: "SLE", label: "Сьерра-Леоне" },
  { value: "USA", label: "США" },
  { value: "TJK", label: "Таджикистан" },
  { value: "THA", label: "Таиланд" },
  { value: "TZA", label: "Танзания" },
  { value: "TGO", label: "Того" },
  { value: "TON", label: "Тонга" },
  { value: "TTO", label: "Тринидад и Тобаго" },
  { value: "TUV", label: "Тувалу" },
  { value: "TUN", label: "Тунис" },
  { value: "TKM", label: "Туркменистан" },
  { value: "TUR", label: "Турция" },
  { value: "UGA", label: "Уганда" },
  { value: "UZB", label: "Узбекистан" },
  { value: "UKR", label: "Украина" },
  { value: "URY", label: "Уругвай" },
  { value: "FJI", label: "Фиджи" },
  { value: "PHL", label: "Филиппины" },
  { value: "FIN", label: "Финляндия" },
  { value: "FRA", label: "Франция" },
  { value: "HRV", label: "Хорватия" },
  { value: "CAF", label: "ЦАР" },
  { value: "TCD", label: "Чад" },
  { value: "MNE", label: "Черногория" },
  { value: "CZE", label: "Чехия" },
  { value: "CHL", label: "Чили" },
  { value: "CHE", label: "Швейцария" },
  { value: "SWE", label: "Швеция" },
  { value: "LKA", label: "Шри-Ланка" },
  { value: "ECU", label: "Эквадор" },
  { value: "GNQ", label: "Экваториальная Гвинея" },
  { value: "ERI", label: "Эритрея" },
  { value: "EST", label: "Эстония" },
  { value: "ETH", label: "Эфиопия" },
  { value: "ZAF", label: "ЮАР" },
  { value: "JAM", label: "Ямайка" },
  { value: "JPN", label: "Япония" },
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
  { id: "approved", label: "Одобрены", statuses: ["approved"] },
  { id: "problems", label: "Проблемы", statuses: ["rejected", "needs_followup", "cancelled"] },
];

export function getClientLink(token: string): string {
  if (typeof window !== "undefined") return `${window.location.origin}/client/${token}`;
  return `/client/${token}`;
}

/**
 * Pack 42.1 — удалить документ клиента (БД + R2 storage).
 * Возвращает {deleted: true, doc_id} при успехе.
 */
export async function adminDeleteClientDocument(
  applicationId: number,
  docId: number,
): Promise<{ deleted: boolean; doc_id: number }> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/client-documents/${docId}`,
    {
      method: "DELETE",
      headers: authHeaders(),
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    let errMessage = `Не удалось удалить документ (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      errMessage = errJson.detail || errMessage;
    } catch {}
    throw new Error(errMessage);
  }
  return res.json();
}


export const DOCUMENT_TYPE_LABELS: Record<ClientDocumentType, string> = {
  passport_internal_main: "Паспорт РФ — главный разворот",
  passport_internal_address: "Паспорт РФ — страница прописки",
  passport_foreign: "Загранпаспорт РФ",
  // Pack 14a — для иностранных клиентов
  passport_national: "Национальный паспорт (не РФ)",
  residence_card: "ВНЖ / Residence card",
  criminal_record: "Справка о несудимости",
  // Pack 14b — выписка из ЕГРЮЛ
  egryl_extract: "Выписка из ЕГРЮЛ (компания)",
  diploma_main: "Диплом — основная страница",
  diploma_apostille: "Диплом — апостиль",
  other: "Другой документ",
};

// Pack 13.1.1: метки для конфликт-полей в Review
export const FIELD_LABELS: Record<string, string> = {
  last_name_native: "Фамилия (рус)",
  first_name_native: "Имя (рус)",
  middle_name_native: "Отчество",
  last_name_latin: "Фамилия (лат)",
  first_name_latin: "Имя (лат)",
  birth_date: "Дата рождения",
  birth_place_latin: "Место рождения (лат)",
  nationality: "Гражданство",
  sex: "Пол",
  passport_number: "Номер паспорта",
  passport_issue_date: "Дата выдачи паспорта",
  passport_issuer: "Кем выдан",
  passport_issuer_ru: "Кем выдан (рус., для договора)",
  home_address: "Адрес регистрации",
  home_country: "Страна",
};
// ============================================================================
// Pack 15 — Translations (испанский перевод документов)
// ============================================================================

export type TranslationKind =
  | "contract"
  | "act_1"
  | "act_2"
  | "act_3"
  | "invoice_1"
  | "invoice_2"
  | "invoice_3"
  | "employer_letter"
  | "cv"
  | "bank_statement"
  // Pack 50.34 — документы найма
  | "employment_contract"
  | "business_trip_order"
  | "ndfl_2"
  | "stdr"
  | "payslip_1"
  | "payslip_2"
  | "payslip_3"
  | "employer_letter_naim"
  | "soo"
  | "apostille_sfr";

export type TranslationStatus = "pending" | "in_progress" | "done" | "failed";

export type TranslationItem = {
  id: number;
  kind: TranslationKind;
  status: TranslationStatus;
  file_name?: string;
  file_size?: number;
  error_message?: string;
  created_at: string;
  completed_at?: string;
  download_url?: string;
};

export type TranslationsSummary = {
  total: number;
  pending: number;
  in_progress: number;
  done: number;
  failed: number;
  is_active: boolean;  // есть ли pending или in_progress
  has_any: boolean;    // есть ли хоть одна запись
};

export type TranslationsResponse = {
  translations: TranslationItem[];
  summary: TranslationsSummary;
};

// Метаинформация о документах для UI: красивые имена и порядок
export const TRANSLATION_KIND_INFO: Record<
  TranslationKind,
  { ru_label: string; es_filename: string; order: number }
> = {
  contract:        { ru_label: "Договор",     es_filename: "01_Contrato.docx",            order: 1  },
  act_1:           { ru_label: "Акт 1",       es_filename: "02_Acta_1.docx",              order: 2  },
  act_2:           { ru_label: "Акт 2",       es_filename: "03_Acta_2.docx",              order: 3  },
  act_3:           { ru_label: "Акт 3",       es_filename: "04_Acta_3.docx",              order: 4  },
  invoice_1:       { ru_label: "Счёт 1",      es_filename: "05_Factura_1.docx",           order: 5  },
  invoice_2:       { ru_label: "Счёт 2",      es_filename: "06_Factura_2.docx",           order: 6  },
  invoice_3:       { ru_label: "Счёт 3",      es_filename: "07_Factura_3.docx",           order: 7  },
  employer_letter: { ru_label: "Письмо",      es_filename: "08_Carta_de_la_empresa.docx", order: 8  },
  cv:              { ru_label: "Резюме",      es_filename: "09_CV.docx",                  order: 9  },
  bank_statement:  { ru_label: "Выписка",     es_filename: "10_Extracto_bancario.docx",   order: 10 },
  // Pack 50.34 — документы найма
  employment_contract:  { ru_label: "Трудовой договор",   es_filename: "01_Contrato_de_trabajo.docx",            order: 11 },
  business_trip_order:  { ru_label: "Приказ Т-9",         es_filename: "17_Orden_de_comision_de_servicio.docx",  order: 12 },
  ndfl_2:               { ru_label: "2-НДФЛ",             es_filename: "18_Certificado_2-NDFL.docx",             order: 13 },
  stdr:                 { ru_label: "СТД-Р",              es_filename: "19_STD-R.docx",                          order: 14 },
  payslip_1:            { ru_label: "Расчётный листок 1", es_filename: "20_Nomina_1.docx",                       order: 15 },
  payslip_2:            { ru_label: "Расчётный листок 2", es_filename: "21_Nomina_2.docx",                       order: 16 },
  payslip_3:            { ru_label: "Расчётный листок 3", es_filename: "22_Nomina_3.docx",                       order: 17 },
  employer_letter_naim: { ru_label: "Письмо работодателя", es_filename: "23_Carta_del_empleador.docx",          order: 18 },
  soo:                  { ru_label: "Свидетельство об отъезде", es_filename: "24_Certificado_de_salida.docx",   order: 19 },
  apostille_sfr:        { ru_label: "Апостиль СФР",       es_filename: "25_Apostilla_SFR.docx",                  order: 20 },
};

/** Запустить перевод всего пакета (10 документов) в фоне. */
export async function startPackageTranslation(applicationId: number): Promise<{ status: string; kinds_count: number }> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/translate`,
    { method: "POST", headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/** Перевести один документ (или повторить для упавшего). */
export async function startSingleTranslation(
  applicationId: number,
  kind: TranslationKind,
): Promise<{ status: string; kind: string }> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/translate/${kind}`,
    { method: "POST", headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/** Получить список всех переводов заявки + сводку статусов. */
export async function getTranslations(applicationId: number): Promise<TranslationsResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations`,
    { headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/** Удалить все переводы (для «Перевести заново»). */
export async function deleteAllTranslations(applicationId: number): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations`,
    { method: "DELETE", headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
}

/** Pack 35.8: отменить зависшие переводы (PENDING/IN_PROGRESS) — для очистки крутилок. */
export async function cancelStuckTranslations(applicationId: number): Promise<{ cancelled: number }> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations/cancel-stuck`,
    { method: "POST", headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/** Скачать ZIP всех успешно переведённых документов. */
export async function downloadTranslationsZip(applicationId: number): Promise<Blob> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations/zip`,
    { headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.blob();
}

/** Скачать один переведённый файл по типу. */
export async function downloadTranslationFile(
  applicationId: number,
  kind: TranslationKind,
): Promise<Blob> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/translations/${kind}/download`,
    { headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.blob();
}
// ============================================================================
// Pack 15.1 — Translit suggest helper
// ============================================================================
//
// ВАЖНО: updateCompany уже существует в этом файле (строка ~4525),
// я её НЕ дублирую. Только новый translit-suggest endpoint.
//
// Также нужно ОТДЕЛЬНО добавить опциональное поле в существующий
// CompanyResponse (см. INSTRUCTIONS.md, шаг 2a).

export type TranslitField = "director_name" | "company_name";

export type TranslitSuggestResponse = {
  text: string;
  suggestion: string;
};

/**
 * Pack 15.1: GOST-транслит чернового латинского написания для поля компании.
 * Менеджер потом может подправить в drawer.
 */
export async function getTranslitSuggestion(
  text: string,
  field: TranslitField = "director_name",
): Promise<TranslitSuggestResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/companies/translit-suggest`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ text, field }),
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}
// ============================================================================
// Pack 16 — Banks + account generator
// ============================================================================
//
// Эти функции добавить в КОНЕЦ frontend/lib/api.ts.
//
// ВАЖНО: также добавить опциональное поле bank_id в ApplicantResponse
// (см. INSTRUCTIONS.md, шаг 2a).

export type BankResponse = {
  id: number;
  name: string;
  short_name?: string | null;
  bik: string;
  inn: string;
  kpp?: string | null;
  correspondent_account: string;
  swift?: string | null;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  website?: string | null;
  is_active: boolean;
  notes?: string | null;
  applicant_count?: number;
};

export async function listBanks(includeInactive = false): Promise<BankResponse[]> {
  const url = `${API_BASE_URL}/api/admin/banks${includeInactive ? "?include_inactive=true" : ""}`;
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function getBank(id: number): Promise<BankResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/banks/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function createBank(data: Partial<BankResponse>): Promise<BankResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/banks`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function updateBank(id: number, data: Partial<BankResponse>): Promise<BankResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/banks/${id}`, {
    method: "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function deleteBank(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/admin/banks/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
}

export type GenerateAccountResponse = {
  account: string;
  bik: string;
  bank_name: string;
};

/**
 * Pack 16: генерирует уникальный 20-значный расчётный счёт по алгоритму ЦБ РФ
 * для указанного банка.
 *
 * @param bankId ID банка из справочника
 * @param isResident true для гр. РФ (40817), false для нерезидентов (40820)
 */
export async function generateAccount(
  bankId: number,
  isResident: boolean = true,
): Promise<GenerateAccountResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/banks/${bankId}/generate-account`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ is_resident: isResident }),
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}



// ============================================================================
// Pack 17 — Regions for INN auto-generation
// ============================================================================
//
// Справочник регионов РФ для системы автогенерации ИНН самозанятого.
// Используется в Pack 17.3 для UI настроек /admin/settings/regions
// и в модале «Сгенерировать ИНН».

export type RegionResponse = {
  id: number;
  kladr_code: string;        // 13 цифр, например "2300000700000" = Сочи
  region_code: string;       // 2 цифры, например "23" = Краснодарский край
  name: string;              // "Сочи"
  name_full: string;         // "Краснодарский край, городской округ Сочи"
  type: string;              // "city"
  is_active: boolean;
  diaspora_for_countries: string[];  // ["TUR", "AZE"]
  notes: string | null;
};

/**
 * Список регионов.
 * @param isActive если true — только активные. По умолчанию все.
 * @param country ISO-3 код страны. Если задан — фильтр по диаспоре.
 *                Например country="TUR" вернёт только регионы где TUR в diaspora_for_countries.
 */
export async function listRegions(
  isActive?: boolean,
  country?: string,
): Promise<RegionResponse[]> {
  const params = new URLSearchParams();
  if (isActive !== undefined) params.append("is_active", String(isActive));
  if (country) params.append("country", country);
  const qs = params.toString() ? `?${params.toString()}` : "";

  const res = await fetch(`${API_BASE_URL}/api/admin/regions${qs}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function getRegion(id: number): Promise<RegionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/regions/${id}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function createRegion(
  data: Partial<RegionResponse>,
): Promise<RegionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/regions`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function updateRegion(
  id: number,
  data: Partial<RegionResponse>,
): Promise<RegionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/regions/${id}`, {
    method: "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function deleteRegion(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/admin/regions/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
}


// ============================================================================
// Pack 17.2 — INN auto-generation API client
// ============================================================================

// Pack 18.6 — синхронизация с реальным API (см. backend/app/api/inn_generation.py).
// Старая версия (Pack 17.3) описывала поля которых бэкенд не шлёт:
//   full_name_rmsp, address_was_generated, estimated_npd_start*, target_*,
//   region_pick_*, yandex_search_url, rusprofile_url, rmsp_raw.
// Реальные имена полей — ниже. Также добавлены fallback_* поля Pack 18.1.
// Pack 28.2 Часть Б: discriminated union — backend может вернуть либо
// мгновенный результат (kind: "immediate"), либо task_id для поллинга
// (kind: "task") если в пуле verified=0 для региона applicant'а.
export type InnSuggestionImmediate = {
  kind: "immediate";
  inn: string;
  full_name: string;
  home_address: string;
  kladr_code: string;
  region_name: string;
  region_code: string;
  inn_registration_date: string;
  source: string;
  fallback_used: boolean;
  requested_region_name: string | null;
  requested_region_code: string | null;
  fallback_reason: string | null;
};

export type InnSuggestionTask = {
  kind: "task";
  task_id: number;
  region_code: string;
  region_name: string;
  estimated_seconds: number;
};

export type InnSuggestionResponse = InnSuggestionImmediate | InnSuggestionTask;

// Pack 18.6 fix: backend ждёт `kladr_code`, не `region_kladr_code`.
// Старое имя молча игнорировалось pydantic'ом > applicant.inn_kladr_code не записывался.
// Это был root cause костыля Pack 18.3.1 (auto-fill при генерации справки).
// После этого фикса можно убирать костыль (см. Pack 17.7 в roadmap).
export type InnAcceptPayload = {
  inn: string;
  home_address?: string | null;
  kladr_code?: string | null;
  inn_registration_date?: string | null;
  inn_source?: string | null;
};

// Pack 18.6 — согласован с InnAcceptResponse из inn_generation.py.
// Старая версия не показывала поля Pack 18.2 (npd_check_status / manual_check_url) —
// менеджер не видел когда ФНС был недоступен и нужна ручная проверка.
export type InnAcceptResult = {
  ok: boolean;
  applicant_id: number;
  inn: string;
  // Pack 18.2:
  npd_check_status: "confirmed" | "skipped_fns_unavailable" | "skipped_already_checked";
  manual_check_url: string | null;
  npd_check_message: string | null;
};

/**
 * Pack 17.2: подбирает ИНН + адрес + дату для заявителя через rmsp-pp.nalog.ru.
 * НЕ сохраняет в БД — только возвращает кандидата для отображения в модале.
 *
 * Каждый вызов даёт нового кандидата (sortBy ИНН + skip used_inns).
 */
export async function suggestInn(applicantId: number): Promise<InnSuggestionResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/${applicantId}/inn-suggest`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/**
 * Pack 17.2: сохраняет выбранного кандидата в applicant.
 * После сохранения этот ИНН попадает в used_inns — не будет предложен другому.
 */
export async function acceptInn(
  applicantId: number,
  payload: InnAcceptPayload,
): Promise<InnAcceptResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/${applicantId}/inn-accept`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}


// Pack 18.8 — перегенерация адреса в том же городе куда привязан ИНН.
// Не требует обращения в ФНС, не пишет в БД — только возвращает новый случайный
// адрес из шаблонов KNOWN_REGIONS для KLADR'а который уже у applicant.
// Запись в БД — через обычный PATCH /applicants/{id} (UI «Сохранить»).
export type RegenAddressResult = {
  home_address: string;
  kladr_code: string;
};

/**
 * Pack 18.8: перегенерировать случайный адрес в том же городе что у ИНН.
 *
 * По умолчанию использует applicant.inn_kladr_code как KLADR.
 * Опционально можно передать kladr_code (override) — пока во фронте не используется,
 * заложено на будущее (если когда-нибудь добавим выбор региона из выпадающего меню).
 *
 * Может выкинуть 400 если у applicant'а нет inn_kladr_code (ИНН не выдан) или
 * если KLADR не в KNOWN_REGIONS (старые данные до Pack 18.6).
 */
export async function regenerateAddress(
  applicantId: number,
  kladr_code?: string,
): Promise<RegenAddressResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/${applicantId}/regen-address`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(kladr_code ? { kladr_code } : {}),
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}




// ============================================================================
// Pack 19.0 — Автогенерация образования (вуз + специальность + год выпуска)
// ============================================================================
// Подбирает один вуз по региону клиента (из inn_kladr_code) и специальности,
// которая в свою очередь определяется по последней должности из work_history.
// Год выпуска вычисляется как (год_рождения + 22 + случайный 0-5).
// Не пишет в БД — только возвращает данные для UI; запись в БД делается
// обычным PATCH /applicants/{id} (UI «Сохранить»).

export type RegenEducationResult = {
  institution: string;        // Полное название вуза (для CV)
  institution_short: string;  // Короткое название (для UI)
  degree: string;             // Бакалавр / Специалист / Магистр
  specialty: string;          // "08.03.01 Строительство"
  graduation_year: number;
  fallback_used: boolean;     // True если регион клиента не нашёлся > подобрали Москву
  matched_pattern: string | null;  // Какой position_pattern сработал (для отладки)
};

/**
 * Pack 19.0: автогенерация образования.
 *
 * Может выкинуть 500 если:
 *  - у клиента нет должности в work_history и нет дефолтного маппинга
 *  - в БД нет вузов с подходящей специальностью даже в Москве (рассинхрон seed'а)
 *
 * UX: фронт получает результат, кладёт в applicant.education[0] и просит
 * менеджера нажать «Сохранить» (либо сохраняет автоматически).
 */
export async function regenerateEducation(
  applicantId: number,
): Promise<RegenEducationResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/${applicantId}/regen-education`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}


// ============================================================================
// Pack 19.1 — Автогенерация work_history (компании + должности + даты)
// ============================================================================
// Подбирает 1-3 правдоподобные записи трудового стажа на основе:
//  - Регион клиента (из applicant.inn_kladr_code → first 2 chars)
//  - Специальность из applicant.education[-1] (если уже сгенерирована Pack 19.0)
//    или из work_history[0].position через PositionSpecialtyMap
//    или из application.position.title_ru (Pack 19.0.2 fallback)
//  - Career-track: уровни 1-4 (Junior/Middle/Senior/Lead)
//
// Гарантирует минимум 3.5 года в последней записи (требование DN-визы).
// Не пишет в БД — фронт получает массив записей и сохраняет через PATCH
// /applicants/{id} с work_history[].
//
// Pack 19.1a: duties=[] для каждой записи (заполнится в Pack 19.1b после
// ревью CV-шаблона).

export type RegenWorkHistoryRecord = {
  period_start: string;       // "Сентябрь 2022" или "09/2022"
  period_end: string;         // "Август 2025" или "по настоящее время"
  company: string;            // Полное название (для CV)
  position: string;           // Название должности на русском
  duties: string[];           // Pack 19.1a: пустой массив
};

export type RegenWorkHistoryResult = {
  records: RegenWorkHistoryRecord[];   // 1-3 записи
  fallback_used: boolean;              // True если ушли в Москву из-за пустого региона
  specialty_used: string;              // "08.03.01 Строительство" (для отладки)
  matched_pattern: string | null;      // Какой position_pattern сработал ("education[0]" / "инженер" / null)
};

/**
 * Pack 19.1: автогенерация work_history.
 *
 * Может выкинуть 500 если:
 *  - Pack 19.0 (specialty seed) не применён — таблица specialty пуста
 *  - Pack 19.1 (legend_company seed) не применён — нет компаний в БД
 *  - Не нашлось подходящего career_track (рассинхрон seed'а)
 *
 * UX: фронт получает результат, заменяет applicant.work_history полностью
 * на пришедшие records, и просит менеджера нажать «Сохранить» (либо
 * сохраняет автоматически).
 */
export async function regenerateWorkHistory(
  applicantId: number,
): Promise<RegenWorkHistoryResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/${applicantId}/regen-work-history`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}


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
 * Pack 51 — дополнить выписку транзакциями за [periodFrom, periodTo]
 * БЕЗ перезаписи существующих. Backend пересчитает opening_balance чтобы
 * closing на старом period_end не сдвинулся (точка непрерывности баланса).
 */
export async function appendBankTransactions(
  appId: number,
  periodFrom: string,
  periodTo: string
): Promise<BankStatementResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${appId}/bank-transactions/append`,
    {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ period_from: periodFrom, period_to: periodTo }),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to append bank transactions: ${res.status}`);
  }
  return res.json();
}

/**
 * Pack 53 — перевод банковской выписки на испанский (long-running ~30-60 сек).
 * Backend: POST /bank-statement/translate
 *
 * Переводит RU выписку v2 (без печатей) → ES через LLM, сохраняет в R2,
 * обновляет Application.bank_statement_translation_storage_key.
 * После этого /download-file/bank_statement возвращает combined PDF (RU+ES).
 *
 * Каждое нажатие = новый LLM-запрос (~$0.05). Старый ключ перетирается.
 * Доступно только для v2-выписок (bank_template_legacy_v1=false).
 */
export async function translateBankStatement(
  appId: number
): Promise<{ status: string; storage_key: string }> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${appId}/bank-statement/translate`,
    {
      method: "POST",
      headers: jsonHeaders(),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to translate bank statement: ${res.status}`);
  }
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

// Pack 26.0 — извлечение реквизитов компании из DOCX
export interface ExtractedCompanyFields {
  fields: {
    full_name_ru?: string | null;
    full_name_es?: string | null;
    short_name?: string | null;
    ogrn?: string | null;
    inn?: string | null;
    kpp?: string | null;
    legal_address?: string | null;
    postal_address?: string | null;
    director_full_name_ru?: string | null;
    director_full_name_genitive_ru?: string | null;
    director_short_ru?: string | null;
    director_full_name_latin?: string | null;
    director_position_ru?: string | null;
    bank_name?: string | null;
    bank_account?: string | null;
    bank_bic?: string | null;
    bank_correspondent_account?: string | null;
    charter_capital?: string | null;
  };
  existing_company_id: number | null;
  existing_company_name: string | null;
}

/**
 * Загружает DOCX с реквизитами компании на бэкенд, возвращает извлечённые поля
 * + existing_company_id если компания с таким ИНН уже есть в БД.
 */
export async function extractCompanyFromDocument(
  file: File
): Promise<ExtractedCompanyFields> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(
    `${API_BASE_URL}/api/admin/companies/extract-from-document`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: formData,
    }
  );
  if (!res.ok) {
    const errText = await res.text();
    let msg = `Не удалось извлечь реквизиты (${res.status})`;
    try {
      const errJson = JSON.parse(errText);
      msg = errJson.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// Pack 27.0 — Корзина (soft-delete с автоудалением через 7 дней)

/**
 * Soft-delete: помещает заявку в корзину. Обратимо в течение 7 дней через restoreApplication.
 * Доступно из любого статуса. Если заявка в архиве — выводит из архива и удаляет.
 */
export async function softDeleteApplication(appId: number): Promise<{ id: number; deleted_at: string }> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось удалить: ${res.status} ${await res.text()}`);
  return res.json();
}

/**
 * Восстановить заявку из корзины. Очищает deleted_at.
 */
export async function restoreApplication(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/restore`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось восстановить: ${res.status} ${await res.text()}`);
  return res.json();
}

/**
 * Удалить заявку НАВСЕГДА. Удаляет:
 * - файлы R2 (applicant_document, generated_document, uploaded_file)
 * - все связанные записи (family_member, timeline_event, translation, и т.д.)
 * - саму application
 * applicant НЕ удаляется (может быть привязан к другой заявке).
 */
export async function permanentDeleteApplication(appId: number): Promise<{ deleted: boolean; reference: string }> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/permanent`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Не удалось удалить навсегда: ${res.status} ${await res.text()}`);
  return res.json();
}


// ============================================================================
// Pack 28.2 Part B - NPD Pool admin endpoints
// ============================================================================

export type NpdPoolStats = {
  total: number;
  by_status: Record<string, number>;
  by_region_verified: Record<string, number>;
  last_refill_at: string | null;
  last_refill_region: string | null;
};

export type NpdRefillTask = {
  id: number;
  kind: string; // 'lazy_region' | 'global' | 'revalidate'
  status: string; // 'pending' | 'running' | 'done' | 'failed'
  region_code: string | null;

  progress_text: string | null;
  progress_current: number;
  progress_total: number;

  result_inn: string | null;
  result_region_code: string | null;

  verified_added: number;
  egrul_rejected: number;
  npd_rejected: number;
  revalidated_total: number;
  revalidated_invalidated: number;

  error: string | null;

  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

/**
 * Pack 28.2 Часть Б: получить статистику пула.
 */
export async function getNpdPoolStats(): Promise<NpdPoolStats> {
  const res = await fetch(`${API_BASE_URL}/api/admin/npd-pool/stats`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/**
 * Pack 28.2 Часть Б: получить статус задачи refill (для поллинга).
 */
export async function getNpdPoolTask(taskId: number): Promise<NpdRefillTask> {
  const res = await fetch(`${API_BASE_URL}/api/admin/npd-pool/tasks/${taskId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/**
 * Pack 28.2 Часть Б: запустить глобальный refill (ревалидация + добивка).
 * Возвращает task_id, фронт поллит /tasks/{id} до завершения.
 */
export async function refillPoolGlobal(payload?: {
  target_per_region?: number;
  revalidate_first?: boolean;
  regions?: string[];
}): Promise<NpdRefillTask> {
  const body = {
    target_per_region: payload?.target_per_region ?? 5,
    revalidate_first: payload?.revalidate_first ?? true,
    regions: payload?.regions ?? null,
  };
  const res = await fetch(`${API_BASE_URL}/api/admin/npd-pool/refill-all`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}


// ============================================================================
// Pack 28.5 — Уточнение реальной даты регистрации НПД через бинпоиск
// ============================================================================

export type RefineInnDateTask = {
  id: number;
  kind: string;
  status: string; // 'pending' | 'running' | 'done' | 'failed'

  progress_text: string | null;
  progress_current: number;
  progress_total: number;

  result_inn: string | null;
  result_registration_date: string | null; // ISO дата при status='done'

  error: string | null;

  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

/**
 * Pack 28.5: запустить бинпоиск даты регистрации НПД для applicant'а.
 * Возвращает task — поллить через getRefineTask каждые 5-10 сек до status='done'.
 */
export async function startRefineInnDate(
  applicantId: number,
): Promise<RefineInnDateTask> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/${applicantId}/refine-inn-date`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/**
 * Pack 28.5: получить статус refine-задачи (для поллинга).
 */
export async function getRefineTask(taskId: number): Promise<RefineInnDateTask> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/refine-tasks/${taskId}`,
    {
      headers: authHeaders(),
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}


// ============================================================================
// Pack 28.6 — Кнопка "+ Добавить" по региону в табе настроек
// ============================================================================

/**
 * Pack 28.6: запустить lazy refill для конкретного региона.
 * addTarget — сколько ДОПОЛНИТЕЛЬНО verified искать (поверх текущего).
 *
 * Возвращает task — поллить через getNpdPoolTask до status='done' или 'failed'.
 */
export async function refillRegion(
  regionCode: string,
  addTarget: number = 5,
): Promise<NpdRefillTask> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/npd-pool/region/${regionCode}/refill?add_target=${addTarget}`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}




// ============================================================================
// Pack 35.3 — Resolve passport_issuer_ru
// ============================================================================

export async function resolvePassportIssuerRu(
  issuer: string,
  nationality: string | null,
): Promise<{ resolved: string | null }> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/resolve-passport-issuer-ru`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        issuer: issuer || "",
        nationality: nationality || null,
      }),
    },
  );
  if (!res.ok) {
    throw new Error(`resolvePassportIssuerRu failed: ${res.status} ${await res.text()}`);
  }
  return res.json();
}
// ============================================================================
// Pack 37.0-D — AI Document Audit API
// ============================================================================
// Endpoints системы проверки пакета документов перед подачей.
// Backend: backend/app/api/audit.py (Pack 37.0-C).

export type AuditVerdict = "PASS" | "WARN" | "FAIL";

export type AuditCategory =
  | "identity"
  | "financial"
  | "company"
  | "education"
  | "spain_pack"
  | "formal";

export type AuditSeverity = "critical" | "warning" | "info";

export type AuditFindingStatus =
  | "open"
  | "accepted"
  | "dismissed"
  | "manually_fixed";

export interface AuditFinding {
  id: number;
  report_id: number;
  category: AuditCategory;
  severity: AuditSeverity;
  title: string;
  description: string | null;
  evidence: string | null;
  field_path: string | null;
  current_value: string | null;
  suggested_value: string | null;
  fix_action: string | null;
  fix_payload: Record<string, unknown>;
  can_auto_apply: boolean;
  status: AuditFindingStatus;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  sort_order: number;
}

export interface AuditReport {
  id: number;
  application_id: number;
  verdict: AuditVerdict;
  model_used: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: string | number | null;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  is_running: boolean;
  error: string | null;
  triggered_by: string | null;
  summary_counts: Record<string, number | string>;
}

export interface AuditReportWithFindings extends AuditReport {
  findings: AuditFinding[];
}

export interface AuditAcceptResponse {
  success: boolean;
  applied_changes: Record<string, [unknown, unknown]>;
  message: string | null;
}

export interface AuditRunResponse {
  report_id: number;
  status: string;
}

/**
 * Запустить новый прогон аудита. Возвращает report_id сразу;
 * сам аудит работает в фоне 30-90 сек.
 *
 * UI должен polling'ом проверять getAuditReport(report_id).is_running
 * каждые 2 секунды пока он true.
 */
export async function runAudit(
  applicationId: number,
  triggeredBy?: string,
): Promise<AuditRunResponse> {
  const res = await fetch(`${API_BASE_URL}/api/applications/${applicationId}/audit/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ triggered_by: triggeredBy ?? null }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to run audit: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * История прогонов аудита для заявки (последние сверху).
 */
export async function listAuditReports(applicationId: number): Promise<AuditReport[]> {
  const res = await fetch(`${API_BASE_URL}/api/applications/${applicationId}/audit/reports`);
  if (!res.ok) throw new Error(`Failed to list audit reports: ${res.status}`);
  return res.json();
}

/**
 * Получить полный отчёт с findings. Используется на странице /audit
 * и для polling при is_running=true.
 */
export async function getAuditReport(reportId: number): Promise<AuditReportWithFindings> {
  const res = await fetch(`${API_BASE_URL}/api/audit/reports/${reportId}`);
  if (!res.ok) throw new Error(`Failed to get audit report: ${res.status}`);
  return res.json();
}

/**
 * Применить fix_action для finding через whitelist handler.
 * Меняет только БД. Пакет 16 файлов НЕ перегенерируется автоматически
 * — менеджер пересобирает кнопкой «Сгенерировать пакет» когда готов.
 */
export async function acceptAuditFinding(findingId: number): Promise<AuditAcceptResponse> {
  const res = await fetch(`${API_BASE_URL}/api/audit/findings/${findingId}/accept`, {
    method: "POST",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to accept finding: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Отклонить finding (менеджер считает что это не проблема, либо решит руками).
 */
export async function dismissAuditFinding(
  findingId: number,
  note?: string,
): Promise<AuditFinding> {
  const res = await fetch(`${API_BASE_URL}/api/audit/findings/${findingId}/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: note ?? null }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to dismiss finding: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Ручной фикс — менеджер сам ввёл правильное значение для field_path.
 * field_path формат: "applicant.<field>" или "company.<field>" — проверяется
 * по whitelist в backend (fix_handlers.APPLICANT_WRITABLE_FIELDS / COMPANY_WRITABLE_FIELDS).
 */
export async function manualFixAuditFinding(
  findingId: number,
  fieldPath: string,
  newValue: string,
  note?: string,
): Promise<AuditFinding> {
  const res = await fetch(`${API_BASE_URL}/api/audit/findings/${findingId}/manual-fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      field_path: fieldPath,
      new_value: newValue,
      note: note ?? null,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to apply manual fix: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * URL для скачивания DOCX-отчёта. Используется как href в <a download>.
 * Pack 37.1.
 */
export function getAuditReportDocxUrl(reportId: number): string {
  return `${API_BASE_URL}/api/audit/reports/${reportId}/export.docx`;
}

// Русские лейблы для UI
export const AUDIT_CATEGORY_LABELS: Record<AuditCategory, string> = {
  identity: "Личные данные",
  financial: "Финансы",
  company: "Компания",
  education: "Образование",
  spain_pack: "Испанские документы",
  formal: "Комплектность пакета",
};

export const AUDIT_SEVERITY_LABELS: Record<AuditSeverity, string> = {
  critical: "Критично",
  warning: "Предупреждение",
  info: "Замечание",
};

export const AUDIT_VERDICT_LABELS: Record<AuditVerdict, string> = {
  PASS: "Готов к подаче",
  WARN: "Можно подавать с риском",
  FAIL: "Подавать нельзя",
};


// ============================================================================
// Pack 39.0 — Final Submission Audit (физическая проверка перед подачей)
// ============================================================================

export type FinalSubmissionDocCategory =
  | "passport_main"
  | "passport_other"
  | "apostille"
  | "contract"
  | "act"
  | "invoice"
  | "bank_statement"
  | "cv"
  | "npd_certificate"
  | "diploma"
  | "jurada_translation"
  | "mi_t_form"
  | "designacion"
  | "compromiso"
  | "declaracion"
  | "ex17"
  | "photo_3x4"
  | "medical_insurance"
  | "criminal_record"
  | "marriage_certificate"
  | "other";

export const FINAL_DOC_CATEGORY_LABELS: Record<FinalSubmissionDocCategory, string> = {
  passport_main: "Паспорт (главная)",
  passport_other: "Паспорт (доп. страницы)",
  apostille: "Апостиль",
  contract: "Договор",
  act: "Акт",
  invoice: "Счёт",
  bank_statement: "Банковская выписка",
  cv: "Резюме",
  npd_certificate: "Справка НПД",
  diploma: "Диплом",
  jurada_translation: "Перевод jurada",
  mi_t_form: "Форма MI-T",
  designacion: "Designación",
  compromiso: "Compromiso",
  declaracion: "Declaración",
  ex17: "Форма EX-17",
  photo_3x4: "Фото 3×4",
  medical_insurance: "Мед. страховка",
  criminal_record: "Справка о несудимости",
  marriage_certificate: "Свид. о браке",
  other: "Прочее",
};

export type FinalSubmissionDocument = {
  id: number;
  applicant_id: number;
  application_id: number | null;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  storage_key: string;
  original_storage_key: string | null;
  sha256: string;
  doc_category: FinalSubmissionDocCategory | null;
  doc_category_confidence: string | null; // backend возвращает Decimal как строку
  doc_category_source: "ai" | "manual" | string;
  extraction_method: "pypdf" | "vision" | "docx2txt" | "mixed" | string | null;
  page_count: number | null;
  is_active: boolean;
  previous_version_id: number | null;
  replaced_at: string | null;
  uploaded_at: string;
  uploaded_by: string | null;
  download_url: string | null;
  original_download_url: string | null;
};

export type FinalSubmissionUploadError = {
  filename: string;
  error: string;
};

export type FinalSubmissionUploadResponse = {
  uploaded: FinalSubmissionDocument[];
  skipped_duplicates: string[];
  errors: FinalSubmissionUploadError[];
};

/**
 * Загрузить N файлов для финальной проверки.
 * Поддерживает ZIP (распаковка на сервере), дедупликацию по SHA256.
 */
export async function uploadFinalSubmissionDocuments(
  applicantId: number,
  files: File[],
  applicationId?: number | null
): Promise<FinalSubmissionUploadResponse> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  if (applicationId != null) fd.append("application_id", String(applicationId));

  const res = await fetch(
    `${API_BASE_URL}/admin/applicants/${applicantId}/final-submission/upload`,
    {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Список документов клиента. include_history=false (default) — только активные.
 */
export async function listFinalSubmissionDocuments(
  applicantId: number,
  includeHistory: boolean = false
): Promise<FinalSubmissionDocument[]> {
  const url = new URL(
    `${API_BASE_URL}/admin/applicants/${applicantId}/final-submission/documents`
  );
  if (includeHistory) url.searchParams.set("include_history", "true");

  const res = await fetch(url.toString(), {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`List failed: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Заменить документ новым файлом (старый -> is_active=false с previous_version_id).
 * keep_category=true (default) копирует категорию со старого.
 */
export async function replaceFinalSubmissionDocument(
  applicantId: number,
  docId: number,
  newFile: File,
  keepCategory: boolean = true
): Promise<FinalSubmissionDocument> {
  const fd = new FormData();
  fd.append("file", newFile);
  fd.append("keep_category", keepCategory ? "true" : "false");

  const res = await fetch(
    `${API_BASE_URL}/admin/applicants/${applicantId}/final-submission/documents/${docId}/replace`,
    {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Replace failed: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Удалить документ. hard=false (default) — soft delete (is_active=false).
 * hard=true — permanent delete + удаление из R2.
 */
export async function deleteFinalSubmissionDocument(
  applicantId: number,
  docId: number,
  hard: boolean = false
): Promise<{ deleted: boolean; hard: boolean; doc_id: number }> {
  const url = new URL(
    `${API_BASE_URL}/admin/applicants/${applicantId}/final-submission/documents/${docId}`
  );
  if (hard) url.searchParams.set("hard", "true");

  const res = await fetch(url.toString(), {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Delete failed: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Ручная коррекция категории документа.
 * doc_category_source автоматически становится 'manual'.
 */
export async function updateFinalSubmissionDocumentCategory(
  applicantId: number,
  docId: number,
  category: FinalSubmissionDocCategory
): Promise<FinalSubmissionDocument> {
  const res = await fetch(
    `${API_BASE_URL}/admin/applicants/${applicantId}/final-submission/documents/${docId}/category`,
    {
      method: "PATCH",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ doc_category: category }),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Update category failed: ${res.status} ${text}`);
  }
  return res.json();
}


// ============================================================================
// Pack 39.0-E2 — Final Submission Audit Report API
// ============================================================================

export type FinalSubmissionVerdict = "PASS" | "WARN" | "FAIL";

export type FinalSubmissionCategory =
  | "A_identity"
  | "B_numeric"
  | "C_dates"
  | "D_company"
  | "E_translation"
  | "F_completeness"
  | "G_quality"
  | "H_stale";

export type FinalSubmissionSeverity = "critical" | "warning" | "info";

export type FinalSubmissionFindingStatus = "open" | "acknowledged" | "dismissed";

export const FINAL_AUDIT_CATEGORY_LABELS: Record<FinalSubmissionCategory, string> = {
  A_identity: "A · Личные данные",
  B_numeric: "B · Суммы и числа",
  C_dates: "C · Даты",
  D_company: "D · Реквизиты компании",
  E_translation: "E · Переводы jurada",
  F_completeness: "F · Комплектность",
  G_quality: "G · Качество сканов",
  H_stale: "H · Хвосты прошлых клиентов",
};

export const FINAL_AUDIT_VERDICT_LABELS: Record<FinalSubmissionVerdict, string> = {
  PASS: "Пакет готов к подаче",
  WARN: "Есть предупреждения",
  FAIL: "Найдены критические ошибки",
};

export type AffectedDocument = {
  document_id: number;
  filename: string;
  page: number | null;
};

export type FinalSubmissionFinding = {
  id: number;
  report_id: number;
  category: FinalSubmissionCategory;
  severity: FinalSubmissionSeverity;
  title: string;
  description: string | null;
  recommendation: string | null;
  affected_documents: AffectedDocument[];
  field_name: string | null;
  values_found: Record<string, string>;
  status: FinalSubmissionFindingStatus;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  sort_order: number;
  created_at?: string;
};

export type FinalSubmissionAuditReport = {
  id: number;
  application_id: number;
  applicant_id: number;
  verdict: FinalSubmissionVerdict;
  model_used: string | null;
  prompt_version: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  vision_pages: number | null;
  cost_usd: string | null;
  included_document_ids: number[] | null;
  document_categories_snapshot: Record<string, number> | null;
  is_running: boolean;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  triggered_by: string | null;
  summary_counts: {
    critical?: number;
    warning?: number;
    info?: number;
    total?: number;
    open?: number;
  } | null;
  inspector_summary: string | null;
};

export type FinalSubmissionAuditReportWithFindings = FinalSubmissionAuditReport & {
  findings: FinalSubmissionFinding[];
  documents: FinalSubmissionDocument[];
};

/**
 * Запустить финальный аудит. Создаёт report в БД (is_running=true)
 * + запускает BackgroundTask. Polling по getFinalSubmissionAuditReport.
 */
export async function runFinalSubmissionAudit(
  applicantId: number,
  applicationId: number
): Promise<{ report_id: number; status: string }> {
  const res = await fetch(
    `${API_BASE_URL}/admin/applicants/${applicantId}/final-submission/audit/run`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ application_id: applicationId }),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Run audit failed: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Список прогонов для клиента (свежие сверху).
 */
export async function listFinalSubmissionAuditReports(
  applicantId: number
): Promise<FinalSubmissionAuditReport[]> {
  const res = await fetch(
    `${API_BASE_URL}/admin/applicants/${applicantId}/final-submission/audit/reports`,
    { headers: authHeaders() }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`List reports failed: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Полный отчёт + findings + список документов которые в нём участвовали.
 */
export async function getFinalSubmissionAuditReport(
  reportId: number
): Promise<FinalSubmissionAuditReportWithFindings> {
  const res = await fetch(
    `${API_BASE_URL}/admin/final-submission/audit/reports/${reportId}`,
    { headers: authHeaders() }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Get report failed: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Пометить finding как acknowledged ("учёл, иду исправлять").
 */
export async function acknowledgeFinalSubmissionFinding(
  findingId: number,
  note?: string
): Promise<FinalSubmissionFinding> {
  const res = await fetch(
    `${API_BASE_URL}/admin/final-submission/findings/${findingId}/acknowledge`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ note: note || null }),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Acknowledge failed: ${res.status} ${text}`);
  }
  return res.json();
}

/**
 * Пометить finding как dismissed (false positive).
 */
export async function dismissFinalSubmissionFinding(
  findingId: number,
  note?: string
): Promise<FinalSubmissionFinding> {
  const res = await fetch(
    `${API_BASE_URL}/admin/final-submission/findings/${findingId}/dismiss`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ note: note || null }),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Dismiss failed: ${res.status} ${text}`);
  }
  return res.json();
}


// ============================================================================
// Pack 39.0-F — Final Submission DOCX export
// ============================================================================

/**
 * Возвращает URL для скачивания DOCX отчёта финальной проверки.
 * Используется с <a href={...} download>.
 * NB: токен в URL не передаётся, нужно использовать window.open или fetch.
 * Простейший вариант — fetch + Blob download.
 */
export function getFinalSubmissionAuditReportDocxUrl(reportId: number): string {
  return `${API_BASE_URL}/admin/final-submission/audit/reports/${reportId}/export.docx`;
}

/**
 * Скачать DOCX отчёт финальной проверки через fetch (нужен auth header).
 * Автоматически инициирует загрузку браузером.
 */
export async function downloadFinalSubmissionAuditReportDocx(reportId: number): Promise<void> {
  const url = getFinalSubmissionAuditReportDocxUrl(reportId);
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Download failed: ${res.status} ${text}`);
  }
  const blob = await res.blob();

  // Извлечь имя файла из Content-Disposition
  const cd = res.headers.get("Content-Disposition") || "";
  let filename = `final_check_report_${reportId}.docx`;
  const match = cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="?([^";]+)"?/i);
  if (match) {
    try {
      filename = decodeURIComponent(match[1]);
    } catch {
      filename = match[1];
    }
  }

  // Браузерный download
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(blobUrl);
}


// ============================================================
// Pack 43.0 — LLM-перевод полей Position на испанский
// ============================================================

/**
 * Pack 43.0: переводит русские tech_opinion поля Position на испанский.
 * НЕ сохраняет в БД. Возвращает dict с ES-полями.
 * Менеджер видит результат в форме, может править, потом сохраняет через updatePosition.
 *
 * Endpoint: POST /api/admin/positions/{id}/translate-spanish
 * Время: ~30-60 сек (один LLM-вызов Sonnet 4.6)
 */
export async function translatePositionToSpanish(positionId: number): Promise<{
  tech_opinion_description_es: string;
  tech_opinion_tools_es: Array<{ name: string; purpose: string }>;
  tech_opinion_steps_es: Array<{ title: string; body: string }>;
  tech_opinion_grounds_es: string[];
  tech_opinion_contract_clause_es: string;
  title_es?: string;
}> {
  const response = await fetch(
    `${API_BASE_URL}/api/admin/positions/${positionId}/translate-spanish`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
    }
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}


// ============================================================
// Pack 50.7-B — LLM-генерация цели командировки для Приказа Т-9
// ============================================================

/**
 * Pack 50.7-B: генерирует текст цели командировки для Приказа Т-9 по
 * сохранённым полям Position (title_ru, profile_description,
 * tech_opinion_description_ru, international_analog_ru).
 *
 * Возвращает {"business_trip_purpose": "<текст>"}. В БД НЕ пишет.
 * Менеджер видит текст в textarea, может править, сохраняет через updatePosition.
 *
 * Endpoint: POST /api/admin/positions/{id}/generate-business-trip-purpose
 */
export async function generateBusinessTripPurpose(positionId: number): Promise<{
  business_trip_purpose: string;
}> {
  const response = await fetch(
    `${API_BASE_URL}/api/admin/positions/${positionId}/generate-business-trip-purpose`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
    }
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}


// ============================================================
// Pack 45.0 — LLM-генерация русских полей Position
// ============================================================

export interface PositionGenerateInput {
  title_ru: string;
  title_es: string;
  primary_specialty_id: number;
  level: number;
  title_ru_genitive?: string | null;
  profile_description_existing?: string | null;
  salary_rub_default?: number | null;
}

export interface PositionGenerateResult {
  duties: string[];
  tags: string[];
  profile_description: string;
  tech_opinion_description_ru: string;
  tech_opinion_tools_ru: Array<{ name: string; purpose: string }>;
  tech_opinion_steps_ru: Array<{ title: string; body: string }>;
  tech_opinion_grounds_ru: string[];
  tech_opinion_contract_clause_ru: string;
  international_analog_ru: string;
}

/**
 * Pack 45.0: сгенерировать 9 русских полей Position через LLM.
 * НЕ сохраняет в БД. Менеджер видит результат в форме, может править, потом сохраняет.
 *
 * Endpoint: POST /api/admin/positions/generate-russian
 * Время: ~30-50 сек (один LLM-вызов Sonnet 4.6)
 */
export async function generatePositionRussian(
  input: PositionGenerateInput
): Promise<PositionGenerateResult> {
  const response = await fetch(
    `${API_BASE_URL}/api/admin/positions/generate-russian`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify(input),
    }
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

// ============================================================
// Pack 46.0 — Диплом для хурадо
// ============================================================

export interface DiplomaSigner {
  name: string;
  position?: string | null;
}

export interface DiplomaFieldsResult {
  diploma_number: string;
  registration_number: string;
  protocol_number: string;
  protocol_date: string; // ISO YYYY-MM-DD
  issue_date: string; // ISO YYYY-MM-DD
  signers: DiplomaSigner[];
}

/**
 * Pack 46.0: сгенерировать 6 полей диплома через LLM.
 * Возвращает dict — фронт сам сохраняет через PATCH applicant.education.
 * Endpoint: POST /api/admin/applicants/{id}/education/{idx}/generate-fields
 */
export async function generateDiplomaFields(
  applicantId: number,
  idx: number
): Promise<DiplomaFieldsResult> {
  const response = await fetch(
    `${API_BASE_URL}/api/admin/applicants/${applicantId}/education/${idx}/generate-fields`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
    }
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Pack 46.0: URL для PDF-диплома (открывается через window.open в новой вкладке).
 * Endpoint: GET /api/admin/applicants/{id}/education/{idx}/diploma.pdf
 *
 * Поскольку PDF идёт inline и нужен Authorization header, открываем через blob:
 */
export async function openDiplomaPdf(
  applicantId: number,
  idx: number
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/admin/applicants/${applicantId}/education/${idx}/diploma.pdf`,
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${getToken()}`,
      },
    }
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  // URL отзываем через минуту — даём времени браузеру прогрузить
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}


// ============================================================================
// Pack 50.1-F2 — генерация СНИЛС
// ============================================================================
//
// Возвращает правдоподобный СНИЛС с правильной контрольной суммой по алгоритму ПФР.
// Бэк генерирует — фронт только подставляет в поле.

export async function generateSnils(): Promise<string> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applicants/generate-snils`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
    },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  const data = await res.json();
  return data.snils as string;
}


// ============================================================================
// Pack 50.41 — состояние «просмотрено» документов (сетки + сканы клиента)
// ============================================================================
export async function getDocViewState(applicationId: number): Promise<string[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/doc-view-state`,
    { headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`doc-view-state ${res.status}`);
  const data = await res.json();
  return (data.seen as string[]) || [];
}

export async function markDocsSeen(applicationId: number, keys: string[]): Promise<void> {
  if (!keys.length) return;
  await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/doc-view-state/seen`,
    { method: "POST", headers: jsonHeaders(), body: JSON.stringify({ keys }) },
  );
}

export async function markDocsUnseen(applicationId: number, keys: string[]): Promise<void> {
  if (!keys.length) return;
  await fetch(
    `${API_BASE_URL}/api/admin/applications/${applicationId}/doc-view-state/unseen`,
    { method: "POST", headers: jsonHeaders(), body: JSON.stringify({ keys }) },
  );
}
