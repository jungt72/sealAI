import type { ReactNode } from "react";
import ConversationSidebar from "@/components/ConversationSidebar";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function ChatLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh w-full overflow-hidden bg-white">
      <div className="shrink-0">
        <ConversationSidebar />
      </div>

      <main className="relative flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
