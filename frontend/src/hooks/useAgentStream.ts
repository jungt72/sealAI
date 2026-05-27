import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";

import type {
  AgentAnswerTrace,
  AgentStreamRequest,
  AgentStateUpdateEvent,
} from "@/lib/contracts/agent";
import { appendAssistantText, normalizeAssistantMarkdown } from "@/lib/assistantText";
import { trackProductEvent, trackSeoEvent } from "@/lib/analytics/events";
import { buildStreamWorkspaceView, type StreamWorkspaceView } from "@/lib/streamWorkspace";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  answerSource?: "answer_markdown" | "reply";
  answerTrace?: AgentAnswerTrace | null;
  /** ISO timestamp of when the message was added (optional, for display) */
  timestamp?: string;
};

function streamProgressText(data: unknown): string {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return "Eine Sekunde bitte, ich prüfe den technischen Kontext.";
  }
  const eventType = String((data as Record<string, unknown>).event_type || "");
  if (eventType === "evidence_retrieved") {
    return "SealingAI prüft passende Quellen...";
  }
  if (eventType === "compute_complete") {
    return "SealingAI rechnet prüfbare Kenngrößen...";
  }
  if (eventType === "challenge_ready") {
    return "SealingAI bewertet technische Risiken...";
  }
  if (eventType === "governance_ready") {
    return "SealingAI formuliert die Antwort...";
  }
  if (eventType === "draft.created_internal") {
    return "SealingAI erstellt intern einen geprüften Antwortentwurf...";
  }
  if (eventType === "final_guard.running") {
    return "SealingAI prüft Claims und Evidenzgrenzen...";
  }
  if (eventType === "final_guard.done") {
    return "SealingAI gibt die geprüfte Antwort frei...";
  }
  return "Eine Sekunde bitte, ich prüfe den technischen Kontext.";
}

type UseAgentStreamOptions = {
  initialCaseId?: string;
  onCaseBound?: (caseId: string) => void;
  onNoCaseTurn?: () => void;
  onTurnComplete?: (caseId: string) => void;
};

function isAgentAnswerTrace(value: unknown): value is AgentAnswerTrace {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const trace = value as Record<string, unknown>;
  return (
    typeof trace.reply_source === "string" &&
    typeof trace.answer_markdown_source === "string" &&
    typeof trace.final_visible_source === "string" &&
    typeof trace.composer_attempted === "boolean" &&
    typeof trace.composer_succeeded === "boolean" &&
    typeof trace.hcl_attempted === "boolean" &&
    typeof trace.hcl_succeeded === "boolean" &&
    (trace.fallback_reason === null || typeof trace.fallback_reason === "string")
  );
}

function unknownAnswerTrace(finalVisibleSource: NonNullable<ChatMessage["answerSource"]>): AgentAnswerTrace {
  return {
    reply_source: "unknown",
    answer_markdown_source: "unknown",
    final_visible_source: finalVisibleSource,
    composer_attempted: false,
    composer_succeeded: false,
    hcl_attempted: false,
    hcl_succeeded: false,
    fallback_reason: null,
  };
}

function visibleAnswerTrace(
  runMeta: AgentStateUpdateEvent["runMeta"],
  finalVisibleSource: NonNullable<ChatMessage["answerSource"]>,
): AgentAnswerTrace {
  const trace = isAgentAnswerTrace(runMeta?.answer_trace)
    ? runMeta.answer_trace
    : unknownAnswerTrace(finalVisibleSource);
  return {
    ...trace,
    final_visible_source: finalVisibleSource,
  };
}

function isHistoryMessage(value: unknown): value is { role: "user" | "assistant"; content: string } {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const message = value as Record<string, unknown>;
  return (
    (message.role === "user" || message.role === "assistant") &&
    typeof message.content === "string"
  );
}

function parseHistoryMessages(data: unknown): ChatMessage[] {
  const messages = Array.isArray(data)
    ? data
    : data && typeof data === "object" && Array.isArray((data as { messages?: unknown }).messages)
      ? (data as { messages: unknown[] }).messages
      : [];

  return messages
    .filter(isHistoryMessage)
    .map((message) => ({ role: message.role, content: message.content }));
}

