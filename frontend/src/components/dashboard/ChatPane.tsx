"use client";

import React, { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, UserRound } from "lucide-react";

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
        <div className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#EAF1FF] text-[#0B5BD3]">
          <Bot size={14} />
        </div>
      )}
      <div
        className={cn(
          "max-w-[min(720px,84%)] px-1 py-1 text-[14px] leading-relaxed",
          isUser ? "text-[#111827]" : "text-slate-900",
          isStreaming && "text-[#1F3B63]",
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
        <div className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full border border-[#DDE6F2] bg-white/70 text-slate-500">
          <UserRound size={14} />
        </div>
      )}
    </div>
  );
}

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
    if (typeof scrollAnchorRef.current?.scrollIntoView === "function") {
      scrollAnchorRef.current.scrollIntoView({ block: "end", behavior: "smooth" });
    }
  }, [messages, streamingText, isStreaming, error]);

  const hasConversation = messages.length > 0 || Boolean(streamingText);
  const currentCaseId = activeCaseId || caseId;
  const isFreshStart = !hasConversation && !currentCaseId;

  return (
    <div className="flex h-full w-full flex-col bg-transparent">
      <div className="custom-scrollbar flex-1 overflow-y-auto">
        <div className={cn(
          "mx-auto flex min-h-full w-full max-w-[760px] flex-col px-4 sm:px-5",
          isFreshStart ? "justify-center py-10" : "py-5",
        )}>
          {isFreshStart ? (
            <div className="mx-auto w-full max-w-[720px]">
              <ChatComposer
                externalValue={initialGoal}
                onSend={(message) => void sendMessage(message)}
                isLoading={isStreaming}
                autoFocus
              />
            </div>
          ) : (
            <div className="flex flex-1 flex-col gap-5 pb-4">
              {!hasConversation && currentCaseId ? (
                <div className="py-8 text-center text-sm text-[#8A94A6]">
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
                  <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#EAF1FF] text-[#0B5BD3]">
                    <Bot size={14} />
                  </div>
                  sealingAI verbindet den LLM-Stream...
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
      <div className="bg-transparent px-4 pb-4 pt-2 sm:px-5">
        <div className="mx-auto max-w-[760px]">
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
