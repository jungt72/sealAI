import CaseScreen from "@/components/dashboard/CaseScreen";

export default async function DashboardNewPage({
  searchParams,
}: {
  searchParams: Promise<{ goal?: string; request_type?: string }>;
}) {
  const { goal, request_type } = await searchParams;
  return <CaseScreen initialGoal={goal} initialRequestType={request_type} />;
}
