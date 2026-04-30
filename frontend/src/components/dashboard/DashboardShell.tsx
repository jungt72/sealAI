"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Bell,
  Database,
  MessageSquareText,
  Clock3,
  Bookmark,
  FileText,
  PanelLeftClose,
  PanelLeftOpen,
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

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [isNavExpanded, setIsNavExpanded] = useState(false);

  const userName = "Thorsten";
  const greeting = "Guten Tag";

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#F5F7FB] font-sans text-foreground">
      <aside
        className={cn(
          "hidden h-full shrink-0 flex-col border-r border-[#E7ECF3] bg-white transition-[width] duration-200 ease-out md:flex",
          isNavExpanded ? "w-[244px]" : "w-[72px]",
        )}
      >
        <div
          className={cn(
            "flex h-[72px] items-center border-b border-[#E7ECF3] px-3",
            isNavExpanded ? "justify-between" : "justify-center",
          )}
        >
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-[14px] border border-[#E7ECF3] bg-white shadow-[0_10px_26px_rgba(4,30,73,0.12)]">
              <Image
                src="/images/logo/sealai-symbol.png"
                alt="SeaLAI"
                width={36}
                height={36}
                className="object-contain"
                priority
              />
            </div>
            {isNavExpanded ? (
              <div className="min-w-0 animate-in fade-in duration-200">
                <div className="truncate text-[17px] font-semibold tracking-[0.12em] text-[#0F172A]">SEALING</div>
                <div className="truncate text-[10px] font-medium tracking-[0.16em] text-[#6B7280]">INTELLIGENCE</div>
              </div>
            ) : null}
          </div>
          {isNavExpanded ? (
            <button
              type="button"
              aria-label="Navigation einklappen"
              aria-expanded={isNavExpanded}
              title="Navigation einklappen"
              onClick={() => setIsNavExpanded(false)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-transparent text-[#6B7280] transition-colors hover:border-[#E7ECF3] hover:bg-[#F8FAFD] hover:text-[#111827]"
            >
              <PanelLeftClose size={18} />
            </button>
          ) : null}
        </div>

        <nav
          className={cn(
            "flex flex-1 flex-col gap-3 px-3 py-6",
            isNavExpanded ? "items-stretch" : "items-center",
          )}
        >
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
                  "flex h-11 items-center rounded-[14px] border transition-colors",
                  isNavExpanded ? "w-full justify-start gap-3 px-3" : "w-11 justify-center",
                  isActive
                    ? "border-[#CFE0FF] bg-[#EEF4FF] text-[#0B5BD3]"
                    : "border-transparent text-[#6B7280] hover:border-[#E7ECF3] hover:bg-[#F8FAFD] hover:text-[#111827]",
                )}
              >
                <item.icon size={19} className="shrink-0" />
                {isNavExpanded ? (
                  <span className="min-w-0 truncate text-[13px] font-medium">{item.label}</span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div
          className={cn(
            "flex flex-col gap-3 border-t border-[#E7ECF3] px-3 py-4",
            isNavExpanded ? "items-stretch" : "items-center",
          )}
        >
          {!isNavExpanded ? (
            <button
              type="button"
              aria-label="Navigation erweitern"
              aria-expanded={isNavExpanded}
              title="Navigation erweitern"
              onClick={() => setIsNavExpanded(true)}
              className="flex h-11 w-11 items-center justify-center rounded-[14px] border border-transparent text-[#6B7280] transition-colors hover:border-[#E7ECF3] hover:bg-[#F8FAFD] hover:text-[#111827]"
            >
              <PanelLeftOpen size={18} />
            </button>
          ) : null}
          <button
            type="button"
            title="Einstellungen"
            className={cn(
              "flex h-11 items-center rounded-[14px] border border-transparent text-[#6B7280] transition-colors hover:border-[#E7ECF3] hover:bg-[#F8FAFD] hover:text-[#111827]",
              isNavExpanded ? "w-full justify-start gap-3 px-3" : "w-11 justify-center",
            )}
          >
            <Settings size={18} className="shrink-0" />
            {isNavExpanded ? <span className="text-[13px] font-medium">Einstellungen</span> : null}
          </button>
          <div className={cn("w-full", isNavExpanded ? "" : "px-1")}>
            <LogoutButton showLabel={isNavExpanded} />
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-transparent bg-transparent px-5 sm:px-7">
          <div className="min-w-0">
            <div className={cn("items-center gap-3", isNavExpanded ? "hidden" : "flex")}>
              <div className="text-[20px] font-semibold tracking-[0.14em] text-[#1F2937]">SEALING</div>
              <div className="h-5 w-px bg-[#D7DDE8]" />
              <div className="text-[15px] font-medium tracking-[0.11em] text-[#374151]">INTELLIGENCE</div>
            </div>
            <div className={cn("truncate text-[12px] text-[#6B7280]", isNavExpanded ? "mt-0" : "mt-1")}>
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
