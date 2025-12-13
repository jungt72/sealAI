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
  send: (input: string) => void;
  cancel: () => void;
};

function buildEndpointUrl() {
  if (typeof window === 'undefined') return '';
  const { origin } = window.location;
  return `${origin}/api/v1/langgraph/chat/v2`;
}

function parseSseFrame(frame: string): { event?: string; data?: any } {
  const lines = frame.split('\n').map(l => l.trimEnd());
  let event: string | undefined;
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith('event:')) event = line.slice('event:'.length).trim();
    if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trim());
  }
  const dataRaw = dataLines.join('\n');
  if (!dataRaw) return { event };
  try {
    return { event, data: JSON.parse(dataRaw) };
  } catch {
    return { event, data: dataRaw };
  }
}

export function useChatSseV2({ chatId, token }: UseChatSseV2Opts): SseState {
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState('');
  const [lastError, setLastError] = useState<string | null>(null);
  const [confirmCheckpoint, setConfirmCheckpoint] = useState<ConfirmCheckpointPayload | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const endpointUrl = useMemo(() => buildEndpointUrl(), []);

  useEffect(() => {
    setConnected(Boolean(endpointUrl));
  }, [endpointUrl]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const send = useCallback(
    async (input: string) => {
      if (!endpointUrl) return;
      if (!chatId) return;
      const trimmed = (input || '').trim();
      if (!trimmed) return;

      cancel();
      setLastError(null);
      setText('');
      setConfirmCheckpoint(null);

      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      try {
        const res = await fetch(endpointUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ input: trimmed, chat_id: chatId }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
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
            const { event, data } = parseSseFrame(part);
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
              return;
            }
            if (event === 'done') {
              setStreaming(false);
              abortRef.current = null;
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

  return { connected, streaming, text, lastError, confirmCheckpoint, send, cancel };
}
