"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Loader2, AlertCircle } from "lucide-react";
import { login, saveToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!email || !password) {
      setError("Введите email и пароль");
      return;
    }

    setLoading(true);
    try {
      const result = await login(email, password);
      saveToken(result.access_token, {
        email: result.user?.email || email,
        name: result.user?.name,
      });
      router.replace("/admin");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div
        className="w-full max-w-sm bg-primary rounded-xl border p-6"
        style={{ borderColor: "var(--color-border-tertiary)", borderWidth: 0.5 }}
      >
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-primary">Visa kit · Admin</h1>
          <p className="text-sm text-tertiary mt-1">Вход для менеджеров</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              Email
            </label>
            <input
              type="email"
              autoComplete="username"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="manager@visa-kit.local"
              className="w-full px-3 py-2 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
              style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              Пароль
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-md border bg-primary text-primary placeholder:text-tertiary focus:outline-none focus:ring-2"
              style={{ borderColor: "var(--color-border-secondary)", borderWidth: 0.5 }}
            />
          </div>

          {error && (
            <div className="bg-danger text-danger text-sm p-3 rounded-md flex items-start gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>{error}</div>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full px-4 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 flex items-center justify-center gap-2"
            style={{ background: "var(--color-accent)" }}
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Войти
          </button>
        </form>

        <p className="text-xs text-tertiary mt-4 text-center">
          Если забыл пароль — обратись к администратору
        </p>
      </div>
    </div>
  );
}
