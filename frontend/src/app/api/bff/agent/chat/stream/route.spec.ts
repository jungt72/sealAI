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

function buildInterruptedBackendSseStream(frames: string[], error: Error): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      controller.error(error);
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

  it("drops legacy backend preview chunks and streams only the guarded final answer", async () => {
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
    expect(payloads[0]).toMatchObject({ type: "answer.stream.start", source: "reply" });
    expect(payloads[1]).toMatchObject({ type: "answer.token", text: "Finale Antwort" });
    expect(payloads[2]).toMatchObject({ type: "answer.done" });
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

    expect(payloads[0]).toMatchObject({ type: "answer.stream.start", source: "reply" });
    expect(stateUpdate).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      reply: "Hallo! Schoen, dass du da bist.",
      responseClass: "conversational_answer",
    });
    expect(stateUpdate).not.toHaveProperty("caseId");
    expect(payloads.at(-1)).toBe("[DONE]");
  });

  it("uses a no-case conversation id as backend session context without binding a case", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","reply":"PTFE Antwort","response_class":"conversational_answer","run_meta":{"knowledge_service":{"no_case_created":true,"source_classification":"KNOWLEDGE_QUERY"}}}\n\n',
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
      body: JSON.stringify({
        conversationId: "knowledge-dialogue-session-1",
        message: "ich brauche informationen zu PTFE",
      }),
    });

    const response = await POST(request);
    const backendInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const backendBody = JSON.parse(String(backendInit.body));
    const payloads = parseSsePayloads(await response.text());
    const stateUpdate = findPayload(payloads, "state_update");

    expect(backendBody.session_id).toBe("knowledge-dialogue-session-1");
    expect(payloads.some((payload) => typeof payload !== "string" && payload.type === "case_bound")).toBe(false);
    expect(stateUpdate).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      reply: "PTFE Antwort",
      responseClass: "conversational_answer",
    });
    expect(stateUpdate).not.toHaveProperty("caseId");
  });

  it("sends an explicit client turn id to the backend", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","turn_id":"client-turn-1","reply":"ok","response_class":"conversational_answer"}\n\n',
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
      body: JSON.stringify({ message: "Hallo", turnId: "client-turn-1" }),
    });

    const response = await POST(request);
    const backendInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const backendBody = JSON.parse(String(backendInit.body));
    const payloads = parseSsePayloads(await response.text());
    const stateUpdate = findPayload(payloads, "state_update");

    expect(backendBody.turn_id).toBe("client-turn-1");
    expect(stateUpdate.turn_id).toBe("client-turn-1");
  });

  it("creates a turn id for legacy clients before calling the backend", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
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
    const backendInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const backendBody = JSON.parse(String(backendInit.body));
    const payloads = parseSsePayloads(await response.text());
    const stateUpdate = findPayload(payloads, "state_update");

    expect(backendBody.turn_id).toEqual(expect.any(String));
    expect(backendBody.turn_id).not.toContain("Hallo");
    expect(stateUpdate.turn_id).toBe(backendBody.turn_id);
  });

  it("does not bind a fresh conversational turn just because backend includes UI projections", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          `data: ${JSON.stringify({
            type: "state_update",
            reply: "Hallo! Mir geht es gut, danke der Nachfrage.",
            response_class: "conversational_answer",
            ui: {
              parameter: {
                status: "available",
              },
            },
            structured_state: {
              conversation_messages: [
                { role: "user", content: "Hallo, wie geht es dir?" },
              ],
            },
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
      body: JSON.stringify({ message: "Hallo, wie geht es dir?" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());
    const stateUpdate = findPayload(payloads, "state_update");

    expect(payloads.some((payload) => typeof payload !== "string" && payload.type === "case_bound")).toBe(false);
    expect(stateUpdate).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      responseClass: "conversational_answer",
    });
    expect(stateUpdate).not.toHaveProperty("caseId");
    expect(stateUpdate.ui).toEqual({ parameter: { status: "available" } });
    expect(stateUpdate.structuredState).toEqual({
      conversation_messages: [
        { role: "user", content: "Hallo, wie geht es dir?" },
      ],
    });
  });

  it("binds conversational governed turns when workspace parameters override a soft no-case marker", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          `data: ${JSON.stringify({
            type: "state_update",
            reply: "Ich habe die Angaben als Fallkandidaten erkannt.",
            response_class: "conversational_answer",
            run_meta: {
              conversation: {
                no_case_created: true,
              },
            },
            structured_state: {
              view: {
                parameter: {
                  parameters: [
                    { field_name: "medium", value: "Dampf CIP", confidence: "inferred" },
                    { field_name: "temperature_c", value: 120, unit: "°C", confidence: "inferred" },
                  ],
                  parameter_count: 2,
                  needs_confirmation: true,
                },
              },
            },
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
      body: JSON.stringify({
        message: "Pharma-Pumpe mit Dampf CIP, 120 C und PTFE O-Ring",
      }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());
    const caseBound = findPayload(payloads, "case_bound");
    const stateUpdate = findPayload(payloads, "state_update");

    expect(caseBound.caseId).toEqual(expect.any(String));
    expect(stateUpdate).toMatchObject({
      type: "state_update",
      noCaseCreated: false,
      responseClass: "conversational_answer",
    });
    expect(stateUpdate.caseId).toEqual(caseBound.caseId);
    expect(stateUpdate.structuredState).toMatchObject({
      view: {
        parameter: {
          parameter_count: 2,
        },
      },
    });
  });

  it("does not bind hard no-case knowledge turns even when material-like projections are present", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          `data: ${JSON.stringify({
            type: "state_update",
            reply: "PTFE ist ein Fluorpolymer.",
            response_class: "conversational_answer",
            run_meta: {
              knowledge_service: {
                no_case_created: true,
                source_classification: "KNOWLEDGE_QUERY",
              },
            },
            structured_state: {
              view: {
                parameter: {
                  parameters: [
                    { field_name: "material", value: "PTFE", confidence: "contextual" },
                  ],
                  parameter_count: 1,
                },
              },
            },
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
      body: JSON.stringify({ message: "ich brauche informationen zu PTFE" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());
    const stateUpdate = findPayload(payloads, "state_update");

    expect(payloads.some((payload) => typeof payload !== "string" && payload.type === "case_bound")).toBe(false);
    expect(stateUpdate).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      responseClass: "conversational_answer",
    });
    expect(stateUpdate).not.toHaveProperty("caseId");
  });

  it("does not expose raw backend auth details when the token expired", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "token_expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
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

  it("emits a structured interrupted event when backend stream reading fails mid-stream", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildInterruptedBackendSseStream(
          ['data: {"type":"progress","data":{"event_type":"final_guard.running"}}\n\n'],
          new Error("network connection terminated"),
        ),
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );

    const request = new Request("https://sealai.test/api/bff/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Bitte prüfen", turnId: "client-turn-interrupted" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());
    const interrupted = findPayload(payloads, "interrupted");

    expect(interrupted).toMatchObject({
      type: "interrupted",
      code: "network_error",
      error_code: "network_error",
      turn_id: "client-turn-interrupted",
      is_final: false,
      message: "Die Verbindung zur Antwort wurde unterbrochen. Bitte versuche es erneut.",
    });
    expect(JSON.stringify(interrupted)).not.toContain("terminated");
  });

  it("refreshes and retries once when backend rejects an expired bearer token", async () => {
    vi.mocked(getAccessTokenResult).mockClear();
    vi.mocked(getAccessTokenResult)
      .mockResolvedValueOnce({
        accessToken: "stale-token",
        cookieUpdates: [],
      })
      .mockResolvedValueOnce({
        accessToken: "refreshed-token",
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
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "token_expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
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
      body: JSON.stringify({ message: "Was ist NBR?" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());
    const firstInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const secondInit = fetchMock.mock.calls[1]?.[1] as RequestInit;
    const firstBody = JSON.parse(String(firstInit.body));
    const secondBody = JSON.parse(String(secondInit.body));

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(firstInit.headers).toMatchObject({ Authorization: "Bearer stale-token" });
    expect(secondInit.headers).toMatchObject({ Authorization: "Bearer refreshed-token" });
    expect(firstBody.turn_id).toEqual(expect.any(String));
    expect(secondBody.turn_id).toBe(firstBody.turn_id);
    expect(vi.mocked(getAccessTokenResult).mock.calls[1]?.[1]).toEqual({ forceRefresh: true });
    expect(response.headers.get("set-cookie")).toContain("__Secure-authjs.session-token=rotated-session");
    expect(findPayload(payloads, "state_update")).toMatchObject({ reply: "ok" });
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

    expect(payloads[0]).toMatchObject({ type: "answer.stream.start", source: "answer_markdown" });
    expect(payloads[1]).toMatchObject({ type: "answer.token", text: "real assistant answer" });
    expect(stateUpdate).toMatchObject({
      type: "state_update",
      noCaseCreated: true,
      reply: "deterministic fallback",
      answer_markdown: "real assistant answer",
    });
    expect(stateUpdate).not.toHaveProperty("caseId");
  });

  it("preserves backend stream metadata for frontend event dedupe", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          'data: {"type":"state_update","event_id":"event-1","turn_id":"turn-1","sequence":7,"event_type":"state_update","is_final":true,"reply":"ok","response_class":"conversational_answer"}\n\n',
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

    expect(stateUpdate).toMatchObject({
      type: "state_update",
      event_id: "event-1",
      turn_id: "turn-1",
      sequence: 7,
      event_type: "state_update",
      is_final: true,
      reply: "ok",
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
          'data: {"type":"progress","data":{"event_type":"final_guard.done"}}\n\n',
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
    const progress = findPayload(payloads, "progress");
    const stateUpdate = findPayload(payloads, "state_update");

    expect(progress).toMatchObject({
      type: "progress",
      data: { event_type: "final_guard.done" },
    });
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

  it("forwards V9.2 turn, guard and dashboard contracts from backend state_update events", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        buildBackendSseStream([
          `data: ${JSON.stringify({
            type: "state_update",
            reply: "Geprüfte Antwort",
            response_class: "structured_clarification",
            turn_envelope: {
              turn_id: "turn-1",
              session_id: "case-1",
              user_message: "Technische Frage",
              route: "engineering_case_update",
              intent: "engineering_case_update",
              is_technical: true,
              state_mutation_policy: "case_revision_allowed",
              requires_engine: true,
              requires_evidence: true,
              requires_adversarial_review: false,
              requires_final_guard: true,
              streaming_policy: "status_only_until_guarded_final",
              created_at: "2026-05-18T00:00:00+00:00",
              trace_id: "trace-1",
            },
            turn_boundary_decision: {
              route: "engineering_case_update",
              state_mutation_policy: "case_revision_allowed",
              requires_engine: true,
              streaming_policy: "status_only_until_guarded_final",
            },
            final_guard_result: {
              decision: "pass",
              severity: "none",
              final_stream_allowed: true,
            },
            v92_dashboard: {
              schema_version: "v92_dashboard_contract_1",
              turn_id: "turn-1",
              route: "engineering_case_update",
              readiness_band: "screening_possible",
            },
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
      body: JSON.stringify({ message: "Technische Frage" }),
    });

    const response = await POST(request);
    const payloads = parseSsePayloads(await response.text());
    const stateUpdate = findPayload(payloads, "state_update");

    expect(stateUpdate).toMatchObject({
      type: "state_update",
      turnEnvelope: {
        turn_id: "turn-1",
        streaming_policy: "status_only_until_guarded_final",
      },
      turnBoundaryDecision: {
        route: "engineering_case_update",
        streaming_policy: "status_only_until_guarded_final",
      },
      finalGuardResult: {
        decision: "pass",
        final_stream_allowed: true,
      },
      v92Dashboard: {
        schema_version: "v92_dashboard_contract_1",
        readiness_band: "screening_possible",
      },
    });
  });
});
