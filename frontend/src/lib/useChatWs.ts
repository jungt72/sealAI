'use client';

import { useEffect, useRef, useState } from 'react';
import { buildWsUrl } from './ws';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export function useChatWs(token?: string) {
  const [ws,        setWs]        = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages,  setMessages]  = useState<ChatMessage[]>([]);
  const chatIdRef                 = useRef('default');

  // ---------------- connect / reconnect ----------------
  useEffect(() => {
    if (!token) return;

    const url = buildWsUrl(
      `/api/v1/ai/ws?token=${encodeURIComponent(token)}&json_stream=1`,
    );
    const sock = new WebSocket(url);

    sock.onopen    = () => setConnected(true);
    sock.onclose   = () => setConnected(false);
    sock.onerror   = e => console.error('❌ WS error', e);
    sock.onmessage = e => {
      try {
        const parsed = JSON.parse(e.data);

        // Fehler-Frames vom Backend
        if (parsed.type === 'error') {
          console.error('WS-error:', parsed);
          return;
        }

        // OpenAI stream frames
        if (parsed.choices?.[0]?.delta) {
          const chunk = parsed.choices[0].delta.content ?? '';
          setMessages(prev => {
            // angefangene Assistant-Nachricht fortsetzen
            if (prev.length && prev.at(-1)!.role === 'assistant') {
              const next = [...prev];
              next[next.length - 1].content += chunk;
              return next;
            }
            return [...prev, { role: 'assistant', content: chunk }];
          });
        }
      } catch {
        /** Fallback → Plain Text (eher im Fallback-Modus ohne json_stream) */
        setMessages(prev => [...prev, { role: 'assistant', content: e.data }]);
      }
    };

    setWs(sock);
    return () => sock.close();
  }, [token]);

  // ---------------- send ----------------
  function send(text: string) {
    if (!ws || !connected || !text.trim()) return;
    ws.send(JSON.stringify({ chat_id: chatIdRef.current, input: text.trim() }));
    setMessages(p => [
      ...p,
      { role: 'user',      content: text.trim() },
      { role: 'assistant', content: '' },      // Platzhalter für Stream
    ]);
  }

  return { connected, messages, send };
}
