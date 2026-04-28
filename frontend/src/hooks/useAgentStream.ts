import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";

import type { AgentStreamRequest, AgentStateUpdateEvent } from "@/lib/contracts/agent";
import { buildStreamWorkspaceView, type StreamWorkspaceView } from "@/lib/streamWorkspace";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  /** ISO timestamp of when the message was added (optional, for display) */
  timestamp?: string;
};

type UseAgentStreamOptions = {
  initialCaseId?: string;
  onCaseBound?: (caseId: string) => void;
  onTurnComplete?: (caseId: string) => void;
};

export function useAgentStream(options: UseAgentStreamOptions = {}) {
  const { initialCaseId, onCaseBound, onTurnComplete } = options;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
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
          return restored.length >= current.length ? restored : current;
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
    finalizedRequestIdRef.current = requestId;
    finalAssistantTextRef.current = "";
    setStreamingText("");

    if (!finalText) {
      if (latestCaseIdRef.current) {
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
      return [...existing, { role: "assistant", content: finalText, timestamp: new Date().toISOString() }];
    });
    if (latestCaseIdRef.current) {
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
      finalAssistantTextRef.current = "";
      setError(null);
      setIsStreaming(true);

      abortControllerRef.current = new AbortController();
      streamRequestIdRef.current += 1;
      const requestId = streamRequestIdRef.current;
      finalizedRequestIdRef.current = null;

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
              if (latestCaseIdRef.current) {
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
              setStreamingText(finalAssistantTextRef.current);
              return;
            }

            if (type === "state_update" && typeof payload.caseId === "string") {
              const stateUpdate = payload as unknown as AgentStateUpdateEvent;
              latestCaseIdRef.current = stateUpdate.caseId;
              const nextWorkspace = buildStreamWorkspaceView(stateUpdate);
              setStreamWorkspace(nextWorkspace);
              if (typeof stateUpdate.reply === "string" && stateUpdate.reply) {
                finalAssistantTextRef.current = stateUpdate.reply;
                setStreamingText(stateUpdate.reply);
              }
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
              if (latestCaseIdRef.current) {
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
    setStreamingText("");
    setIsStreaming(false);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const resetConversation = useCallback(() => {
    cancelStream();
    setMessages([]);
    setStreamingText("");
    finalAssistantTextRef.current = "";
    setError(null);
    setActiveCaseId(null);
    setStreamWorkspace(null);
  }, [cancelStream]);

  return {
    activeCaseId,
    messages,
    streamingText,
    streamWorkspace,
    isStreaming,
    error,
    sendMessage,
    cancelStream,
    clearError,
    resetConversation,
  };
}
