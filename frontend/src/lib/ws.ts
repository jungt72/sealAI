// WebSocket-Client mit Token-Refresh, Reconnect, Heartbeat und Stream-Events.

export type StreamStartPayload = { threadId: string; agent?: string };
export type StreamDeltaPayload = { delta: string; done?: boolean };
export type StreamDonePayload = { threadId?: string };

export type ChatWsEvents = {
  onOpen?: () => void;
  onClose?: (ev: CloseEvent) => void;
  onError?: (ev: Event) => void;
  onMessage?: (msg: unknown) => void;
  onStreamStart?: (p: StreamStartPayload) => void;
  onStreamDelta?: (p: StreamDeltaPayload) => void;
  onStreamDone?: (p: StreamDonePayload) => void;
};

export type WSOptions = {
  /** Optionaler Token (Fallback). Besser: getToken() verwenden. */
  token?: string;
  /** Entweder absolut (ws[s]://...) oder Pfad (/api/v1/ai/ws). */
  url?: string;
  protocols?: string | string[];
  heartbeatMs?: number;
  maxBackoffMs?: number;
  /** Liefert bei jedem Connect/Reconnect einen FRISCHEN Token. */
  getToken?: () => Promise<string | undefined>;
};

function wsOrigin(): { proto: "ws:" | "wss:"; host: string } {
  const { protocol, host } = window.location;
  return { proto: protocol === "https:" ? "wss:" : "ws:", host };
}

function withToken(urlOrPath: string, token: string | undefined): string {
  const { proto, host } = wsOrigin();
  const isAbs = urlOrPath.startsWith("ws://") || urlOrPath.startsWith("wss://");
  const base = isAbs ? urlOrPath : `${proto}//${host}${urlOrPath.startsWith("/") ? "" : "/"}${urlOrPath}`;
  if (!token) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}token=${encodeURIComponent(token)}`;
}

function safeParse(s: string): unknown {
  try { return JSON.parse(s); } catch { return s; }
}

class ChatWsClient {
  private ws?: WebSocket;
  private hb?: number;
  private backoff = 1000;
  private closed = false;
  private openPromise?: Promise<void>;
  private started = false;
  private lastThreadId?: string;

  private readonly opts: Required<Pick<WSOptions, "heartbeatMs" | "maxBackoffMs">> & Omit<WSOptions, "heartbeatMs" | "maxBackoffMs">;
  private readonly ev: ChatWsEvents;
  private readonly subs = new Set<(msg: unknown) => void>();

  constructor(options: WSOptions & ChatWsEvents) {
    this.opts = {
      url: options.url ?? "/api/v1/ai/ws",
      protocols: options.protocols ?? "json",
      heartbeatMs: options.heartbeatMs ?? 15000,
      maxBackoffMs: options.maxBackoffMs ?? 30000,
      token: options.token,
      getToken: options.getToken,
    };
    this.ev = {
      onOpen: options.onOpen,
      onClose: options.onClose,
      onError: options.onError,
      onMessage: options.onMessage,
      onStreamStart: options.onStreamStart,
      onStreamDelta: options.onStreamDelta,
      onStreamDone: options.onStreamDone,
    };
  }

  async connect(): Promise<void> {
    if (this.openPromise) return this.openPromise;
    this.closed = false;

    this.openPromise = new Promise<void>(async (resolve, reject) => {
      let token: string | undefined = undefined;
      try {
        token = (await this.opts.getToken?.()) ?? this.opts.token;
      } catch {
        // wenn fetch des Tokens scheitert, trotzdem weiter (Backend wird ggf. ablehnen)
      }

      const url = withToken(this.opts.url!, token);
      try { this.ws = new WebSocket(url, this.opts.protocols as any); }
      catch (e) { reject(e); return; }

      const ws = this.ws;

      ws.onopen = () => {
        this.backoff = 1000;
        this.started = false;
        this.startHeartbeat();
        this.ev.onOpen?.();
        resolve();
      };

      ws.onmessage = (ev) => {
        const data = typeof ev.data === "string" ? safeParse(ev.data) : ev.data;
        this.ev.onMessage?.(data);
        for (const cb of this.subs) cb(data);
        this.routeStreamEvents(data);
      };

      ws.onclose = (ev) => {
        this.stopHeartbeat();
        this.ev.onClose?.(ev);
        if (!this.closed) this.scheduleReconnect();
      };

      ws.onerror = (ev) => {
        this.ev.onError?.(ev);
      };
    });

    return this.openPromise;
  }

  subscribe(handler: (msg: unknown) => void): () => void {
    this.subs.add(handler);
    return () => this.subs.delete(handler);
  }

  private sendInternal(payload: unknown): void {
    const s = JSON.stringify(payload);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(s);
  }

  send(payload: unknown): void { this.sendInternal(payload); }

  request(input: string, chatId = "default", extra?: Record<string, unknown>): void {
    this.sendInternal({ chat_id: chatId, input, ...(extra || {}) });
  }

  /** Stoppt den aktuellen Stream (wenn Backend cancel unterstützt). */
  cancel(threadId?: string): void {
    const tid = threadId ?? this.lastThreadId ?? "default";
    this.sendInternal({ type: "cancel", thread_id: tid });
  }

  close(): void {
    this.closed = true;
    this.stopHeartbeat();
    try { this.ws?.close(); } catch {}
    this.ws = undefined;
    this.openPromise = undefined;
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.hb = window.setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      try { this.ws.send(JSON.stringify({ type: "ping", ts: Date.now() })); } catch {}
    }, this.opts.heartbeatMs);
  }

  private stopHeartbeat() {
    if (this.hb) { window.clearInterval(this.hb); this.hb = undefined; }
  }

  private scheduleReconnect() {
    const delay = Math.min(this.backoff, this.opts.maxBackoffMs);
    this.backoff = Math.min(this.backoff * 2, this.opts.maxBackoffMs);
    window.setTimeout(() => {
      if (this.closed) return;
      this.openPromise = undefined; // damit connect() erneut läuft (mit neuem Token)
      this.connect().catch(() => this.scheduleReconnect());
    }, delay);
  }

  private routeStreamEvents(raw: unknown) {
    const d = raw as any;
    if (d?.phase === "starting") {
      this.started = true;
      const tid = d.thread_id ?? "default";
      this.lastThreadId = tid;
      this.ev.onStreamStart?.({ threadId: tid, agent: d.agent });
    }
    if (typeof d?.delta !== "undefined") {
      this.ev.onStreamDelta?.({ delta: String(d.delta), done: false });
    }
    if (d?.final?.text && !d?.delta) {
      // fallback: falls Server am Ende nur final.text schickt
      this.ev.onStreamDelta?.({ delta: String(d.final.text), done: false });
    }
    if (d?.event === "done" || d?.done === true) {
      this.ev.onStreamDone?.({ threadId: d.thread_id });
    }
    // LangGraph/LCEL-Style message frames
    if (d?.message) {
      if (!this.started) {
        this.started = true;
        const tid = d?.meta?.thread_id ?? "default";
        this.lastThreadId = tid;
        this.ev.onStreamStart?.({ threadId: tid, agent: d?.message?.name });
      }
      const content = d?.message?.data?.content ?? d?.message?.content;
      if (typeof content === "string") this.ev.onStreamDelta?.({ delta: content, done: false });
    }
  }
}

export default ChatWsClient;
