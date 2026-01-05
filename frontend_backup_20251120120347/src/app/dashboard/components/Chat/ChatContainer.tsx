"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";

import { useAccessToken } from "@/lib/useAccessToken";
import { useChatThreadId } from "@/lib/useChatThreadId";
import { useConsentPreference } from "@/lib/useConsentPreference";
import { useChatWs, type LanggraphWsEvent } from "@/lib/useChatWs";
import type { FlowMeta, Message, MessageMeta } from "@/types/chat";
import type { ChatMeta } from "@/types/chatMeta";
import type { TimelineStep, TimelineStepStatus } from "../StreamingTimeline";

import BedarfsanalyseCard, { type BedarfsanalyseData } from "../BedarfsanalyseCard";
import ChatHistory from "./ChatHistory";
import ChatInput from "./ChatInput";
import ChatDebugPanel from "./ChatDebugPanel";
import QualityMetaPanel from "../QualityMetaPanel";
import StreamingTimeline from "../StreamingTimeline";
import Thinking from "./Thinking";

type ChatContainerProps = {
  onTimelineUpdate?: React.Dispatch<React.SetStateAction<TimelineStep[]>>;
};

type TimelineStepId = "ws-connect" | "warmup" | "analysis" | "routing" | "checklist" | "answer";

const TIMELINE_BLUEPRINT: TimelineStep[] = [
  { id: "ws-connect", label: "Verbinde mit SealAI", kind: "system", status: "pending" },
  { id: "warmup", label: "Warm-up", kind: "phase", status: "pending" },
  { id: "analysis", label: "Bedarfsanalyse", kind: "phase", status: "pending" },
  { id: "routing", label: "Routing & Spezialisten", kind: "phase", status: "pending" },
  { id: "checklist", label: "Qualitäts-Check", kind: "agent", status: "pending" },
  { id: "answer", label: "Antwort ausgeben", kind: "phase", status: "pending" },
];

const PHASE_TO_STEP: Record<string, TimelineStepId> = {
  warmup: "warmup",
  rapport: "warmup",
  bedarfsanalyse: "analysis",
  analyse: "analysis",
  analysis: "analysis",
  intake: "analysis",
  routing: "routing",
  spezialist: "routing",
  spezialisten: "routing",
  specialist: "routing",
  checklist: "checklist",
  qa: "checklist",
  qa_check: "checklist",
  qualitaet: "checklist",
  qualitätscheck: "checklist",
  antwort: "answer",
  answering: "answer",
  answer_ready: "answer",
  answer: "answer",
};

const normalizePhase = (raw?: string): TimelineStepId | null => {
  if (!raw) return null;
  const normalized = raw.trim().toLowerCase().replace(/[\s_]+/g, "_");
  return PHASE_TO_STEP[normalized] ?? null;
};

const deriveFlowMeta = (messages: Message[]): FlowMeta | null => {
  const idx = [...messages].reverse().findIndex((m) => m.role === "assistant" && m.meta && (m.meta as MessageMeta).flow);
  if (idx === -1) return null;
  const msg = messages[messages.length - 1 - idx];
  const flow = (msg.meta as MessageMeta | undefined)?.flow;
  return flow ?? null;
};

const deriveBedarfsanalyse = (messages: Message[]): BedarfsanalyseData | null => {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (msg.role !== "assistant" || !msg.meta) continue;
    const candidate = (msg.meta as any).final?.slots?.bedarfsanalyse ?? (msg.meta as any).final?.bedarfsanalyse;
    if (candidate && typeof candidate === "object") {
      return candidate as BedarfsanalyseData;
    }
  }
  return null;
};

const computeTimeline = (
  connected: boolean,
  isStreaming: boolean,
  metaPhase?: string,
  lastEvent?: LanggraphWsEvent | null,
): TimelineStep[] => {
  const phaseId = normalizePhase(metaPhase);
  const order = TIMELINE_BLUEPRINT.map((step) => step.id);
  const phaseIndex = phaseId ? order.indexOf(phaseId) : -1;
  return TIMELINE_BLUEPRINT.map((step, idx) => {
    let status: TimelineStepStatus = step.status;

    if (step.id === "ws-connect") {
      status = connected ? "done" : "active";
    }

    if (phaseIndex >= 0) {
      if (idx < phaseIndex) {
        status = "done";
      } else if (idx === phaseIndex) {
        status = isStreaming ? "active" : "done";
      } else {
        status = "pending";
      }
    }

    if (step.id === "answer" && isStreaming) {
      status = "active";
    }
    if (step.id === "answer" && lastEvent?.type === "done") {
      status = "done";
    }

    return {
      ...step,
      status,
      timestamp: status === "done" || status === "active" ? new Date().toISOString() : undefined,
    };
  });
};

