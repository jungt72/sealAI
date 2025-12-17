// Server Component
export const dynamic = "force-dynamic";
export const revalidate = 0;

import { redirect } from "next/navigation";

export default function DashboardCatchAllPage({
  searchParams,
}: {
  searchParams?: { chat_id?: string };
}) {
  if (searchParams?.chat_id) {
    const chatId = encodeURIComponent(searchParams.chat_id);
    redirect(`/chat/${chatId}`);
  }

  redirect("/chat");
}
