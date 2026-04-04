"use client";

/**
 * ChatPane — Chat-UI mit Streaming-Anzeige.
 * Liest State aus chatStore und workspaceStore, empfängt keine Props mehr.
 */

import {
  AlertCircle,
  PanelRightClose,
  PanelRightOpen,
  RotateCcw,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useSession } from "next-auth/react";
import { useEffect, useMemo, useRef } from "react";

import ChatComposer from "@/components/dashboard/ChatComposer";
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";
import { useChatStore } from "@/lib/store/chatStore";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

function formatTimestamp(iso: string | undefined): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return null;
  }
}

const SUGGESTION_CHIPS: Array<{ label: string; icon: string }> = [
  { label: "Wellendichtring gesucht",        icon: "🔧" },
  { label: "Hydraulikdichtung auswählen",     icon: "💧" },
  { label: "Medium identifizieren",           icon: "🧪" },
  { label: "Vorhandene Dichtung ersetzen",    icon: "🔄" },
];

export default function ChatPane() {
  // ── Session ───────────────────────────────────────────────────────────────
  const { data: session } = useSession();
  const userName = (session?.user as { name?: string | null } | undefined)?.name;

  // ── Store-Selectors (granular) ────────────────────────────────────────────
  const messages = useChatStore((s) => s.messages);
  const streamingText = useChatStore((s) => s.streamingText);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const error = useChatStore((s) => s.error);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const startNewChat = useChatStore((s) => s.startNewChat);

  const isSidebarOpen = useWorkspaceStore((s) => s.isSidebarOpen);
  const toggleSidebar = useWorkspaceStore((s) => s.toggleSidebar);
  const chatInput = useWorkspaceStore((s) => s.chatInput);
  const setChatInput = useWorkspaceStore((s) => s.setChatInput);

  // ── Abgeleitete Anzeige-State ─────────────────────────────────────────────
  const displayedMessages = useMemo(
    () =>
      error
        ? [...messages, { role: "assistant" as const, content: `⚠️ **Fehler:** ${error}` }]
        : messages,
    [error, messages],
  );
  const shouldShowStreamingBubble = isStreaming || Boolean(streamingText);
  const isZeroState = displayedMessages.length === 0 && !shouldShowStreamingBubble;

  // ── Auto-Scroll ───────────────────────────────────────────────────────────
  const assistantMessageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const streamingAssistantRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (isZeroState) {
      return;
    }

    if (shouldShowStreamingBubble && streamingAssistantRef.current) {
      streamingAssistantRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }

    for (let index = displayedMessages.length - 1; index >= 0; index -= 1) {
      if (displayedMessages[index]?.role !== "assistant") {
        continue;
      }
      const node = assistantMessageRefs.current[index];
      if (!node) {
        continue;
      }
      node.scrollIntoView({ behavior: "smooth", block: "start" });
      break;
    }
  }, [displayedMessages, isZeroState, shouldShowStreamingBubble, streamingText]);

  return (
    <div
      className={`relative flex h-full min-w-0 flex-1 flex-col overflow-hidden border-r border-[#e8ecf1] transition-colors duration-300 ${
        isZeroState ? "bg-gemini-bg" : "bg-white"
      }`}
    >
      {/* Toolbar (only when messages exist) */}
      {!isZeroState && (
        <div className="absolute right-4 top-4 z-[70] flex items-center gap-2">
          <button
            onClick={toggleSidebar}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:bg-white hover:text-blue-600 active:scale-95 xl:hidden"
            title="Engineering-Dashboard"
          >
            {isSidebarOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
            <span>Dashboard</span>
          </button>
          <button
            onClick={startNewChat}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:bg-white hover:text-blue-600 active:scale-95"
            title="Neuer Chat"
          >
            <RotateCcw size={18} />
            <span>Neuer Chat</span>
          </button>
        </div>
      )}

      {/* Message list */}
      {!isZeroState && (
        <div className="w-full flex-1 overflow-y-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 pb-40 pt-14 md:px-8">
            {displayedMessages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`w-full ${message.role === "user" ? "flex justify-end" : "flex justify-start"}`}
              >
                {message.role === "assistant" ? (
                  <div
                    ref={(node) => {
                      assistantMessageRefs.current[index] = node;
                    }}
                    className="flex w-full items-start gap-[10px]"
                  >
                    {message.content.includes("⚠️ **Fehler:**") ? (
                      // Error: keep the icon indicator
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-red-100 bg-red-50">
                        <AlertCircle size={14} className="text-red-500" />
                      </div>
                    ) : (
                      // Normal bot: small blue dot avatar
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-[#dce4ff] bg-[#eff6ff]">
                        <div className="h-2.5 w-2.5 rounded-full bg-blue-500" />
                      </div>
                    )}
                    <div className="group min-w-0 flex-1">
                      <div
                        className={`text-[13.5px] leading-[1.6] ${
                          message.content.includes("⚠️ **Fehler:**")
                            ? "text-red-700"
                            : "text-[#1a2332]"
                        }`}
                      >
                        <MarkdownRenderer>{message.content}</MarkdownRenderer>
                      </div>
                      {formatTimestamp(message.timestamp) && (
                        <span className="mt-0.5 block text-[10px] text-slate-300 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                          {formatTimestamp(message.timestamp)}
                        </span>
                      )}
                    </div>
                  </div>
                ) : (
                  // User bubble
                  <div className="group flex flex-col items-end gap-0.5">
                    <div className="max-w-[75%] rounded-[12px] rounded-tr-[2px] bg-[#2563eb] px-[14px] py-[10px] text-[13.5px] leading-[1.6] text-white">
                      {message.content}
                    </div>
                    {formatTimestamp(message.timestamp) && (
                      <span className="text-[10px] text-slate-400 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                        {formatTimestamp(message.timestamp)}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* Streaming bubble */}
            {shouldShowStreamingBubble && (
              <div className="flex w-full justify-start">
                <div ref={streamingAssistantRef} className="flex w-full items-start gap-[10px]">
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-[#dce4ff] bg-[#eff6ff]">
                    <div className="h-2.5 w-2.5 rounded-full bg-blue-500" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[13.5px] leading-[1.6] text-[#1a2332]">
                      <MarkdownRenderer>{streamingText}</MarkdownRenderer>
                    </div>
                    {isStreaming && (
                      <div className="mt-2 flex items-center gap-2">
                        {!streamingText && (
                          <span className="text-xs italic text-slate-400">SealAI denkt nach...</span>
                        )}
                        <div className="flex gap-1">
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500 [animation-delay:-0.3s]" />
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500 [animation-delay:-0.15s]" />
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500" />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Zero state — Gemini-style, left-aligned */}
      <AnimatePresence>
        {isZeroState && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8, transition: { duration: 0.2 } }}
            transition={{ duration: 0.3 }}
            className="flex flex-1 flex-col justify-center py-12"
          >
            <div className="pl-[15%] pr-[8%]">
              {/* Gem icon + greeting */}
              <div className="mb-4 flex items-center gap-2">
                <div
                  className="h-4 w-4 rotate-45 rounded-sm"
                  style={{ background: "linear-gradient(135deg, #2563eb, #60a5fa)" }}
                />
                <span className="text-sm text-slate-500">
                  {userName ? `Guten Tag, ${userName}` : "Guten Tag"}
                </span>
              </div>

              {/* Headline — left-aligned */}
              <h1 className="mb-2 text-[28px] font-semibold leading-tight text-[#1a2332]">
                Ich bin SealAI — Ihr digitaler Dichtungstechnik-Experte.
              </h1>
              <p className="mb-8 text-[15px] text-slate-500">
                Beschreiben Sie Ihre Anwendung, oder wählen Sie einen Einstieg:
              </p>

              {/* Composer — up to 70% of available width */}
              <div className="mb-5 w-[70%]">
                <ChatComposer
                  onSend={async (message) => {
                    setChatInput(null);
                    await sendMessage(message);
                  }}
                  isLoading={isStreaming}
                  autoFocus
                  externalValue={chatInput}
                />
              </div>

              {/* Suggestion chips — left-aligned */}
              <div className="flex flex-wrap gap-2">
                {SUGGESTION_CHIPS.map(({ label, icon }) => (
                  <button
                    key={label}
                    onClick={() => sendMessage(label)}
                    className="flex items-center gap-1.5 rounded-[20px] border border-[#e2e8f0] bg-white px-4 py-2 text-[13px] text-slate-600 transition-colors hover:border-blue-400 hover:bg-blue-50 hover:text-blue-600"
                  >
                    <span>{icon}</span>
                    <span>{label}</span>
                  </button>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Fixed composer (active state) */}
      {!isZeroState && (
        <motion.div
          layout
          transition={{ type: "spring", stiffness: 200, damping: 25 }}
          className="absolute bottom-6 left-0 right-0 z-50 mx-auto w-full max-w-3xl px-4"
        >
          <ChatComposer
            onSend={async (message) => {
              setChatInput(null);
              await sendMessage(message);
            }}
            isLoading={isStreaming}
            externalValue={chatInput}
          />
        </motion.div>
      )}
    </div>
  );
}
