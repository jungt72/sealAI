"use client";

import React, { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

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
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[82%] rounded-xl border px-4 py-3 text-[15px] leading-relaxed shadow-sm",
          isUser
            ? "border-seal-blue bg-seal-blue text-white"
            : "border-border bg-white text-foreground",
          isStreaming && "border-seal-blue/30",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0 prose-strong:text-foreground">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

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
    <div className="flex h-full w-full flex-col bg-slate-50/30">
      <div className="custom-scrollbar flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-8">
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <div className="text-sm font-semibold uppercase tracking-widest text-seal-blue opacity-70">
                SeaLAI Analyse-Workbench
              </div>
              <h1 className="text-2xl font-bold text-foreground">
                {currentCaseId ? `Analyse-Fall: ${currentCaseId}` : "Neue Dichtungsanalyse"}
              </h1>
              <p className="mt-2 max-w-2xl text-muted-foreground leading-relaxed">
                Willkommen in der SeaLAI Workbench. Ich unterstütze Sie bei der technischen
                Einordnung und Qualifizierung Ihres Dichtungsproblems.
              </p>
            </div>

            {!hasConversation && (
              <>
                <div className="rounded-xl border border-border bg-white p-6 shadow-sm">
                  <p className="text-[15px] leading-relaxed">
                    Beschreiben Sie den Dichtfall so konkret wie möglich. Für PTFE-RWDR sind
                    Medium, Temperatur, Druck, Wellendurchmesser, Drehzahl und Einbausituation
                    besonders wertvoll.
                  </p>
                </div>

                {!caseId && (
                  <div className="flex flex-col gap-4 border-t border-border pt-6">
                    <p className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
                      Vorschläge für den Einstieg:
                    </p>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {[
                        "PTFE-RWDR für eine rotierende Welle in Hydrauliköl auslegen.",
                        "Vorzeitiger Ausfall eines PTFE-Wellendichtrings analysieren.",
                        "Retrofit: Elastomer-RWDR durch PTFE-RWDR ersetzen.",
                        "Bestehenden Radialwellendichtring technisch identifizieren.",
                      ].map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          onClick={() => void sendMessage(suggestion)}
                          disabled={isStreaming}
                          className="rounded-xl border border-border bg-white p-4 text-left text-sm font-medium text-foreground/80 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
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
              <div className="flex justify-start">
                <div className="rounded-xl border border-border bg-white px-4 py-3 text-[13px] text-muted-foreground shadow-sm">
                  SeaLAI analysiert...
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
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

      <div className="border-t border-border bg-white p-4">
        <div className="mx-auto max-w-3xl">
          <ChatComposer onSend={(message) => void sendMessage(message)} isLoading={isStreaming} />
          <div className="mt-3 text-center">
            <p className="text-[11px] text-muted-foreground opacity-60">
              SeaLAI liefert technische Vorqualifizierungen. Herstellerfreigabe bleibt die finale Instanz.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
