"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { LogOut, Moon, Sun } from "lucide-react";
import { getToken, getCurrentUser, clearAuth } from "@/lib/api";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [user, setUser] = useState<{ email: string; name?: string } | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    document.documentElement.dataset.theme = theme === "dark" ? "dark" : "";
  }, [theme]);

  useEffect(() => {
    // Проверяем авторизацию (кроме страницы логина)
    if (pathname === "/admin/login") {
      setChecking(false);
      return;
    }
    const token = getToken();
    if (!token) {
      router.replace("/admin/login");
      return;
    }
    setUser(getCurrentUser());
    setChecking(false);
  }, [pathname, router]);

  function handleLogout() {
    clearAuth();
    router.replace("/admin/login");
  }

  if (checking) {
    return (
      <div className="min-h-screen bg-tertiary flex items-center justify-center">
        <div className="text-secondary">Загрузка...</div>
      </div>
    );
  }

  // На странице логина — без шапки
  if (pathname === "/admin/login") {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-tertiary">
      <header
        className="bg-primary border-b sticky top-0 z-10"
        style={{
          borderColor: "var(--color-border-tertiary)",
          borderBottomWidth: 0.5,
        }}
      >
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-semibold"
              style={{ background: "var(--color-accent)" }}
            >
              V
            </div>
            <div>
              <div className="text-sm font-semibold text-primary">
                Visa kit · Admin
              </div>
              <div className="text-xs text-tertiary">
                {user?.email || "manager"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="text-sm px-3 py-1.5 rounded-md border text-secondary hover:bg-secondary transition-colors flex items-center gap-2"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
              title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            >
              {theme === "dark" ? (
                <Sun className="w-4 h-4" />
              ) : (
                <Moon className="w-4 h-4" />
              )}
            </button>

            <button
              onClick={handleLogout}
              className="text-sm px-3 py-1.5 rounded-md border text-secondary hover:bg-secondary transition-colors flex items-center gap-2"
              style={{
                borderColor: "var(--color-border-tertiary)",
                borderWidth: 0.5,
              }}
            >
              <LogOut className="w-4 h-4" />
              Выйти
            </button>
          </div>
        </div>
      </header>

      <main>{children}</main>
    </div>
  );
}
