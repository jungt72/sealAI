"use client";

/**
 * CaseScreen — Orchestriert useAgentStream und useWorkspace,
 * synchronisiert deren State in die Zustand-Stores und rendert
 * ChatPane + WorkspacePane ohne Props-Drilling.
 *
 * Loop-Invarianten:
 *  1. Granulare Selectors (ein Feld pro useStore-Call) — Zustand-Setter sind
 *     stabile Referenzen, daher löst kein Store-Write einen Re-render aus.
 *  2. onCaseBound ist mit useCallback stabilisiert — verhindert, dass
 *     useAgentStream's sendMessage bei jedem Render neu erstellt wird.
 *  3. Store-Registrierungen laufen einmalig (leeres deps-Array) und nutzen
 *     Refs, damit Store-Consumer immer die aktuelle Impl. aufrufen.
 *  4. showWorkspacePanel aus primitiven Store-Selectors (boolean/number) —
 *     kein useMemo, kein Objekt als Dependency → kein Loop-Risiko.
 */

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import ChatPane from "@/components/dashboard/ChatPane";
import WorkspacePane from "@/components/dashboard/WorkspacePane";
import { useAgentStream } from "@/hooks/useAgentStream";
import { useWorkspace } from "@/hooks/useWorkspace";
import { useCaseStore } from "@/lib/store/caseStore";
import { useChatStore } from "@/lib/store/chatStore";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

// Module-level constant — no new reference on each render
const GOVERNED_CLASSES = new Set([
  "structured_clarification",
  "governed_state_update",
  "governed_recommendation",
  "manufacturer_match_result",
  "rfq_ready",
]);

type Props = {
  caseId?: string;
};

