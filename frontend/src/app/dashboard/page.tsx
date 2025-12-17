// Server Component
export const dynamic = "force-dynamic";
export const revalidate = 0;

import { redirect } from "next/navigation";

export default function DashboardPage({
  searchParams,
}: {
  searchParams?: { chat_id?: string };
}) {
  const requestedChatId = searchParams?.chat_id?.trim();
  const target = requestedChatId
    ? `/chat/${encodeURIComponent(requestedChatId)}`
    : "/chat";

  redirect(target);
}