export default function ChatContainer({ onTimelineUpdate }: ChatContainerProps) {
  const { data: session, status } = useSession();
  const token = useAccessToken();
  const chatId = useChatThreadId();
  const [consent, setConsent] = useConsentPreference(false);
  const [inputValue, setInputValue] = useState("");

  const {
    connected,
    isStreaming,
    messages,
    meta,
    lastError,
    lastEvent,
    sendMessage,
    cancel,
    threadId,
  } = useChatWs({
    chatId,
    token,
    consent,
    onEvent: undefined,
  });

  const timelineSteps = useMemo(() => computeTimeline(connected, isStreaming, meta?.phase, lastEvent), [connected, isStreaming, meta?.phase, lastEvent]);

  useEffect(() => {
    if (onTimelineUpdate) {
      onTimelineUpdate(timelineSteps);
    }
  }, [timelineSteps, onTimelineUpdate]);

  const userId = useMemo(() => {
    if (!session?.user) return "unbekannt";
    const user = session.user as Record<string, unknown>;
    return (
      (typeof user.email === "string" && user.email) ||
      (typeof user.name === "string" && user.name) ||
      (typeof user.sub === "string" && user.sub) ||
      "nutzer"
    );
  }, [session]);

  const handleSend = useCallback(
    (raw: string) => {
      const trimmed = raw.trim();
      if (!trimmed) return;
      sendMessage(trimmed, { extra: { user_id: userId } });
      setInputValue("");
    },
    [sendMessage, userId],
  );

  const canSend = Boolean(token && connected && chatId);
  const waitingForTokens = isStreaming;
  const hasMessages = messages.length > 0;
  const firstName = (session?.user?.name || "").split(" ")[0] || "";
  const placeholderText =
    status === "authenticated"
      ? connected
        ? "Was möchtest du wissen?"
        : "Verbinde …"
      : "Bitte anmelden, um zu schreiben";
  const connectionHint =
    status === "authenticated"
      ? connected
        ? "Verbunden mit SealAI"
        : "WebSocket verbindet …"
      : "Bitte anmelden, um zu schreiben";
  const chatInputSection = (
    <div className="w-full max-w-[768px]">
      <ChatInput
        value={inputValue}
        setValue={setInputValue}
        onSend={handleSend}
        onStop={cancel}
        disabled={!canSend}
        streaming={isStreaming}
        placeholder={placeholderText}
      />
      <div className="mt-3">
        <label className="flex items-center gap-2 text-xs text-gray-600">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span>Antworten für Qualitätsanalyse speichern (verschlüsselt in Postgres)</span>
        </label>
        <p className="ml-6 mt-1 text-[11px] text-gray-400">
          {consent
            ? "Der Supervisor darf Ergebnisse für Audits und Verbesserungen vormerken."
            : "Sitzung ohne Persistenz."}
        </p>
      </div>
      <div className="mt-2 text-xs text-gray-500">{connectionHint}</div>
      {lastError && (
        <div className="mt-2 text-xs text-red-500">Fehler: {lastError}</div>
      )}
    </div>
  );

  const latestFlowMeta = useMemo(() => deriveFlowMeta(messages), [messages]);
  const bedarfsanalyseData = useMemo(() => deriveBedarfsanalyse(messages), [messages]);

  const metaPanel = meta ? <QualityMetaPanel meta={meta} /> : null;
  const analysisPanel = bedarfsanalyseData ? <BedarfsanalyseCard data={bedarfsanalyseData} /> : null;
  const latestMeta = meta ?? (latestFlowMeta as ChatMeta | null);

  useEffect(() => {
    if (lastError) {
      console.warn("ChatContainer WS Error", lastError);
    }
  }, [lastError]);

  return (
    <div className="flex h-full w-full flex-col bg-transparent">
      <div className="flex flex-1 flex-col overflow-hidden">
        {hasMessages ? (
          <div className="flex flex-1 flex-col overflow-y-auto pb-32" style={{ minHeight: 0 }}>
            <ChatHistory messages={messages} />
            {analysisPanel}
            {waitingForTokens ? (
              <div className="mx-auto mt-2 flex w-full max-w-[768px] items-center gap-2 px-4">
                <Thinking />
                <span className="text-xs text-gray-500">LangGraph arbeitet …</span>
              </div>
            ) : null}
            <div className="mt-6 px-4" />
          </div>
        ) : (
          <div
            className="flex flex-1 flex-col items-center justify-center px-4"
            style={{ minHeight: 0 }}
          >
            <div className="max-w-2xl w-full flex flex-col items-center gap-4 px-4 text-center">
              <h1 className="text-3xl font-semibold text-gray-900">
                Guten Morgen{firstName ? `, ${firstName}` : ""} – wie kann ich dir helfen?
              </h1>
              <p className="text-sm text-gray-500">
                Beschreibe kurz deine Aufgabe – zum Beispiel eine Dichtungsanfrage, eine technische
                Herausforderung oder eine Angebotskalkulation. SealAI liefert dir sofort eine Antwort.
              </p>
              {chatInputSection}
            </div>
          </div>
        )}
      </div>

      {hasMessages && (
        <div className="sticky bottom-0 left-0 right-0 z-20 flex justify-center bg-gradient-to-t from-white via-white/80 to-transparent pb-2 pt-4">
          {chatInputSection}
        </div>
      )}

      <div className="mt-4 px-4">
        <StreamingTimeline steps={timelineSteps} />
        <div className="mt-2 text-[11px] text-gray-400">
          Thread-ID: {threadId ?? "default"}
        </div>
      </div>
      {metaPanel}
      <ChatDebugPanel flow={latestFlowMeta} meta={latestMeta ?? null} />
    </div>
  );
}
