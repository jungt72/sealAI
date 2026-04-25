"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Check, CheckCircle2, ChevronRight, Loader2, Paperclip, UserRound, X } from "lucide-react";

import ChatComposer from "@/components/dashboard/ChatComposer";
import { useAgentStream } from "@/hooks/useAgentStream";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { decideCaseDelta } from "@/lib/bff/caseDelta";
import type { ProposedCaseDeltaField } from "@/lib/contracts/agent";

interface ChatPaneProps {
  caseId?: string;
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

function formatDeltaValue(field: ProposedCaseDeltaField): string {
  const value =
    typeof field.proposed_value === "string"
      ? field.proposed_value
      : JSON.stringify(field.proposed_value);
  return [value, field.unit].filter(Boolean).join(" ");
}

function ProposedDeltaPanel({
  caseId,
  fields,
  onSettled,
}: {
  caseId: string | undefined;
  fields: ProposedCaseDeltaField[];
  onSettled: () => void;
}) {
  const [pendingAction, setPendingAction] = useState<"accept" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = async (action: "accept" | "reject") => {
    if (!caseId || pendingAction) {
      return;
    }
    setPendingAction(action);
    setError(null);
    try {
      await decideCaseDelta(
        caseId,
        action,
        fields.map((field) => field.field_name),
      );
      onSettled();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aenderung konnte nicht verarbeitet werden.");
    } finally {
      setPendingAction(null);
    }
  };

  if (!caseId || fields.length === 0) {
    return null;
  }

  return (
    <div className="ml-12 max-w-[min(720px,84%)] rounded-[12px] border border-[#CFE0FF] bg-[#F8FBFF] p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#315B8D]">
            Vorgeschlagene Case-Aenderung
          </div>
          <div className="mt-2 grid gap-1.5">
            {fields.map((field) => (
              <div key={field.field_name} className="flex flex-wrap items-center gap-2 text-[12px] text-slate-700">
                <span className="font-semibold text-slate-900">{field.field_name}</span>
                <span className="rounded-md border border-[#DCE8FA] bg-white px-2 py-0.5 font-medium">
                  {formatDeltaValue(field)}
                </span>
                {field.confidence && <span className="text-slate-500">{field.confidence}</span>}
              </div>
            ))}
          </div>
          {error && <div className="mt-2 text-[12px] font-medium text-rose-700">{error}</div>}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => void decide("accept")}
            disabled={Boolean(pendingAction)}
            aria-label="Vorgeschlagene Aenderung uebernehmen"
            className="grid h-8 w-8 place-items-center rounded-md border border-emerald-200 bg-white text-emerald-700 transition-colors hover:bg-emerald-50 disabled:cursor-wait disabled:opacity-60"
          >
            {pendingAction === "accept" ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
          </button>
          <button
            type="button"
            onClick={() => void decide("reject")}
            disabled={Boolean(pendingAction)}
            aria-label="Vorgeschlagene Aenderung ablehnen"
            className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
          >
            {pendingAction === "reject" ? <Loader2 size={15} className="animate-spin" /> : <X size={15} />}
          </button>
        </div>
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  "Bitte vergleiche NBR und PTFE hinsichtlich chemischer Bestaendigkeit, Temperaturbereich, Elastizitaet, Reibung, FDA-Eignung, Kosten und typischer Anwendungen.",
  "PTFE-RWDR fuer Hydraulikoel, 80 Grad Celsius und 1.500 rpm vorqualifizieren.",
  "Welche Parameter brauchst du fuer eine belastbare PTFE-RWDR Anfrage?",
  "Elastomer-RWDR durch PTFE-RWDR ersetzen: welche Risiken zuerst klaeren?",
];

export default function ChatPane({ caseId, onCaseBound, onTurnComplete }: ChatPaneProps) {
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
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const [settledDeltaKey, setSettledDeltaKey] = useState<string | null>(null);

  useEffect(() => {
    setStreamWorkspace(streamWorkspace);
    setActiveResponseClass(streamWorkspace?.responseClass ?? null);
  }, [setActiveResponseClass, setStreamWorkspace, streamWorkspace]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, streamingText, isStreaming, error]);

  const hasConversation = messages.length > 0 || Boolean(streamingText);
  const currentCaseId = activeCaseId || caseId;
  const proposedDeltaFields = useMemo(() => {
    const fields = streamWorkspace?.proposedCaseDelta?.fields ?? [];
    return fields.filter((field) => field.status === "proposed" || !field.status);
  }, [streamWorkspace?.proposedCaseDelta]);
  const proposedDeltaKey = proposedDeltaFields
    .map((field) => `${field.field_name}:${String(field.proposed_value)}:${field.unit ?? ""}`)
    .join("|");
  const visibleDeltaFields = proposedDeltaKey && settledDeltaKey !== proposedDeltaKey ? proposedDeltaFields : [];

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
                Governed Conversation
              </div>
              <h1 className="mt-1 truncate text-[18px] font-semibold tracking-tight text-[#111827]">
                {currentCaseId ? `Fall ${currentCaseId}` : "Neue PTFE-RWDR Analyse"}
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
                Ich vergleiche Werkstoffe und PTFE-RWDR-Loesungen anhand technischer und wirtschaftlicher Kriterien und halte den Arbeitsstand rechts synchron.
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

            {streamingText && <MessageBubble role="assistant" content={streamingText} isStreaming />}

            <ProposedDeltaPanel
              caseId={currentCaseId}
              fields={visibleDeltaFields}
              onSettled={() => {
                setSettledDeltaKey(proposedDeltaKey || null);
                if (currentCaseId) {
                  onTurnComplete?.(currentCaseId);
                }
              }}
            />

            {isStreaming && !streamingText && (
              <div className="flex justify-start gap-3">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#0B5BD3] text-white shadow-sm">
                  <Bot size={16} />
                </div>
                <div className="rounded-[18px] border border-[#E7ECF3] bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
                  SeaLAI verbindet den LLM-Stream...
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
                    Schliessen
                  </button>
                </div>
              </div>
            )}

            <div ref={scrollAnchorRef} />
          </div>

          {hasConversation && (
            <div className="mt-2 flex flex-wrap gap-2 pb-3">
              {[
                "Medienliste pruefen",
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
          <ChatComposer onSend={(message) => void sendMessage(message)} isLoading={isStreaming} />
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
