"use client";

import React, { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, CheckCircle2, ChevronRight, Paperclip, UserRound } from "lucide-react";

import ChatComposer from "@/components/dashboard/ChatComposer";
import { useAgentStream } from "@/hooks/useAgentStream";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/lib/store/chatStore";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

interface ChatPaneProps {
  caseId?: string;
  initialGoal?: string;
  onCaseBound?: (caseId: string) => void;
  onTurnComplete?: (caseId: string) => void;
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
    <div className={cn("flex w-full gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#0B5BD3] text-white shadow-[0_8px_20px_rgba(11,91,211,0.16)]">
          <Bot size={16} />
        </div>
      )}
      <div
        className={cn(
          "max-w-[min(720px,84%)] rounded-[18px] border px-4 py-3 text-[14px] leading-relaxed shadow-sm",
          isUser
            ? "border-[#CFE0FF] bg-[#EEF5FF] text-[#1F3B63]"
            : "border-[#E7ECF3] bg-white text-slate-900",
          isStreaming && "border-[#BFD4FF] shadow-[#0B5BD3]/10",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="prose prose-sm max-w-none prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0 prose-strong:text-slate-950">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
      </div>
      {isUser && (
        <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full border border-[#E7ECF3] bg-white text-slate-600">
          <UserRound size={16} />
        </div>
      )}
    </div>
  );
}

const SUGGESTIONS = [
  "Bitte vergleiche NBR und PTFE hinsichtlich chemischer Beständigkeit, Temperaturbereich, Elastizität, Reibung, FDA-Eignung, Kosten und typischer Anwendungen.",
  "Dichtungsfall mit Medium, Temperatur, Druck und Drehzahl analysieren.",
  "Welche Angaben fehlen noch für eine belastbare Anfragebasis?",
  "Bestehende Dichtung ersetzen: welche Risiken zuerst klären?",
];

export default function ChatPane({ caseId, initialGoal, onCaseBound, onTurnComplete }: ChatPaneProps) {
  const {
    activeCaseId,
    messages,
    streamingText,
    streamWorkspace,
    isStreaming,
    error,
    sendMessage,
    clearError,
  } = useAgentStream({ initialCaseId: caseId, onCaseBound, onTurnComplete });
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
    scrollAnchorRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, streamingText, isStreaming, error]);

  const hasConversation = messages.length > 0 || Boolean(streamingText);
  const currentCaseId = activeCaseId || caseId;

  return (
    <div className="flex h-full w-full flex-col bg-[#FBFCFE]">
      <div className="flex h-[58px] shrink-0 items-center border-b border-[#E7ECF3] bg-white px-5">
        <div className="flex items-center gap-2 text-[18px] font-semibold text-[#1F2937]">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-[#EEF4FF] text-[#0B5BD3]">
            <Bot size={16} />
          </span>
          Chat
        </div>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full w-full max-w-[760px] flex-col px-4 py-5 sm:px-5">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-[#E7ECF3] bg-white px-4 py-3 shadow-sm">
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                Governed RFQ Qualification
              </div>
              <h1 className="mt-1 truncate text-[18px] font-semibold tracking-tight text-[#111827]">
                {currentCaseId ? `Fall ${currentCaseId}` : "Neue Dichtungsanalyse"}
              </h1>
            </div>
            <div className="flex items-center gap-2 text-xs font-medium text-slate-600">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-emerald-700">
                <CheckCircle2 size={13} /> SSoT aktiv
              </span>
            </div>
          </div>

          {!hasConversation && (
            <div className="mb-6">
              <div className="max-w-[88%] rounded-[18px] border border-[#E7ECF3] bg-white px-4 py-4 text-[14px] leading-6 text-[#4B5563] shadow-sm">
                Ich entwickle aus deinen Angaben eine belastbare Anfragebasis, erkenne offene Punkte und stelle gezielte Rückfragen für die spätere Herstellerprüfung.
              </div>
            </div>
          )}

          <div className="flex flex-1 flex-col gap-5 pb-4">
            {!hasConversation && !caseId && (
              <div className="grid grid-cols-1 gap-3">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => void sendMessage(suggestion)}
                    disabled={isStreaming}
                    className="rounded-[16px] border border-[#E7ECF3] bg-white px-4 py-3 text-left text-sm font-medium leading-5 text-slate-800 shadow-sm transition-colors hover:border-[#CFE0FF] hover:bg-[#F8FBFF] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}

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
              <div className="flex justify-start gap-3">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#0B5BD3] text-white shadow-sm">
                  <Bot size={16} />
                </div>
                <div className="rounded-[18px] border border-[#E7ECF3] bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
                  sealingAI verbindet den LLM-Stream...
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-[18px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
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

          {hasConversation && (
            <div className="mt-2 flex flex-wrap gap-2 pb-3">
              {[
                "Medienliste prüfen",
                "Dichtungsprofile empfehlen",
                "Weitere Werkstoffe vergleichen",
              ].map((item) => (
                <button
                  key={item}
                  type="button"
                  className="rounded-full border border-[#CFE0FF] bg-white px-3 py-2 text-[12px] font-medium text-[#0B5BD3] transition-colors hover:bg-[#F5F9FF]"
                >
                  {item}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-[#E7ECF3] bg-white p-3 sm:p-4">
        <div className="mx-auto max-w-[760px]">
          <ChatComposer
            externalValue={!hasConversation ? initialGoal : null}
            onSend={(message) => void sendMessage(message)}
            isLoading={isStreaming}
          />
          <div className="mt-3 flex items-center justify-between gap-3 px-1 text-[11px] text-slate-400">
            <div className="flex items-center gap-2">
              <Paperclip size={12} />
              Technische Vorqualifizierung. Herstellerfreigabe bleibt finale Instanz.
            </div>
            <div className="hidden items-center gap-1 md:flex">
              Details anzeigen
              <ChevronRight size={12} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
