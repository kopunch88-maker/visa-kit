import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Visa Kit — Анкета клиента",
  description: "Заполнение анкеты для подачи заявки на визу цифрового кочевника",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
<html lang="ru" suppressHydrationWarning>
  <body suppressHydrationWarning>{children}</body>
</html>
  );
}
