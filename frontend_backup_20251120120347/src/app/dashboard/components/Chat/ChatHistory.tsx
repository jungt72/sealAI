// frontend/src/app/dashboard/components/Chat/ChatHistory.tsx
'use client';

import React, { memo } from "react";
import type { FlowMeta, Message, MessageMeta } from "@/types/chat";
import MarkdownMessage from "./MarkdownMessage";

type Props = {
  messages: Message[];
  className?: string;
};

const PHASE_LABELS: Record<string, string> = {
  rapport: "Vorgespräch",
  warmup: "Warm-up",
  bedarfsanalyse: "Bedarfsanalyse",
  berechnung: "Berechnung",
  auswahl: "Auswahl",
  review: "Review",
  exit: "Abschluss",
};

const PHASE_STYLES: Record<string, string> = {
  rapport: "bg-rose-50 text-rose-700 border-rose-200",
  warmup: "bg-orange-50 text-orange-700 border-orange-200",
  bedarfsanalyse: "bg-blue-50 text-blue-700 border-blue-200",
  berechnung: "bg-indigo-50 text-indigo-700 border-indigo-200",
  auswahl: "bg-emerald-50 text-emerald-700 border-emerald-200",
  review: "bg-violet-50 text-violet-700 border-violet-200",
  exit: "bg-slate-50 text-slate-700 border-slate-200",
};

const badgeClass =
  "inline-flex items-center gap-1 rounded-full border px-2 py-[2px] text-[11px] font-medium leading-tight";

const MessageBadges = ({ flow }: { flow?: FlowMeta }) => {
  if (!flow) return null;
  const badges: React.ReactNode[] = [];

  if (flow.phase) {
    const phaseKey = flow.phase.toLowerCase();
    badges.push(
      <span
        key="phase"
        className={`${badgeClass} ${PHASE_STYLES[phaseKey] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}
      >
        {PHASE_LABELS[phaseKey] ?? flow.phase}
      </span>,
    );
  }

  if (flow.memoryContextLoaded) {
    badges.push(
      <span key="memory-load" className={`${badgeClass} bg-cyan-50 text-cyan-700 border-cyan-200`}>
        Kontext geladen
      </span>,
    );
  }

  if (flow.memoryCommitted) {
    badges.push(
      <span key="memory-commit" className={`${badgeClass} bg-teal-50 text-teal-700 border-teal-200`}>
        Kontext gespeichert
      </span>,
    );
  }

  if (typeof flow.longTermMemoryRefs === "number" && flow.longTermMemoryRefs > 0) {
    badges.push(
      <span key="memory-refs" className={`${badgeClass} bg-slate-50 text-slate-600 border-slate-200`}>
        LTM {flow.longTermMemoryRefs}
      </span>,
    );
  }

  if (typeof flow.confidence === "number") {
    const pct = Math.round(flow.confidence * 100);
    badges.push(
      <span key="confidence" className={`${badgeClass} bg-amber-50 text-amber-700 border-amber-200`}>
        Confidence {pct}%
      </span>,
    );
  }

  if (typeof flow.reviewLoops === "number" && flow.reviewLoops > 0) {
    badges.push(
      <span key="reviews" className={`${badgeClass} bg-purple-50 text-purple-700 border-purple-200`}>
        Review-Loops {flow.reviewLoops}
      </span>,
    );
  }

  if (flow.arbiter) {
    badges.push(
      <span key="arbiter" className={`${badgeClass} bg-gray-900 text-white border-gray-900`}>
        🧑‍⚖️ Arbiter
      </span>,
    );
  }

  if (!badges.length) return null;
  return <div className="mb-2 flex flex-wrap gap-2">{badges}</div>;
};

function ChatHistoryBase({ messages, className }: Props) {
  if (!messages || messages.length === 0) return null;

  const visibleMessages = messages.filter((m) => m.role === "assistant" || m.role === "user");
  if (!visibleMessages.length) return null;

  return (
    <div className={className}>
      <div className="mx-auto w-full max-w-[768px] space-y-6 px-4 py-4">
        {visibleMessages.map((m) => {
          const isUser = m.role === "user";
          const alignment = isUser ? "justify-end" : "justify-start";
          const bubbleClass = isUser
            ? "bg-blue-600 text-white cm-user"
            : "bg-white text-gray-900 cm-assistant";

          const flowMeta = (m.meta as MessageMeta | undefined)?.flow;

          return (
            <div key={m.id} className={`flex ${alignment}`}>
              <div
                className={[
                  "max-w-[680px]",
                  "rounded-2xl",
                  "px-4 py-3",
                  "shadow-sm",
                  bubbleClass,
                ].join(" ")}
              >
                {!isUser ? <MessageBadges flow={flowMeta} /> : null}
                {isUser ? (
                  <div className="whitespace-pre-wrap break-words leading-relaxed">{m.content}</div>
                ) : (
                  <MarkdownMessage>{m.content || ""}</MarkdownMessage>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const ChatHistory = memo(ChatHistoryBase);
export default ChatHistory;
