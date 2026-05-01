// =============================================================================
// PACK 13.1.3 — изменения в api.ts
// =============================================================================
//
// Замени:
// 1. Тип ClientDocument (добавлены 3 поля)
// 2. Функцию uploadDocument (теперь принимает опциональный original)

// === ИЗМЕНЕНИЕ 1: ClientDocument ===

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
  // Pack 13.1.3: оригинальный PDF (если был)
  has_original?: boolean;
  original_download_url?: string;
  original_file_name?: string;
};


// === ИЗМЕНЕНИЕ 2: uploadDocument ===

/**
 * Pack 13.1.3: теперь принимает опциональный originalFile
 * (например, PDF — когда image это конвертированная страница из PDF).
 */
export async function uploadDocument(
  token: string,
  docType: ClientDocumentType,
  file: File,                   // основной файл (всегда image: jpg/png/webp)
  originalFile?: File | null,   // опциональный оригинал (PDF/HEIC)
): Promise<ClientDocument> {
  const formData = new FormData();
  formData.append("doc_type", docType);
  formData.append("file", file);
  if (originalFile) {
    formData.append("original_file", originalFile);
  }

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
