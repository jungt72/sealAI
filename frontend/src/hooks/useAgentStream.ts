import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";

import type {
  AgentAnswerTrace,
  AgentStreamRequest,
  AgentStateUpdateEvent,
} from "@/lib/contracts/agent";
import { appendAssistantText, normalizeAssistantMarkdown } from "@/lib/assistantText";
import { trackSeoEvent } from "@/lib/analytics/events";
import { buildStreamWorkspaceView, type StreamWorkspaceView } from "@/lib/streamWorkspace";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  answerSource?: "answer_markdown" | "reply" | "text_chunk";
  answerTrace?: AgentAnswerTrace | null;
  /** ISO timestamp of when the message was added (optional, for display) */
  timestamp?: string;
};

function streamProgressText(data: unknown): string {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return "SealingAI prüft den Fall...";
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
  return "SealingAI prüft den Fall...";
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
  if (!parsed || parsed.startsWith("{") || parsed.startsWith("[")) {
    return "Die Antwort konnte gerade nicht geladen werden. Bitte versuche es erneut.";
  }
  return parsed;
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
  const noCaseTurnRef = useRef(false);
  const finalAssistantAnswerSourceRef = useRef<ChatMessage["answerSource"] | null>(null);
  const finalAssistantAnswerTraceRef = useRef<AgentAnswerTrace | null>(null);
  const trackedCaseIdsRef = useRef<Set<string>>(new Set());

  const trackCaseBound = useCallback((caseId: string, source: string) => {
    if (trackedCaseIdsRef.current.has(caseId)) {
      return;
    }
    trackedCaseIdsRef.current.add(caseId);
    trackSeoEvent("case_started", { case_id: caseId, source });
    trackSeoEvent("rfq_started", { case_id: caseId, source: "agent_chat" });
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
      setStreamingStatusText("SealingAI prüft den Fall...");
      setStreamingAnswerSource(null);
      finalAssistantTextRef.current = "";
      finalAssistantAnswerSourceRef.current = null;
      finalAssistantAnswerTraceRef.current = null;
      setError(null);
      setIsStreaming(true);

      abortControllerRef.current = new AbortController();
      streamRequestIdRef.current += 1;
      const requestId = streamRequestIdRef.current;
      finalizedRequestIdRef.current = null;
      noCaseTurnRef.current = false;

      const payload: AgentStreamRequest = {
        caseId: activeCaseId || undefined,
        message: trimmed,
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

            const type = String(payload.type || "message");
            if (type === "case_bound" && typeof payload.caseId === "string") {
              latestCaseIdRef.current = payload.caseId;
              setActiveCaseId(payload.caseId);
              trackCaseBound(payload.caseId, "case_bound_event");
              onCaseBound?.(payload.caseId);
              return;
            }

            if (type === "text_chunk" && typeof payload.text === "string") {
              finalAssistantTextRef.current = appendAssistantText(
                finalAssistantTextRef.current,
                payload.text,
              );
              finalAssistantAnswerSourceRef.current = "text_chunk";
              finalAssistantAnswerTraceRef.current = unknownAnswerTrace("text_chunk");
              setStreamingStatusText("");
              setStreamingText(normalizeAssistantMarkdown(finalAssistantTextRef.current));
              setStreamingAnswerSource("text_chunk");
              return;
            }

            if (type === "text_reset") {
              finalAssistantTextRef.current = "";
              finalAssistantAnswerSourceRef.current = "text_chunk";
              finalAssistantAnswerTraceRef.current = unknownAnswerTrace("text_chunk");
              setStreamingStatusText("SealingAI schärft die Antwort...");
              setStreamingText("");
              setStreamingAnswerSource("text_chunk");
              return;
            }

            if (type === "progress") {
              if (!finalAssistantTextRef.current) {
                setStreamingStatusText(streamProgressText(payload.data));
              }
              return;
            }

            if (type === "state_update") {
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
              setActiveCaseId(streamCaseId);
              const nextWorkspace = buildStreamWorkspaceView(
                stateUpdate as AgentStateUpdateEvent & { caseId: string },
              );
              setStreamWorkspace(nextWorkspace);
              return;
            }

            if (type === "error") {
              setError(userVisibleStreamError(payload.message || payload));
              setStreamingStatusText("");
              setIsStreaming(false);
            }
          },
          onclose() {
            if (streamRequestIdRef.current === requestId) {
              setIsStreaming(false);
              setStreamingStatusText("");
              if (latestCaseIdRef.current && !noCaseTurnRef.current) {
                void syncHistory(latestCaseIdRef.current);
              }
            }
          },
          onerror(error) {
            if (streamRequestIdRef.current === requestId) {
              setError(userVisibleStreamError(error));
              setStreamingStatusText("");
              setIsStreaming(false);
            }
            throw error;
          },
        });
        finalizeAssistantTurn(requestId);
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
    setError(null);
    setActiveCaseId(null);
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
