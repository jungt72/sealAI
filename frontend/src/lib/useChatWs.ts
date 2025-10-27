'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { AgentPayload, AggregatedResponse, LangGraphFinalPayload } from './types/langgraph';

type UseChatWsOpts = {
  chatId?: string | null;
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

const HUMAN_KEY_OVERRIDES: Record<string, string> = {
  empfohlene_materialien: 'Empfohlene Materialien',
  kennzahlen: 'Kennzahlen',
  alternativen: 'Alternativen',
  rueckfragen: 'Rückfragen',
  annahmen: 'Annahmen',
};

const HUMAN_VALUE_OVERRIDES: Record<string, string> = {
  einsatz: 'Einsatz',
  medien: 'Medien',
};

function humanizeKey(key: string): string {
  if (!key) return '';
  if (HUMAN_KEY_OVERRIDES[key]) return HUMAN_KEY_OVERRIDES[key];
  const pretty = key
    .split('_')
    .map(chunk => chunk.trim())
    .filter(Boolean)
    .map(chunk => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(' ');
  return pretty || key;
}

function humanizeValueKey(key: string): string {
  if (!key) return '';
  if (HUMAN_VALUE_OVERRIDES[key]) return HUMAN_VALUE_OVERRIDES[key];
  return humanizeKey(key);
}

function tryParseJson(raw: unknown): Record<string, unknown> | null {
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed);
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function normalizeMultiline(text: string, indent = ''): string {
  if (!text.includes('\n')) return text;
  const lines = text.split('\n');
  return lines
    .map((line, idx) => (idx === 0 ? line : `${indent}${line}`))
    .join('\n');
}

function formatValue(value: unknown, depth = 0): string {
  if (value == null) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);

  if (Array.isArray(value)) {
    if (value.length === 0) return '';
    const indentLevel = Math.max(depth - 1, 0);
    const indent = indentLevel > 0 ? '  '.repeat(indentLevel) : '';
    const childIndent = '  '.repeat(indentLevel + 1);
    return value
      .map(item => formatValue(item, depth + 1))
      .filter(Boolean)
      .map(item => `${indent}- ${normalizeMultiline(item, childIndent)}`)
      .join('\n');
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => v != null);
    if (entries.length === 0) return '';

    const nameEntry = entries.find(([key]) => key === 'name');
    const nameValue = nameEntry && typeof nameEntry[1] === 'string' ? nameEntry[1].trim() : '';
    const rest = entries.filter(([key]) => key !== 'name');

    if (depth > 0) {
      const restParts = rest
        .map(([key, val]) => {
          const formatted = formatValue(val, depth + 1);
          if (!formatted) return '';
          return `${humanizeValueKey(key)}: ${formatted}`;
        })
        .filter(Boolean)
        .join(', ');
      if (nameValue) {
        return restParts ? `**${nameValue}** – ${restParts}` : `**${nameValue}**`;
      }
      return restParts || '';
    }

    const sections = rest
      .map(([key, val]) => {
        const formatted = formatValue(val, depth + 1);
        if (!formatted) return '';
        return `**${humanizeKey(key)}**\n${formatted}`;
      })
      .filter(Boolean);

    if (sections.length === 0 && nameValue) {
      return `**Name**\n${nameValue}`;
    }

    return sections.join('\n\n');
  }

  return String(value);
}

function formatStructuredAnswer(raw: unknown): string | null {
  const parsed = tryParseJson(raw);
  if (!parsed) return null;

  const title = typeof parsed.title === 'string' ? parsed.title.trim() : '';
  const rationale = typeof parsed.rationale === 'string' ? parsed.rationale.trim() : '';
  const data = parsed.data && typeof parsed.data === 'object' ? (parsed.data as Record<string, unknown>) : null;
  const sources = Array.isArray(parsed.sources) ? parsed.sources.filter((v): v is string => typeof v === 'string' && v.trim().length > 0) : [];
  const needSource = parsed.need_source && typeof parsed.need_source === 'object' ? parsed.need_source as Record<string, unknown> : null;

  const blocks: string[] = [];
  if (title) blocks.push(`**${title}**`);
  if (rationale) blocks.push(rationale);

  if (data) {
    for (const [key, value] of Object.entries(data)) {
      const formatted = formatValue(value, 1);
      if (!formatted) continue;
      blocks.push(`**${humanizeKey(key)}**\n${formatted}`);
    }
  }

  if (sources.length > 0) {
    blocks.push(`_Quellen:_ ${sources.join(', ')}`);
  }

  if (needSource) {
    const reason = typeof needSource.reason === 'string' ? needSource.reason.trim() : '';
    if (reason) blocks.push(`⚠️ ${reason}`);
  }

  const joined = blocks.filter(Boolean).join('\n\n').trim();
  return joined || null;
}

