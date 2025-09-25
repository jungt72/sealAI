'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type UseChatWsOpts = {
  chatId: string;
  token?: string | null; // Keycloak Access Token
};

type WsState = {
  connected: boolean;
  streaming: boolean;
  text: string;
  lastError: string | null;
  send: (input: string, params?: Record<string, any>) => void;
  cancel: () => void;
};

function buildWsUrl(token?: string | null) {
  if (typeof window === 'undefined') return '';
  const { protocol, host } = window.location;
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:';
  const qp = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${wsProto}//${host}/api/v1/ai/ws${qp}`;
}

// kleine Helfer
function safeParse(data: string) {
  try { return JSON.parse(data); } catch { return data; }
}

export function useChatWs({ chatId, token }: UseChatWsOpts): WsState {
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState('');
  const [lastError, setLastError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const backoffRef = useRef(1000);
  const lastThreadIdRef = useRef<string | null>(null);
  const firedNeedParamsRef = useRef(false);

  const url = useMemo(() => buildWsUrl(token), [token]);

  const clearHeartbeat = () => {
    if (heartbeatRef.current) {
      window.clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  };

  const startHeartbeat = () => {
    clearHeartbeat();
    heartbeatRef.current = window.setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping', ts: Date.now() }));
      }
    }, 12_000);
  };

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) return;
    const delay = Math.min(backoffRef.current, 10_000);
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
      backoffRef.current = Math.min(backoffRef.current * 2, 10_000);
    }, delay) as unknown as number;
  }, []);

  const cleanup = useCallback(() => {
    clearHeartbeat();
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    try { wsRef.current?.close(); } catch {}
    wsRef.current = null;
    setConnected(false);
    setStreaming(false);
  }, []);

  // ---- zentrale UI-Event-Brücke ----
  const emitUiAction = useCallback((ua: any) => {
    try {
      // Normalisieren
      const payload = typeof ua === 'object' && ua !== null
        ? ua
        : { ui_action: String(ua || '') };

      // einheitliches CustomEvent
      window.dispatchEvent(new CustomEvent('sealai:ui', { detail: payload }));
      window.dispatchEvent(new CustomEvent('sealai:ui_action', { detail: payload }));
    } catch {}
  }, []);

  // Wenn Text-Rückfrage nach Pflichtfeldern erkannt wird, Sidebar öffnen
  const maybeOpenFormFromText = useCallback((s: string) => {
    if (firedNeedParamsRef.current) return;
    if (!s) return;
    if (/(mir fehlen.*angaben|kannst du.*bitte nennen|präzise.*empfehlung.*brauche.*noch kurz|in einer zeile.*angabe)/i.test(s)) {
      firedNeedParamsRef.current = true;
      emitUiAction({ ui_action: 'open_form' });
    }
  }, [emitUiAction]);

  const handleMessage = useCallback((ev: MessageEvent) => {
    const payload: any = typeof ev.data === 'string' ? safeParse(ev.data) : ev.data;
    if (!payload) return;

    // Roh-Frames ignorieren
    if (payload?.event === 'idle') return;
    if (payload?.event === 'error' && payload?.code === 'idle_timeout') return;

    // ---- Debug-Routing (z. B. ask_missing) -> sofort Formular öffnen
    if (payload?.event === 'dbg') {
      const node = (payload?.meta?.langgraph_node || payload?.meta?.run_name || '').toString().toLowerCase();
      if (node === 'ask_missing' && !firedNeedParamsRef.current) {
        firedNeedParamsRef.current = true;
        emitUiAction({ ui_action: 'open_form' });
      }
    }

    // ---- UI-Event: unterstützt event:'ui_action', ui_event:{} oder ui_action:'open_form'
    if (payload?.event === 'ui_action' || payload?.ui_event || typeof payload?.ui_action !== 'undefined') {
      const ua = typeof payload?.ui_action === 'string'
        ? { ui_action: payload.ui_action }
        : (payload?.ui_event && typeof payload.ui_event === 'object' ? payload.ui_event : payload);
      emitUiAction(ua);
    }

    switch (payload.event) {
      case 'start':
        lastThreadIdRef.current = payload.thread_id ?? null;
        setStreaming(true);
        setText('');
        break;

      case 'token': {
        const delta: string = payload.delta ?? '';
        if (delta) {
          setText(prev => prev + delta);
          maybeOpenFormFromText(delta);
        }
        break;
      }

      case 'final': {
        const t: string = payload.text ?? '';
        if (t) {
          setText(t);
          maybeOpenFormFromText(t);
        }
        break;
      }

      case 'done':
        setStreaming(false);
        backoffRef.current = 1000;
        break;

      case 'error':
        setLastError(payload.message || 'Unbekannter Fehler');
        setStreaming(false);
        break;

      case 'pong':
        break;

      default:
        // Falls ein Textfeld außerhalb obiger Events kommt (LCEL frames o.ä.)
        const maybeText =
          payload?.message?.data?.content ??
          payload?.message?.content ??
          payload?.content;
        if (typeof maybeText === 'string') {
          setText(prev => prev + maybeText);
          maybeOpenFormFromText(maybeText);
        }
        break;
    }
  }, [emitUiAction, maybeOpenFormFromText]);

  const connect = useCallback(() => {
    if (!url) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(url, 'json');
      wsRef.current = ws;
      setLastError(null);

      ws.onopen = () => {
        setConnected(true);
        backoffRef.current = 1000;
        firedNeedParamsRef.current = false;
        startHeartbeat();
      };

      ws.onmessage = handleMessage;
      ws.onerror = () => setLastError('WebSocket Fehler');
      ws.onclose = () => {
        setConnected(false);
        setStreaming(false);
        clearHeartbeat();
        scheduleReconnect();
      };
    } catch (e: any) {
      setLastError(e?.message ?? 'Verbindungsfehler');
      scheduleReconnect();
    }
  }, [handleMessage, scheduleReconnect, url]);

  useEffect(() => {
    if (!token) return;
    connect();
    return () => cleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  const send = useCallback(
    (input: string, params?: Record<string, any>) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        setLastError('Nicht verbunden');
        return;
      }
      setStreaming(true);
      setText('');
      firedNeedParamsRef.current = false;

      // Graph-Modus + expliziter Graph-Name (consult), damit der Consult-Flow sicher läuft
      const payload: any = { chat_id: chatId, input, mode: 'graph', graph: 'consult' };
      if (params && typeof params === 'object') payload.params = params;

      try {
        ws.send(JSON.stringify(payload));
      } catch (e: any) {
        setLastError(e?.message ?? 'Senden fehlgeschlagen');
        setStreaming(false);
      }
    },
    [chatId]
  );

  const cancel = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const threadId = lastThreadIdRef.current || `api:${chatId}`;
    try {
      ws.send(JSON.stringify({ type: 'cancel', chat_id: chatId, thread_id: threadId }));
    } catch {}
    setStreaming(false);
  }, [chatId]);

  return { connected, streaming, text, lastError, send, cancel };
}
