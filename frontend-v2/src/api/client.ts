/* M7 API client (build-gate check 5 — graceful fail-closed). Talks ONLY to /api/v2 (+ the Bearer);
 * never the V1 backend, no domain logic. A 401 → onUnauthenticated() (the app re-logs-in) + throws,
 * so the caller never renders stale/wrong content; any non-OK → throws (the caller shows an error
 * state and the persistent SafetyBanner stays — the framing is never dropped). */

import type {
  AdminContribution,
  AdminLead,
  AdminPartner,
  AnfrageResponse,
  Briefing,
  CaseSummary,
  ChatResponse,
  ComputeResponse,
  ConfirmationResponse,
  ContributePayload,
  ConversationMemory,
  ParamItem,
  SelfLead,
  SelfPartnerUpdate,
} from "../contracts";
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

  chat(message: string, caseId?: string): Promise<ChatResponse> {
    return this.req("/chat", {
      method: "POST",
      body: JSON.stringify(caseId ? { message, case_id: caseId } : { message }),
    });
  }

  /** P4b — same turn as chat(), streamed: `stage` frames report live progress (keys only; the
   * frontend owns labels), then ONE gated `result` frame carries the full /chat payload. Stage
   * `start`s reach onStage; ends/keepalives are transport detail. An `error` frame or a stream
   * that ends without a result rejects — no partial content ever surfaces. 404/405 (backend
   * without the endpoint yet) falls back to plain /chat once, so the dual deploy is order-free.
   * `caseId` ("Fälle"-Sidebar) targets one of the caller's own several persisted cases instead of
   * always the token's default session — omitted, this is byte-identical to before. */
  async chatStream(
    message: string,
    onStage?: (stage: string) => void,
    caseId?: string,
  ): Promise<ChatResponse> {
    const token = this.getToken();
    const res = await fetch(this.base + "/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(caseId ? { message, case_id: caseId } : { message }),
    });
    if (res.status === 401) {
      this.onUnauthenticated();
      throw new ApiError(401, "unauthenticated");
    }
    if (res.status === 404 || res.status === 405) return this.chat(message, caseId);
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
  /** Appends `?case_id=` when given ("Fälle"-Sidebar) — omitted, the path is unchanged, so a
   * caller that never passes caseId gets byte-identical URLs to before this feature. */
  private withCase(path: string, caseId?: string): string {
    return caseId ? `${path}?case_id=${encodeURIComponent(caseId)}` : path;
  }
  memory(caseId?: string): Promise<ConversationMemory> {
    return this.req(this.withCase("/conversations/current/memory", caseId));
  }
  /** M8 kernel channel: the deterministic compute for the current session (the Berechnungen panel's
   * source). Backend-only numbers — the client never computes. */
  compute(): Promise<ComputeResponse> {
    return this.req("/compute");
  }
  editFact(feld: string, wert: string, origin?: string, caseId?: string): Promise<unknown> {
    return this.req(this.withCase(`/conversations/current/facts/${encodeURIComponent(feld)}`, caseId), {
      method: "PUT",
      body: JSON.stringify(origin ? { wert, origin } : { wert }),
    });
  }
  /** Phase 2b — the parameter-form batch settle: all fields in one POST → one settle + recompute,
   * returns the deterministic confirmation (post-bind echo + kern result + Rückfragen). */
  submitParams(items: ParamItem[], caseId?: string): Promise<ConfirmationResponse> {
    return this.req(this.withCase("/conversations/current/facts", caseId), {
      method: "POST",
      body: JSON.stringify({ items }),
    });
  }
  /** R2 live preview — the SAME deterministic kern as submitParams over the form's DRAFT values,
   * but READ-ONLY (no settle, no persist, no provenance). Returns the Berechnete Werte to show as
   * „Vorschau · nicht übernommen". Backend-only numbers — the client never computes. Stateless (no
   * session write at all), so it never needs a caseId — nothing to target. */
  previewParams(items: ParamItem[]): Promise<ComputeResponse> {
    return this.req("/conversations/current/preview", {
      method: "POST",
      body: JSON.stringify({ items }),
    });
  }
  forgetFact(feld: string, caseId?: string): Promise<unknown> {
    return this.req(this.withCase(`/conversations/current/facts/${encodeURIComponent(feld)}`, caseId), {
      method: "DELETE",
    });
  }
  forgetAll(caseId?: string): Promise<unknown> {
    return this.req(this.withCase("/conversations/current", caseId), { method: "DELETE" });
  }
  /** "Fälle"-Sidebar: the tenant's case list, sorted server-side by most-recently-updated. */
  listCases(): Promise<{ cases: CaseSummary[] }> {
    return this.req("/conversations");
  }
  briefing(message: string): Promise<Briefing> {
    return this.req("/briefing", { method: "POST", body: JSON.stringify({ message }) });
  }
  /** Modus F lead-gen: route a structured RFQ briefing (rendered server-side from the session) to the
   * chosen partner. Returns the briefing preview so the user sees what was sent; lead_email never is. */
  anfrage(partnerId: string, message: string): Promise<AnfrageResponse> {
    return this.req("/anfrage", {
      method: "POST",
      body: JSON.stringify({ partner_id: partnerId, message }),
    });
  }

  // ── Owner/admin surface (role-gated server-side; a non-admin token 403s) ──────────────────────
  adminListHersteller(): Promise<{ hersteller: AdminPartner[] }> {
    return this.req("/admin/hersteller");
  }
  adminUpsertHersteller(
    id: string,
    body: Omit<AdminPartner, "hersteller">,
  ): Promise<AdminPartner> {
    return this.req(`/admin/hersteller/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }
  adminDeleteHersteller(id: string): Promise<{ deleted: string }> {
    return this.req(`/admin/hersteller/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  }
  adminListLeads(partnerId?: string): Promise<{ leads: AdminLead[] }> {
    const q = partnerId ? `?partner_id=${encodeURIComponent(partnerId)}` : "";
    return this.req(`/admin/leads${q}`);
  }

  // ── Manufacturer self-service (role-gated + scoped to the token's hersteller_id, server-side) ──
  partnerSelfGet(): Promise<AdminPartner> {
    return this.req("/partner/me");
  }
  partnerSelfUpdate(body: SelfPartnerUpdate): Promise<AdminPartner> {
    return this.req("/partner/me", { method: "PUT", body: JSON.stringify(body) });
  }
  partnerSelfLeads(): Promise<{ leads: SelfLead[] }> {
    return this.req("/partner/me/leads");
  }

  // ── Wissens-Beitrag: a user shares their solution (→ untrusted DRAFT in the owner review queue) ──
  contribute(body: ContributePayload): Promise<{ status: string; id: number; hinweis: string }> {
    return this.req("/contribute", { method: "POST", body: JSON.stringify(body) });
  }
  adminListContributions(): Promise<{ contributions: AdminContribution[] }> {
    return this.req("/admin/contributions");
  }
  adminSetContributionStatus(id: number, status: string, reviewNote: string): Promise<unknown> {
    return this.req(`/admin/contributions/${id}/status`, {
      method: "PUT",
      body: JSON.stringify({ status, review_note: reviewNote }),
    });
  }
}
