/**
 * Pack 11 — обновление функции login в lib/api.ts
 *
 * НАЙДИТЕ в файле frontend/lib/api.ts существующую функцию:
 *
 *   export async function login(
 *     email: string,
 *     password?: string,
 *   ): Promise<{ access_token: string; token_type: string }> {
 *     const body: any = { email };
 *     if (password) body.password = password;
 *     ...
 *   }
 *
 * ЗАМЕНИТЕ на эту версию (теперь password обязательный + возвращает user):
 */

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
