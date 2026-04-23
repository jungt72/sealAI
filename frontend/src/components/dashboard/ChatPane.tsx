"use client";

import React, { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, CheckCircle2, CircleDot, Gauge, Sparkles, UserRound } from "lucide-react";

import ChatComposer from "@/components/dashboard/ChatComposer";
import { useAgentStream } from "@/hooks/useAgentStream";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

interface ChatPaneProps {
  caseId?: string;
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
        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-slate-200 bg-white text-seal-blue shadow-sm">
          <Bot size={16} />
        </div>
      )}
      <div
        className={cn(
          "max-w-[min(760px,86%)] rounded-lg border px-4 py-3 text-[15px] leading-relaxed shadow-sm",
          isUser
            ? "border-seal-blue bg-seal-blue text-white"
            : "border-slate-200 bg-white text-slate-900",
          isStreaming && "border-seal-blue/30 shadow-seal-blue/10",
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
        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600">
          <UserRound size={16} />
        </div>
      )}
    </div>
  );
}

const SUGGESTIONS = [
  "PTFE-RWDR für Hydrauliköl, 80 Grad Celsius und 1.500 rpm vorqualifizieren.",
  "Warum fällt ein PTFE-Wellendichtring an einer rotierenden Welle vorzeitig aus?",
  "Welche Parameter brauchst du für eine belastbare PTFE-RWDR Anfrage?",
  "Elastomer-RWDR durch PTFE-RWDR ersetzen: welche Risiken zuerst klären?",
];

export default function ChatPane({ caseId }: ChatPaneProps) {
  const {
    activeCaseId,
    messages,
    streamingText,
    streamWorkspace,
    isStreaming,
    error,
    sendMessage,
    clearError,
  } = useAgentStream({ initialCaseId: caseId });
  const setStreamWorkspace = useWorkspaceStore((s) => s.setStreamWorkspace);
  const setActiveResponseClass = useWorkspaceStore((s) => s.setActiveResponseClass);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setStreamWorkspace(streamWorkspace);
    setActiveResponseClass(streamWorkspace?.responseClass ?? null);
  }, [setActiveResponseClass, setStreamWorkspace, streamWorkspace]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, streamingText, isStreaming, error]);

  const hasConversation = messages.length > 0 || Boolean(streamingText);
  const currentCaseId = activeCaseId || caseId;

  return (
    <div className="flex h-full w-full flex-col bg-[#f8fafc]">
      <div className="custom-scrollbar flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-4xl flex-col px-4 py-5 sm:px-6 lg:px-8">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-seal-blue">
                <CircleDot size={13} /> Live-Klärung
              </div>
              <h1 className="mt-1 truncate text-xl font-semibold tracking-tight text-slate-950">
                {currentCaseId ? `Fall ${currentCaseId}` : "Neue PTFE-RWDR Analyse"}
              </h1>
            </div>
            <div className="flex items-center gap-2 text-xs font-medium text-slate-600">
              <span className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-emerald-700">
                <CheckCircle2 size={13} /> SSoT aktiv
              </span>
              <span className="hidden items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 sm:inline-flex">
                <Gauge size={13} /> PTFE-RWDR Fokus
              </span>
            </div>
          </div>

          {!hasConversation && (
            <div className="mb-6 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                  <Sparkles size={17} className="text-seal-blue" />
                  Technischen Fall starten
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  Beschreibe Anwendung, Medium, Temperatur, Druck, Welle, Drehzahl oder Ausfallbild. SeaLAI führt die Klärung Schritt für Schritt und hält den Fallstatus rechts synchron.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-5">
                <div className="text-[11px] font-bold uppercase tracking-widest text-slate-500">Kritische Startdaten</div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-700">
                  {[
                    "Medium",
                    "Temperatur",
                    "Druck",
                    "Welle",
                    "Drehzahl",
                    "Einbauraum",
                  ].map((item) => (
                    <span key={item} className="rounded-md border border-slate-200 bg-white px-2.5 py-2 font-medium">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-1 flex-col gap-5 pb-4">
            {!hasConversation && !caseId && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => void sendMessage(suggestion)}
                    disabled={isStreaming}
                    className="min-h-[86px] rounded-lg border border-slate-200 bg-white p-4 text-left text-sm font-medium leading-5 text-slate-800 shadow-sm transition-colors hover:border-seal-blue/30 hover:bg-[#f7faff] disabled:cursor-not-allowed disabled:opacity-60"
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
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-slate-200 bg-white text-seal-blue shadow-sm">
                  <Bot size={16} />
                </div>
                <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
                  SeaLAI verbindet den LLM-Stream...
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
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
        </div>
      </div>

      <div className="border-t border-slate-200 bg-white p-3 sm:p-4">
        <div className="mx-auto max-w-4xl">
          <ChatComposer onSend={(message) => void sendMessage(message)} isLoading={isStreaming} />
          <p className="mt-2 text-center text-[11px] text-slate-400">
            Technische Vorqualifizierung. Herstellerfreigabe bleibt finale Instanz.
          </p>
        </div>
      </div>
    </div>
  );
}
