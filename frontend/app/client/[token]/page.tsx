import { ClientWizard } from "@/components/wizard/ClientWizard";

interface PageProps {
  params: Promise<{ token: string }>;
}

export default async function ClientPage({ params }: PageProps) {
  const { token } = await params;
  return <ClientWizard token={token} />;
}
