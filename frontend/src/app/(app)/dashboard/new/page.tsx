import CaseScreen from "@/components/dashboard/CaseScreen";

export default async function DashboardNewPage({
  searchParams,
}: {
  searchParams: Promise<{ request_type?: string }>;
}) {
  const { request_type } = await searchParams;
  return <CaseScreen initialRequestType={request_type} />;
}
