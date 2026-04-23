"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import {
  Activity,
  Bell,
  Database,
  HelpCircle,
  LayoutDashboard,
  Menu,
  Plus,
  Search,
  Settings,
} from "lucide-react";

import LogoutButton from "@/components/dashboard/LogoutButton";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard/new", icon: LayoutDashboard, label: "Analyse-Workbench" },
  { href: "/rag", icon: Database, label: "Mediendatenbank" },
];

function greetingForNow(date = new Date()) {
  const hour = date.getHours();
  if (hour < 11) return "Guten Morgen";
  if (hour < 17) return "Guten Tag";
  return "Guten Abend";
}

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
  const [isExpanded, setIsExpanded] = useState(true);

  const userName = firstNameFromSession(session?.user?.name, session?.user?.email);
  const greeting = useMemo(() => greetingForNow(), []);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#eef2f6] font-sans text-foreground">
      <aside
        className={cn(
          "relative z-20 hidden h-full flex-col border-r border-slate-200 bg-[#f8fafc] transition-all duration-300 ease-in-out lg:flex",
          isExpanded ? "w-[272px]" : "w-[72px]",
        )}
      >
        <div className="flex h-16 items-center gap-3 px-4">
          <button
            type="button"
            aria-label="Navigation umschalten"
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
          >
            <Menu size={20} />
          </button>
          <div
            className={cn(
              "flex min-w-0 items-center gap-3 overflow-hidden transition-opacity duration-300",
              isExpanded ? "opacity-100" : "w-0 opacity-0",
            )}
          >
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-seal-blue text-sm font-bold text-white">
              S
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-slate-950">SeaLAI</div>
              <div className="truncate text-[11px] font-medium uppercase tracking-widest text-slate-500">
                PTFE-RWDR Workbench
              </div>
            </div>
          </div>
        </div>

        <div className="px-3 py-3">
          <Link
            href="/dashboard/new"
            className={cn(
              "flex h-11 items-center gap-3 rounded-lg bg-seal-blue text-white shadow-sm shadow-slate-200 transition-colors hover:bg-[#0a2e68]",
              isExpanded ? "px-3" : "justify-center px-0",
            )}
          >
            <Plus size={19} className="shrink-0" />
            {isExpanded && <span className="truncate text-sm font-semibold">Neue Analyse</span>}
          </Link>
        </div>

        <nav className="custom-scrollbar flex-1 overflow-y-auto px-3 py-2">
          {isExpanded && (
            <div className="px-3 pb-2 text-[11px] font-bold uppercase tracking-widest text-slate-400">
              Arbeitsbereiche
            </div>
          )}
          <div className="space-y-1">
            {NAV_ITEMS.map((item) => {
              const isActive =
                item.href === "/dashboard/new"
                  ? pathname.startsWith("/dashboard")
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-[#e6eefc] text-seal-blue"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                    !isExpanded && "justify-center px-0",
                  )}
                >
                  <item.icon size={18} className="shrink-0" />
                  {isExpanded && <span className="truncate">{item.label}</span>}
                </Link>
              );
            })}
          </div>
        </nav>

        <div className="space-y-1 border-t border-slate-200 px-3 py-4">
          {[
            { icon: HelpCircle, label: "Hilfe" },
            { icon: Activity, label: "Aktivität" },
            { icon: Settings, label: "Einstellungen" },
          ].map((item) => (
            <button
              key={item.label}
              type="button"
              title={item.label}
              className={cn(
                "flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-950",
                !isExpanded && "justify-center px-0",
              )}
            >
              <item.icon size={18} className="shrink-0" />
              {isExpanded && <span className="truncate">{item.label}</span>}
            </button>
          ))}
          {isExpanded && (
            <div className="pt-2">
              <LogoutButton />
            </div>
          )}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6">
          <div className="min-w-0">
            <p className="truncate text-lg font-semibold tracking-tight text-slate-950">
              {greeting} {userName}, schön, dass du da bist.
            </p>
            <p className="mt-0.5 truncate text-sm text-slate-500">
              Technische Klärung, Live-Antwort und Fallstatus in einem Arbeitsbereich.
            </p>
          </div>
          <div className="ml-4 flex shrink-0 items-center gap-2">
            <button
              type="button"
              title="Suchen"
              className="hidden h-10 w-10 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-950 sm:flex"
            >
              <Search size={18} />
            </button>
            <button
              type="button"
              title="Benachrichtigungen"
              className="hidden h-10 w-10 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-950 sm:flex"
            >
              <Bell size={18} />
            </button>
            <Link
              href="/dashboard/new"
              title="Neue Analyse"
              className="flex h-10 w-10 items-center justify-center rounded-lg bg-seal-blue text-white transition-colors hover:bg-[#0a2e68] lg:hidden"
            >
              <Plus size={18} />
            </Link>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-hidden bg-[#f5f7fb] p-2 sm:p-3">
          <div className="h-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
