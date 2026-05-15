"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import {
  Activity,
  BarChart3,
  Bell,
  Database,
  ChevronRight,
  FileText,
  HelpCircle,
  Menu,
  PencilLine,
  Plus,
  Search,
  Settings,
  Sparkles,
  Target,
} from "lucide-react";

import LogoutButton from "@/components/dashboard/LogoutButton";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard/new", icon: PencilLine, label: "Neuer Chat" },
  { href: "/rag", icon: Sparkles, label: "Meine Inhalte" },
];

const WORKSPACE_ITEMS = [
  { href: "/dashboard/seo", icon: BarChart3, label: "SEO" },
  { href: "/goal", icon: Target, label: "Goal" },
  { href: "/rag", icon: Database, label: "SealingPedia" },
  { href: "/dashboard/new", icon: FileText, label: "Dokumente" },
];

type CaseHistoryItem = {
  id: string;
  title: string;
  subtitle: string;
  updatedAt: string | null;
};

function identityFromSession(name?: string | null, email?: string | null) {
  const source = (name || email || "Nutzer").trim();
  const displayName = source || "Nutzer";
  const parts = displayName.split(/[\s@._-]+/).filter(Boolean);
  const firstName = parts[0] || displayName;
  const initials = parts
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();

  return {
    firstName,
    displayName,
    initials: initials || "SI",
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function caseIdFromPayload(item: Record<string, unknown>) {
  return String(
    item.thread_id ||
      item.threadId ||
      item.case_number ||
      item.caseNumber ||
      item.session_id ||
      item.conversation_id ||
      item.case_id ||
      item.caseId ||
      item.id ||
      "",
  );
}

function formatHistoryDate(value: unknown) {
  if (typeof value !== "string" || !value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function normalizeCaseHistory(payload: unknown): CaseHistoryItem[] {
  const rawItems = Array.isArray(payload)
    ? payload
    : Array.isArray(asRecord(payload).items)
      ? (asRecord(payload).items as unknown[])
      : Array.isArray(asRecord(payload).cases)
        ? (asRecord(payload).cases as unknown[])
        : [];

  return rawItems
    .map((raw) => {
      const item = asRecord(raw);
      const id = caseIdFromPayload(item);
      if (!id) return null;
      const title = String(
        item.title ||
          item.last_preview ||
          item.lastPreview ||
          item.name ||
          item.case_number ||
          item.summary ||
          `Fall ${id}`,
      );
      const status = String(item.status || item.phase || item.request_type || "Analyse");
      const updatedAt =
        formatHistoryDate(item.updated_at) ||
        formatHistoryDate(item.updatedAt) ||
        formatHistoryDate(item.last_activity_at);
      return {
        id,
        title,
        subtitle: updatedAt ? `${status} · ${updatedAt}` : status,
        updatedAt,
      };
    })
    .filter((item): item is CaseHistoryItem => Boolean(item))
    .slice(0, 30);
}

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { data: session } = useSession();
  const userIdentity = identityFromSession(session?.user?.name, session?.user?.email);
  const [historyItems, setHistoryItems] = useState<CaseHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isHistorySearchOpen, setIsHistorySearchOpen] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [isHistoryOpen, setIsHistoryOpen] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    const stored = window.localStorage.getItem("sealai:historyOpen");
    if (stored === "1" || stored === "0") {
      return stored === "1";
    }
    return window.matchMedia?.("(min-width: 1024px)").matches ?? false;
  });

  useEffect(() => {
    window.localStorage.setItem("sealai:historyOpen", isHistoryOpen ? "1" : "0");
  }, [isHistoryOpen]);

  useEffect(() => {
    let isCurrent = true;
    queueMicrotask(() => {
      if (!isCurrent) return;
      setHistoryLoading(true);
      setHistoryError(null);
    });
    fetch("/api/bff/agent/cases?limit=30", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body?.error?.message || `case_history_failed:${response.status}`);
        }
        return response.json();
      })
      .then((payload) => {
        if (!isCurrent) return;
        setHistoryItems(normalizeCaseHistory(payload));
      })
      .catch((error: unknown) => {
        if (!isCurrent) return;
        setHistoryError(error instanceof Error ? error.message : "Verlauf konnte nicht geladen werden.");
      })
      .finally(() => {
        if (isCurrent) {
          setHistoryLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [pathname]);

  const normalizedHistorySearch = historySearch.trim().toLowerCase();
  const visibleHistoryItems = normalizedHistorySearch
    ? historyItems.filter(
        (item) =>
          item.title.toLowerCase().includes(normalizedHistorySearch) ||
          item.subtitle.toLowerCase().includes(normalizedHistorySearch),
      )
    : historyItems;

  return (
    <div className="relative flex h-screen w-full overflow-hidden bg-white font-sans text-foreground">
      <aside
        className={cn(
          "relative z-40 flex h-full shrink-0 flex-col border-r border-border/80 bg-sidebar text-muted-foreground transition-[width] duration-200 ease-out",
          isHistoryOpen ? "w-[304px]" : "w-[72px]",
        )}
      >
        <div className={cn("flex h-[72px] items-center", isHistoryOpen ? "justify-between px-5" : "justify-center")}>
          <button
            type="button"
            aria-label={isHistoryOpen ? "Seitenleiste einklappen" : "Seitenleiste ausklappen"}
            aria-expanded={isHistoryOpen}
            title={isHistoryOpen ? "Seitenleiste einklappen" : "Seitenleiste ausklappen"}
            onClick={() => setIsHistoryOpen((current) => !current)}
            className="grid h-10 w-10 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-white hover:text-seal-blue"
          >
            <Menu size={20} />
          </button>
          {isHistoryOpen ? (
            <button
              type="button"
              aria-label="Chats durchsuchen"
              title="Chats durchsuchen"
              onClick={() => setIsHistorySearchOpen((current) => !current)}
              className="grid h-10 w-10 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-white hover:text-seal-blue"
            >
              <Search size={20} />
            </button>
          ) : null}
        </div>

        {isHistoryOpen ? (
          <>
            <nav className="px-3 pb-5">
              <div className="space-y-1">
                {NAV_ITEMS.map((item) => {
                  const isAnalysisRoute =
                    pathname === "/dashboard" ||
                    pathname === "/dashboard/new" ||
                    (pathname.startsWith("/dashboard/") && !pathname.startsWith("/dashboard/seo"));
                  const isActive =
                    item.href === "/dashboard/new"
                      ? isAnalysisRoute
                      : pathname.startsWith(item.href);
                  return (
                    <Link
                      key={`${item.label}-${item.href}`}
                      href={item.href}
                      className={cn(
                        "flex h-11 items-center gap-4 rounded-full border border-transparent px-4 text-[15px] font-medium transition-colors",
                        isActive
                          ? "border-border bg-white text-seal-blue shadow-sm"
                          : "text-muted-foreground hover:bg-white hover:text-seal-blue",
                      )}
                    >
                      <item.icon size={20} />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  );
                })}
              </div>

              <div className="mt-7">
                <div className="mb-2 flex items-center justify-between px-3 text-[14px] font-semibold text-foreground">
                  <span>Bereiche</span>
                  <ChevronRight size={16} className="text-muted-foreground" />
                </div>
                <div className="space-y-1">
                  {WORKSPACE_ITEMS.map((item) => {
                    const isActive = item.href !== "/dashboard/new" && pathname.startsWith(item.href);
                    return (
                      <Link
                        key={`${item.label}-${item.href}`}
                        href={item.href}
                        className={cn(
                          "flex h-10 items-center gap-4 rounded-full border border-transparent px-4 text-[14px] font-medium transition-colors",
                          isActive
                            ? "border-border bg-white text-seal-blue shadow-sm"
                            : "text-muted-foreground hover:bg-white hover:text-seal-blue",
                        )}
                      >
                        <item.icon size={18} />
                        <span className="truncate">{item.label}</span>
                      </Link>
                    );
                  })}
                </div>
              </div>
            </nav>

            <div className="mb-2 px-6 text-[14px] font-semibold text-foreground">
              Chats
            </div>

            {isHistorySearchOpen ? (
              <div className="px-4 pb-3">
                <label className="sr-only" htmlFor="dashboard-history-search">
                  Chats suchen
                </label>
                <input
                  id="dashboard-history-search"
                  value={historySearch}
                  onChange={(event) => setHistorySearch(event.target.value)}
                  placeholder="Chats suchen"
                  className="h-10 w-full rounded-full border border-border bg-white px-4 text-[14px] text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-seal-blue"
                />
              </div>
            ) : null}

            <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-3 pb-4">
              {historyLoading ? (
                <div className="rounded-[22px] px-3 py-2.5 text-[14px] text-muted-foreground">
                  Lade Gespräche...
                </div>
              ) : historyError ? (
                <div className="rounded-[22px] bg-[#FBE8D1] px-3 py-2.5 text-[14px] text-[#8A4A15]">
                  {historyError}
                </div>
              ) : historyItems.length === 0 ? (
                <div className="rounded-[22px] px-3 py-2.5 text-[14px] text-muted-foreground">
                  Noch keine gespeicherten Chats.
                </div>
              ) : visibleHistoryItems.length === 0 ? (
                <div className="rounded-[22px] px-3 py-2.5 text-[14px] text-muted-foreground">
                  Kein passender Chat.
                </div>
              ) : (
                <div className="space-y-0.5">
                  {visibleHistoryItems.map((item) => {
                    const href = `/dashboard/${encodeURIComponent(item.id)}`;
                    const isActive = pathname === href;
                    return (
                      <Link
                        key={item.id}
                        href={href}
                        title={`${item.title} · ${item.subtitle}`}
                        aria-label={`${item.title} ${item.subtitle}`}
                        className={cn(
                          "block rounded-full border border-transparent px-3 py-2 text-[14px] font-medium leading-6 transition-colors",
                          isActive
                            ? "border-border bg-white text-seal-blue shadow-sm"
                            : "text-muted-foreground hover:bg-white hover:text-seal-blue",
                        )}
                      >
                        <span className="block truncate">{item.title}</span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="mt-auto px-3 pb-5 pt-3">
              <div className="space-y-1">
                <Link
                  href="/dashboard/seo"
                  className="flex h-10 items-center gap-4 rounded-full px-4 text-[14px] font-medium text-muted-foreground transition-colors hover:bg-white hover:text-seal-blue"
                >
                  <Activity size={18} />
                  <span>Aktivitäten</span>
                </Link>
                <button
                  type="button"
                  aria-label="Einstellungen"
                  title="Einstellungen"
                  className="flex h-10 w-full items-center gap-4 rounded-full px-4 text-[14px] font-medium text-muted-foreground transition-colors hover:bg-white hover:text-seal-blue"
                >
                  <Settings size={18} />
                  <span>Einstellungen & Hilfe</span>
                </button>
                <LogoutButton className="rounded-full px-4 text-muted-foreground hover:bg-white hover:text-red-600" />
              </div>
              <div className="mt-5 px-4 text-[12px] leading-5 text-muted-foreground">
                <div className="font-medium text-seal-blue">Anfragebasis</div>
                <div>Governed Workspace</div>
              </div>
            </div>
          </>
        ) : (
          <>
            <nav className="flex flex-1 flex-col items-center gap-3 px-3 py-3">
              {[...NAV_ITEMS, ...WORKSPACE_ITEMS].map((item) => (
                <Link
                  key={`${item.label}-${item.href}-collapsed`}
                  href={item.href}
                  title={item.label}
                  aria-label={item.label}
                  className="grid h-10 w-10 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-white hover:text-seal-blue"
                >
                  <item.icon size={19} />
                </Link>
              ))}
            </nav>
            <div className="flex flex-col items-center gap-3 px-3 pb-5">
              <button
                type="button"
                aria-label="Einstellungen"
                title="Einstellungen"
                className="grid h-10 w-10 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-white hover:text-seal-blue"
              >
                <HelpCircle size={19} />
              </button>
              <LogoutButton showLabel={false} className="h-10 w-10 rounded-full p-0" />
            </div>
          </>
        )}
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-border/70 bg-white px-5 sm:px-7">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <div className="text-[18px] font-semibold tracking-tight text-seal-blue">SEALING</div>
              <div className="h-5 w-px bg-border" />
              <div className="text-[16px] font-medium text-foreground">INTELLIGENCE</div>
            </div>
          </div>
          <div className="ml-4 flex shrink-0 items-center gap-2 sm:gap-3">
            <div className="hidden text-sm text-muted-foreground md:block">
              Arbeitsraum: <span className="font-semibold text-seal-blue">Anfragebasis</span>
            </div>
            <span className="inline-flex items-center rounded-full border border-[#D8EEDB] bg-[#EEF9F0] px-3 py-1 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#2F8F46]">
              Governed
            </span>
            <button
              type="button"
              title="Benachrichtigungen"
              className="hidden h-10 w-10 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:flex"
            >
              <Bell size={18} />
            </button>
            <div className="flex items-center gap-3 rounded-full border border-border bg-white px-2.5 py-1.5">
              <div className="grid h-9 w-9 place-items-center rounded-full border border-border bg-muted text-sm font-semibold text-muted-foreground">
                {userIdentity.initials}
              </div>
              <div className="hidden text-left md:block">
                <div className="text-sm font-medium text-foreground">{userIdentity.displayName}</div>
                <div className="text-[12px] text-muted-foreground">Angemeldet</div>
              </div>
            </div>
            <Link
              href="/dashboard/new"
              title="Neue Analyse"
              className="flex h-10 w-10 items-center justify-center rounded-full bg-seal-blue text-white transition-colors hover:opacity-90 lg:hidden"
            >
              <Plus size={18} />
            </Link>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-hidden bg-white">{children}</div>
      </main>
    </div>
  );
}
