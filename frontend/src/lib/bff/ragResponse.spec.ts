import { describe, expect, it } from "vitest";

import { REDACTED_PATH_LABEL } from "@/lib/ragRedaction";

import { ragPassthroughResponse } from "./ragResponse";

describe("ragPassthroughResponse", () => {
  it("redacts internal path fields in json responses", async () => {
    const response = new Response(null, {
      status: 200,
      headers: { "content-type": "application/json" },
    });

    const result = ragPassthroughResponse(
      response,
      JSON.stringify({ filesystem: { path: "/home/thorsten/sealai/uploads/doc.pdf", exists: false } }),
    );

    expect(await result.json()).toEqual({
      filesystem: { path: REDACTED_PATH_LABEL, exists: false },
    });
  });

  it("redacts plain text fallback responses", async () => {
    const response = new Response(null, {
      status: 500,
      headers: { "content-type": "text/plain" },
    });

    const result = ragPassthroughResponse(response, "failed at /tmp/sealai/uploads/doc.pdf");

    expect(await result.text()).toBe(`failed at ${REDACTED_PATH_LABEL}`);
  });
});
