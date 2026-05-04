import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

vi.mock("@/lib/bff/auth-token", () => ({
  getAccessToken: vi.fn(async () => "test-token"),
}));

vi.mock("@/lib/bff/backend", () => ({
  buildBackendUrl: vi.fn((path: string) => `https://backend.test${path}`),
}));

function buildBackendSseStream(frames: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      controller.close();
    },
  });
}

function parseSsePayloads(raw: string): Array<string | Record<string, unknown>> {
  return raw
    .split("\n\n")
    .map((frame) => frame.trim())
    .filter(Boolean)
    .map((frame) => frame.replace(/^data:\s*/, ""))
    .map((payload) => (payload === "[DONE]" ? payload : JSON.parse(payload)));
}

describe("BFF agent chat stream route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("forwards live text chunks and keeps state_update as the canonical final contract", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"text_chunk","text":"Preview"}\n\n',
          'data: {"type":"text_replacement","text":"Audit only"}\n\n',
          'data: {"type":"boundary_block","text":"Disclaimer"}\n\n',
          'data: {"type":"state_update","reply":"Finale Antwort","response_class":"conversational_answer"}\n\n',
          'data: {"type":"stream_end"}\n\n',
          "data: [DONE]\n\n",
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Hallo" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());

    expect(payloads).toHaveLength(4);
    expect(payloads[0]).toMatchObject({ type: "text_chunk", text: "Preview" });
    expect(payloads[1]).toMatchObject({ type: "case_bound" });
    expect(payloads[2]).toMatchObject({
      type: "state_update",
      caseId: expect.any(String),
      reply: "Finale Antwort",
      responseClass: "conversational_answer",
    });
    expect(payloads[3]).toBe("[DONE]");
  });

  it("keeps backend no-case fast responses session-bound without creating a case", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","reply":"Hallo! Schoen, dass du da bist.","response_class":"conversational_answer","run_meta":{"fast_responder":{"no_case_created":true,"source_classification":"GREETING"}}}\n\n',
          "data: [DONE]\n\n",
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Hallo" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());

    expect(payloads).toHaveLength(2);
    expect(payloads[0]).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      reply: "Hallo! Schoen, dass du da bist.",
      responseClass: "conversational_answer",
    });
    expect(payloads[0]).not.toHaveProperty("caseId");
    expect(payloads[1]).toBe("[DONE]");
  });

  it("forwards answer_markdown from backend state_update events", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","reply":"deterministic fallback","answer_markdown":"real assistant answer","response_class":"conversational_answer"}\n\n',
          "data: [DONE]\n\n",
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Hallo" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());

    expect(payloads[1]).toMatchObject({
      type: "state_update",
      reply: "deterministic fallback",
      answer_markdown: "real assistant answer",
    });
  });

  it("forwards answer_trace under runMeta without rewriting it", async () => {
    const answerTrace = {
      reply_source: "knowledge_service",
      answer_markdown_source: "knowledge_composer",
      final_visible_source: "answer_markdown",
      composer_attempted: true,
      composer_succeeded: true,
      hcl_attempted: false,
      hcl_succeeded: false,
      fallback_reason: null,
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          `data: ${JSON.stringify({
            type: "state_update",
            reply: "deterministic fallback",
            answer_markdown: "real assistant answer",
            response_class: "conversational_answer",
            run_meta: { answer_trace: answerTrace },
          })}\n\n`,
          "data: [DONE]\n\n",
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Was ist PTFE?" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());

    expect(payloads[1]).toMatchObject({
      type: "state_update",
      runMeta: { answer_trace: answerTrace },
    });
  });

  it("forwards rfq_readiness_projection from backend state_update events", async () => {
    const rfqReadinessProjection = {
      manufacturer_review_ready: false,
      rfq_basis_ready: true,
      known_missing_fields: ["surface_finish"],
      open_points: ["Compound durch Hersteller pruefen"],
      blocking_reasons: [],
      pending_question: {
        target_field: "surface_finish",
        question_text: "Welche Oberflaeche ist dokumentiert?",
      },
      consent_required: true,
      dispatch_allowed: false,
      external_contact_allowed: false,
      final_approval_claim_allowed: false,
      preview_available: true,
      preview_possible: true,
      preview_action_available: true,
      preview_action_name: "create_preview",
      preview_endpoint: "/api/v1/rfq/preview",
      preview_creation_requires_explicit_user_intent: true,
      preview_export_requires_consent: true,
      preview_requires_explicit_endpoint: true,
      preview_service_boundary: "RfqPreviewService.create_preview_for_case",
      projection_version: "rfq_readiness_projection_v1",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          `data: ${JSON.stringify({
            type: "state_update",
            reply: "Die Anfragebasis kann vorbereitet werden.",
            response_class: "governed_state_update",
            rfq_readiness_projection: rfqReadinessProjection,
          })}\n\n`,
          "data: [DONE]\n\n",
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "RFQ-Basis?" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());

    expect(payloads[1]).toMatchObject({
      type: "state_update",
      rfq_readiness_projection: {
        preview_action_name: "create_preview",
        dispatch_allowed: false,
        external_contact_allowed: false,
        pending_question: {
          target_field: "surface_finish",
          question_text: "Welche Oberflaeche ist dokumentiert?",
        },
      },
    });
  });

  it("forwards assertions from backend state_update events", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","reply":"OK","response_class":"governed_state_update","assertions":{"temperature_c":{"asserted_value":80,"unit":"°C","confidence":0.92}}}\n\n',
          "data: [DONE]\n\n",
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "80°C" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());

    expect(payloads[1]).toMatchObject({
      type: "state_update",
      assertions: { temperature_c: { asserted_value: 80, unit: "°C", confidence: 0.92 } },
    });
  });


  it("forwards proposed case deltas from backend state_update events", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","reply":"OK","response_class":"governed_state_update","proposed_case_delta":{"schema_version":"case_delta_v0_4","fields":[{"field_name":"pressure_bar","proposed_value":4,"unit":"bar","status":"proposed"}]}}\n\n',
          "data: [DONE]\n\n",
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "4 bar" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());

    expect(payloads[1]).toMatchObject({
      type: "state_update",
      proposedCaseDelta: {
        schema_version: "case_delta_v0_4",
        fields: [{ field_name: "pressure_bar", proposed_value: 4, unit: "bar" }],
      },
    });
  });

  it("does not forward legacy outward class aliases into the productive UI contract", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","reply":"Alte Klasse","response_class":"rfq_ready"}\n\n',
          "data: [DONE]\n\n",
        ]),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Status?" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());

    expect(payloads[1]).toMatchObject({
      type: "state_update",
      reply: "Alte Klasse",
      responseClass: null,
    });
  });
});
