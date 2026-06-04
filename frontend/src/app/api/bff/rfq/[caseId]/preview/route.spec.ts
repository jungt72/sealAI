import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

vi.mock("@/lib/bff/auth-token", () => ({
  getAccessToken: vi.fn(async () => "test-token"),
}));

vi.mock("@/lib/bff/backend", () => ({
  buildBackendUrl: vi.fn((path: string) => `https://backend.test${path}`),
}));

function postPreviewRequest(body?: Record<string, unknown>) {
  return new Request("https://sealai.test/api/bff/rfq/session-should-not-be-case/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}

function previewRouteContext(caseId = "case-123") {
  return { params: Promise.resolve({ caseId }) };
}

describe("BFF RFQ preview route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("forwards the exact safe create_preview body with the durable case id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        preview_id: "preview-1",
        case_id: "case-123",
        dispatch_allowed: false,
        external_contact_allowed: false,
      }),
    );

    await POST(
      postPreviewRequest({
        expected_case_revision: 7,
        session_id: "session-should-not-be-case",
      }),
      previewRouteContext("case-123"),
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    const backendBody = JSON.parse(String(init?.body));
    expect(url).toBe("https://backend.test/api/v1/rfq/preview?case_id=case-123");
    expect(backendBody).toEqual({
      action: "create_preview",
      explicit_user_intent: true,
      dispatch_allowed: false,
      external_contact_allowed: false,
      expected_case_revision: 7,
    });
    expect(String(init?.body)).not.toContain("session-should-not-be-case");
    expect(backendBody).not.toHaveProperty("export_allowed");
    expect(backendBody).not.toHaveProperty("send_allowed");
    expect(backendBody).not.toHaveProperty("contact_manufacturer");
  });

  it("does not forward unsafe caller dispatch, export, send, or contact flags", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        preview_id: "preview-2",
        case_id: "case-123",
        dispatch_allowed: false,
        external_contact_allowed: false,
      }),
    );

    await POST(
      postPreviewRequest({
        dispatch_allowed: true,
        external_contact_allowed: true,
        export_allowed: true,
        send_allowed: true,
        contact_manufacturer: true,
      }),
      previewRouteContext("case-123"),
    );

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      action: "create_preview",
      explicit_user_intent: true,
      dispatch_allowed: false,
      external_contact_allowed: false,
    });
  });

  it("passes through the backend action gate and result contract without adding send semantics", async () => {
    const backendResponse = {
      preview_id: "preview-3",
      case_id: "case-123",
      case_revision: 9,
      current_case_revision: 9,
      stale: false,
      consent_status: "not_requested",
      dispatch_enabled: false,
      dispatch_allowed: false,
      external_contact_allowed: false,
      qualified_action_gate: {
        consent_required_before_export_or_sharing: true,
        dispatch_allowed: false,
        external_contact_allowed: false,
        preview_creation_requires_explicit_user_intent: true,
        export_requires_consent: true,
      },
      result_contract: {
        artifact_type: "rfq_preview",
        action: "create_rfq_preview",
        service_boundary: "RfqPreviewService.create_preview_for_case",
        case_revision: 9,
        no_external_dispatch: true,
        manufacturer_review_required: true,
      },
      payload: {
        consent_boundary: {
          export_intent_acknowledgement_required: true,
          automatic_dispatch_allowed: false,
        },
      },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(backendResponse));

    const response = await POST(postPreviewRequest(), previewRouteContext("case-123"));
    const body = await response.json();

    expect(body).toEqual(backendResponse);
    expect(body.dispatch_allowed).toBe(false);
    expect(body.external_contact_allowed).toBe(false);
    expect(body.qualified_action_gate.dispatch_allowed).toBe(false);
    expect(body.qualified_action_gate.external_contact_allowed).toBe(false);
    expect(body.payload.consent_boundary.export_intent_acknowledgement_required).toBe(true);
    expect(JSON.stringify(body)).not.toMatch(/send_allowed|contact_manufacturer|manufacturer_send/i);
  });
});
