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

  it("drops backend preview events and forwards only the canonical state_update contract", async () => {
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

    expect(payloads).toHaveLength(3);
    expect(payloads[0]).toMatchObject({ type: "case_bound" });
    expect(payloads[1]).toMatchObject({
      type: "state_update",
      caseId: expect.any(String),
      reply: "Finale Antwort",
      responseClass: "conversational_answer",
    });
    expect(payloads[2]).toBe("[DONE]");
  });
});
