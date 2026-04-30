"use client";

import { useEffect, use } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

interface PageProps {
  params: Promise<{ id: string }>;
}

/**
 * Pack 8.5: страница деталей переехала в правую панель главной страницы /admin.
 * Эта страница оставлена как редирект — старые ссылки не сломаются.
 */
export default function LegacyApplicationDetailPage({ params }: PageProps) {
  const router = useRouter();
  const { id } = use(params);

  useEffect(() => {
    router.replace(`/admin?id=${id}`);
  }, [id, router]);

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <Loader2 className="w-6 h-6 animate-spin text-tertiary" />
    </div>
  );
}
