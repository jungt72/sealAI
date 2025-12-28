'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type UseChatSseV2Opts = {
  chatId?: string | null;
  token?: string | null;
  onToken?: (chunk: string) => void;
  onDone?: (finalText: string) => void;
  onStart?: (isRetry: boolean) => void;
  onAuthExpired?: () => void;
};

export type SseStatus = 'idle' | 'connecting' | 'streaming' | 'done' | 'retrying' | 'error';

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
  status: SseStatus;
  retryAttempt: number;
  retryMax: number;
  streaming: boolean;
  lastError: string | null;
  confirmCheckpoint: ConfirmCheckpointPayload | null;
  lastEventId: string | null;
  lastDoneEvent: { id: string | null; data: Record<string, unknown> } | null;
  send: (input: string, metadata?: Record<string, unknown>) => void;
  cancel: () => void;
  retryNow: () => void;
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

export function useChatSseV2({
  chatId,
  token,
  onToken,
  onDone,
  onStart,
  onAuthExpired,
}: UseChatSseV2Opts): SseState {
  const retryMax = 5;
  const [status, setStatus] = useState<SseStatus>('idle');
  const [retryAttempt, setRetryAttempt] = useState(0);
  const [streaming, setStreaming] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [confirmCheckpoint, setConfirmCheckpoint] = useState<ConfirmCheckpointPayload | null>(null);
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const [lastDoneEvent, setLastDoneEvent] = useState<{ id: string | null; data: Record<string, unknown> } | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const lastEventIdRef = useRef<string | null>(null);
  const retryRef = useRef<{ attempt: number; timer: ReturnType<typeof setTimeout> | null }>(
    { attempt: 0, timer: null },
  );
  const lastRequestRef = useRef<{ input: string; metadata?: Record<string, unknown> } | null>(null);
  const textBufferRef = useRef('');

  const endpointUrl = useMemo(() => ENDPOINT_URL, []);
  const connected = status !== 'idle' && status !== 'error';

  useEffect(() => {
    if (!chatId || typeof window === "undefined") {
      lastEventIdRef.current = null;
      setLastEventId(null);
      setLastDoneEvent(null);
      setStatus('idle');
      setRetryAttempt(0);
      retryRef.current.attempt = 0;
      if (retryRef.current.timer) clearTimeout(retryRef.current.timer);
      retryRef.current.timer = null;
      return;
    }
    const stored = sessionStorage.getItem(`${LAST_EVENT_STORAGE_PREFIX}${chatId}`);
    lastEventIdRef.current = stored;
    setLastEventId(stored);
    setLastDoneEvent(null);
  }, [chatId]);

  const abortStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const cancel = useCallback(() => {
    abortStream();
    setStatus('idle');
    retryRef.current.attempt = 0;
    setRetryAttempt(0);
    if (retryRef.current.timer) clearTimeout(retryRef.current.timer);
    retryRef.current.timer = null;
  }, [abortStream]);

  useEffect(() => {
    return () => {
      abortStream();
      if (retryRef.current.timer) clearTimeout(retryRef.current.timer);
      retryRef.current.timer = null;
    };
  }, [abortStream]);

  const clearRetryTimer = useCallback(() => {
    if (retryRef.current.timer) clearTimeout(retryRef.current.timer);
    retryRef.current.timer = null;
  }, []);

  const resetRetry = useCallback(() => {
    retryRef.current.attempt = 0;
    setRetryAttempt(0);
    clearRetryTimer();
  }, [clearRetryTimer]);

  const scheduleRetry = useCallback((reason: string) => {
    const attempt = retryRef.current.attempt;
    if (attempt >= retryMax) {
      setStatus('error');
      return;
    }
    setLastError(reason);
    setStatus('retrying');
    const delay = Math.min(1000 * 2 ** attempt, 15000);
    retryRef.current.attempt += 1;
    setRetryAttempt(retryRef.current.attempt);
    clearRetryTimer();
    retryRef.current.timer = setTimeout(() => {
      if (!lastRequestRef.current) {
        setStatus('error');
        return;
      }
      internalSend(lastRequestRef.current.input, lastRequestRef.current.metadata, true);
    }, delay);
  }, [clearRetryTimer, retryMax]);

  const internalSend = useCallback(
    async (input: string, metadata?: Record<string, unknown>, isRetry?: boolean) => {
      if (!endpointUrl) return;
      if (!chatId) return;
      if (!token) {
        setLastError("Nicht angemeldet (Token fehlt).");
        setStatus('error');
        onAuthExpired?.();
        return;
      }
      const trimmed = (input || '').trim();
      if (!trimmed) return;

      if (!isRetry) {
        resetRetry();
        lastRequestRef.current = { input: trimmed, metadata };
        textBufferRef.current = '';
        onStart?.(false);
      } else {
        onStart?.(true);
      }

      abortStream();
      setLastError(null);
      setConfirmCheckpoint(null);
      setLastDoneEvent(null);
      setStatus('connecting');

      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      const lastEventId = lastEventIdRef.current;
      let hasFirstChunk = false;
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
          if (res.status === 401 || res.status === 403) {
            setLastError(detail || `HTTP ${res.status}`);
            setStatus('error');
            setStreaming(false);
            abortRef.current = null;
            resetRetry();
            onAuthExpired?.();
            return;
          }
          scheduleRetry(detail || `HTTP ${res.status}`);
          setStreaming(false);
          abortRef.current = null;
          return;
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
            if (!hasFirstChunk) {
              hasFirstChunk = true;
              setStatus('streaming');
              resetRetry();
            }
            const { event, data, id } = parseSseFrame(part);
            if (id) {
              lastEventIdRef.current = id;
              if (chatId && typeof window !== "undefined") {
                sessionStorage.setItem(`${LAST_EVENT_STORAGE_PREFIX}${chatId}`, id);
              }
              setLastEventId(id);
            }
            if (event === 'token' && data && typeof data.text === 'string') {
              textBufferRef.current = `${textBufferRef.current}${data.text}`;
              onToken?.(data.text);
              continue;
            }
            if (event === 'confirm_checkpoint' && data && typeof data === 'object') {
              setConfirmCheckpoint(data as ConfirmCheckpointPayload);
              continue;
            }
            if (event === 'error') {
              const msg = data && typeof data.message === 'string' ? data.message : 'unknown error';
              setLastError(msg);
              setStatus('error');
              setStreaming(false);
              abortRef.current = null;
              resetRetry();
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
              setStatus('done');
              resetRetry();
              if (textBufferRef.current) onDone?.(textBufferRef.current);
              if (chatId && typeof window !== "undefined") {
                sessionStorage.removeItem(`${LAST_EVENT_STORAGE_PREFIX}${chatId}`);
              }
              return;
            }
          }
        }

        setStreaming(false);
        abortRef.current = null;
        setStatus('done');
        resetRetry();
        if (textBufferRef.current) onDone?.(textBufferRef.current);
      } catch (e: any) {
        if (e?.name === 'AbortError') return;
        scheduleRetry(String(e?.message || e));
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [abortStream, chatId, endpointUrl, onAuthExpired, onDone, onStart, onToken, resetRetry, scheduleRetry, token],
  );

  const send = useCallback(
    (input: string, metadata?: Record<string, unknown>) => {
      internalSend(input, metadata, false);
    },
    [internalSend],
  );

  const retryNow = useCallback(() => {
    if (!lastRequestRef.current) return;
    resetRetry();
    internalSend(lastRequestRef.current.input, lastRequestRef.current.metadata, true);
  }, [internalSend, resetRetry]);

  return {
    connected,
    status,
    retryAttempt,
    retryMax,
    streaming,
    lastError,
    confirmCheckpoint,
    lastEventId,
    lastDoneEvent,
    send,
    cancel,
    retryNow,
  };
}
