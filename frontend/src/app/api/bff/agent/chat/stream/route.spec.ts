import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { getAccessTokenResult } from "@/lib/bff/auth-token";

import { POST } from "./route";

const RFQ_READINESS_CONTRACT_FIXTURE_PATH = resolve(
  process.cwd(),
  "../contracts/rfq_readiness_projection_v1.fixture.json",
);

vi.mock("@/lib/bff/auth-token", () => ({
  getAccessTokenResult: vi.fn(async () => ({
    accessToken: "test-token",
    cookieUpdates: [],
  })),
  applyBffCookieUpdates: vi.fn(
    (
      response: { cookies: { set: (name: string, value: string, options: Record<string, unknown>) => void } },
      updates: Array<{ name: string; value: string; options: Record<string, unknown> }>,
    ) => {
      for (const update of updates) {
        response.cookies.set(update.name, update.value, update.options);
      }
    },
  ),
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

function findPayload(
  payloads: Array<string | Record<string, unknown>>,
  type: string,
): Record<string, unknown> {
  const payload = payloads.find(
    (candidate): candidate is Record<string, unknown> =>
      typeof candidate !== "string" && candidate.type === type,
  );
  expect(payload).toBeDefined();
  return payload as Record<string, unknown>;
}

function rfqReadinessContractFixture(): Record<string, unknown> {
  return JSON.parse(
    readFileSync(RFQ_READINESS_CONTRACT_FIXTURE_PATH, "utf8"),
  ) as Record<string, unknown>;
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
          'data: {"type":"text_reset"}\n\n',
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

    expect(payloads).toHaveLength(5);
    expect(payloads[0]).toMatchObject({ type: "text_chunk", text: "Preview" });
    expect(payloads[1]).toMatchObject({ type: "text_reset" });
    expect(payloads[2]).toMatchObject({ type: "text_chunk", text: "Finale Antwort" });
    expect(payloads[3]).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      reply: "Finale Antwort",
      responseClass: "conversational_answer",
    });
    expect(payloads[3]).not.toHaveProperty("caseId");
    expect(payloads[4]).toBe("[DONE]");
  });

  it("persists rotated auth cookies on streaming responses", async () => {
    vi.mocked(getAccessTokenResult).mockResolvedValueOnce({
      accessToken: "fresh-token",
      cookieUpdates: [
        {
          name: "__Secure-authjs.session-token",
          value: "rotated-session",
          options: {
            httpOnly: true,
            sameSite: "lax",
            secure: true,
            path: "/",
            maxAge: 3600,
          },
        },
      ],
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","reply":"ok","response_class":"conversational_answer"}\n\n',
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

    expect(response.headers.get("set-cookie")).toContain("__Secure-authjs.session-token=rotated-session");
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
    const stateUpdate = findPayload(payloads, "state_update");

    expect(payloads[0]).toMatchObject({ type: "text_chunk" });
    expect(stateUpdate).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      reply: "Hallo! Schoen, dass du da bist.",
      responseClass: "conversational_answer",
    });
    expect(stateUpdate).not.toHaveProperty("caseId");
    expect(payloads.at(-1)).toBe("[DONE]");
  });

  it("does not expose raw backend auth details when the token expired", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "token_expired" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Was ist NBR?" }),
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(401);
    expect(body.error.message).toBe("Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.");
    expect(body.error.message).not.toContain("token_expired");
    expect(body.error.message).not.toContain("{");
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
    const stateUpdate = findPayload(payloads, "state_update");

    expect(payloads[0]).toMatchObject({ type: "text_chunk", text: "real assistant answer" });
    expect(stateUpdate).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      reply: "deterministic fallback",
      answer_markdown: "real assistant answer",
    });
    expect(stateUpdate).not.toHaveProperty("caseId");
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
    const stateUpdate = findPayload(payloads, "state_update");

    expect(stateUpdate).toMatchObject({
      type: "state_update",
      runMeta: { answer_trace: answerTrace },
    });
  });

  it("forwards rfq_readiness_projection from backend state_update events", async () => {
    const rfqReadinessProjection = rfqReadinessContractFixture();
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
    const stateUpdate = findPayload(payloads, "state_update");

    expect(stateUpdate).toMatchObject({
      type: "state_update",
      rfq_readiness_projection: rfqReadinessProjection,
    });
    expect(stateUpdate.rfq_readiness_projection).toEqual(
      rfqReadinessProjection,
    );
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
    const stateUpdate = findPayload(payloads, "state_update");

    expect(stateUpdate).toMatchObject({
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
    const stateUpdate = findPayload(payloads, "state_update");

    expect(stateUpdate).toMatchObject({
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
    const stateUpdate = findPayload(payloads, "state_update");

    expect(stateUpdate).toMatchObject({
      type: "state_update",
      reply: "Alte Klasse",
      responseClass: null,
    });
  });
});
