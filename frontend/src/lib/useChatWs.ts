'use client';

import { useEffect, useRef, useState } from 'react';

/* -------------------------------------------------
   Nachricht‑Typen
--------------------------------------------------*/
export interface ChatMessage {
  role: 'user' | 'assistant';        // ← *tool* wird unten in 'assistant' gemappt
  content: string;
}

/* -------------------------------------------------
   Heuristik: Ist es ein einfacher Klartext‑Chunk?
--------------------------------------------------*/
function isSingleChunk(str: string): boolean {
  return (
    typeof str === 'string' &&
    str.length > 0 &&                 // ✓ bool statt number
    !str.includes('additional_kwargs') &&
    !str.includes('response_metadata') &&
    !str.includes("content='") &&
    !str.includes("id='run-")
  );
}

/* -------------------------------------------------
   WebSocket‑Hook
--------------------------------------------------*/
export function useChatWs(token?: string) {
  const [ws,        setWs]        = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages,  setMessages]  = useState<ChatMessage[]>([]);
  const chatIdRef                 = useRef('default');

  /* -------- Verbindungs‑Lifecycle -------- */
  useEffect(() => {
    if (!token) { setConnected(false); setWs(null); return; }

    const url  = buildWsUrl(
      `/api/v1/ai/ws?token=${encodeURIComponent(token)}&json_stream=1`
    );
    const sock = new WebSocket(url, 'json');
    setWs(sock);

    sock.onopen  = () => setConnected(true);
    sock.onclose = () => { setConnected(false); setWs(null); };
    sock.onerror = e  => console.error('❌  WS‑Error', e);

    /* -------- eingehende Nachrichten -------- */
    sock.onmessage = e => {
      try {
        const parsed = JSON.parse(e.data);

        if (parsed.type === 'error') {
          console.error('WS‑Error‑Payload', parsed);
          return;
        }

        /* ----- OpenAI‑Fallback (alt) ----- */
        if (parsed.choices?.[0]?.delta) {
          const chunk = parsed.choices[0].delta.content;
          if (isSingleChunk(chunk)) pushChunk(chunk);
          return;
        }

        /* ----- SealAI‑Chunk ----- */
        if (parsed.type === 'chunk' && typeof parsed.content === 'string') {
          pushChunk(parsed.content);          // agent egal ⇒ assistant
          return;
        }

      } catch {
        /* Fallback: Plain‑Text‑Streaming */
        pushChunk(e.data as string);
      }
    };

    return () => {
      if (sock.readyState === WebSocket.OPEN || sock.readyState === WebSocket.CONNECTING) {
        sock.close(1000, 'client closed');
      }
      setConnected(false);
      setWs(null);
    };
  }, [token]);

  /* -------- Helper: Chunk anhängen -------- */
  function pushChunk(text: string) {
    setMessages(prev => {
      if (prev.length && prev.at(-1)!.role === 'assistant') {
        const next = [...prev];
        next[next.length - 1].content += text;
        return next;
      }
      return [...prev, { role: 'assistant', content: text }];
    });
  }

  /* -------- Senden -------- */
  function send(text: string) {
    if (!ws || !connected || !text.trim()) return;
    ws.send(JSON.stringify({ chat_id: chatIdRef.current, input: text.trim() }));
    setMessages(p => [
      ...p,
      { role: 'user',      content: text.trim() },
      { role: 'assistant', content: '' },       // Platzhalter für Stream
    ]);
  }

  return { connected, messages, send };
}

/* -------------------------------------------------
   Absoluten WS‑Pfad bauen
--------------------------------------------------*/
export function buildWsUrl(path: string) {
  if (typeof window === 'undefined') return path;  // SSR
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}${path}`;
}
