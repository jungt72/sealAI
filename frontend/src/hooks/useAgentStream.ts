import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";

import type {
  AgentAnswerTrace,
  AgentStreamRequest,
  AgentStateUpdateEvent,
} from "@/lib/contracts/agent";
import { buildStreamWorkspaceView, type StreamWorkspaceView } from "@/lib/streamWorkspace";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  answerSource?: "answer_markdown" | "reply" | "text_chunk";
  answerTrace?: AgentAnswerTrace | null;
  /** ISO timestamp of when the message was added (optional, for display) */
  timestamp?: string;
};

type UseAgentStreamOptions = {
  initialCaseId?: string;
  onCaseBound?: (caseId: string) => void;
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

export function useAgentStream(options: UseAgentStreamOptions = {}) {
  const { initialCaseId, onCaseBound, onTurnComplete } = options;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
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

  const fetchHistory = useCallback(async (caseId: string) => {
    const response = await fetch(`/api/bff/agent/chat/history/${encodeURIComponent(caseId)}`);
    if (!response.ok) {
      return [];
    }
    const data = (await response.json()) as { messages?: Array<{ role: string; content: string }> } | null;
    return (data?.messages ?? [])
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));
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

    const finalText = finalAssistantTextRef.current.trim();
    const answerSource = finalAssistantAnswerSourceRef.current || undefined;
    const answerTrace = finalAssistantAnswerTraceRef.current;
    finalizedRequestIdRef.current = requestId;
    finalAssistantTextRef.current = "";
    finalAssistantAnswerSourceRef.current = null;
    finalAssistantAnswerTraceRef.current = null;
    setStreamingText("");
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
            const message =
              body?.error?.message ||
              `Agent stream could not be opened (${response.status}).`;
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
              onCaseBound?.(payload.caseId);
              return;
            }

            if (type === "text_chunk" && typeof payload.text === "string") {
              finalAssistantTextRef.current += payload.text;
              finalAssistantAnswerSourceRef.current = "text_chunk";
              finalAssistantAnswerTraceRef.current = unknownAnswerTrace("text_chunk");
              setStreamingText(finalAssistantTextRef.current);
              setStreamingAnswerSource("text_chunk");
              return;
            }

            if (type === "state_update") {
              const stateUpdate = payload as unknown as AgentStateUpdateEvent;
              const answerMarkdown =
                typeof stateUpdate.answer_markdown === "string" ? stateUpdate.answer_markdown.trim() : "";
              const reply = typeof stateUpdate.reply === "string" ? stateUpdate.reply : "";
              const assistantText = answerMarkdown || reply;
              if (assistantText) {
                const answerSource = answerMarkdown ? "answer_markdown" : "reply";
                finalAssistantTextRef.current = assistantText;
                finalAssistantAnswerSourceRef.current = answerSource;
                finalAssistantAnswerTraceRef.current = visibleAnswerTrace(stateUpdate.runMeta, answerSource);
                setStreamingText(assistantText);
                setStreamingAnswerSource(answerSource);
              }

              if (stateUpdate.noCaseCreated || typeof stateUpdate.caseId !== "string") {
                noCaseTurnRef.current = Boolean(stateUpdate.noCaseCreated);
                return;
              }

              noCaseTurnRef.current = false;
              const streamCaseId = stateUpdate.caseId;
              if (latestCaseIdRef.current !== streamCaseId) {
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

            if (type === "error" && typeof payload.message === "string") {
              setError(payload.message);
              setIsStreaming(false);
            }
          },
          onclose() {
            if (streamRequestIdRef.current === requestId) {
              setIsStreaming(false);
              if (latestCaseIdRef.current && !noCaseTurnRef.current) {
                void syncHistory(latestCaseIdRef.current);
              }
            }
          },
          onerror(error) {
            if (streamRequestIdRef.current === requestId) {
              setError(error instanceof Error ? error.message : "Agent stream failed.");
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
    [activeCaseId, finalizeAssistantTurn, isStreaming, onCaseBound, syncHistory],
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
    setStreamingAnswerSource(null);
    finalAssistantTextRef.current = "";
    finalAssistantAnswerSourceRef.current = null;
    finalAssistantAnswerTraceRef.current = null;
    setError(null);
    setActiveCaseId(null);
    setStreamWorkspace(null);
  }, [cancelStream]);

  return {
    activeCaseId,
    messages,
    streamingText,
    streamingAnswerSource,
    streamWorkspace,
    isStreaming,
    error,
    sendMessage,
    cancelStream,
    clearError,
    resetConversation,
  };
}
