'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { emit } from "@/lib/telemetry";
import { fetchWithAuth } from "@/lib/fetchWithAuth";

type UseChatSseV2Opts = {
  chatId?: string | null;
  token?: string | null;
  tokenExpiresAt?: number | null;
  refreshAccessToken?: () => Promise<string | null>;
  onToken?: (chunk: string) => void;
  onDone?: (finalText: string) => void;
  onStart?: (isRetry: boolean) => void;
  onAuthExpired?: () => void;
  onStateDelta?: (
    delta: Record<string, unknown>,
    meta?: { event: string; id?: string | null },
    payload?: Record<string, unknown>,
  ) => void;
  onEvent?: (event: { event: string; data?: unknown; id?: string | null }) => void;
};

export type SseStatus = 'idle' | 'connecting' | 'streaming' | 'done' | 'retrying' | 'error';

export type ConfirmCheckpointPayload = {
  checkpoint_id: string;
  required_user_sub: string;
  conversation_id: string;
  action: string;
  risk: 'low' | 'med' | 'high';
  preview: {
    text?: string;
    summary?: string;
    parameters?: Record<string, unknown>;
    coverage_score?: number;
    coverage_gaps?: string[];
  };
  diff?: Record<string, unknown> | null;
  created_at: string;
};

type PendingCheckpointSignal = {
  checkpointId?: string | null;
  awaitingConfirmation?: boolean | null;
  checkpointPayload?: Record<string, unknown> | null;
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
  lastEvent: { event: string; data?: unknown; id?: string | null } | null;
  send: (input: string, metadata?: Record<string, unknown>) => void;
  cancel: () => void;
  retryNow: () => void;
};

