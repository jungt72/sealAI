import type { ReactNode } from "react";
import ConversationSidebar from "@/components/ConversationSidebar";
import DashboardShell from "./DashboardShell";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh w-full overflow-hidden bg-white">
      <div className="shrink-0">
        <ConversationSidebar />
      </div>

      <div className="min-w-0 flex-1 overflow-hidden">
        <DashboardShell>{children}</DashboardShell>
      </div>
    </div>
  );
}
