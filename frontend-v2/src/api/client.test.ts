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
