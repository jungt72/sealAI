import assert from "node:assert/strict";
import test from "node:test";

import { invokeQualifiedAction } from "./qualifiedActionContract.ts";

test("frontend button path uses backend action contract", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(
      JSON.stringify({
        case_id: "case-1",
        action: "download_rfq",
        allowed: true,
        executed: true,
        block_reasons: [],
        runtime_path: "STRUCTURED_QUALIFICATION",
        binding_level: "QUALIFIED_PRESELECTION",
        qualified_action_gate: { allowed: true },
        case_state: {
          qualified_action_status: {
            last_status: "executed",
          },
        },
        action_payload: { artifact_stub: "rfq_download_contract_v1" },
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  }) as typeof fetch;

  try {
    const result = await invokeQualifiedAction({
      apiEndpoint: "/api/agent",
      caseId: "case-1",
      authToken: "token-1",
    });

    assert.equal(result.executed, true);
    assert.equal((result.case_state as any)?.qualified_action_status?.last_status, "executed");
    assert.equal(calls[0]?.url, "/api/agent/cases/case-1/actions/download-rfq");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(
      (calls[0]?.init?.body as string | undefined) ?? "",
      JSON.stringify({ action: "download_rfq" }),
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
