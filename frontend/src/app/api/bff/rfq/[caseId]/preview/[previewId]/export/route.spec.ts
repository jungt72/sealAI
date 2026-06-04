import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

vi.mock("@/lib/bff/auth-token", () => ({
  getAccessToken: vi.fn(async () => "test-token"),
}));

vi.mock("@/lib/bff/backend", () => ({
  buildBackendUrl: vi.fn((path: string) => `https://backend.test${path}`),
}));

function exportRequest() {
  return new Request("https://sealai.test/api/bff/rfq/case-123/preview/preview-1/export");
}

function exportRouteContext(caseId = "case-123", previewId = "preview-1") {
  return { params: Promise.resolve({ caseId, previewId }) };
}

describe("BFF RFQ preview PDF export route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("proxies only the governed PDF export and preserves no-dispatch headers", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Uint8Array([37, 80, 68, 70]), {
        status: 200,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": 'attachment; filename="sealai-rfq-case-123-preview-1.pdf"',
          "X-SealAI-Dispatch-Allowed": "false",
          "X-SealAI-External-Contact-Allowed": "false",
        },
      }),
    );

    const response = await GET(exportRequest(), exportRouteContext());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://backend.test/api/v1/rfq/preview/preview-1/export.pdf");
    expect(init?.method).toBe("GET");
    expect(new Headers(init?.headers).get("Accept")).toBe("application/pdf");
    expect(response.headers.get("Content-Type")).toContain("application/pdf");
    expect(response.headers.get("Content-Disposition")).toContain("sealai-rfq-case-123-preview-1.pdf");
    expect(response.headers.get("X-SealAI-Dispatch-Allowed")).toBe("false");
    expect(response.headers.get("X-SealAI-External-Contact-Allowed")).toBe("false");
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(
      new Uint8Array([37, 80, 68, 70]),
    );
  });
});