export default function CaseScreen({ caseId: initialCaseId }: Props) {
  const router = useRouter();

  // ── Store-Setter: granulare Selectors (je ein Feld) ───────────────────────
  // Zustand-Setter sind stabile Refs → Object.is(prev, next) === true →
  // kein Re-render von CaseScreen bei Store-Writes aus Child-Komponenten.
  const setCaseId = useCaseStore((s) => s.setCaseId);

  const setMessages = useChatStore((s) => s.setMessages);
  const setStreamingText = useChatStore((s) => s.setStreamingText);
  const setIsStreaming = useChatStore((s) => s.setIsStreaming);
  const setChatError = useChatStore((s) => s.setError);
  const registerChatCallbacks = useChatStore((s) => s.registerCallbacks);
  // Primitive: only re-renders CaseScreen when message count changes
  const messageCount = useChatStore((s) => s.messages.length);

  const setWorkspace = useWorkspaceStore((s) => s.setWorkspace);
  const setWorkspaceLoading = useWorkspaceStore((s) => s.setWorkspaceLoading);
  const setStreamWorkspace = useWorkspaceStore((s) => s.setStreamWorkspace);
  const setIsSidebarOpen = useWorkspaceStore((s) => s.setIsSidebarOpen);
  const setIsDesktopViewport = useWorkspaceStore((s) => s.setIsDesktopViewport);
  const setChatInput = useWorkspaceStore((s) => s.setChatInput);
  const setActiveResponseClass = useWorkspaceStore((s) => s.setActiveResponseClass);
  const registerWorkspaceCallbacks = useWorkspaceStore((s) => s.registerCallbacks);

  // Primitive selectors for showWorkspacePanel — booleans, no object deps
  const hasParams = useWorkspaceStore(
    (s) => (s.workspace?.claims.items ?? []).filter((c) => c.value !== null).length > 0,
  );
  const activeResponseClass = useWorkspaceStore((s) => s.activeResponseClass);
  // Read responseClass as a primitive string from the synced store value
  const streamResponseClass = useWorkspaceStore(
    (s) => s.streamWorkspace?.responseClass ?? null,
  );

  // ── onCaseBound stabilisieren ─────────────────────────────────────────────
  const initialCaseIdRef = useRef(initialCaseId);
  initialCaseIdRef.current = initialCaseId;

  const onCaseBound = useCallback(
    (caseId: string) => {
      setCaseId(caseId);
      if (caseId !== initialCaseIdRef.current) {
        window.history.replaceState(null, "", `/dashboard/${caseId}`);
      }
    },
    [setCaseId],
  );

  // ── Hooks ─────────────────────────────────────────────────────────────────
  const {
    activeCaseId,
    messages,
    streamingText,
    streamWorkspace,
    isStreaming,
    error,
    sendMessage,
    clearError,
    resetConversation,
  } = useAgentStream({ initialCaseId, onCaseBound });

  const {
    workspace,
    isLoading: workspaceLoading,
    refresh: refreshWorkspace,
    reset: resetWorkspace,
  } = useWorkspace(activeCaseId || initialCaseId || null, {
    autoLoad: Boolean(initialCaseId) && !(streamWorkspace && isStreaming),
  });

  // ── Initial caseId in Store ───────────────────────────────────────────────
  useEffect(() => {
    if (initialCaseId) {
      setCaseId(initialCaseId);
    }
  }, [initialCaseId, setCaseId]);

  // ── Viewport-Detection → workspaceStore ──────────────────────────────────
  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 1280px)");
    const syncViewport = () => {
      const desktop = mediaQuery.matches;
      setIsDesktopViewport(desktop);
      setIsSidebarOpen(desktop);
    };
    syncViewport();
    mediaQuery.addEventListener("change", syncViewport);
    return () => mediaQuery.removeEventListener("change", syncViewport);
  }, [setIsDesktopViewport, setIsSidebarOpen]);

  // ── Hook-State → chatStore (1:1-Sync) ────────────────────────────────────
  useEffect(() => { setMessages(messages); }, [messages, setMessages]);
  useEffect(() => { setStreamingText(streamingText); }, [streamingText, setStreamingText]);
  useEffect(() => { setIsStreaming(isStreaming); }, [isStreaming, setIsStreaming]);
  useEffect(() => { setChatError(error); }, [error, setChatError]);

  // ── Hook-State → workspaceStore (1:1-Sync) ────────────────────────────────
  useEffect(() => { setWorkspace(workspace); }, [workspace, setWorkspace]);
  useEffect(() => { setWorkspaceLoading(workspaceLoading); }, [workspaceLoading, setWorkspaceLoading]);
  useEffect(() => { setStreamWorkspace(streamWorkspace); }, [streamWorkspace, setStreamWorkspace]);

  // After a governed turn completes, refresh the canonical workspace once so
  // the sidebar can hand back authority from the transient stream view.
  useEffect(() => {
    if (isStreaming || !streamWorkspace || !(activeCaseId || initialCaseId)) {
      return;
    }
    void refreshWorkspace();
  }, [isStreaming, streamWorkspace, activeCaseId, initialCaseId, refreshWorkspace]);

  // Once the refreshed canonical workspace for the same case is available,
  // drop the transient stream workspace to avoid stale turn-context bleed-through.
  useEffect(() => {
    if (isStreaming || !streamWorkspace || !workspace) {
      return;
    }
    if (workspace.caseId !== streamWorkspace.caseId) {
      return;
    }
    setStreamWorkspace(null);
  }, [isStreaming, streamWorkspace, workspace, setStreamWorkspace]);

  // Persist the last known response class — dep is a primitive string, not an object
  useEffect(() => {
    if (streamResponseClass) {
      setActiveResponseClass(streamResponseClass);
    }
  }, [streamResponseClass, setActiveResponseClass]);

  // ── Workspace panel visibility ────────────────────────────────────────────
  // Computed directly from primitives — no useMemo, no object deps, no loop risk.
  const showWorkspacePanel =
    hasParams ||
    GOVERNED_CLASSES.has(activeResponseClass ?? "") ||
    messageCount > 0;

  // ── Zusammengesetzte Aktionen ─────────────────────────────────────────────
  const handleSendMessage = useCallback(
    async (message: string) => {
      setChatInput(null);
      await sendMessage(message);
      if (!activeCaseId && !initialCaseId) {
        void refreshWorkspace();
      }
    },
    [sendMessage, activeCaseId, initialCaseId, refreshWorkspace, setChatInput],
  );

  const handleStartNewChat = useCallback(() => {
    clearError();
    resetConversation();
    resetWorkspace();
    setChatInput(null);
    router.replace("/dashboard/new");
  }, [clearError, resetConversation, resetWorkspace, setChatInput, router]);

  // ── Callbacks in Stores registrieren (useRef-Pattern) ────────────────────
  const handleSendMessageRef = useRef(handleSendMessage);
  handleSendMessageRef.current = handleSendMessage;

  const handleStartNewChatRef = useRef(handleStartNewChat);
  handleStartNewChatRef.current = handleStartNewChat;

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    registerChatCallbacks({
      sendMessage: (...args) => handleSendMessageRef.current(...args),
      startNewChat: () => handleStartNewChatRef.current(),
    });
  }, []);

  const refreshWorkspaceRef = useRef(refreshWorkspace);
  refreshWorkspaceRef.current = refreshWorkspace;

  const setChatInputRef = useRef(setChatInput);
  setChatInputRef.current = setChatInput;

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    registerWorkspaceCallbacks({
      refreshWorkspace: () => refreshWorkspaceRef.current(),
      actionBridge: (text: string) => setChatInputRef.current(text),
    });
  }, []);

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Left: chat – flex-1 gives it the remaining width when right panel is open */}
      <div className="min-w-0 flex-1 overflow-hidden">
        <ChatPane />
      </div>
      {/* Right: dashboard cockpit – 50% when visible, 0 when hidden */}
      <div
        className={`h-full overflow-hidden transition-all duration-300 ease-in-out ${
          showWorkspacePanel ? "w-1/2 min-w-0" : "w-0"
        }`}
      >
        <WorkspacePane />
      </div>
    </div>
  );
}
