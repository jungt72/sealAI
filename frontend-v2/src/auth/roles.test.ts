import { describe, expect, it } from "vitest";

import { herstellerIdFromToken, rolesFromToken } from "./oidc";

// rolesFromToken only DECODES the payload (no signature check — the backend re-verifies every call);
// a hand-built "header.payload.sig" with a base64 payload is enough to exercise the extraction.
function tokenWith(payload: object): string {
  return "h." + btoa(JSON.stringify(payload)) + ".s";
}

describe("rolesFromToken", () => {
  it("extracts realm_access.roles", () => {
    expect(
      rolesFromToken(tokenWith({ realm_access: { roles: ["sealai-admin", "user"] } })),
    ).toEqual(["sealai-admin", "user"]);
  });

  it("returns [] without realm_access", () => {
    expect(rolesFromToken(tokenWith({ sub: "x" }))).toEqual([]);
  });

  it("ignores non-string role entries", () => {
    expect(
      rolesFromToken(tokenWith({ realm_access: { roles: ["ok", 1, null] } })),
    ).toEqual(["ok"]);
  });

  it("returns [] for null / malformed tokens", () => {
    expect(rolesFromToken(null)).toEqual([]);
    expect(rolesFromToken("garbage")).toEqual([]);
  });
});

describe("herstellerIdFromToken", () => {
  it("extracts the hersteller_id claim", () => {
    expect(herstellerIdFromToken(tokenWith({ hersteller_id: "acme" }))).toBe("acme");
  });

  it('returns "" when absent / null / malformed', () => {
    expect(herstellerIdFromToken(tokenWith({ sub: "x" }))).toBe("");
    expect(herstellerIdFromToken(null)).toBe("");
    expect(herstellerIdFromToken("garbage")).toBe("");
  });
});
