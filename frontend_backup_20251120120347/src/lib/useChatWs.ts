"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useChatThreadId } from "@/lib/useChatThreadId";
import type { Message } from "@/types/chat";
import type { ChatMeta } from "@/types/chatMeta";

export type LanggraphTokenEvent = {
  type: "token";
  event?: "token";
  text: string;
  role?: string;
  [key: string]: unknown;
};

export type LanggraphMessageEvent = {
  type: "message";
  event?: "message";
  text: string;
  [key: string]: unknown;
};

export type LanggraphMetaEvent = {
  type: "meta";
  event?: "meta";
  slots?: Record<string, unknown>;
  routing?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  thread_id?: string;
  user_id?: string;
  [key: string]: unknown;
};

export type LanggraphDoneEvent = {
  type: "done";
  event?: "done";
  [key: string]: unknown;
};

export type LanggraphErrorEvent = {
  type: "error";
  event?: "error";
  message?: string;
  [key: string]: unknown;
};

export type LanggraphToolEvent = {
  type: "tool";
  event?: "tool";
  output: string;
  [key: string]: unknown;
};

export type LanggraphWsEvent =
  | LanggraphTokenEvent
  | LanggraphMessageEvent
  | LanggraphMetaEvent
  | LanggraphDoneEvent
  | LanggraphErrorEvent
  | LanggraphToolEvent;

export type UseChatWsArgs = {
  chatId: string | null;
  token: string | null;
  consent: boolean;
  onEvent?: (event: LanggraphWsEvent) => void;
};

export type UseChatWsResult = {
  connected: boolean;
  isStreaming: boolean;
  messages: Message[];
  meta: ChatMeta | null;
  lastError: string | null;
  threadId: string | null;
  lastEvent: LanggraphWsEvent | null;
  sendMessage: (
    input: string,
    options?: { extra?: Record<string, unknown> },
  ) => void;
  cancel: () => void;
};

const buildWsUrl = (token: string | null, chatId: string | null): string | null => {
  if (typeof window === "undefined") return null;
  if (!token) return null;

  const base =
    process.env.NEXT_PUBLIC_AI_WS_URL && process.env.NEXT_PUBLIC_AI_WS_URL.length > 0
      ? process.env.NEXT_PUBLIC_AI_WS_URL
      : (() => {
          const { protocol, host } = window.location;
          const wsProto = protocol === "https:" ? "wss:" : "ws:";
          return `${wsProto}//${host}/api/v1/langgraph/chat/ws`;
        })();

  const url = new URL(base);
  url.searchParams.set("token", token);
  if (chatId) {
    url.searchParams.set("chat_id", chatId);
  }
  return url.toString();
};

const makeId = (prefix: string) =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

const ALLOWED_EVENT_TYPES: LanggraphWsEvent["type"][] = ["token", "message", "meta", "done", "error", "tool"];

const normalizeEvent = (value: unknown): LanggraphWsEvent | null => {
  if (typeof value !== "object" || value === null) return null;
  const raw = value as Record<string, unknown>;
  const rawType = typeof raw.type === "string" ? raw.type : undefined;
  const rawEvent = typeof raw.event === "string" ? raw.event : undefined;

  let normalizedType = rawType || rawEvent;
  if (normalizedType === "final") {
    normalizedType = "done";
  }

  if (!normalizedType || !ALLOWED_EVENT_TYPES.includes(normalizedType as LanggraphWsEvent["type"])) {
    return null;
  }

  return { ...raw, type: normalizedType as LanggraphWsEvent["type"] };
};

const isIntentDebugText = (text: string): boolean => {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return false;
  try {
    const obj = JSON.parse(trimmed);
    if (!obj || typeof obj !== "object") return false;
    const lowerKeys = new Set(Object.keys(obj as Record<string, unknown>).map((k) => k.toLowerCase()));
    const hasIntentShape =
      lowerKeys.has("type") &&
      lowerKeys.has("confidence") &&
      (lowerKeys.has("reason") || lowerKeys.has("task"));
    const hasAnswerField = lowerKeys.has("answer") || lowerKeys.has("text") || lowerKeys.has("message") || lowerKeys.has("content");
    return hasIntentShape && !hasAnswerField;
  } catch {
    return false;
  }
};

