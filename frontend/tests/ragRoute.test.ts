import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { GET } from "../src/app/api/rag/documents/route";

vi.mock("../src/lib/backend-internal", () => ({
  getBackendInternalBase: () => "http://backend.test",
}));

const makeRequest = (url: string) =>
  new NextRequest(url, {
    method: "GET",
    headers: {
      Authorization: "Bearer token-123",
    },
  });

describe("api/rag/documents route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("forwards auth and query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const req = makeRequest("http://localhost/api/rag/documents?limit=20&status=done");
    const resp = await GET(req);

    expect(resp.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://backend.test/api/v1/rag/documents?limit=20&status=done");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer token-123");
  });
});
