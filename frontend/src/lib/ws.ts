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
  onUiAction?: (ui: any) => void; // ← hinzugefügt
};

export type WSOptions = {
  token?: string; // Fallback-Token (besser: getToken)
  url?: string; // ws[s]://… oder Pfad (/api/v1/ai/ws)
  protocols?: string | string[];
  heartbeatMs?: number;
  maxBackoffMs?: number;
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
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}

class ChatWsClient {
  private ws?: WebSocket;
  private hb?: number;
  private backoff = 1000;
  private closed = false;
  private openPromise?: Promise<void>;
  private started = false;
  private lastThreadId?: string;
  private firedNeedParams = false;

  private readonly opts: Required<Pick<WSOptions, "heartbeatMs" | "maxBackoffMs">> & Omit<WSOptions, "heartbeatMs" | "maxBackoffMs">;
  private readonly ev: ChatWsEvents;
  private readonly subs = new Set<(msg: unknown) => void>();

  constructor(options: WSOptions & ChatWsEvents) {
    this.opts = {
      url: options.url ?? "/api/v1/ai/ws",
      protocols: options.protocols ?? ["json"],
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
      onUiAction: options.onUiAction, // ← hinzugefügt
    };
  }

  async connect(): Promise<void> {
    if (this.openPromise) return this.openPromise;
    this.closed = false;

    this.openPromise = new Promise<void>(async (resolve, reject) => {
      let token: string | undefined = undefined;
      try {
        token = (await this.opts.getToken?.()) ?? this.opts.token;
      } catch {}

      const url = withToken(this.opts.url!, token);
      try {
        this.ws = new WebSocket(url, this.opts.protocols as string[]);
      } catch (e) {
        reject(e);
        return;
      }

      const ws = this.ws;

      ws.onopen = () => {
        this.backoff = 1000;
        this.started = false;
        this.firedNeedParams = false;
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

  send(payload: unknown): void {
    this.sendInternal(payload);
  }

  request(input: string, chatId = "default", extra?: Record<string, unknown>): void {
    this.firedNeedParams = false;
    this.sendInternal({ chat_id: chatId || "default", input, ...(extra || {}) });
  }

  cancel(threadId?: string): void {
    const tid = threadId ?? this.lastThreadId ?? "default";
    this.sendInternal({ type: "cancel", thread_id: tid });
  }

  close(): void {
    this.closed = true;
    this.stopHeartbeat();
    try {
      this.ws?.close();
    } catch {}
    this.ws = undefined;
    this.openPromise = undefined;
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.hb = window.setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      try {
        this.ws.send(JSON.stringify({ type: "ping", ts: Date.now() }));
      } catch {}
    }, this.opts.heartbeatMs);
  }

  private stopHeartbeat() {
    if (this.hb) {
      window.clearInterval(this.hb);
      this.hb = undefined;
    }
  }

  private scheduleReconnect() {
    const delay = Math.min(this.backoff, this.opts.maxBackoffMs);
    this.backoff = Math.min(this.backoff * 2, this.opts.maxBackoffMs);
    window.setTimeout(() => {
      if (this.closed) return;
      this.openPromise = undefined; // neues connect() → neuer Token
      this.connect().catch(() => this.scheduleReconnect());
    }, delay);
  }

  private routeStreamEvents(raw: unknown) {
    const d = raw as any;

    // Backend: {"phase":"starting", thread_id, ...}
    if (d?.phase === "starting") {
      this.started = true;
      const tid = d.thread_id ?? "default";
      this.lastThreadId = tid;
      this.ev.onStreamStart?.({ threadId: tid, agent: d?.agent });
    }

    // Debug-Events: {"event":"dbg", "meta":{"langgraph_node":"ask_missing"}, ...}
    if (d?.event === "dbg") {
      const node = (d?.meta?.langgraph_node || d?.meta?.run_name || d?.name || "").toString().toLowerCase();
      if (!this.firedNeedParams && node === "ask_missing") {
        this.firedNeedParams = true;
        window.dispatchEvent(new CustomEvent("sai:need-params", { detail: { node } }));
        // echtes UI-Open-Event
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: { ui_action: "open_form" } }));
      }
    }

    // UI-Events: {"event":"ui_action", ...} oder Backward-Compat {"ui_event": {...}}: {"event":"ui_action", ...} oder Backward-Compat {"ui_event": {...}}
      if (d?.event === "ui_action" || d?.ui_event || typeof d?.ui_action !== "undefined") {
        const ua = typeof d?.ui_action === "string"
          ? { ui_action: d.ui_action }
          : (d?.ui_event && typeof d.ui_event === "object" ? d.ui_event : d);
        this.ev.onUiAction?.(ua);
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: ua }));
      }

    // Token-Stream
    if (typeof d?.delta !== "undefined") {
      if (
        !this.firedNeedParams &&
        typeof d.delta === "string" &&
        /mir fehlen noch folgende angaben|kannst du mir diese bitte nennen|präzise.*empfehlung.*brauche.*noch kurz|pack die werte gern.*eine zeile/i.test(d.delta)
      ) {
        this.firedNeedParams = true;
        window.dispatchEvent(new CustomEvent("sai:need-params", { detail: { hint: "text" } }));
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: { ui_action: "open_form" } }));
      }
      this.ev.onStreamDelta?.({ delta: String(d.delta), done: false });
    }

    // Optional final text
    if (d?.final?.text && !d?.delta) {
      if (
        !this.firedNeedParams &&
        typeof d.final.text === "string" &&
        /mir fehlen noch folgende angaben|kannst du mir diese bitte nennen|präzise.*empfehlung.*brauche.*noch kurz|pack die werte gern.*eine zeile/i.test(d.final.text)
      ) {
        this.firedNeedParams = true;
        window.dispatchEvent(new CustomEvent("sai:need-params", { detail: { hint: "final" } }));
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: { ui_action: "open_form" } }));
      }
      this.ev.onStreamDelta?.({ delta: String(d.final.text), done: false });
    }

    // Done
    if (d?.event === "done" || d?.done === true) {
      this.ev.onStreamDone?.({ threadId: d.thread_id });
    }

    // LCEL / frames
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