const deriveMeta = (payload: LanggraphMetaEvent): ChatMeta | null => {
  if (!payload || typeof payload !== "object") return null;
  if (payload.meta && typeof payload.meta === "object") {
    return { ...(payload.meta as ChatMeta) };
  }
  return null;
};

const INTENT_FALLBACK_REPLY =
  "Vielen Dank für Ihre Nachricht.\n" +
  "Damit ich Sie gezielt unterstützen kann: Wünschen Sie eher\n" +
  "1) eine kurze Übersicht zu den wichtigsten Eigenschaften oder\n" +
  "2) eine ausführlichere technische Beratung mit konkreten Empfehlungen für Ihre Anwendung?\n" +
  "Wenn Sie möchten, können Sie kurz etwas zu Medium, Temperatur, Druck und Bewegungsart Ihrer Anwendung schreiben.";

export function useChatWs(args: UseChatWsArgs): UseChatWsResult {
  const { chatId, token, consent, onEvent } = args;
  const threadFromHook = useChatThreadId();
  const threadId = chatId ?? threadFromHook;
  const effectiveThreadId = threadId ?? "default";

  const [connected, setConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [meta, setMeta] = useState<ChatMeta | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastEvent, setLastEvent] = useState<LanggraphWsEvent | null>(null);
  const [retryTrigger, setRetryTrigger] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const assistantMessageIdRef = useRef<string | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const streamedTokenRef = useRef(false);

  const resetStreamMessage = useCallback(() => {
    assistantMessageIdRef.current = null;
    streamedTokenRef.current = false;
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (typeof window === "undefined") return;
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
    }
    const attempt = reconnectAttemptRef.current;
    const delay = Math.min(500 + attempt * 500, 5000);
    reconnectTimerRef.current = window.setTimeout(() => {
      setRetryTrigger((prev) => prev + 1);
    }, delay);
    reconnectAttemptRef.current = attempt + 1;
  }, [setRetryTrigger]);

  const appendAssistant = useCallback((text: string, replace = false) => {
    setMessages((prev) => {
      const now = new Date().toISOString();
      const lastId = assistantMessageIdRef.current;
      if (lastId) {
        const idx = prev.findIndex((msg) => msg.id === lastId);
        if (idx !== -1) {
          const updated = [...prev];
          const existing = updated[idx];
          updated[idx] = {
            ...existing,
            content: replace ? text : `${existing.content || ""}${text}`,
            createdAt: existing.createdAt || now,
          };
          return updated;
        }
      }
      const newId = `assistant-${makeId("assistant")}`;
      assistantMessageIdRef.current = newId;
      return [
        ...prev,
        {
          id: newId,
          role: "assistant",
          content: replace ? text : text,
          createdAt: now,
        },
      ];
    });
  }, []);

  const handleToken = useCallback(
    (event: LanggraphTokenEvent) => {
      const text = event.text || "";
      if (!text || isIntentDebugText(text)) return;
      setIsStreaming(true);
      streamedTokenRef.current = true;
      appendAssistant(text);
    },
    [appendAssistant],
  );

  const handleMessage = useCallback(
    (event: LanggraphMessageEvent) => {
      const text = event.text || "";
      setIsStreaming(false);
      if (streamedTokenRef.current) {
        // Token-Stream lief bereits – nur anhängen, falls echter Text und kein Intent-Debug-JSON.
        if (text && !isIntentDebugText(text)) {
          appendAssistant(text);
        }
      } else if (text && !isIntentDebugText(text)) {
        appendAssistant(text, true);
      }
      streamedTokenRef.current = false;
      resetStreamMessage();
    },
    [appendAssistant, resetStreamMessage],
  );

  const handleMeta = useCallback((event: LanggraphMetaEvent) => {
    setMeta(deriveMeta(event));
  }, []);

  const scrubIntentDebugMessage = useCallback(() => {
    setMessages((prev) => {
      if (!prev.length) return prev;
      const idx = [...prev].reverse().findIndex((msg) => msg.role === "assistant");
      if (idx === -1) return prev;
      const targetIndex = prev.length - 1 - idx;
      const target = prev[targetIndex];
      if (typeof target.content !== "string" || !isIntentDebugText(target.content)) {
        return prev;
      }
      const updated = [...prev];
      updated[targetIndex] = { ...target, content: INTENT_FALLBACK_REPLY };
      return updated;
    });
  }, []);

  const handleDone = useCallback(() => {
    setIsStreaming(false);
    streamedTokenRef.current = false;
    scrubIntentDebugMessage();
    resetStreamMessage();
  }, [resetStreamMessage, scrubIntentDebugMessage]);

  const handleError = useCallback((event: LanggraphErrorEvent) => {
    setIsStreaming(false);
    streamedTokenRef.current = false;
    setLastError(event.message || "Unbekannter Fehler");
    setMessages((prev) => [
      ...prev,
      {
        id: `system-${makeId("sys")}`,
        role: "system",
        content:
          event.message ||
          "Die Verbindung wurde unterbrochen. Bitte versuche es erneut.",
        createdAt: new Date().toISOString(),
      },
    ]);
  }, []);

  const handleIncomingEvent = useCallback(
    (payload: LanggraphWsEvent) => {
      setLastEvent(payload);
      switch (payload.type) {
        case "token":
          handleToken(payload as LanggraphTokenEvent);
          break;
        case "message":
          handleMessage(payload as LanggraphMessageEvent);
          break;
        case "meta":
          handleMeta(payload as LanggraphMetaEvent);
          break;
        case "done":
          handleDone();
          break;
        case "error":
          handleError(payload as LanggraphErrorEvent);
          break;
        default:
          break;
      }
      onEvent?.(payload);
    },
    [handleToken, handleMessage, handleMeta, handleDone, handleError, onEvent],
  );

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!token) {
      setConnected(false);
      return;
    }

    const url = buildWsUrl(token, effectiveThreadId);
    if (!url) {
      setConnected(false);
      return;
    }

    let isActive = true;
    const socket = new WebSocket(url);
    wsRef.current = socket;
    setConnected(false);

    socket.onopen = () => {
      if (!isActive) return;
      setConnected(true);
      setLastError(null);
      reconnectAttemptRef.current = 0;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    socket.onclose = (event) => {
      if (wsRef.current === socket) {
        wsRef.current = null;
      }
      setConnected(false);
      setIsStreaming(false);

      if (!isActive) return;
      if (event.code !== 1000) {
        scheduleReconnect();
      }
    };

    socket.onerror = () => {
      setLastError("WebSocket-Fehler");
    };

    socket.onmessage = (event) => {
      let data: unknown;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      const normalized = normalizeEvent(data);
      if (!normalized) return;
      handleIncomingEvent(normalized);
    };

    return () => {
      isActive = false;
      if (socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, [token, effectiveThreadId, handleIncomingEvent, retryTrigger, scheduleReconnect]);

  useEffect(() => {
    setMessages([]);
    setIsStreaming(false);
    setLastError(null);
    setMeta(null);
    resetStreamMessage();
  }, [threadId, resetStreamMessage]);

  const sendMessage = useCallback(
    (input: string, options?: { extra?: Record<string, unknown> }) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      const payload: Record<string, unknown> = {
        input,
        thread_id: effectiveThreadId,
        chat_id: effectiveThreadId,
        consent,
        ...options?.extra,
      };
      wsRef.current.send(JSON.stringify(payload));
      const now = new Date().toISOString();
      setMessages((prev) => [
        ...prev,
        {
          id: `user-${makeId("user")}`,
          role: "user",
          content: input,
          createdAt: now,
        },
      ]);
      setIsStreaming(true);
      resetStreamMessage();
      console.debug("WS payload", payload);
    },
    [threadId, consent, resetStreamMessage],
  );

  const cancel = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    try {
      wsRef.current.send(JSON.stringify({ event: "cancel" }));
    } catch {
      // ignore
    }
  }, []);

  return {
    connected,
    isStreaming,
    messages,
    meta,
    lastError,
    threadId,
    lastEvent,
    sendMessage,
    cancel,
  };
}