function rawErrorText(value: unknown): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message;
  if (typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    return rawErrorText(record.message || record.detail || record.code);
  }
  return String(value);
}

function parseNestedJsonError(value: string): string {
  const trimmed = value.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
    return trimmed;
  }
  try {
    return rawErrorText(JSON.parse(trimmed)) || trimmed;
  } catch {
    return trimmed;
  }
}

function userVisibleStreamError(value: unknown, status?: number): string {
  const parsed = parseNestedJsonError(rawErrorText(value));
  const lowered = parsed.toLowerCase();
  if (
    status === 401 ||
    status === 403 ||
    lowered.includes("token_expired") ||
    lowered.includes("refresh token") ||
    lowered.includes("unauthorized")
  ) {
    return "Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.";
  }
  if (lowered.includes("method not allowed")) {
    return "Die Anfrage konnte nicht gesendet werden. Bitte lade die Seite neu und versuche es erneut.";
  }
  if (lowered.includes("agent stream failed") || lowered.includes("agent_stream_failed")) {
    return "Die Antwort konnte gerade nicht geladen werden. Bitte versuche es erneut.";
  }
  if (
    lowered.includes("network") ||
    lowered.includes("aborted") ||
    lowered.includes("terminated") ||
    lowered.includes("connection") ||
    lowered.includes("failed to fetch")
  ) {
    return "Die Verbindung zur Antwort wurde unterbrochen. Bitte prüfe die Verbindung und versuche es erneut.";
  }
  if (!parsed || parsed.startsWith("{") || parsed.startsWith("[")) {
    return "Die Antwort konnte gerade nicht geladen werden. Bitte versuche es erneut.";
  }
  return parsed;
}

function streamErrorStatus(payload: Record<string, unknown>): number | undefined {
  const code = String(payload.error_code || payload.code || "").toLowerCase();
  if (
    code.includes("auth") ||
    code.includes("token") ||
    code.includes("unauthorized") ||
    code.includes("expired")
  ) {
    return 401;
  }
  return undefined;
}

function streamEventDedupeKey(payload: Record<string, unknown>): string | null {
  const explicitId = payload.event_id || payload.eventId;
  if (typeof explicitId === "string" && explicitId.trim()) {
    return `event:${explicitId.trim()}`;
  }
  const turnId = payload.turn_id || payload.turnId;
  const sequence = payload.sequence;
  const type = typeof payload.type === "string" ? payload.type : "message";
  if (
    typeof turnId === "string" &&
    turnId.trim() &&
    (typeof sequence === "number" || typeof sequence === "string")
  ) {
    return `turn:${turnId.trim()}:${type}:${String(sequence)}`;
  }
  return null;
}

const NO_CASE_CONVERSATION_STORAGE_KEY = "sealai:no-case-conversation-id";

function createClientConversationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `conversation-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function createClientTurnId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `turn-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function payloadTurnId(payload: Record<string, unknown>): string | null {
  const turnId = payload.turn_id || payload.turnId;
  return typeof turnId === "string" && turnId.trim() ? turnId.trim() : null;
}

function readStoredNoCaseConversationId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const stored = window.sessionStorage.getItem(NO_CASE_CONVERSATION_STORAGE_KEY);
    return stored && stored.trim() ? stored : null;
  } catch {
    return null;
  }
}

function storeNoCaseConversationId(conversationId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.sessionStorage.setItem(NO_CASE_CONVERSATION_STORAGE_KEY, conversationId);
  } catch {
    // Session storage is a resilience layer; the in-memory ref remains authoritative.
  }
}

function getInitialConversationId(initialCaseId?: string): string {
  if (initialCaseId) {
    return initialCaseId;
  }
  const stored = readStoredNoCaseConversationId();
  if (stored) {
    return stored;
  }
  const conversationId = createClientConversationId();
  storeNoCaseConversationId(conversationId);
  return conversationId;
}

function rotateNoCaseConversationId(): string {
  const conversationId = createClientConversationId();
  storeNoCaseConversationId(conversationId);
  return conversationId;
}

