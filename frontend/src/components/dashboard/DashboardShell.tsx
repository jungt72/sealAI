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

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#EEF2F7] font-sans text-foreground">
      <aside
        className={cn(
          "hidden h-full shrink-0 flex-col border-r border-[#D6E4F6] bg-[#EAF2FF] transition-[width] duration-200 ease-out md:flex",
          isNavExpanded ? "w-[244px]" : "w-[72px]",
        )}
      >
        <div
          className={cn(
            "flex items-center border-b border-[#D6E4F6] px-3",
            isNavExpanded ? "h-[72px] justify-between" : "h-[126px] flex-col justify-start gap-3 py-3",
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
          ) : (
            <button
              type="button"
              aria-label="Navigation erweitern"
              aria-expanded={isNavExpanded}
              title="Navigation erweitern"
              onClick={() => setIsNavExpanded(true)}
              className="flex h-11 w-11 items-center justify-center rounded-[14px] border border-[#BFD6F6] bg-[#F7FBFF] text-[#5F7FA8] transition-colors hover:border-[#9DBDED] hover:bg-white hover:text-[#0B5BD3]"
            >
              <PanelLeftOpen size={18} />
            </button>
          )}
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
            "flex flex-col gap-3 border-t border-[#D6E4F6] px-3 py-4",
            isNavExpanded ? "items-stretch" : "items-center",
          )}
        >
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
          <div className="flex min-w-0 items-center">
            <div className={cn("items-center gap-3 leading-none", isNavExpanded ? "hidden" : "flex")}>
              <div className="text-[21px] font-semibold tracking-[0.18em] text-[#1F2937]">SEALING</div>
              <div className="h-5 w-px bg-[#D7DDE8]" />
              <div className="text-[14px] font-medium tracking-[0.12em] text-[#374151]">INTELLIGENCE</div>
            </div>
          </div>
          <div className="ml-4 flex shrink-0 items-center gap-2 sm:gap-3">
            <div className="hidden text-sm text-[#6B7280] md:block">
              Vorgang: <span className="font-semibold text-[#0B5BD3]">COMP-2025-000245</span>
            </div>
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
        <div className="min-h-0 flex-1 overflow-hidden bg-[#EEF2F7]">{children}</div>
      </main>
    </div>
  );
}
