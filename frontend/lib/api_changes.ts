// =============================================================================
// PACK 13.1 — изменения в lib/api.ts
// =============================================================================
//
// 1. Замени существующую функцию recognizeDocument на новую (с лучшей обработкой ошибок)
// 2. Добавь новую функцию applyDocumentsToApplicant
// 3. Тип ClientDocument уже корректный, не меняй
//
// Найди в файле блок "Pack 13.0b: Client documents" и замени функцию recognizeDocument:

/**
 * Запустить OCR для документа.
 * Возвращает обновлённый документ с parsed_data или с ocr_error.
 *
 * Endpoint может вернуть статус "ocr_failed" — это НЕ ошибка функции,
 * проверяй doc.status в результате.
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


// Добавь новую функцию ниже recognizeDocument:

/**
 * Применить распознанные данные из всех OCR-документов к анкете клиента.
 *
 * Только пустые поля заполняются — уже введённые клиентом данные не перезаписываются.
 *
 * Возвращает:
 *   - applied_fields: какие поля были заполнены
 *   - applicant: обновлённый профиль клиента (можно сразу подставить в state)
 */
export async function applyDocumentsToApplicant(
  token: string,
): Promise<{
  applied_fields: string[];
  applicant?: ApplicantResponse;
  message?: string;
}> {
  const res = await fetch(
    `${API_BASE_URL}/api/client/${token}/documents/apply-to-applicant`,
    { method: "POST" },
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