export function useAgentStream(options: UseAgentStreamOptions = {}) {
  const { initialCaseId, onCaseBound, onNoCaseTurn, onTurnComplete } = options;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [streamingStatusText, setStreamingStatusText] = useState("");
  const [streamingAnswerSource, setStreamingAnswerSource] = useState<ChatMessage["answerSource"] | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(initialCaseId || null);
  const [streamWorkspace, setStreamWorkspace] = useState<StreamWorkspaceView | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const finalAssistantTextRef = useRef("");
  const historyLoadedCaseIdRef = useRef<string | null>(null);
  const streamRequestIdRef = useRef(0);
  const finalizedRequestIdRef = useRef<number | null>(null);
  const latestCaseIdRef = useRef<string | null>(initialCaseId || null);
  const conversationIdRef = useRef<string>(getInitialConversationId(initialCaseId));
  const noCaseTurnRef = useRef(false);
  const finalAssistantAnswerSourceRef = useRef<ChatMessage["answerSource"] | null>(null);
  const finalAssistantAnswerTraceRef = useRef<AgentAnswerTrace | null>(null);
  const trackedCaseIdsRef = useRef<Set<string>>(new Set());
  const trackedFirstInputCaseIdsRef = useRef<Set<string>>(new Set());
  const finalStateReceivedRef = useRef(false);
  const streamDoneReceivedRef = useRef(false);
  const streamInterruptedRef = useRef(false);
  const seenStreamEventKeysRef = useRef<Set<string>>(new Set());
  const activeTurnIdRef = useRef<string | null>(null);

  const trackCaseBound = useCallback((caseId: string, source: string) => {
    if (trackedCaseIdsRef.current.has(caseId)) {
      return;
    }
    trackedCaseIdsRef.current.add(caseId);
    trackProductEvent("case_started", { case_present: true, source });
    trackSeoEvent("case_started", { source });
    trackSeoEvent("rfq_started", { source: "agent_chat" });
    if (!trackedFirstInputCaseIdsRef.current.has(caseId)) {
      trackedFirstInputCaseIdsRef.current.add(caseId);
      trackProductEvent("case_first_input_added", { case_present: true, source });
    }
  }, []);

  const fetchHistory = useCallback(async (caseId: string) => {
    const response = await fetch(`/api/bff/agent/chat/history/${encodeURIComponent(caseId)}`);
    if (!response.ok) {
      return [];
    }
    const data = await response.json();
    return parseHistoryMessages(data);
  }, []);

  const syncHistory = useCallback(
    async (caseId: string, mode: "restore" | "merge" = "merge") => {
      try {
        const restored = await fetchHistory(caseId);
        if (restored.length === 0) return;
        setMessages((current) => {
          if (mode === "restore") {
            return current.length > 0 ? current : restored;
          }
          const restoredWithSources = restored.map((message, index) => {
            const currentMessage = current[index];
            if (
              currentMessage?.answerSource &&
              currentMessage.role === message.role &&
              currentMessage.content === message.content
            ) {
              return {
                ...message,
                answerSource: currentMessage.answerSource,
                answerTrace: currentMessage.answerTrace,
              };
            }
            return message;
          });
          return restoredWithSources.length >= current.length ? restoredWithSources : current;
        });
      } catch (err: unknown) {
        console.warn("[useAgentStream] History load failed:", err);
      }
    },
    [fetchHistory],
  );

  // Restore chat history on mount when a caseId is given (page reload)
  useEffect(() => {
    const caseId = initialCaseId;
    if (!caseId || historyLoadedCaseIdRef.current === caseId) {
      return;
    }
    latestCaseIdRef.current = caseId;
    conversationIdRef.current = caseId;
    setActiveCaseId(caseId);
    let isCurrent = true;
    const historyCaseId = caseId;
    historyLoadedCaseIdRef.current = historyCaseId;
    async function restoreInitialHistory() {
      try {
        const restored = await fetchHistory(historyCaseId);
        if (!isCurrent || restored.length === 0) return;
        setMessages((current) => (current.length > 0 ? current : restored));
      } catch (err: unknown) {
        console.warn("[useAgentStream] History load failed:", err);
      }
    }
    void restoreInitialHistory();
    return () => {
      isCurrent = false;
    };
  }, [fetchHistory, initialCaseId]);

  const finalizeAssistantTurn = useCallback((requestId: number) => {
    if (streamRequestIdRef.current !== requestId || finalizedRequestIdRef.current === requestId) {
      return;
    }

    const finalText = normalizeAssistantMarkdown(finalAssistantTextRef.current).trim();
    const answerSource = finalAssistantAnswerSourceRef.current || undefined;
    const answerTrace = finalAssistantAnswerTraceRef.current;
    finalizedRequestIdRef.current = requestId;
    finalAssistantTextRef.current = "";
    finalAssistantAnswerSourceRef.current = null;
    finalAssistantAnswerTraceRef.current = null;
    setStreamingText("");
    setStreamingStatusText("");
    setStreamingAnswerSource(null);

    if (!finalText) {
      if (latestCaseIdRef.current && !noCaseTurnRef.current) {
        void syncHistory(latestCaseIdRef.current);
        onTurnComplete?.(latestCaseIdRef.current);
      }
      return;
    }

    setMessages((existing) => {
      const lastMessage = existing[existing.length - 1];
      if (lastMessage?.role === "assistant" && lastMessage.content === finalText) {
        return existing;
      }
      return [
        ...existing,
        { role: "assistant", content: finalText, answerSource, answerTrace, timestamp: new Date().toISOString() },
      ];
    });
    if (latestCaseIdRef.current && !noCaseTurnRef.current) {
      void syncHistory(latestCaseIdRef.current);
      onTurnComplete?.(latestCaseIdRef.current);
    }
  }, [onTurnComplete, syncHistory]);

  const sendMessage = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || isStreaming) {
        return;
      }

      setMessages((current) => [...current, { role: "user", content: trimmed, timestamp: new Date().toISOString() }]);
      setStreamingText("");
      setStreamingStatusText("Eine Sekunde bitte, ich prüfe den technischen Kontext.");
      setStreamingAnswerSource(null);
      finalAssistantTextRef.current = "";
      finalAssistantAnswerSourceRef.current = null;
      finalAssistantAnswerTraceRef.current = null;
      finalStateReceivedRef.current = false;
      streamDoneReceivedRef.current = false;
      streamInterruptedRef.current = false;
      seenStreamEventKeysRef.current.clear();
      setError(null);
      setIsStreaming(true);

      abortControllerRef.current = new AbortController();
      streamRequestIdRef.current += 1;
      const requestId = streamRequestIdRef.current;
      const turnId = createClientTurnId();
      activeTurnIdRef.current = turnId;
      finalizedRequestIdRef.current = null;
      noCaseTurnRef.current = false;

      const markStreamInterrupted = (reason: unknown, status?: number) => {
        if (streamRequestIdRef.current !== requestId) {
          return;
        }
        streamInterruptedRef.current = true;
        finalizedRequestIdRef.current = requestId;
        finalAssistantTextRef.current = "";
        finalAssistantAnswerSourceRef.current = null;
        finalAssistantAnswerTraceRef.current = null;
        setError(userVisibleStreamError(reason, status));
        setStreamingStatusText("");
        setStreamingAnswerSource(null);
        setIsStreaming(false);
      };

      const payload: AgentStreamRequest = {
        caseId: activeCaseId || undefined,
        conversationId: activeCaseId ? undefined : conversationIdRef.current,
        message: trimmed,
        turnId,
      };

      try {
        await fetchEventSource("/api/bff/agent/chat/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
          signal: abortControllerRef.current.signal,
          openWhenHidden: true,
          async onopen(response) {
            if (response.ok) {
              return;
            }

            const body = await response.json().catch(() => ({}));
            const message = userVisibleStreamError(
              (body as { error?: { message?: unknown }; detail?: unknown })?.error?.message ||
                (body as { detail?: unknown })?.detail ||
                `Agent stream could not be opened (${response.status}).`,
              response.status,
            );
            setError(message);
            throw new Error(message);
          },
          onmessage(event) {
            if (streamRequestIdRef.current !== requestId) {
              return;
            }
            if (!event.data) {
              return;
            }

            if (event.data === "[DONE]") {
              streamDoneReceivedRef.current = true;
              setIsStreaming(false);
              setStreamingStatusText("");
              if (latestCaseIdRef.current && !noCaseTurnRef.current) {
                void syncHistory(latestCaseIdRef.current);
              }
              return;
            }

            let payload: Record<string, unknown>;
            try {
              payload = JSON.parse(event.data) as Record<string, unknown>;
            } catch {
              return;
            }

            const eventTurnId = payloadTurnId(payload);
            if (eventTurnId && activeTurnIdRef.current && eventTurnId !== activeTurnIdRef.current) {
              return;
            }

            const dedupeKey = streamEventDedupeKey(payload);
            if (dedupeKey) {
              if (seenStreamEventKeysRef.current.has(dedupeKey)) {
                return;
              }
              seenStreamEventKeysRef.current.add(dedupeKey);
            }

            const type = String(payload.type || "message");
            if (type === "case_bound" && typeof payload.caseId === "string") {
              latestCaseIdRef.current = payload.caseId;
              conversationIdRef.current = payload.caseId;
              setActiveCaseId(payload.caseId);
              trackCaseBound(payload.caseId, "case_bound_event");
              onCaseBound?.(payload.caseId);
              return;
            }

            if (type === "answer.stream.start") {
              const source =
                payload.source === "answer_markdown" || payload.source === "reply"
                  ? payload.source
                  : null;
              finalAssistantTextRef.current = "";
              finalAssistantAnswerSourceRef.current = source;
              finalAssistantAnswerTraceRef.current = null;
              setStreamingStatusText("");
              setStreamingText("");
              setStreamingAnswerSource(source);
              return;
            }

            if (type === "answer.token" && typeof payload.text === "string") {
              finalAssistantTextRef.current = appendAssistantText(
                finalAssistantTextRef.current,
                payload.text,
              );
              setStreamingStatusText("");
              setStreamingText(normalizeAssistantMarkdown(finalAssistantTextRef.current));
              return;
            }

            if (type === "answer.done") {
              return;
            }

            if (type === "progress") {
              if (!finalAssistantTextRef.current) {
                setStreamingStatusText(streamProgressText(payload.data));
              }
              return;
            }

            if (type === "state_update") {
              finalStateReceivedRef.current = true;
              const stateUpdate = payload as unknown as AgentStateUpdateEvent;
              const answerMarkdown =
                typeof stateUpdate.answer_markdown === "string" ? stateUpdate.answer_markdown.trim() : "";
              const reply = typeof stateUpdate.reply === "string" ? stateUpdate.reply : "";
              const assistantText = normalizeAssistantMarkdown(answerMarkdown || reply);
              if (assistantText) {
                const answerSource = answerMarkdown ? "answer_markdown" : "reply";
                finalAssistantTextRef.current = assistantText;
                finalAssistantAnswerSourceRef.current = answerSource;
                finalAssistantAnswerTraceRef.current = visibleAnswerTrace(stateUpdate.runMeta, answerSource);
                setStreamingStatusText("");
                setStreamingText(assistantText);
                setStreamingAnswerSource(answerSource);
              }

              if (stateUpdate.noCaseCreated || typeof stateUpdate.caseId !== "string") {
                noCaseTurnRef.current = Boolean(stateUpdate.noCaseCreated);
                onNoCaseTurn?.();
                return;
              }

              noCaseTurnRef.current = false;
              const streamCaseId = stateUpdate.caseId;
              if (latestCaseIdRef.current !== streamCaseId) {
                trackCaseBound(streamCaseId, "state_update");
                onCaseBound?.(streamCaseId);
              }
              latestCaseIdRef.current = streamCaseId;
              conversationIdRef.current = streamCaseId;
              setActiveCaseId(streamCaseId);
              const nextWorkspace = buildStreamWorkspaceView(
                stateUpdate as AgentStateUpdateEvent & { caseId: string },
              );
              setStreamWorkspace(nextWorkspace);
              return;
            }

            if (type === "error" || type === "interrupted") {
              markStreamInterrupted(payload.message || payload, streamErrorStatus(payload));
            }
          },
          onclose() {
            if (streamRequestIdRef.current === requestId) {
              if (
                !streamDoneReceivedRef.current &&
                !finalStateReceivedRef.current &&
                finalAssistantTextRef.current
              ) {
                markStreamInterrupted(
                  "Die Verbindung zur Antwort wurde unterbrochen. Bitte versuche es erneut.",
                );
                return;
              }
              setIsStreaming(false);
              setStreamingStatusText("");
              if (latestCaseIdRef.current && !noCaseTurnRef.current) {
                void syncHistory(latestCaseIdRef.current);
              }
            }
          },
          onerror(error) {
            if (streamRequestIdRef.current === requestId) {
              markStreamInterrupted(error);
            }
            throw error;
          },
        });
        if (streamRequestIdRef.current !== requestId || streamInterruptedRef.current) {
          return;
        }
        if (finalStateReceivedRef.current) {
          finalizeAssistantTurn(requestId);
          return;
        }
        if (finalAssistantTextRef.current) {
          markStreamInterrupted(
            "Die Verbindung zur Antwort wurde vor der finalen Bestätigung unterbrochen. Bitte versuche es erneut.",
          );
        }
      } catch {
        setIsStreaming(false);
      }
    },
    [activeCaseId, finalizeAssistantTurn, isStreaming, onCaseBound, onNoCaseTurn, syncHistory, trackCaseBound],
  );

  const cancelStream = useCallback(() => {
    abortControllerRef.current?.abort();
    streamRequestIdRef.current += 1;
    finalizedRequestIdRef.current = streamRequestIdRef.current;
    finalAssistantTextRef.current = "";
    finalAssistantAnswerSourceRef.current = null;
    finalAssistantAnswerTraceRef.current = null;
    finalStateReceivedRef.current = false;
    streamDoneReceivedRef.current = false;
    streamInterruptedRef.current = true;
    seenStreamEventKeysRef.current.clear();
    activeTurnIdRef.current = null;
    noCaseTurnRef.current = false;
    setStreamingText("");
    setStreamingStatusText("");
    setStreamingAnswerSource(null);
    setIsStreaming(false);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const resetConversation = useCallback(() => {
    cancelStream();
    setMessages([]);
    setStreamingText("");
    setStreamingStatusText("");
    setStreamingAnswerSource(null);
    finalAssistantTextRef.current = "";
    finalAssistantAnswerSourceRef.current = null;
    finalAssistantAnswerTraceRef.current = null;
    finalStateReceivedRef.current = false;
    streamDoneReceivedRef.current = false;
    streamInterruptedRef.current = false;
    seenStreamEventKeysRef.current.clear();
    activeTurnIdRef.current = null;
    setError(null);
    setActiveCaseId(null);
    latestCaseIdRef.current = null;
    conversationIdRef.current = rotateNoCaseConversationId();
    noCaseTurnRef.current = false;
    setStreamWorkspace(null);
  }, [cancelStream]);

  const appendAssistantMessage = useCallback((message: string) => {
    const trimmed = normalizeAssistantMarkdown(message).trim();
    if (!trimmed) {
      return;
    }
    finalAssistantTextRef.current = "";
    finalAssistantAnswerSourceRef.current = null;
    finalAssistantAnswerTraceRef.current = null;
    finalStateReceivedRef.current = false;
    streamDoneReceivedRef.current = false;
    streamInterruptedRef.current = false;
    seenStreamEventKeysRef.current.clear();
    activeTurnIdRef.current = null;
    setStreamingText("");
    setStreamingStatusText("");
    setStreamingAnswerSource(null);
    setMessages((current) => {
      const lastMessage = current[current.length - 1];
      if (lastMessage?.role === "assistant" && lastMessage.content === trimmed) {
        return current;
      }
      return [
        ...current,
        {
          role: "assistant",
          content: trimmed,
          answerSource: "answer_markdown",
          timestamp: new Date().toISOString(),
        },
      ];
    });
  }, []);

  return {
    activeCaseId,
    messages,
    streamingText,
    streamingStatusText,
    streamingAnswerSource,
    streamWorkspace,
    isStreaming,
    error,
    sendMessage,
    cancelStream,
    clearError,
    resetConversation,
    appendAssistantMessage,
  };
}
