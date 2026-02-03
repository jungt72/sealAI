import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { GET as getState } from "../src/app/api/langgraph/state/route";
import { POST as postPatch } from "../src/app/api/langgraph/parameters/patch/route";
import { POST as postConfirm } from "../src/app/api/langgraph/confirm/go/route";

vi.mock("../src/lib/backend-internal", () => ({
  getBackendInternalBase: () => "http://backend.test/",
}));

const makeGetRequest = (url: string) =>
  new NextRequest(url, {
    method: "GET",
    headers: {
      Authorization: "Bearer token-123",
    },
  });

const makePostRequest = (url: string, token: string, body: Record<string, unknown>) =>
  new NextRequest(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

describe("api/langgraph routes", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("forwards state to /api/v1/langgraph/state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const req = makeGetRequest("http://localhost/api/langgraph/state?thread_id=smoke");
    const resp = await getState(req);

    expect(resp.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://backend.test/api/v1/langgraph/state?thread_id=smoke");
    expect(init.method).toBe("GET");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer token-123");
  });

  it("forwards parameters patch to /api/v1/langgraph/parameters/patch", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const req = makePostRequest("http://localhost/api/langgraph/parameters/patch", "token-456", {
      parameters: { medium: "oil" },
    });
    const resp = await postPatch(req);

    expect(resp.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://backend.test/api/v1/langgraph/parameters/patch");
    expect(init.method).toBe("POST");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer token-456");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ parameters: { medium: "oil" } }));
  });

  it("forwards confirm go to /api/v1/langgraph/confirm/go", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const req = makePostRequest("http://localhost/api/langgraph/confirm/go", "token-789", {
      confirm: true,
    });
    const resp = await postConfirm(req);

    expect(resp.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://backend.test/api/v1/langgraph/confirm/go");
    expect(init.method).toBe("POST");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer token-789");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ confirm: true }));
  });
});
