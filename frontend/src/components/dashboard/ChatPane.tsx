"use client";

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown, Bot, UserRound } from "lucide-react";

import ChatComposer from "@/components/dashboard/ChatComposer";
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";
import { useAgentStream } from "@/hooks/useAgentStream";
import {
  isAtLiveBottom,
  isProgrammaticScroll,
  nextModeAfterUserScroll,
  shouldShowJumpToLive,
  submitAnchorBottomSpacer,
  submitAnchorOffset,
  type ChatScrollMode,
} from "@/lib/chatScroll";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/lib/store/chatStore";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

const CHAT_SURFACE_MAX_WIDTH = 800;
const CHAT_SURFACE_STYLE: React.CSSProperties = { maxWidth: CHAT_SURFACE_MAX_WIDTH };
const PROGRAMMATIC_SCROLL_GUARD_MS = 180;
const CHAT_NAVIGATION_KEYS = new Set([
  "ArrowDown",
  "ArrowUp",
  "End",
  "Home",
  "PageDown",
  "PageUp",
  " ",
]);

interface ChatPaneProps {
  caseId?: string;
  initialGoal?: string;
  onCaseBound?: (caseId: string) => void;
  onNoCaseTurn?: () => void;
  onTurnComplete?: (caseId: string) => void;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function messageIdentity(message: { role: string; content: string; timestamp?: string }, index: number): string {
  return `${message.role}:${message.timestamp ?? index}:${message.content.slice(0, 80)}`;
}

const MessageBubble = React.memo(function MessageBubble({
  role,
  content,
  isStreaming = false,
}: {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}) {
  const isUser = role === "user";

  return (
    <div className={cn("flex w-full gap-3", isUser ? "justify-end" : "relative justify-start")}>
      {!isUser && (
        <div
          data-testid="message-avatar-assistant"
          className="absolute -left-10 top-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-seal-blue/10 text-seal-blue"
        >
          <Bot size={14} />
        </div>
      )}
      <div
        data-private
        className={cn(
          "min-w-0 px-1 py-1 text-[14px] leading-relaxed",
          isUser ? "max-w-[min(720px,84%)] text-[#111827]" : "w-full max-w-none flex-1 text-slate-900",
          isStreaming && "text-seal-blue",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="prose prose-sm max-w-none prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0 prose-strong:text-slate-950">
            <MarkdownRenderer variant="chat">{content}</MarkdownRenderer>
          </div>
        )}
      </div>
      {isUser && (
        <div
          data-testid="message-avatar-user"
          className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full border border-seal-blue/15 bg-white/70 text-slate-500"
        >
          <UserRound size={14} />
        </div>
      )}
    </div>
  );
});

function EmptyChatStart({
  initialGoal,
  isStreaming,
  onSend,
}: {
  initialGoal?: string;
  isStreaming: boolean;
  onSend: (message: string) => void;
}) {
  return (
    <div className="relative mx-auto flex min-h-[calc(100vh-120px)] w-full max-w-[1040px] flex-col items-center justify-center px-4 pb-24 pt-10">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/2 h-[540px] w-[min(920px,82vw)] -translate-x-1/2 -translate-y-[44%] rounded-full bg-[#BFE4FF]/55 blur-[72px]"
      />
      <div className="relative z-10 flex w-full max-w-[760px] flex-col items-center">
        <h1 className="mb-10 text-center text-[32px] font-normal leading-tight tracking-[0] text-[#1F2933] sm:text-[38px]">
          Womit sollen wir anfangen?
        </h1>

        <ChatComposer
          externalValue={initialGoal}
          onSend={onSend}
          isLoading={isStreaming}
          autoFocus
          placeholder="Was möchtest du wissen"
          variant="hero"
        />
      </div>
    </div>
  );
}

export default function ChatPane({
  caseId,
  initialGoal,
  onCaseBound,
  onNoCaseTurn,
  onTurnComplete,
}: ChatPaneProps) {
  const {
    activeCaseId,
    messages,
    streamingText,
    streamingStatusText,
    streamWorkspace,
    isStreaming,
    error,
    sendMessage,
    clearError,
    appendAssistantMessage,
  } = useAgentStream({ initialCaseId: caseId, onCaseBound, onNoCaseTurn, onTurnComplete });
  const setStreamWorkspace = useWorkspaceStore((s) => s.setStreamWorkspace);
  const setActiveResponseClass = useWorkspaceStore((s) => s.setActiveResponseClass);
  const registerChatCallbacks = useChatStore((s) => s.registerCallbacks);
  const setChatActiveCaseId = useChatStore((s) => s.setActiveCaseId);
  const viewportRef = useRef<HTMLDivElement>(null);
  const messageFlowRef = useRef<HTMLDivElement>(null);
  const latestUserRef = useRef<HTMLDivElement | null>(null);
  const submitAnchorSpacerRef = useRef<HTMLDivElement>(null);
  const scrollModeRef = useRef<ChatScrollMode>("following-bottom");
  const pendingSubmitAnchorRef = useRef(false);
  const frozenScrollTopRef = useRef<number | null>(null);
  const lastAnchoredUserKeyRef = useRef<string | null>(null);
  const programmaticScrollUntilRef = useRef(0);
  const hasConversationRef = useRef(false);
  const showJumpToLiveRef = useRef(false);
  const submitAnchorSpacerPxRef = useRef(0);
  const [showJumpToLiveButton, setShowJumpToLiveButton] = useState(false);

  const hasConversation = messages.length > 0 || Boolean(streamingText);
  const currentCaseId = activeCaseId || caseId;
  const isFreshStart = !hasConversation && !currentCaseId;
  const latestUserIndex = messages.reduce((latest, message, index) => (
    message.role === "user" ? index : latest
  ), -1);
  const latestUserKey = latestUserIndex >= 0 ? messageIdentity(messages[latestUserIndex], latestUserIndex) : null;

  const setJumpToLiveVisible = useCallback((nextVisible: boolean) => {
    if (showJumpToLiveRef.current === nextVisible) {
      return;
    }
    showJumpToLiveRef.current = nextVisible;
    setShowJumpToLiveButton(nextVisible);
  }, []);

  const scheduleJumpToLiveVisible = useCallback((nextVisible: boolean) => {
    window.requestAnimationFrame(() => {
      setJumpToLiveVisible(nextVisible);
    });
  }, [setJumpToLiveVisible]);

  const updateJumpToLiveState = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) {
      scheduleJumpToLiveVisible(false);
      return;
    }
    scheduleJumpToLiveVisible(shouldShowJumpToLive(hasConversationRef.current, viewport));
  }, [scheduleJumpToLiveVisible]);

  const runProgrammaticScroll = useCallback((scrollAction: () => void) => {
    programmaticScrollUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_GUARD_MS;
    scrollAction();
    window.requestAnimationFrame(updateJumpToLiveState);
  }, [updateJumpToLiveState]);

  const setSubmitAnchorSpacer = useCallback((nextSpacerPx: number) => {
    const normalized = Math.ceil(Math.max(0, nextSpacerPx));
    if (Math.abs(submitAnchorSpacerPxRef.current - normalized) < 2) {
      return false;
    }
    submitAnchorSpacerPxRef.current = normalized;
    if (submitAnchorSpacerRef.current) {
      submitAnchorSpacerRef.current.style.height = `${normalized}px`;
    }
    return true;
  }, []);

  const latestUserElement = useCallback(() => {
    return latestUserRef.current || messageFlowRef.current?.querySelector<HTMLElement>('[data-latest-user="true"]') || null;
  }, []);

  const refreshSubmitAnchorSpacer = useCallback(() => {
    const viewport = viewportRef.current;
    const latestUser = latestUserElement();
    if (!viewport || !latestUser) {
      return false;
    }

    return setSubmitAnchorSpacer(submitAnchorBottomSpacer(
      viewport,
      latestUser,
      submitAnchorSpacerPxRef.current,
    ));
  }, [latestUserElement, setSubmitAnchorSpacer]);

  const alignLatestUserToTop = useCallback(() => {
    const viewport = viewportRef.current;
    const latestUser = latestUserElement();
    if (!viewport || !latestUser) {
      return false;
    }

    refreshSubmitAnchorSpacer();

    const viewportBox = viewport.getBoundingClientRect();
    const userBox = latestUser.getBoundingClientRect();
    const maxTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    const nextTop = Math.max(
      0,
      Math.min(
        maxTop,
        viewport.scrollTop + userBox.top - viewportBox.top - submitAnchorOffset(viewport),
      ),
    );

    runProgrammaticScroll(() => {
      viewport.scrollTo({ top: nextTop, behavior: "auto" });
      frozenScrollTopRef.current = nextTop;
    });
    return true;
  }, [latestUserElement, refreshSubmitAnchorSpacer, runProgrammaticScroll]);

  const scrollToLiveBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }
    const requestedBehavior = prefersReducedMotion() ? "auto" : behavior;
    setSubmitAnchorSpacer(0);
    runProgrammaticScroll(() => {
      viewport.scrollTo({ top: viewport.scrollHeight, behavior: requestedBehavior });
      frozenScrollTopRef.current = null;
      scrollModeRef.current = "following-bottom";
    });
  }, [runProgrammaticScroll, setSubmitAnchorSpacer]);

  const maintainScrollPosition = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }

    if (scrollModeRef.current === "frozen" && frozenScrollTopRef.current !== null) {
      refreshSubmitAnchorSpacer();
      runProgrammaticScroll(() => {
        viewport.scrollTop = frozenScrollTopRef.current ?? viewport.scrollTop;
      });
      return;
    }

    if (scrollModeRef.current === "following-bottom") {
      scrollToLiveBottom("auto");
      return;
    }

    updateJumpToLiveState();
  }, [refreshSubmitAnchorSpacer, runProgrammaticScroll, scrollToLiveBottom, updateJumpToLiveState]);

  const markUserScrollIntent = useCallback(() => {
    if (isProgrammaticScroll(programmaticScrollUntilRef.current, Date.now())) {
      return;
    }
    scrollModeRef.current = "user-browsing";
    frozenScrollTopRef.current = null;
  }, []);

  const handleViewportScroll = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }
    if (isProgrammaticScroll(programmaticScrollUntilRef.current, Date.now())) {
      updateJumpToLiveState();
      return;
    }

    const atLiveBottom = isAtLiveBottom(viewport);
    scrollModeRef.current = nextModeAfterUserScroll(atLiveBottom);
    if (atLiveBottom) {
      frozenScrollTopRef.current = null;
    }
    updateJumpToLiveState();
  }, [updateJumpToLiveState]);

  const handleViewportKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (CHAT_NAVIGATION_KEYS.has(event.key)) {
      markUserScrollIntent();
    }
  }, [markUserScrollIntent]);

  const handleSend = useCallback(async (message: string) => {
    if (!message.trim() || isStreaming) {
      return;
    }
    pendingSubmitAnchorRef.current = true;
    scrollModeRef.current = "submit-anchor";
    frozenScrollTopRef.current = null;
    setJumpToLiveVisible(false);
    await sendMessage(message);
  }, [isStreaming, sendMessage, setJumpToLiveVisible]);

  useEffect(() => {
    registerChatCallbacks({
      sendMessage: handleSend,
      appendAssistantMessage,
      startNewChat: () => {
        window.location.href = "/dashboard/new";
      },
    });
  }, [appendAssistantMessage, handleSend, registerChatCallbacks]);

  useEffect(() => {
    setStreamWorkspace(streamWorkspace);
    setActiveResponseClass(streamWorkspace?.responseClass ?? null);
  }, [setActiveResponseClass, setStreamWorkspace, streamWorkspace]);

  useEffect(() => {
    setChatActiveCaseId(activeCaseId || caseId || null);
  }, [activeCaseId, caseId, setChatActiveCaseId]);

  useEffect(() => {
    if (!activeCaseId) {
      return;
    }
    window.localStorage.setItem("sealai:lastCaseId", activeCaseId);
    if (!caseId && window.location.pathname === "/dashboard/new") {
      window.history.replaceState(null, "", `/dashboard/${encodeURIComponent(activeCaseId)}`);
    }
  }, [activeCaseId, caseId]);

  useEffect(() => {
    hasConversationRef.current = hasConversation;
    if (!hasConversation) {
      scheduleJumpToLiveVisible(false);
      scrollModeRef.current = "following-bottom";
      pendingSubmitAnchorRef.current = false;
      frozenScrollTopRef.current = null;
      lastAnchoredUserKeyRef.current = null;
      setSubmitAnchorSpacer(0);
    }
  }, [hasConversation, scheduleJumpToLiveVisible, setSubmitAnchorSpacer]);

  useLayoutEffect(() => {
    hasConversationRef.current = hasConversation;

    if (isFreshStart) {
      return;
    }

    if (pendingSubmitAnchorRef.current && latestUserKey && latestUserKey !== lastAnchoredUserKeyRef.current) {
      if (!alignLatestUserToTop()) {
        return;
      }
      pendingSubmitAnchorRef.current = false;
      lastAnchoredUserKeyRef.current = latestUserKey;
      scrollModeRef.current = "frozen";
      return;
    }

    maintainScrollPosition();
  }, [
    alignLatestUserToTop,
    error,
    hasConversation,
    isFreshStart,
    isStreaming,
    latestUserKey,
    maintainScrollPosition,
    messages.length,
    streamingStatusText,
    streamingText,
  ]);

  useEffect(() => {
    const flow = messageFlowRef.current;
    if (!flow || typeof ResizeObserver === "undefined") {
      return undefined;
    }

    const observer = new ResizeObserver(() => {
      maintainScrollPosition();
    });
    observer.observe(flow);
    return () => observer.disconnect();
  }, [hasConversation, maintainScrollPosition]);

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col bg-transparent">
      <div
        ref={viewportRef}
        data-testid="chat-scroll-region"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-busy={isStreaming}
        aria-label="Chatverlauf"
        tabIndex={0}
        onScroll={handleViewportScroll}
        onWheel={markUserScrollIntent}
        onTouchStart={markUserScrollIntent}
        onKeyDown={handleViewportKeyDown}
        className="chat-scroll-viewport custom-scrollbar min-h-0 flex-1 overflow-y-auto px-4 outline-none sm:px-5"
      >
        <div
          className={cn(
            "mx-auto flex min-h-full w-full flex-col",
            isFreshStart ? "justify-center py-10" : "py-5",
          )}
          style={CHAT_SURFACE_STYLE}
        >
          {isFreshStart ? (
            <EmptyChatStart
              initialGoal={initialGoal}
              onSend={(message) => void handleSend(message)}
              isStreaming={isStreaming}
            />
          ) : (
            <div ref={messageFlowRef} className="flex flex-1 flex-col gap-5 pb-4">
              {!hasConversation && currentCaseId ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  Dieser Fall ist bereit. Stelle eine Frage oder ergänze Parameter.
                </div>
              ) : null}

              {messages.map((message, index) => {
                const isLatestUser = index === latestUserIndex;
                return (
                  <div
                    key={messageIdentity(message, index)}
                    ref={isLatestUser ? latestUserRef : undefined}
                    data-role={message.role}
                    data-latest-user={isLatestUser || undefined}
                  >
                    <MessageBubble
                      role={message.role}
                      content={message.content}
                    />
                  </div>
                );
              })}

              {streamingText && (
                <MessageBubble role="assistant" content={streamingText} isStreaming />
              )}

              {isStreaming && !streamingText && (
                <div
                  data-testid="thinking-indicator"
                  className="flex justify-start gap-3 text-sm text-slate-500"
                >
                  <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-seal-blue/10 text-seal-blue">
                    <Bot size={14} />
                  </div>
                  {streamingStatusText || "SealingAI formuliert die Antwort..."}
                </div>
              )}

              {error && (
                <div className="rounded-[14px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
                  <div className="flex items-start justify-between gap-3">
                    <p>{error}</p>
                    <button
                      type="button"
                      onClick={clearError}
                      className="shrink-0 rounded-md px-2 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                    >
                      Schließen
                    </button>
                  </div>
                </div>
              )}

              <div
                ref={submitAnchorSpacerRef}
                aria-hidden="true"
                data-testid="submit-anchor-spacer"
                className="shrink-0"
                style={{ height: 0 }}
              />

            </div>
          )}
        </div>
      </div>

      {showJumpToLiveButton && !isFreshStart && (
        <div className="pointer-events-none absolute inset-x-0 bottom-[88px] z-10 flex justify-center px-4">
          <button
            type="button"
            onClick={() => scrollToLiveBottom("smooth")}
            className="pointer-events-auto inline-flex items-center gap-2 rounded-full border border-seal-blue/20 bg-white px-4 py-2 text-sm font-semibold text-seal-blue shadow-[0_12px_32px_rgba(0,42,91,0.16)] transition-colors hover:border-seal-blue"
          >
            <ArrowDown size={16} />
            Zum aktuellen Ende
          </button>
        </div>
      )}

      {!isFreshStart && (
        <div data-testid="chat-composer-dock" className="relative shrink-0 bg-transparent px-4 pb-4 pt-8 sm:px-5">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 mx-auto h-40 max-w-[980px] rounded-full bg-[#BFE4FF]/55 blur-[60px]"
          />
          <div className="relative z-10 mx-auto w-full" style={CHAT_SURFACE_STYLE}>
            <ChatComposer
              externalValue={null}
              onSend={(message) => void handleSend(message)}
              isLoading={isStreaming}
            />
          </div>
        </div>
      )}
    </div>
  );
}
