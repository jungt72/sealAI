"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import {
  Bell,
  Database,
  MessageSquareText,
  Clock3,
  Bookmark,
  FileText,
  Plus,
  Settings,
} from "lucide-react";

import LogoutButton from "@/components/dashboard/LogoutButton";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard/new", icon: MessageSquareText, label: "Chat" },
  { href: "/rag", icon: Database, label: "Wissen" },
  { href: "/dashboard/new", icon: Clock3, label: "Verlauf" },
  { href: "/dashboard/new", icon: Bookmark, label: "Merkliste" },
  { href: "/dashboard/new", icon: FileText, label: "Dokumente" },
];

function firstNameFromSession(name?: string | null, email?: string | null) {
  const source = (name || email || "Thorsten").trim();
  const first = source.split(/[\s@]/)[0];
  return first || "Thorsten";
}

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { data: session } = useSession();

  const userName = firstNameFromSession(session?.user?.name, session?.user?.email);
  const greeting = "Guten Tag";

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#F5F7FB] font-sans text-foreground">
      <aside className="hidden h-full w-[72px] shrink-0 flex-col border-r border-[#E7ECF3] bg-white lg:flex">
        <div className="flex h-[72px] items-center justify-center border-b border-[#E7ECF3]">
          <div className="grid h-11 w-11 place-items-center rounded-full bg-[#0B5BD3] text-base font-semibold text-white shadow-[0_10px_30px_rgba(11,91,211,0.22)]">
            S
          </div>
        </div>

        <nav className="flex flex-1 flex-col items-center gap-3 px-3 py-6">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/dashboard/new"
                ? pathname.startsWith("/dashboard")
                : pathname.startsWith(item.href);
            return (
              <Link
                key={`${item.label}-${item.href}`}
                href={item.href}
                title={item.label}
                className={cn(
                  "flex h-11 w-11 items-center justify-center rounded-[14px] border transition-colors",
                  isActive
                    ? "border-[#CFE0FF] bg-[#EEF4FF] text-[#0B5BD3]"
                    : "border-transparent text-[#6B7280] hover:border-[#E7ECF3] hover:bg-[#F8FAFD] hover:text-[#111827]",
                )}
              >
                <item.icon size={19} />
              </Link>
            );
          })}
        </nav>

        <div className="flex flex-col items-center gap-3 border-t border-[#E7ECF3] px-3 py-4">
          <button
            type="button"
            title="Einstellungen"
            className="flex h-11 w-11 items-center justify-center rounded-[14px] border border-transparent text-[#6B7280] transition-colors hover:border-[#E7ECF3] hover:bg-[#F8FAFD] hover:text-[#111827]"
          >
            <Settings size={18} />
          </button>
          <div className="w-full px-1">
            <LogoutButton />
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-[#E7ECF3] bg-white px-5 sm:px-7">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <div className="text-[18px] font-semibold tracking-tight text-[#0B5BD3]">SeaLAI</div>
              <div className="h-5 w-px bg-[#D7DDE8]" />
              <div className="text-[16px] font-medium text-[#374151]">Knowledge Modus</div>
            </div>
            <div className="mt-1 truncate text-[12px] text-[#6B7280]">
              {greeting} {userName}, schoen, dass du da bist.
            </div>
          </div>
          <div className="ml-4 flex shrink-0 items-center gap-2 sm:gap-3">
            <div className="hidden text-sm text-[#6B7280] md:block">
              Suche-ID: <span className="font-semibold text-[#0B5BD3]">COMP-2025-000245</span>
            </div>
            <span className="inline-flex items-center rounded-full border border-[#D8EEDB] bg-[#EEF9F0] px-3 py-1 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#2F8F46]">
              Governed
            </span>
            <button
              type="button"
              title="Benachrichtigungen"
              className="hidden h-10 w-10 items-center justify-center rounded-full border border-[#E7ECF3] text-[#6B7280] transition-colors hover:bg-[#F8FAFD] hover:text-[#111827] md:flex"
            >
              <Bell size={18} />
            </button>
            <div className="flex items-center gap-3 rounded-full border border-[#E7ECF3] bg-white px-2.5 py-1.5">
              <div className="grid h-9 w-9 place-items-center rounded-full border border-[#D7DDE8] bg-[#F8FAFD] text-sm font-semibold text-[#6B7280]">
                {userName.slice(0, 2).toUpperCase()}
              </div>
              <div className="hidden text-left md:block">
                <div className="text-sm font-medium text-[#111827]">{userName} Mustermann</div>
                <div className="text-[12px] text-[#6B7280]">Ingenieur</div>
              </div>
            </div>
            <Link
              href="/dashboard/new"
              title="Neue Analyse"
              className="flex h-10 w-10 items-center justify-center rounded-full bg-[#0B5BD3] text-white transition-colors hover:bg-[#0A4FB9] lg:hidden"
            >
              <Plus size={18} />
            </Link>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-hidden bg-[#F5F7FB]">{children}</div>
      </main>
    </div>
  );
}
