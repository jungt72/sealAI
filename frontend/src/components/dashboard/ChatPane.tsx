"use client";

import React, { useEffect, useRef } from "react";
import { useSession } from "next-auth/react";
import type { Session } from "next-auth";
import {
  ArrowLeftRight,
  Bot,
  FileSearch,
  FlaskConical,
  ListChecks,
  UserRound,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import ChatComposer from "@/components/dashboard/ChatComposer";
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";
import { useAgentStream } from "@/hooks/useAgentStream";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/lib/store/chatStore";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

const CHAT_SURFACE_MAX_WIDTH = 800;
const CHAT_SURFACE_STYLE: React.CSSProperties = { maxWidth: CHAT_SURFACE_MAX_WIDTH };

type StarterPrompt = {
  label: string;
  prompt: string;
  icon: LucideIcon;
};

const STARTER_PROMPTS: StarterPrompt[] = [
  {
    label: "Lösung erarbeiten",
    icon: Wrench,
    prompt:
      "Ich möchte eine Dichtungslösung erarbeiten. Bitte führe mich Schritt für Schritt durch die wichtigsten Angaben und erkläre, warum sie relevant sind.",
  },
  {
    label: "Material vergleichen",
    icon: ArrowLeftRight,
    prompt:
      "Bitte vergleiche zwei Dichtungswerkstoffe für einen konkreten Einsatzfall. Ich nenne dir gleich Materialien, Medium, Temperatur und Randbedingungen.",
  },
  {
    label: "Materialdetails",
    icon: FlaskConical,
    prompt:
      "Bitte erkläre mir einen Dichtungswerkstoff mit typischen Medien, Temperaturrahmen, Stärken, Grenzen und wichtigen Prüfpunkten.",
  },
  {
    label: "Ursache finden",
    icon: FileSearch,
    prompt:
      "Ich möchte eine Dichtungsleckage oder einen Ausfall analysieren. Bitte hilf mir strukturiert bei der Ursachenforschung.",
  },
  {
    label: "Anfrage vorbereiten",
    icon: ListChecks,
    prompt:
      "Bitte hilf mir, eine belastbare Anfragebasis für einen Hersteller aufzubauen. Keine Freigabe, sondern offene Punkte und Prüffragen sichtbar machen.",
  },
];

interface ChatPaneProps {
  caseId?: string;
  initialGoal?: string;
  onCaseBound?: (caseId: string) => void;
  onNoCaseTurn?: () => void;
  onTurnComplete?: (caseId: string) => void;
}

function decodeJwtPayload(token?: string | null): Record<string, unknown> | null {
  if (!token || typeof window === "undefined") {
    return null;
  }
  const payload = token.split(".")[1];
  if (!payload) {
    return null;
  }
  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(window.atob(padded)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function stringClaim(payload: Record<string, unknown> | null, key: string): string | null {
  const value = payload?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function firstNameFromSession(session: Session | null | undefined): string | null {
  const tokenPayload = decodeJwtPayload(session?.idToken);
  const source =
    stringClaim(tokenPayload, "given_name") ||
    stringClaim(tokenPayload, "name") ||
    session?.user?.name?.trim() ||
    stringClaim(tokenPayload, "preferred_username") ||
    session?.user?.email?.trim() ||
    "";

  const first = source.split(/[\s@._-]+/).find(Boolean);
  return first || null;
}

function MessageBubble({
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
        <div className="absolute -left-10 top-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#EAF1FF] text-[#041E49]">
          <Bot size={14} />
        </div>
      )}
      <div
        className={cn(
          "min-w-0 px-1 py-1 text-[14px] leading-relaxed",
          isUser ? "max-w-[min(720px,84%)] text-[#111827]" : "w-full max-w-none flex-1 text-slate-900",
          isStreaming && "text-[#1F3B63]",
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
        <div className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full border border-[#DDE6F2] bg-white/70 text-slate-500">
          <UserRound size={14} />
        </div>
      )}
    </div>
  );
}

function EmptyChatStart({
  userName,
  initialGoal,
  isStreaming,
  onSend,
}: {
  userName: string | null;
  initialGoal?: string;
  isStreaming: boolean;
  onSend: (message: string) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-[800px] flex-col items-center">
      <div className="mb-8 w-full">
        <p className="text-[22px] font-medium leading-tight text-seal-blue">
          {userName ? `Hallo ${userName},` : "Hallo,"}
        </p>
        <p className="mt-1 text-[22px] font-medium leading-tight text-seal-blue">
          schön, dass du wieder hier bist
        </p>
        <h1 className="mt-4 text-[42px] font-normal leading-[1.08] tracking-[0] text-seal-blue sm:text-[52px]">
          Womit fangen wir an?
        </h1>
      </div>

      <ChatComposer
        externalValue={initialGoal}
        onSend={onSend}
        isLoading={isStreaming}
        autoFocus
        placeholder="SealingAI fragen"
        variant="hero"
      />

      <div className="mt-6 flex w-full flex-wrap justify-center gap-3">
        {STARTER_PROMPTS.map((starter) => (
          <button
            key={starter.label}
            type="button"
            disabled={isStreaming}
            onClick={() => onSend(starter.prompt)}
            className="inline-flex min-h-12 items-center gap-2 rounded-full border border-[#E0E7F1] bg-white px-5 py-3 text-[15px] font-medium text-[#4B5563] shadow-[0_1px_3px_rgba(15,23,42,0.05)] transition-colors hover:border-[#C9D6E6] hover:text-seal-blue disabled:cursor-not-allowed disabled:opacity-60"
          >
            <starter.icon size={17} />
            <span>{starter.label}</span>
          </button>
        ))}
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
  const { data: session } = useSession();
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
  } = useAgentStream({ initialCaseId: caseId, onCaseBound, onNoCaseTurn, onTurnComplete });
  const setStreamWorkspace = useWorkspaceStore((s) => s.setStreamWorkspace);
  const setActiveResponseClass = useWorkspaceStore((s) => s.setActiveResponseClass);
  const registerChatCallbacks = useChatStore((s) => s.registerCallbacks);
  const setChatActiveCaseId = useChatStore((s) => s.setActiveCaseId);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    registerChatCallbacks({
      sendMessage,
      startNewChat: () => {
        window.location.href = "/dashboard/new";
      },
    });
  }, [registerChatCallbacks, sendMessage]);

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
    if (typeof scrollAnchorRef.current?.scrollIntoView === "function") {
      scrollAnchorRef.current.scrollIntoView({ block: "end", behavior: "smooth" });
    }
  }, [messages, streamingText, isStreaming, error]);

  const hasConversation = messages.length > 0 || Boolean(streamingText);
  const currentCaseId = activeCaseId || caseId;
  const isFreshStart = !hasConversation && !currentCaseId;
  const userFirstName = firstNameFromSession(session);

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-transparent">
      <div data-testid="chat-scroll-region" className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-4 sm:px-5">
        <div
          className={cn(
            "mx-auto flex min-h-full w-full flex-col",
            isFreshStart ? "justify-center py-10" : "py-5",
          )}
          style={CHAT_SURFACE_STYLE}
        >
          {isFreshStart ? (
            <EmptyChatStart
              userName={userFirstName}
              initialGoal={initialGoal}
              onSend={(message) => void sendMessage(message)}
              isStreaming={isStreaming}
            />
          ) : (
            <div className="flex flex-1 flex-col gap-5 pb-4">
              {!hasConversation && currentCaseId ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  Dieser Fall ist bereit. Stelle eine Frage oder ergänze Parameter.
                </div>
              ) : null}

              {messages.map((message, index) => (
                <MessageBubble
                  key={`${message.role}-${index}-${message.timestamp ?? ""}`}
                  role={message.role}
                  content={message.content}
                />
              ))}

              {streamingText && (
                <MessageBubble role="assistant" content={streamingText} isStreaming />
              )}

              {isStreaming && !streamingText && (
                <div className="flex justify-start gap-3 text-sm text-slate-500">
                  <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#EAF1FF] text-[#041E49]">
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

              <div ref={scrollAnchorRef} />
            </div>
          )}
        </div>
      </div>

      {!isFreshStart && (
        <div data-testid="chat-composer-dock" className="shrink-0 bg-transparent px-4 pb-4 pt-2 sm:px-5">
          <div className="mx-auto w-full" style={CHAT_SURFACE_STYLE}>
            <ChatComposer
              externalValue={null}
              onSend={(message) => void sendMessage(message)}
              isLoading={isStreaming}
            />
          </div>
        </div>
      )}
    </div>
  );
}
