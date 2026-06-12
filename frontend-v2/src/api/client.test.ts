import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "./client";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
    Promise.resolve(
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
    ),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** A streamed SSE response from pre-encoded frame strings (the backend's wire format). */
function sseResponse(frames: string[]): Response {
  const enc = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      for (const f of frames) c.enqueue(enc.encode(f));
      c.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

const RESULT_PAYLOAD = { answer: "ok", model: "m", grounded: true, intent: null, citations: [] };

afterEach(() => vi.unstubAllGlobals());

describe("ApiClient (check 5: fail-closed; talks only to /api/v2 + Bearer)", () => {
  it("sends the Bearer token and targets /api/v2", async () => {
    const fetchFn = mockFetch(200, { answer: "ok", model: "m", grounded: true, intent: null, citations: [] });
    const client = new ApiClient(() => "tok-123", () => undefined);
    await client.chat("hi");
    const [url, init] = fetchFn.mock.calls[0];
    expect(String(url)).toBe("/api/v2/chat");
    expect((init as RequestInit).headers).toMatchObject({ Authorization: "Bearer tok-123" });
  });

  it("on 401 → calls onUnauthenticated (re-login) and throws (no stale content)", async () => {
    mockFetch(401, { detail: "invalid token" });
    const onUnauth = vi.fn();
    const client = new ApiClient(() => "tok", onUnauth);
    await expect(client.memory()).rejects.toBeInstanceOf(ApiError);
    expect(onUnauth).toHaveBeenCalledOnce();
  });

  it("on a non-OK backend error → throws (caller shows error, never renders stale content)", async () => {
    mockFetch(500, { detail: "boom" });
    const onUnauth = vi.fn();
    const client = new ApiClient(() => "tok", onUnauth);
    await expect(client.chat("x")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauth).not.toHaveBeenCalled(); // 500 is not an auth failure
  });

  it("chatStream: reports stage starts and resolves with the single gated result", async () => {
    const fetchFn = vi.fn(() =>
      Promise.resolve(
        sseResponse([
          'event: stage\ndata: {"stage":"ground","status":"start"}\n\n',
          'event: stage\ndata: {"stage":"ground","status":"end"}\n\n',
          ": keepalive\n\n",
          'event: stage\ndata: {"stage":"generate","status":"start"}\n\n',
          `event: result\ndata: ${JSON.stringify(RESULT_PAYLOAD)}\n\n`,
        ]),
      ),
    );
    vi.stubGlobal("fetch", fetchFn);
    const stages: string[] = [];
    const client = new ApiClient(() => "tok", () => undefined);
    const res = await client.chatStream("hi", (s) => stages.push(s));
    expect(res).toEqual(RESULT_PAYLOAD);
    expect(stages).toEqual(["ground", "generate"]); // starts only — ends/keepalive ignored
    const [url] = fetchFn.mock.calls[0] as unknown as [string];
    expect(String(url)).toBe("/api/v2/chat/stream");
  });

  it("chatStream: an error frame rejects with ApiError (no partial content surfaced)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          sseResponse([
            'event: stage\ndata: {"stage":"generate","status":"start"}\n\n',
            'event: error\ndata: {"message":"fehlgeschlagen"}\n\n',
          ]),
        ),
      ),
    );
    const client = new ApiClient(() => "tok", () => undefined);
    await expect(client.chatStream("hi", () => undefined)).rejects.toBeInstanceOf(ApiError);
  });

  it("chatStream: a stream that ends without a result frame rejects (fail-closed)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(sseResponse(['event: stage\ndata: {"stage":"recall","status":"start"}\n\n'])),
      ),
    );
    const client = new ApiClient(() => "tok", () => undefined);
    await expect(client.chatStream("hi", () => undefined)).rejects.toBeInstanceOf(ApiError);
  });

  it("chatStream: 401 → onUnauthenticated + throws, like every other call", async () => {
    mockFetch(401, { detail: "invalid token" });
    const onUnauth = vi.fn();
    const client = new ApiClient(() => "tok", onUnauth);
    await expect(client.chatStream("hi", () => undefined)).rejects.toBeInstanceOf(ApiError);
    expect(onUnauth).toHaveBeenCalledOnce();
  });

  it("chatStream: 404 (older backend without /chat/stream) falls back to plain /chat once", async () => {
    const fetchFn = vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(
        String(input).endsWith("/chat/stream")
          ? new Response("not found", { status: 404 })
          : new Response(JSON.stringify(RESULT_PAYLOAD), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
      ),
    );
    vi.stubGlobal("fetch", fetchFn);
    const client = new ApiClient(() => "tok", () => undefined);
    const res = await client.chatStream("hi", () => undefined);
    expect(res).toEqual(RESULT_PAYLOAD);
    expect(fetchFn.mock.calls.map((c) => String(c[0]))).toEqual([
      "/api/v2/chat/stream",
      "/api/v2/chat",
    ]);
  });

  it("only ever calls the /api/v2 base (no V1 backend, no domain logic)", async () => {
    const fetchFn = mockFetch(200, { case_state: [], history: [] });
    const client = new ApiClient(() => "tok", () => undefined);
    await client.memory();
    await client.forgetAll();
    for (const call of fetchFn.mock.calls) {
      expect(String(call[0])).toMatch(/^\/api\/v2\//);
    }
  });
});
