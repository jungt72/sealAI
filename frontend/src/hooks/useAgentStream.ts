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
};

export function useAgentStream(options: UseAgentStreamOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(options.initialCaseId || null);
  const [streamWorkspace, setStreamWorkspace] = useState<StreamWorkspaceView | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const finalAssistantTextRef = useRef("");
  const historyLoadedCaseIdRef = useRef<string | null>(null);
  const streamRequestIdRef = useRef(0);
  const finalizedRequestIdRef = useRef<number | null>(null);

  // Restore chat history on mount when a caseId is given (page reload)
  useEffect(() => {
    const caseId = options.initialCaseId;
    if (!caseId || historyLoadedCaseIdRef.current === caseId) {
      return;
    }
    historyLoadedCaseIdRef.current = caseId;

    fetch(`/api/bff/agent/chat/history/${encodeURIComponent(caseId)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { messages?: Array<{ role: string; content: string }> } | null) => {
        if (!data?.messages?.length) return;
        const restored: ChatMessage[] = data.messages
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));
        if (restored.length > 0) {
          setMessages((current) => (current.length > 0 ? current : restored));
        }
      })
      .catch((err: unknown) => {
        console.warn("[useAgentStream] History load failed:", err);
      });
  }, [options.initialCaseId]);

  const finalizeAssistantTurn = useCallback((requestId: number) => {
    if (streamRequestIdRef.current !== requestId || finalizedRequestIdRef.current === requestId) {
      return;
    }

    const finalText = finalAssistantTextRef.current.trim();
    finalizedRequestIdRef.current = requestId;
    finalAssistantTextRef.current = "";
    setStreamingText("");

    if (!finalText) {
      return;
    }

    setMessages((existing) => {
      const lastMessage = existing[existing.length - 1];
      if (lastMessage?.role === "assistant" && lastMessage.content === finalText) {
        return existing;
      }
      return [...existing, { role: "assistant", content: finalText, timestamp: new Date().toISOString() }];
    });
  }, []);

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
              setActiveCaseId(payload.caseId);
              options.onCaseBound?.(payload.caseId);
              return;
            }

            if (type === "text_chunk" && typeof payload.text === "string") {
              finalAssistantTextRef.current += payload.text;
              setStreamingText(finalAssistantTextRef.current);
              return;
            }

            if (type === "state_update" && typeof payload.caseId === "string") {
              const stateUpdate = payload as unknown as AgentStateUpdateEvent;
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
    [activeCaseId, finalizeAssistantTurn, isStreaming, options],
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
