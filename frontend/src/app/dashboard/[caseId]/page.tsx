import CaseScreen from "@/components/dashboard/CaseScreen";

export default async function DashboardCasePage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;

  return <CaseScreen caseId={caseId} />;
}
