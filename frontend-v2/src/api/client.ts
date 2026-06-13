/* M7 API client (build-gate check 5 — graceful fail-closed). Talks ONLY to /api/v2 (+ the Bearer);
 * never the V1 backend, no domain logic. A 401 → onUnauthenticated() (the app re-logs-in) + throws,
 * so the caller never renders stale/wrong content; any non-OK → throws (the caller shows an error
 * state and the persistent SafetyBanner stays — the framing is never dropped). */

import type { Briefing, ChatResponse, ComputeResponse, ConversationMemory } from "../contracts";
import { SseParser } from "./sse";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export class ApiClient {
  constructor(
    private readonly getToken: () => string | null,
    private readonly onUnauthenticated: () => void,
    private readonly base = "/api/v2",
  ) {}

  private async req<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = this.getToken();
    const res = await fetch(this.base + path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (res.status === 401) {
      this.onUnauthenticated();
      throw new ApiError(401, "unauthenticated");
    }
    if (!res.ok) throw new ApiError(res.status, `request failed (${res.status})`);
    return (await res.json()) as T;
  }

  chat(message: string): Promise<ChatResponse> {
    return this.req("/chat", { method: "POST", body: JSON.stringify({ message }) });
  }

  /** P4b — same turn as chat(), streamed: `stage` frames report live progress (keys only; the
   * frontend owns labels), then ONE gated `result` frame carries the full /chat payload. Stage
   * `start`s reach onStage; ends/keepalives are transport detail. An `error` frame or a stream
   * that ends without a result rejects — no partial content ever surfaces. 404/405 (backend
   * without the endpoint yet) falls back to plain /chat once, so the dual deploy is order-free. */
  async chatStream(message: string, onStage?: (stage: string) => void): Promise<ChatResponse> {
    const token = this.getToken();
    const res = await fetch(this.base + "/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message }),
    });
    if (res.status === 401) {
      this.onUnauthenticated();
      throw new ApiError(401, "unauthenticated");
    }
    if (res.status === 404 || res.status === 405) return this.chat(message);
    if (!res.ok || !res.body) throw new ApiError(res.status, `request failed (${res.status})`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    const parser = new SseParser();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        const chunk = decoder.decode(value ?? new Uint8Array(), { stream: !done });
        for (const frame of parser.push(chunk)) {
          if (frame.event === "stage") {
            try {
              const d = JSON.parse(frame.data) as { stage?: string; status?: string };
              if (d.status === "start" && d.stage) onStage?.(d.stage);
            } catch {
              // malformed stage frame — progress is cosmetic, never fail the turn for it
            }
          } else if (frame.event === "result") {
            return JSON.parse(frame.data) as ChatResponse;
          } else if (frame.event === "error") {
            throw new ApiError(502, "stream error");
          }
        }
        if (done) break;
      }
    } finally {
      void reader.cancel().catch(() => undefined);
    }
    throw new ApiError(502, "stream ended without result");
  }
  memory(): Promise<ConversationMemory> {
    return this.req("/conversations/current/memory");
  }
  /** M8 kernel channel: the deterministic compute for the current session (the Berechnungen panel's
   * source). Backend-only numbers — the client never computes. */
  compute(): Promise<ComputeResponse> {
    return this.req("/compute");
  }
  editFact(feld: string, wert: string, origin?: string): Promise<unknown> {
    return this.req(`/conversations/current/facts/${encodeURIComponent(feld)}`, {
      method: "PUT",
      body: JSON.stringify(origin ? { wert, origin } : { wert }),
    });
  }
  forgetFact(feld: string): Promise<unknown> {
    return this.req(`/conversations/current/facts/${encodeURIComponent(feld)}`, { method: "DELETE" });
  }
  forgetAll(): Promise<unknown> {
    return this.req("/conversations/current", { method: "DELETE" });
  }
  briefing(message: string): Promise<Briefing> {
    return this.req("/briefing", { method: "POST", body: JSON.stringify({ message }) });
  }
}
