/* M7 API client (build-gate check 5 — graceful fail-closed). Talks ONLY to /api/v2 (+ the Bearer);
 * never the V1 backend, no domain logic. A 401 → onUnauthenticated() (the app re-logs-in) + throws,
 * so the caller never renders stale/wrong content; any non-OK → throws (the caller shows an error
 * state and the persistent SafetyBanner stays — the framing is never dropped). */

import type { Briefing, ChatResponse, ConversationMemory } from "../contracts";

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
  memory(): Promise<ConversationMemory> {
    return this.req("/conversations/current/memory");
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