const ENDPOINT_URL = "/api/chat";
const LAST_EVENT_STORAGE_PREFIX = "sealai:sse:last_event_id:";
// Preflight refresh keeps SSE from starting with near-expired tokens.
const PREEMPTIVE_REFRESH_WINDOW_SEC = 60;

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
  tokenExpiresAt,
  refreshAccessToken,
  onToken,
  onDone,
  onStart,
  onAuthExpired,
  onStateDelta,
  onEvent,
}: UseChatSseV2Opts): SseState {
  const retryMax = 5;
  const [status, setStatus] = useState<SseStatus>('idle');
  const [retryAttempt, setRetryAttempt] = useState(0);
  const [streaming, setStreaming] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [confirmCheckpoint, setConfirmCheckpoint] = useState<ConfirmCheckpointPayload | null>(null);
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const [lastDoneEvent, setLastDoneEvent] = useState<{ id: string | null; data: Record<string, unknown> } | null>(null);
  const [lastEvent, setLastEvent] = useState<{ event: string; data?: unknown; id?: string | null } | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const lastEventIdRef = useRef<string | null>(null);
  const retryRef = useRef<{ attempt: number; timer: ReturnType<typeof setTimeout> | null }>(
    { attempt: 0, timer: null },
  );
  const lastRequestRef = useRef<{ input: string; metadata?: Record<string, unknown> } | null>(null);
  const textBufferRef = useRef('');
  const internalSendRef = useRef<
    ((input: string, metadata?: Record<string, unknown>, isRetry?: boolean, didRefresh?: boolean) => void) | null
  >(null);
  const streamStartRef = useRef<number | null>(null);
  const ttftEmittedRef = useRef(false);
  const confirmCheckpointRef = useRef<ConfirmCheckpointPayload | null>(null);
  const tokenRef = useRef<string | null | undefined>(token);
  const tokenExpiresAtRef = useRef<number | null | undefined>(tokenExpiresAt);

  const endpointUrl = useMemo(() => ENDPOINT_URL, []);
  const connected = status !== 'idle' && status !== 'error';

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  useEffect(() => {
    tokenExpiresAtRef.current = tokenExpiresAt;
  }, [tokenExpiresAt]);

  useEffect(() => {
    if (!chatId || typeof window === "undefined") {
      lastEventIdRef.current = null;
      setLastEventId(null);
      setLastDoneEvent(null);
      setConfirmCheckpoint(null);
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
    setConfirmCheckpoint(null);
  }, [chatId]);

  useEffect(() => {
    confirmCheckpointRef.current = confirmCheckpoint;
  }, [confirmCheckpoint]);

  const buildCheckpointFromSignal = useCallback((signal: PendingCheckpointSignal): ConfirmCheckpointPayload | null => {
    const checkpointId = (signal.checkpointId || "").trim();
    if (!checkpointId) return null;
    const payload = signal.checkpointPayload && typeof signal.checkpointPayload === "object"
      ? signal.checkpointPayload
      : null;
    const preview =
      payload && typeof payload.preview === "object"
        ? (payload.preview as ConfirmCheckpointPayload["preview"])
        : {
            text: undefined,
            summary: undefined,
            parameters: undefined,
            coverage_score: undefined,
            coverage_gaps: undefined,
          };
    return {
      checkpoint_id: checkpointId,
      required_user_sub: String(payload?.required_user_sub || ""),
      conversation_id: String(payload?.conversation_id || chatId || ""),
      action: String(payload?.action || "CONFIRM"),
      risk: (payload?.risk as ConfirmCheckpointPayload["risk"]) || "med",
      preview,
      diff: (payload?.diff as Record<string, unknown> | null) ?? null,
      created_at: String(payload?.created_at || new Date().toISOString()),
    };
  }, [chatId]);

  const extractPendingCheckpointSignal = useCallback((data: Record<string, unknown>): PendingCheckpointSignal => {
    const checkpointId =
      typeof data.confirm_checkpoint_id === "string"
        ? data.confirm_checkpoint_id
        : typeof data.checkpoint_id === "string"
          ? data.checkpoint_id
          : null;
    const awaitingConfirmation =
      typeof data.awaiting_user_confirmation === "boolean"
        ? data.awaiting_user_confirmation
        : null;
    const checkpointPayload =
      data.confirm_checkpoint && typeof data.confirm_checkpoint === "object"
        ? (data.confirm_checkpoint as Record<string, unknown>)
        : null;
    return { checkpointId, awaitingConfirmation, checkpointPayload };
  }, []);

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
    const retryState = retryRef.current;
    return () => {
      abortStream();
      if (retryState.timer) clearTimeout(retryState.timer);
      retryState.timer = null;
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

  const scheduleRetry = useCallback((reason: string, didRefresh?: boolean) => {
    const attempt = retryRef.current.attempt;
    if (attempt >= retryMax) {
      setStatus('error');
      return;
    }
    emit({
      type: "chat_retry",
      chatId: chatId ?? "unknown",
      attempt: attempt + 1,
      reason,
    });
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
      internalSendRef.current?.(
        lastRequestRef.current.input,
        lastRequestRef.current.metadata,
        true,
        didRefresh,
      );
    }, delay);
  }, [chatId, clearRetryTimer, retryMax]);

  const internalSend = useCallback(
    async (
      input: string,
      metadata?: Record<string, unknown>,
      isRetry?: boolean,
      didRefresh?: boolean,
    ) => {
      if (!endpointUrl) return;
      if (!chatId) return;
      const now = Math.floor(Date.now() / 1000);
      const exp = tokenExpiresAtRef.current;
      if (exp && now >= exp) {
        console.warn("SSE start requested with expired token.");
      }
      if (exp && now >= exp - PREEMPTIVE_REFRESH_WINDOW_SEC) {
        if (refreshAccessToken) {
          const refreshed = await refreshAccessToken();
          if (refreshed) {
            tokenRef.current = refreshed;
          } else {
            setLastError("Sitzung abgelaufen (Token-Refresh fehlgeschlagen).");
            setStatus('error');
            onAuthExpired?.();
            return;
          }
        }
      }
      const activeToken = tokenRef.current ?? token;
      if (!activeToken) {
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
        streamStartRef.current = performance.now();
        ttftEmittedRef.current = false;
        onStart?.(false);
      } else {
        streamStartRef.current = performance.now();
        ttftEmittedRef.current = false;
        onStart?.(true);
      }

      abortStream();
      setLastError(null);
      if (!confirmCheckpointRef.current) {
        setConfirmCheckpoint(null);
      }
      setLastDoneEvent(null);
      setStatus('connecting');

      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      const lastEventId = lastEventIdRef.current;
      let hasFirstChunk = false;
      try {
        const res = await fetchWithAuth(endpointUrl, activeToken, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
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
            if (refreshAccessToken && !didRefresh) {
              const refreshed = await refreshAccessToken();
              if (refreshed) {
                tokenRef.current = refreshed;
                scheduleRetry("auth_refresh", true);
                setStreaming(false);
                abortRef.current = null;
                return;
              }
            }
            emit({
              type: "chat_error",
              chatId: chatId ?? "unknown",
              code: res.status,
            });
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
              if (!ttftEmittedRef.current && streamStartRef.current !== null) {
                emit({
                  type: "chat_ttft",
                  chatId: chatId ?? "unknown",
                  ms: performance.now() - streamStartRef.current,
                });
                ttftEmittedRef.current = true;
              }
            }
            const { event, data, id } = parseSseFrame(part);
            if (id) {
              lastEventIdRef.current = id;
              if (chatId && typeof window !== "undefined") {
                sessionStorage.setItem(`${LAST_EVENT_STORAGE_PREFIX}${chatId}`, id);
              }
              setLastEventId(id);
            }
            if (event) {
              const evtPayload = { event, data, id: id ?? null };
              setLastEvent(evtPayload);
              onEvent?.(evtPayload);
            }
            if (event === 'token' && data && typeof data.text === 'string') {
              textBufferRef.current = `${textBufferRef.current}${data.text}`;
              onToken?.(data.text);
              continue;
            }
            if (
              event &&
              ["state_update", "state", "partial_state", "patch", "parameter_update"].includes(event) &&
              data &&
              typeof data === "object"
            ) {
              const payload = data as Record<string, unknown>;
              const delta =
                payload.delta && typeof payload.delta === "object"
                  ? (payload.delta as Record<string, unknown>)
                  : payload;
              const signal = extractPendingCheckpointSignal(payload);
              const deltaSignal = payload !== delta ? extractPendingCheckpointSignal(delta) : signal;
              const mergedSignal: PendingCheckpointSignal = {
                checkpointId: signal.checkpointId || deltaSignal.checkpointId,
                awaitingConfirmation:
                  signal.awaitingConfirmation !== null ? signal.awaitingConfirmation : deltaSignal.awaitingConfirmation,
                checkpointPayload: signal.checkpointPayload || deltaSignal.checkpointPayload,
              };
              const nextCheckpoint = buildCheckpointFromSignal(mergedSignal);
              if (nextCheckpoint) {
                setConfirmCheckpoint((prev) => {
                  if (prev?.checkpoint_id === nextCheckpoint.checkpoint_id) return prev;
                  return nextCheckpoint;
                });
              } else if (
                mergedSignal.awaitingConfirmation === false ||
                Object.prototype.hasOwnProperty.call(payload, "confirm_checkpoint_id") ||
                Object.prototype.hasOwnProperty.call(payload, "checkpoint_id")
              ) {
                const hasId =
                  typeof mergedSignal.checkpointId === "string" && mergedSignal.checkpointId.trim().length > 0;
                if (!hasId && confirmCheckpointRef.current) {
                  setConfirmCheckpoint(null);
                }
              }
              onStateDelta?.(delta, { event, id: id ?? null }, payload);
              continue;
            }
            if ((event === 'checkpoint_required' || event === 'confirm_checkpoint') && data && typeof data === 'object') {
              const signal = extractPendingCheckpointSignal(data as Record<string, unknown>);
              const nextCheckpoint = buildCheckpointFromSignal({
                checkpointId: signal.checkpointId || (data as any)?.checkpoint_id,
                awaitingConfirmation: signal.awaitingConfirmation,
                checkpointPayload: (data as Record<string, unknown>) || null,
              });
              setConfirmCheckpoint(nextCheckpoint ?? (data as ConfirmCheckpointPayload));
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
              if (streamStartRef.current !== null) {
                emit({
                  type: "chat_stream_done",
                  chatId: chatId ?? "unknown",
                  ms: performance.now() - streamStartRef.current,
                });
                streamStartRef.current = null;
              }
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
        if (streamStartRef.current !== null) {
          emit({
            type: "chat_stream_done",
            chatId: chatId ?? "unknown",
            ms: performance.now() - streamStartRef.current,
          });
          streamStartRef.current = null;
        }
        if (textBufferRef.current) onDone?.(textBufferRef.current);
      } catch (e: any) {
        if (e?.name === 'AbortError') return;
        scheduleRetry(String(e?.message || e));
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [
      abortStream,
      chatId,
      endpointUrl,
      onAuthExpired,
      onDone,
      onStart,
      onToken,
      onStateDelta,
      refreshAccessToken,
      resetRetry,
      scheduleRetry,
      token,
    ],
  );

  const send = useCallback(
    (input: string, metadata?: Record<string, unknown>) => {
      internalSend(input, metadata, false);
    },
    [internalSend],
  );

  useEffect(() => {
    internalSendRef.current = internalSend;
  }, [internalSend]);

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
    lastEvent,
    send,
    cancel,
    retryNow,
  };
}
