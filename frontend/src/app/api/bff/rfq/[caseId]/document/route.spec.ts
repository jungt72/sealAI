import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

function documentRequest() {
  return new Request("https://sealai.test/api/bff/rfq/case-123/document");
}

function documentRouteContext(caseId = "case-123") {
  return { params: Promise.resolve({ caseId }) };
}

describe("BFF RFQ legacy document route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a safe disabled response without proxying legacy document content", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new Error("legacy document backend must not be called"),
    );

    const response = await GET(documentRequest(), documentRouteContext());
    const body = await response.json();

    expect(response.status).toBe(410);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(body.error.code).toBe("rfq_document_legacy_disabled");
    expect(body.error.message).toContain("governed RFQ preview/export flow");
    expect(body.dispatch_allowed).toBe(false);
    expect(body.external_contact_allowed).toBe(false);
    expect(body.export_requires_consent).toBe(true);
    expect(body.final_approval_claim_allowed).toBe(false);
    expect(body.preview_service_boundary).toBe("RfqPreviewService.create_preview_for_case");
    expect(JSON.stringify(body)).not.toMatch(/<html|send_allowed|contact_manufacturer/i);
  });
});
