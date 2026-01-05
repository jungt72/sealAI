import type { ReactNode } from "react";
import ConversationSidebar from "@/components/ConversationSidebar";
import DashboardShell from "./DashboardShell";
import DashboardProviders from "./DashboardProviders";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <DashboardProviders>
      <div className="flex h-dvh w-full overflow-hidden bg-white">
        <div className="shrink-0">
          <ConversationSidebar />
        </div>

        <div className="min-w-0 flex-1 min-h-0 overflow-hidden">
          <DashboardShell>{children}</DashboardShell>
        </div>
      </div>
    </DashboardProviders>
  );
}
