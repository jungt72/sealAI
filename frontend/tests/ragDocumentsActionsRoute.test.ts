import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { DELETE } from "../src/app/api/rag/documents/[id]/route";
import { POST } from "../src/app/api/rag/documents/[id]/retry/route";

vi.mock("../src/lib/backend-internal", () => ({
  getBackendInternalBase: () => "http://backend.test",
}));

const makeDeleteRequest = (url: string) =>
  new NextRequest(url, {
    method: "DELETE",
    headers: {
      Authorization: "Bearer token-123",
    },
  });

const makeRetryRequest = (url: string) =>
  new NextRequest(url, {
    method: "POST",
    headers: {
      Authorization: "Bearer token-456",
    },
  });

describe("api/rag/documents/[id] routes", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("forwards delete to backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const req = makeDeleteRequest("http://localhost/api/rag/documents/doc-123");
    const resp = await DELETE(req, { params: { id: "doc-123" } });

    expect(resp.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://backend.test/api/v1/rag/documents/doc-123");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer token-123");
    expect(init.method).toBe("DELETE");
  });

  it("forwards retry to backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const req = makeRetryRequest("http://localhost/api/rag/documents/doc-456/retry");
    const resp = await POST(req, { params: { id: "doc-456" } });

    expect(resp.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://backend.test/api/v1/rag/documents/doc-456/retry");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer token-456");
    expect(init.method).toBe("POST");
  });
});
