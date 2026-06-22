/* Phase 1a contract test — the build-time fallback is pinned to contracts/framing.v2.json, the
 * SAME artifact the backend suite pins /api/v2/framing to (test_api_framing.py). While both suites
 * are green, fallback and server text are byte-identical: single source, no drift. */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { FALLBACK_FRAMING } from "./framing";

// vitest runs with cwd = frontend-v2/; the contract artifact lives at the repo root.
const contract = JSON.parse(
  readFileSync(resolve(process.cwd(), "..", "contracts", "framing.v2.json"), "utf-8"),
) as Record<string, string>;

describe("framing contract (single source)", () => {
  it("the fallback deep-equals the committed contract artifact", () => {
    expect(FALLBACK_FRAMING).toEqual(contract);
  });
});
