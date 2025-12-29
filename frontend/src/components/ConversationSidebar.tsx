"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, LogOut, MessageSquare, Plus } from "lucide-react";
import { signIn, useSession } from "next-auth/react";
import { fetchFreshAccessToken } from "@/lib/useAccessToken";

import { cn } from "@/lib/utils";
import { ChatBrandRail } from "@/app/chat/components/ChatBrandRail";

type ConversationListItem = {
  id: string;
  title: string | null;
  updated_at: string;
};

const SESSION_EXPIRED_MESSAGE = "Sitzung abgelaufen – neu anmelden";
const CACHE_TTL_MS = 45 * 1000;
const INVALIDATE_EVENT = "sealai:conversations:invalidate";

const SECTION_THRESHOLD_MS = 24 * 60 * 60 * 1000;

const formatDate = (value: string) => {
  try {
    return new Date(value).toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
};

const makeConversationId = () =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `conv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

const AppleIconButton = ({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={label}
    className={cn(
      "h-8 w-8 rounded-full",
      "bg-white/70 backdrop-blur",
      "border border-slate-200/70",
      "shadow-[0_1px_2px_rgba(0,0,0,0.06)]",
      "hover:bg-white/85 hover:shadow-[0_2px_6px_rgba(0,0,0,0.08)]",
      "active:scale-[0.98]",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300",
      "transition"
    )}
  >
    <span className="flex h-full w-full items-center justify-center text-slate-600">
      {children}
    </span>
  </button>
);

export default function ConversationSidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { status } = useSession();

  const [collapsed, setCollapsed] = useState(true);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authState, setAuthState] = useState<"ok" | "expired">("ok");
  const authStateRef = useRef(authState);
  const abortControllerRef = useRef<AbortController | null>(null);
  const didReauthFetchRef = useRef(false);
  const cacheRef = useRef<{ items: ConversationListItem[]; fetchedAt: number } | null>(null);

  const fetchConversations = useCallback(async (opts?: { force?: boolean }) => {
    if (authStateRef.current === "expired") {
      setLoading(false);
      return;
    }

    const cached = cacheRef.current;
    const isFresh = cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS;
    if (!opts?.force && isFresh) {
      setConversations(cached.items);
      setLoading(false);
      setError(null);
      return;
    }

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/conversations", {
        method: "GET",
        cache: "no-store",
        signal: controller.signal,
      });
      const text = await res.text();
      let payload: any = null;
      try {
        payload = text ? JSON.parse(text) : null;
      } catch {
        payload = null;
      }

      if (!res.ok) {
        if (res.status === 401) {
          const fresh = await fetchFreshAccessToken();
          if (fresh.status === 401 || fresh.error === "expired") {
            didReauthFetchRef.current = false;
            setAuthState("expired");
            setError(SESSION_EXPIRED_MESSAGE);
            return;
          }
          const msg = payload?.detail || "Autorisierung fehlgeschlagen.";
          setConversations([]);
          setError(msg);
          return;
        }

        const msg = payload?.detail || "Fehler beim Laden der Unterhaltungen.";
        setConversations([]);
        setError(msg);
        return;
      }

      if (Array.isArray(payload)) {
        setConversations(payload as ConversationListItem[]);
        cacheRef.current = { items: payload as ConversationListItem[], fetchedAt: Date.now() };
      } else {
        setConversations([]);
        cacheRef.current = { items: [], fetchedAt: Date.now() };
      }
      setAuthState("ok");
    } catch (e: any) {
      if (controller.signal.aborted) {
        return;
      }
      setConversations([]);
      setError(e?.message || "Netzwerkfehler beim Laden der Unterhaltungen.");
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    authStateRef.current = authState;
  }, [authState]);

  useEffect(() => {
    if (status === "loading") return;
    void fetchConversations();
  }, [fetchConversations, status]);

  useEffect(() => {
    if (status === "loading") return;

    if (status === "authenticated") {
      if (authStateRef.current !== "expired") return;
      if (!didReauthFetchRef.current) {
        didReauthFetchRef.current = true;
        authStateRef.current = "ok";
        setAuthState("ok");
        void fetchConversations({ force: true });
      }
      return;
    }

    // Reset one-shot guard when leaving authenticated state.
    didReauthFetchRef.current = false;
    cacheRef.current = null;
    setConversations([]);
    setError(null);
  }, [status, fetchConversations]);

  useEffect(() => {
    const onInvalidate = (ev: Event) => {
      const detail = (ev as CustomEvent<{ reason?: string }>).detail;
      if (detail?.reason === "auth_expired") {
        cacheRef.current = null;
        setConversations([]);
        setError(SESSION_EXPIRED_MESSAGE);
        setAuthState("expired");
        return;
      }
      cacheRef.current = null;
      void fetchConversations({ force: true });
    };
    window.addEventListener(INVALIDATE_EVENT, onInvalidate as EventListener);
    return () => {
      window.removeEventListener(INVALIDATE_EVENT, onInvalidate as EventListener);
    };
  }, [fetchConversations]);

  const recent = useMemo(() => {
    const now = Date.now();
    return conversations.filter((entry) => now - new Date(entry.updated_at).getTime() <= SECTION_THRESHOLD_MS);
  }, [conversations]);

  const older = useMemo(() => {
    const now = Date.now();
    return conversations.filter((entry) => now - new Date(entry.updated_at).getTime() > SECTION_THRESHOLD_MS);
  }, [conversations]);

  const pathSegments = pathname?.split("/").filter(Boolean) ?? [];
  const activeConversationId = pathSegments[0] === "chat" && pathSegments.length > 1 ? pathSegments[1] : null;
  const sessionExpired = authState === "expired";

  const handleNewConversation = useCallback(() => {
    const newId = makeConversationId();
    window.dispatchEvent(new CustomEvent(INVALIDATE_EVENT, { detail: { reason: "new_conversation" } }));
    router.push(`/chat/${newId}`);
  }, [router]);

  const handleConversationSelect = useCallback(
    (conversationId: string) => router.push(`/chat/${conversationId}`),
    [router]
  );

  const handleLogout = useCallback(() => {
    window.location.assign("/api/auth/sso-logout");
  }, []);

  const handleReauth = useCallback(async () => {
    try {
      await signIn("keycloak", { callbackUrl: window.location.href });
    } catch {
      router.push("/auth/signin");
    }
  }, [router]);

  const renderList = (items: ConversationListItem[]) =>
    items.map((item) => {
      const isActive = activeConversationId === item.id;
      return (
        <button
          key={item.id}
          type="button"
          onClick={() => handleConversationSelect(item.id)}
          className={cn(
            "group flex w-full items-center gap-3 rounded-2xl px-2 py-2 text-left transition",
            isActive ? "bg-slate-900 text-white shadow-sm" : "text-slate-700 hover:bg-slate-100"
          )}
          aria-current={isActive ? "page" : undefined}
        >
          <div
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full border transition",
              isActive ? "bg-slate-900 border-slate-900" : "bg-white/70 border-slate-200"
            )}
          >
            <MessageSquare className={cn("h-4 w-4", isActive ? "text-white" : "text-slate-500")} />
          </div>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="text-sm font-semibold truncate">{item.title || "Neue Unterhaltung"}</div>
            <div className={cn("mt-1 text-[11px] truncate", isActive ? "text-white/70" : "text-slate-500")}>
              {formatDate(item.updated_at)}
            </div>
          </div>
        </button>
      );
    });

  // Layout sizes
  const railW = 72; // slim rail
  const panelW = 340; // white panel when expanded

  return (
    <aside className="flex h-dvh">
      {/* LEFT RAIL (hellblau bleibt) */}
      <div
        className="relative flex h-dvh flex-col items-center justify-between"
        style={{
          width: railW,
          background: "#EEF5FF", // hellblau wie vorher
          borderRight: "1px solid rgba(148,163,184,0.25)",
        }}
      >
        {/* brand */}
        <div className="pt-4">
          <ChatBrandRail />
        </div>

        {/* center controls (small apple-style) */}
        <div className="flex flex-col items-center gap-3">
          <AppleIconButton
            onClick={() => setCollapsed((v) => !v)}
            label={collapsed ? "Sidebar öffnen" : "Sidebar schließen"}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </AppleIconButton>

          <AppleIconButton onClick={handleNewConversation} label="Neue Unterhaltung">
            <Plus className="h-4 w-4" />
          </AppleIconButton>
        </div>

        {/* logout */}
        <div className="pb-4">
          <AppleIconButton onClick={handleLogout} label="Logout">
            <LogOut className="h-4 w-4" />
          </AppleIconButton>
        </div>
      </div>

      {/* WHITE PANEL (only when expanded) */}
      {!collapsed && (
        <div
          className="flex h-dvh flex-col bg-white"
          style={{
            width: panelW,
            borderRight: "1px solid rgba(148,163,184,0.25)",
          }}
        >
          {/* header aligned with logo axis */}
          <div className="px-4 pt-6 pb-4">
            <div className="flex flex-col items-start">
              <div className="text-[13px] font-semibold tracking-[0.14em] text-slate-800">
                UNTERHALTUNGEN
              </div>

              <button
                type="button"
                onClick={handleNewConversation}
                className={cn(
                  "mt-3 inline-flex items-center gap-2",
                  "rounded-full px-4 py-2",
                  "bg-slate-900 text-white",
                  "shadow-[0_1px_2px_rgba(0,0,0,0.10)]",
                  "hover:bg-slate-800",
                  "active:scale-[0.99]",
                  "transition"
                )}
              >
                <Plus className="h-4 w-4" />
                <span className="text-sm font-semibold">Neue Unterhaltung</span>
              </button>

              {error && (
                <div className="mt-3 text-sm text-red-600">
                  {error}
                  {sessionExpired && (
                    <button
                      type="button"
                      onClick={handleReauth}
                      className="ml-2 text-xs font-semibold uppercase tracking-wide text-sky-600 underline-offset-4 transition hover:text-sky-800"
                    >
                      Neu anmelden
                    </button>
                  )}
                  {!sessionExpired && (
                    <button
                      type="button"
                      onClick={() => fetchConversations({ force: true })}
                      className="ml-2 text-xs font-semibold uppercase tracking-wide text-sky-600 underline-offset-4 transition hover:text-sky-800"
                    >
                      Erneut laden
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="h-px w-full bg-slate-200/70" />

          <div className="flex-1 overflow-y-auto px-3 py-3">
            {loading ? (
              <div className="px-2 py-2 text-sm text-slate-500">(Liste wird geladen ...)</div>
            ) : (
              <div className="flex flex-col gap-2">
                {recent.length > 0 && <div className="px-2 pt-1 text-[11px] text-slate-400">Aktuell</div>}
                {renderList(recent)}

                {older.length > 0 && <div className="px-2 pt-4 text-[11px] text-slate-400">Älter</div>}
                {renderList(older)}

                {!error && recent.length === 0 && older.length === 0 && (
                  <div className="px-2 py-2 text-sm text-slate-500">
                    Noch keine Unterhaltungen.
                    <button
                      type="button"
                      onClick={handleNewConversation}
                      className="ml-2 text-xs font-semibold text-sky-600 underline underline-offset-2 hover:text-sky-800"
                    >
                      Neue Unterhaltung starten
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="border-t border-slate-200/70 px-4 py-3">
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
