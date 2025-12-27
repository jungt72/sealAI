'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type UseChatSseV2Opts = {
  chatId?: string | null;
  token?: string | null;
};

export type ConfirmCheckpointPayload = {
  type: 'confirm_checkpoint';
  phase?: string;
  recommendation_go?: boolean;
  coverage_score?: number;
  coverage_gaps?: string[];
  missing_core?: string[];
  text?: string;
};

type SseState = {
  connected: boolean;
  streaming: boolean;
  text: string;
  lastError: string | null;
  confirmCheckpoint: ConfirmCheckpointPayload | null;
  lastEventId: string | null;
  lastDoneEvent: { id: string | null; data: Record<string, unknown> } | null;
  send: (input: string, metadata?: Record<string, unknown>) => void;
  cancel: () => void;
};

const ENDPOINT_URL = "/api/chat";
const LAST_EVENT_STORAGE_PREFIX = "sealai:sse:last_event_id:";

function parseSseFrame(frame: string): { event?: string; data?: any; id?: string } {
  const lines = frame.split('\n').map(l => l.trimEnd());
  let event: string | undefined;
  let id: string | undefined;
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith('id:')) id = line.slice('id:'.length).trim();
    if (line.startsWith('event:')) event = line.slice('event:'.length).trim();
    if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trim());
  }
  const dataRaw = dataLines.join('\n');
  if (!dataRaw) return { event };
  try {
    return { event, data: JSON.parse(dataRaw), id };
  } catch {
    return { event, data: dataRaw, id };
  }
}

export function useChatSseV2({ chatId, token }: UseChatSseV2Opts): SseState {
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState('');
  const [lastError, setLastError] = useState<string | null>(null);
  const [confirmCheckpoint, setConfirmCheckpoint] = useState<ConfirmCheckpointPayload | null>(null);
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const [lastDoneEvent, setLastDoneEvent] = useState<{ id: string | null; data: Record<string, unknown> } | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const lastEventIdRef = useRef<string | null>(null);

  const endpointUrl = useMemo(() => ENDPOINT_URL, []);

  useEffect(() => {
    setConnected(Boolean(endpointUrl));
  }, [endpointUrl]);

  useEffect(() => {
    if (!chatId || typeof window === "undefined") {
      lastEventIdRef.current = null;
      setLastEventId(null);
      setLastDoneEvent(null);
      return;
    }
    const stored = sessionStorage.getItem(`${LAST_EVENT_STORAGE_PREFIX}${chatId}`);
    lastEventIdRef.current = stored;
    setLastEventId(stored);
    setLastDoneEvent(null);
  }, [chatId]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const send = useCallback(
    async (input: string, metadata?: Record<string, unknown>) => {
      if (!endpointUrl) return;
      if (!chatId) return;
      if (!token) {
        setLastError("Nicht angemeldet (Token fehlt).");
        return;
      }
      const trimmed = (input || '').trim();
      if (!trimmed) return;

      cancel();
      setLastError(null);
      setText('');
      setConfirmCheckpoint(null);
      setLastDoneEvent(null);

      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      const lastEventId = lastEventIdRef.current;
      try {
        const res = await fetch(endpointUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            Authorization: `Bearer ${token}`,
            ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
          },
          body: JSON.stringify({
            input: trimmed,
            chat_id: chatId,
            client_msg_id: (typeof crypto !== "undefined" && "randomUUID" in crypto)
              ? crypto.randomUUID()
              : `${Date.now()}-${Math.random().toString(16).slice(2)}`,
            ...(metadata && Object.keys(metadata).length ? { metadata } : {}),
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          const detail = await res.text().catch(() => "");
          throw new Error(detail || `HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';

          for (const part of parts) {
            const { event, data, id } = parseSseFrame(part);
            if (id) {
              lastEventIdRef.current = id;
              if (chatId && typeof window !== "undefined") {
                sessionStorage.setItem(`${LAST_EVENT_STORAGE_PREFIX}${chatId}`, id);
              }
              setLastEventId(id);
            }
            if (event === 'token' && data && typeof data.text === 'string') {
              setText(prev => prev + data.text);
              continue;
            }
            if (event === 'confirm_checkpoint' && data && typeof data === 'object') {
              setConfirmCheckpoint(data as ConfirmCheckpointPayload);
              continue;
            }
            if (event === 'error') {
              const msg = data && typeof data.message === 'string' ? data.message : 'unknown error';
              setLastError(msg);
              setStreaming(false);
              abortRef.current = null;
              if (chatId && typeof window !== "undefined") {
                sessionStorage.removeItem(`${LAST_EVENT_STORAGE_PREFIX}${chatId}`);
              }
              return;
            }
            if (event === 'done') {
              const payload =
                data && typeof data === "object" ? (data as Record<string, unknown>) : {};
              setLastDoneEvent({ id: id ?? null, data: payload });
              setStreaming(false);
              abortRef.current = null;
              if (chatId && typeof window !== "undefined") {
                sessionStorage.removeItem(`${LAST_EVENT_STORAGE_PREFIX}${chatId}`);
              }
              return;
            }
          }
        }

        setStreaming(false);
        abortRef.current = null;
      } catch (e: any) {
        if (e?.name === 'AbortError') return;
        setLastError(String(e?.message || e));
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [cancel, chatId, endpointUrl, token],
  );

  return {
    connected,
    streaming,
    text,
    lastError,
    confirmCheckpoint,
    lastEventId,
    lastDoneEvent,
    send,
    cancel,
  };
}
