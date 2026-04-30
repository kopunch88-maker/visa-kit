import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen flex items-center justify-center p-8 bg-tertiary">
      <div className="max-w-2xl text-center space-y-6">
        <h1 className="text-4xl font-bold text-primary">
          Visa Kit
        </h1>
        <p className="text-lg text-secondary">
          Автоматизация подачи заявок на испанскую визу цифрового кочевника
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center mt-8">
          <Link
            href="/admin/login"
            className="px-6 py-3 rounded-md text-white font-medium transition-colors"
            style={{ background: "var(--color-accent)" }}
          >
            Войти как менеджер →
          </Link>
        </div>

        <div
          className="bg-primary border rounded-lg p-6 text-left mt-8"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderWidth: 0.5,
          }}
        >
          <h2 className="font-semibold text-primary mb-2">Для клиентов</h2>
          <p className="text-sm text-secondary mb-3">
            Если вы клиент агентства, перейдите по индивидуальной ссылке
            которую вам отправил менеджер. Ссылка имеет вид:
          </p>
          <code
            className="block p-3 rounded text-sm font-mono text-tertiary border"
            style={{
              background: "var(--color-bg-secondary)",
              borderColor: "var(--color-border-tertiary)",
              borderWidth: 0.5,
            }}
          >
            /client/[ваш_токен]
          </code>
        </div>
      </div>
    </main>
  );
}
