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
  ContributionResponse,
  ConversationMemory,
  HandoffGovernanceSelection,
  InterviewRefreshResponse,
  LegalAcceptancePayload,
  LegalAcceptanceStatus,
  LifecyclePolicyResponse,
  LifecycleReceiptResponse,
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

  private newIdempotencyKey(): string {
    return globalThis.crypto.randomUUID();
  }

  lifecyclePolicy(): Promise<LifecyclePolicyResponse> {
    return this.req("/contribute/policy");
  }

  private async activeLifecyclePolicy(): Promise<LifecyclePolicyResponse> {
    const policy = await this.lifecyclePolicy();
    if (
      !policy.enabled ||
      !policy.policy_authority_ref ||
      !policy.purpose_version ||
      !policy.consent_version
    ) {
      throw new ApiError(503, "API lifecycle policy is unavailable");
    }
    return policy;
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
   * always the token's default session — omitted, this is byte-identical to before.
   *
   * `onToken(text, draft)` — Phase 3A/3B: `draft=false` (smalltalk_navigation only) means `text`
   * IS the final answer being typed (this route never goes through L3); `draft=true` (every other
   * route, Phase 3B) means `text` is a NON-AUTHORITATIVE preview — the real answer only arrives via
   * the returned/resolved `result` payload. A malformed or missing `draft` field defaults to `true`
   * (never treat an ambiguous frame as authoritative). */
  async chatStream(
    message: string,
    onStage?: (stage: string) => void,
    caseId?: string,
    onToken?: (text: string, draft: boolean) => void,
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
    const streamVersion = res.headers.get("X-SealingAI-Stream-Version");
    if (streamVersion !== null && streamVersion !== "1") {
      throw new ApiError(502, `unsupported stream schema (${streamVersion})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    const parser = new SseParser();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        const chunk = decoder.decode(value ?? new Uint8Array(), { stream: !done });
        for (const frame of parser.push(chunk)) {
          if (frame.event === "token") {
            // Phase 3A (smalltalk, draft=false — the delta IS the final answer) + Phase 3B (every
            // other route, draft=true — a non-authoritative preview only). Cosmetic either way — the
            // gated `result` frame is always the authoritative answer, so a malformed token frame
            // never fails the turn.
            try {
              const d = JSON.parse(frame.data) as { text?: string; draft?: boolean };
              if (typeof d.text === "string") onToken?.(d.text, d.draft !== false);
            } catch {
              // malformed token frame — ignore (progress/streamed tokens are never load-bearing)
            }
          } else if (frame.event === "stage") {
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
  /** Case selection is an authenticated header, never a query parameter (access-log/referrer safe). */
  private caseHeaders(caseId?: string): HeadersInit | undefined {
    return caseId ? { "X-SealAI-Case-Id": caseId } : undefined;
  }
  memory(caseId?: string): Promise<ConversationMemory> {
    return this.req("/conversations/current/memory", { headers: this.caseHeaders(caseId) });
  }
  /** Reconciles persisted case facts with the active adaptive-interview controller. Shadow-only and
   * disabled deployments return `next_question: null`; the client never infers controller state. */
  refreshInterview(caseId?: string): Promise<InterviewRefreshResponse> {
    return this.req("/conversations/current/interview/refresh", {
      method: "POST",
      headers: this.caseHeaders(caseId),
    });
  }
  /** M8 kernel channel: the deterministic compute for the current session (the Berechnungen panel's
   * source). Backend-only numbers — the client never computes. */
  compute(caseId?: string): Promise<ComputeResponse> {
    return this.req("/compute", { headers: this.caseHeaders(caseId) });
  }
  editFact(feld: string, wert: string, origin?: string, caseId?: string): Promise<unknown> {
    return this.req(`/conversations/current/facts/${encodeURIComponent(feld)}`, {
      method: "PUT",
      headers: this.caseHeaders(caseId),
      body: JSON.stringify(origin ? { wert, origin } : { wert }),
    });
  }
  /** Phase 2b — the parameter-form batch settle: all fields in one POST → one settle + recompute,
   * returns the deterministic confirmation (post-bind echo + kern result + Rückfragen). */
  submitParams(items: ParamItem[], caseId?: string): Promise<ConfirmationResponse> {
    return this.req("/conversations/current/facts", {
      method: "POST",
      headers: this.caseHeaders(caseId),
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
    return this.req(`/conversations/current/facts/${encodeURIComponent(feld)}`, {
      method: "DELETE",
      headers: this.caseHeaders(caseId),
    });
  }
  forgetAll(caseId?: string): Promise<unknown> {
    return this.req("/conversations/current", {
      method: "DELETE",
      headers: this.caseHeaders(caseId),
    });
  }
  /** "Fälle"-Sidebar: the tenant's case list, sorted server-side by most-recently-updated. */
  listCases(): Promise<{ cases: CaseSummary[] }> {
    return this.req("/conversations");
  }
  briefing(caseId: string, caseRevision: number): Promise<Briefing> {
    return this.req("/briefing", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId, case_revision: caseRevision }),
    });
  }
  /** Modus F lead-gen: route the read-only projection of one exact authorized case revision. */
  async anfrage(
    partnerId: string,
    caseId: string,
    caseRevision: number,
    governance: HandoffGovernanceSelection,
    idempotencyKey = this.newIdempotencyKey(),
  ): Promise<AnfrageResponse> {
    const policy = await this.activeLifecyclePolicy();
    return this.req("/anfrage", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        partner_id: partnerId,
        case_id: caseId,
        case_revision: caseRevision,
        governance: {
          tenant_id: policy.tenant_id,
          policy_authority_ref: policy.policy_authority_ref,
          purpose_version: policy.purpose_version,
          consent_version: policy.consent_version,
          ...governance,
        },
      }),
    });
  }

  cancelLead(
    leadId: number,
    idempotencyKey = this.newIdempotencyKey(),
  ): Promise<LifecycleReceiptResponse> {
    return this.req(`/leads/${leadId}/cancel`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ reason_code: "lead_cancelled" }),
    });
  }

  // Platform-owner surface (role-gated server-side; other roles receive 403)
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
  adminListLeads(
    partnerId?: string,
    cursor?: string,
    limit = 50,
  ): Promise<{ leads: AdminLead[]; next_cursor: string | null; has_more: boolean }> {
    const query = new URLSearchParams({ limit: String(limit) });
    if (partnerId) query.set("partner_id", partnerId);
    if (cursor) query.set("cursor", cursor);
    return this.req(`/admin/leads?${query.toString()}`);
  }

  // ── Manufacturer self-service (role-gated + scoped to the token's hersteller_id, server-side) ──
  partnerSelfGet(): Promise<AdminPartner> {
    return this.req("/partner/me");
  }
  partnerSelfUpdate(body: SelfPartnerUpdate): Promise<AdminPartner> {
    return this.req("/partner/me", { method: "PUT", body: JSON.stringify(body) });
  }
  partnerSelfLeads(
    cursor?: string,
    limit = 50,
  ): Promise<{ leads: SelfLead[]; next_cursor: string | null; has_more: boolean }> {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return this.req(`/partner/me/leads?${query.toString()}`);
  }

  // ── Wissens-Beitrag: explicit governance declaration → untrusted review quarantine ──
  async contribute(
    body: ContributePayload,
    idempotencyKey = this.newIdempotencyKey(),
  ): Promise<ContributionResponse> {
    const policy = await this.activeLifecyclePolicy();
    return this.req("/contribute", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        ...body,
        governance: {
          tenant_id: policy.tenant_id,
          policy_authority_ref: policy.policy_authority_ref,
          purpose_version: policy.purpose_version,
          consent_version: policy.consent_version,
          ...body.governance,
        },
      }),
    });
  }
  withdrawContribution(
    id: number,
    idempotencyKey = this.newIdempotencyKey(),
  ): Promise<LifecycleReceiptResponse> {
    return this.req(`/contributions/${id}/withdrawal`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ reason_code: "user_withdrawal" }),
    });
  }
  adminListContributions(
    cursor?: string,
    limit = 50,
  ): Promise<{ contributions: AdminContribution[]; next_cursor: string | null; has_more: boolean }> {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return this.req(`/admin/contributions?${query.toString()}`);
  }
  adminSetContributionStatus(id: number, status: string, reviewNote: string): Promise<unknown> {
    return this.req(`/admin/contributions/${id}/status`, {
      method: "PUT",
      body: JSON.stringify({ status, review_note: reviewNote }),
    });
  }

  // ── Legal-by-Design (Phase B): the onboarding Legal-Gate ────────────────────────────────────
  legalAcceptanceStatus(): Promise<LegalAcceptanceStatus> {
    return this.req("/legal/acceptance-status");
  }
  submitLegalAcceptance(payload: LegalAcceptancePayload): Promise<unknown> {
    return this.req("/legal/acceptance", { method: "POST", body: JSON.stringify(payload) });
  }
}
