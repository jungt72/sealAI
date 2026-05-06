"use client";

import { useEffect, useState } from "react";
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
  PanelLeftClose,
  Plus,
  Settings,
  Target,
} from "lucide-react";

import LogoutButton from "@/components/dashboard/LogoutButton";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard/new", icon: MessageSquareText, label: "Neue Analyse" },
  { href: "/goal", icon: Target, label: "Goal" },
  { href: "/rag", icon: Database, label: "Wissensbasis" },
  { href: "/dashboard/new", icon: Bookmark, label: "Merkliste" },
  { href: "/dashboard/new", icon: FileText, label: "Dokumente" },
];

type CaseHistoryItem = {
  id: string;
  title: string;
  subtitle: string;
  updatedAt: string | null;
};

function firstNameFromSession(name?: string | null, email?: string | null) {
  const source = (name || email || "Thorsten").trim();
  const first = source.split(/[\s@]/)[0];
  return first || "Thorsten";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function caseIdFromPayload(item: Record<string, unknown>) {
  return String(
    item.case_id ||
      item.caseId ||
      item.id ||
      item.session_id ||
      item.conversation_id ||
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
  const userName = firstNameFromSession(session?.user?.name, session?.user?.email);
  const [historyItems, setHistoryItems] = useState<CaseHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  useEffect(() => {
    let isCurrent = true;
    setHistoryLoading(true);
    setHistoryError(null);
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

  return (
    <div className="relative flex h-screen w-full overflow-hidden bg-[#F5F7FB] font-sans text-foreground">
      <aside className="relative z-40 flex h-full w-[72px] shrink-0 flex-col border-r border-[#E7ECF3] bg-white">
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
          <button
            type="button"
            aria-label={isHistoryOpen ? "Historie umschalten" : "Historie einblenden"}
            aria-expanded={isHistoryOpen}
            title={isHistoryOpen ? "Historie umschalten" : "Historie einblenden"}
            onClick={() => setIsHistoryOpen((current) => !current)}
            className={cn(
              "flex h-11 w-11 items-center justify-center rounded-[14px] border transition-colors",
              isHistoryOpen
                ? "border-[#CFE0FF] bg-[#EEF4FF] text-[#0B5BD3]"
                : "border-transparent text-[#6B7280] hover:border-[#E7ECF3] hover:bg-[#F8FAFD] hover:text-[#111827]",
            )}
          >
            <Clock3 size={19} />
          </button>
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

      {isHistoryOpen ? (
        <aside
          aria-label="Verlauf"
          className="absolute bottom-0 left-[72px] top-0 z-30 flex w-[286px] flex-col border-r border-[#E7ECF3] bg-[#FBFCFE] shadow-[18px_0_45px_rgba(15,23,42,0.12)]"
        >
          <div className="flex h-[72px] items-center gap-2 border-b border-[#E7ECF3] px-4">
            <Link
              href="/dashboard/new"
              className="inline-flex h-10 min-w-0 flex-1 items-center justify-center gap-2 rounded-[14px] border border-[#DCE7F7] bg-white text-sm font-semibold text-[#111827] shadow-sm transition-colors hover:border-[#CFE0FF] hover:bg-[#F8FBFF]"
            >
              <Plus size={16} />
              Neue Analyse
            </Link>
            <button
              type="button"
              aria-label="Historie ausblenden"
              title="Historie ausblenden"
              onClick={() => setIsHistoryOpen(false)}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] border border-[#DCE7F7] bg-white text-[#6B7280] shadow-sm transition-colors hover:border-[#CFE0FF] hover:bg-[#F8FBFF] hover:text-[#0B5BD3]"
            >
              <PanelLeftClose size={17} />
            </button>
          </div>

          <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-3 py-4">
            <div className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8A94A6]">
              Verlauf
            </div>
            {historyLoading ? (
              <div className="rounded-[14px] border border-[#E7ECF3] bg-white px-3 py-3 text-sm text-[#6B7280]">
                Lade Gespräche...
              </div>
            ) : historyError ? (
              <div className="rounded-[14px] border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800">
                {historyError}
              </div>
            ) : historyItems.length === 0 ? (
              <div className="rounded-[14px] border border-[#E7ECF3] bg-white px-3 py-3 text-sm text-[#6B7280]">
                Noch keine gespeicherten Fälle.
              </div>
            ) : (
              <div className="space-y-1">
                {historyItems.map((item) => {
                  const href = `/dashboard/${encodeURIComponent(item.id)}`;
                  const isActive = pathname === href;
                  return (
                    <Link
                      key={item.id}
                      href={href}
                      title={item.title}
                      className={cn(
                        "block rounded-[12px] px-3 py-2.5 text-left transition-colors",
                        isActive
                          ? "bg-[#EEF4FF] text-[#0B5BD3]"
                          : "text-[#374151] hover:bg-white hover:text-[#111827]",
                      )}
                    >
                      <div className="truncate text-sm font-medium">{item.title}</div>
                      <div className="mt-0.5 truncate text-[11px] text-[#8A94A6]">
                        {item.subtitle}
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          <div className="border-t border-[#E7ECF3] px-4 py-3 text-[11px] leading-4 text-[#8A94A6]">
            Fälle bleiben über die Case-ID wiederaufrufbar. Aktive Chats wechseln nach dem ersten Turn automatisch auf die Fall-URL.
          </div>
        </aside>
      ) : null}

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-[#E7ECF3] bg-white px-5 sm:px-7">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <div className="text-[18px] font-semibold tracking-tight text-[#0B5BD3]">SEALING</div>
              <div className="h-5 w-px bg-[#D7DDE8]" />
              <div className="text-[16px] font-medium text-[#374151]">INTELLIGENCE</div>
            </div>
          </div>
          <div className="ml-4 flex shrink-0 items-center gap-2 sm:gap-3">
            <div className="hidden text-sm text-[#6B7280] md:block">
              Arbeitsraum: <span className="font-semibold text-[#0B5BD3]">Anfragebasis</span>
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