function formatAgentAnswer(agentId: string, payload: AgentPayload | undefined): string | null {
  if (!payload) return null;
  const answerRaw = typeof payload.answer === 'string' ? payload.answer.trim() : '';
  if (!answerRaw) return null;
  const structured = formatStructuredAnswer(answerRaw);
  const agentLabel = agentId.replace(/_/g, ' ');
  const prettyAgent = agentLabel.charAt(0).toUpperCase() + agentLabel.slice(1);

  const confidence = typeof payload.confidence === 'number' && Number.isFinite(payload.confidence)
    ? ` _(Konfidenz ${(payload.confidence * 100).toFixed(0)}%)_`
    : '';

  if (structured) {
    return `**${prettyAgent}${confidence}**\n${structured}`;
  }

  return `**${prettyAgent}${confidence}**\n${answerRaw}`;
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
      const payload = typeof ua === 'object' && ua !== null ? ua : { ui_action: String(ua || '') };
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

  const formatContributors = (contributors: AggregatedResponse['metadata'] extends Record<string, any>
    ? AggregatedResponse['metadata']['contributors']
    : undefined) => {
    if (!Array.isArray(contributors) || contributors.length === 0) return '';
    const lines = contributors
      .filter(entry => entry && typeof entry.agent === 'string')
      .map(entry => {
        const agent = entry.agent.replace(/_/g, ' ');
        const pretty = agent.charAt(0).toUpperCase() + agent.slice(1);
        const conf = typeof entry.confidence === 'number' ? ` (${(entry.confidence * 100).toFixed(0)}%)` : '';
        return `- ${pretty}${conf}`;
      })
      .filter(Boolean);
    return lines.length ? `_Beiträge:_\n${lines.join('\n')}` : '';
  };

  const formatGraphResult = useCallback((result: unknown) => {
    if (!result || typeof result !== 'object') return '';
    const payload = result as LangGraphFinalPayload;

    const sections: string[] = [];

    const aggregated = payload.aggregated;
    if (aggregated && typeof aggregated === 'object') {
      const answerStructured = formatStructuredAnswer(aggregated.answer || null);
      const answerPlain = typeof aggregated.answer === 'string' ? aggregated.answer.trim() : '';
      const contributorsBlock = formatContributors(aggregated.metadata?.contributors);
      const debate = payload.debate;
      const debateAnswer = debate && typeof debate.answer === 'string' ? debate.answer.trim() : '';

      if (answerStructured || answerPlain) {
        sections.push(`**Gesamtempfehlung**\n${answerStructured || answerPlain}`);
      }
      if (contributorsBlock) sections.push(contributorsBlock);
      if (debateAnswer) sections.push(`**Debatte**\n${debateAnswer}`);
    }

    const responses = payload.responses;
    if (responses && typeof responses === 'object') {
      const agentBlocks: string[] = [];
      for (const [agentId, responsePayload] of Object.entries(responses)) {
        if (!responsePayload || typeof responsePayload !== 'object') continue;
        const formatted = formatAgentAnswer(agentId, responsePayload as AgentPayload);
        if (formatted) agentBlocks.push(formatted);
      }
      if (agentBlocks.length > 0) sections.push(agentBlocks.join('\n\n'));
    }

    if (sections.length > 0) {
      return sections.join('\n\n');
    }

    const textFallback =
      (typeof payload.text === 'string' && payload.text.trim()) ||
      (typeof payload.message === 'string' && payload.message.trim()) ||
      (typeof payload.answer === 'string' && payload.answer.trim()) ||
      '';
    return textFallback;
  }, [formatContributors]);

  const handleMessage = useCallback((ev: MessageEvent) => {
    const payload: any = typeof ev.data === 'string' ? safeParse(ev.data) : ev.data;
    if (!payload) return;

    if (payload?.event === 'idle') return;
    if (payload?.event === 'error' && payload?.code === 'idle_timeout') return;

    if (payload?.event === 'dbg') {
      const node = (payload?.meta?.langgraph_node || payload?.meta?.run_name || '').toString().toLowerCase();
      if (node === 'ask_missing' && !firedNeedParamsRef.current) {
        firedNeedParamsRef.current = true;
        emitUiAction({ ui_action: 'open_form' });
      }
    }

    const uiEventCandidate =
      payload?.event === 'ui_event'
        ? payload?.payload ?? payload?.ui_event ?? payload
        : payload?.ui_event;
    if (uiEventCandidate && typeof uiEventCandidate === 'object') {
      emitUiAction(uiEventCandidate);
      if (typeof uiEventCandidate.message === 'string') {
        setText(prev => (prev ? `${prev}\n\n${uiEventCandidate.message}` : uiEventCandidate.message));
      }
    } else if (typeof payload?.ui_action !== 'undefined') {
      const ua = typeof payload.ui_action === 'string' ? { ui_action: payload.ui_action } : payload.ui_action;
      if (ua) emitUiAction(ua);
    }

    if (payload?.type === 'memory') {
      const memoryText = typeof payload.text === 'string' ? payload.text : '';
      if (memoryText) {
        setText(prev => (prev ? `${prev}\n\n${memoryText}` : memoryText));
      }
      return;
    }

    switch (payload.event) {
      case 'start':
        lastThreadIdRef.current = payload.thread_id ?? null;
        setStreaming(true);
        setText('');
        setLastError(null);
        break;

      case 'token': {
        const deltaRaw = payload.delta ?? payload.text ?? '';
        const agentLabel = typeof payload.agent === 'string' ? payload.agent : null;
        if (typeof deltaRaw === 'string' && deltaRaw.trim()) {
          const formatted = agentLabel ? `[${agentLabel}] ${deltaRaw.trim()}` : deltaRaw.trim();
          setText(prev => (prev ? `${prev}\n\n${formatted}` : formatted));
          maybeOpenFormFromText(formatted);
        }
        break;
      }

      case 'final': {
        const result = payload.payload ?? payload.data ?? null;
        if (result && typeof result === 'object') {
          if (Array.isArray((result as any).ui_events)) {
            for (const entry of (result as any).ui_events) {
              if (entry && typeof entry === 'object') emitUiAction(entry);
            }
          }
          const formatted = formatGraphResult(result);
          if (formatted) {
            setText(formatted);
            maybeOpenFormFromText(formatted);
          }
        } else if (typeof payload.text === 'string') {
          setText(payload.text);
          maybeOpenFormFromText(payload.text);
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

      default: {
        if (payload?.type === 'response' && payload?.payload) {
          const result = payload.payload;
          if (result && typeof result === 'object') {
            if (Array.isArray(result.ui_events)) {
              for (const entry of result.ui_events) {
                if (entry && typeof entry === 'object') emitUiAction(entry);
              }
            }
            const formatted = formatGraphResult(result);
            if (formatted) {
              setText(formatted);
              maybeOpenFormFromText(formatted);
            }
          }
          break;
        }

        const maybeText =
          (typeof payload?.message?.data?.content === 'string' && payload?.message?.data?.content) ??
          (typeof payload?.message?.content === 'string' && payload?.message?.content) ??
          (typeof payload?.content === 'string' && payload?.content) ??
          (typeof payload?.text === 'string' && payload?.text) ?? '';
        if (maybeText) {
          setText(prev => (prev ? `${prev}\n\n${maybeText}` : maybeText));
          maybeOpenFormFromText(maybeText);
        }
        break;
      }
    }
  }, [emitUiAction, formatGraphResult, maybeOpenFormFromText]);

  const connect = useCallback(() => {
    if (!url) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    try {
      // WICHTIG: kein Sub-Protokoll übergeben
      const ws = new WebSocket(url);
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

  useEffect(() => {
    lastThreadIdRef.current = null;
    setStreaming(false);
    setText('');
  }, [chatId]);

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

      if (!chatId) {
        setLastError('Kein Gesprächskontext verfügbar');
        setStreaming(false);
        return;
      }

      const payload: any = { chat_id: chatId, input, mode: 'graph' };
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
    if (!chatId) return;
    const threadId = lastThreadIdRef.current || `api:${chatId}`;
    try {
      ws.send(JSON.stringify({ type: 'cancel', chat_id: chatId, thread_id: threadId }));
    } catch {}
    setStreaming(false);
  }, [chatId]);

  return { connected, streaming, text, lastError, send, cancel };
}
