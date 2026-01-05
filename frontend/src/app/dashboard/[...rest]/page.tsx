// Server Component
export const dynamic = "force-dynamic";
export const revalidate = 0;

import { redirect } from "next/navigation";

export default function DashboardCatchAllPage({
  searchParams,
}: {
  searchParams?: { chat_id?: string };
}) {
  const requestedChatId = searchParams?.chat_id?.trim();
  const target = requestedChatId
    ? `/dashboard?chat_id=${encodeURIComponent(requestedChatId)}`
    : "/dashboard";

  redirect(target);
}
