import { describe, expect, it } from "vitest";

import { getRolesFromAccessToken } from "../src/lib/authz";

const encodePayload = (payload: Record<string, unknown>) => {
  const json = JSON.stringify(payload);
  const base64 = Buffer.from(json, "utf-8")
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `xxx.${base64}.yyy`;
};

const hasAdminRole = (token: string) => getRolesFromAccessToken(token).roleSet.has("admin");

describe("authz admin access", () => {
  it("allows admin role", () => {
    const token = encodePayload({ realm_access: { roles: ["admin"] } });
    expect(hasAdminRole(token)).toBe(true);
  });

  it("denies editor role", () => {
    const token = encodePayload({ realm_access: { roles: ["editor"] } });
    expect(hasAdminRole(token)).toBe(false);
  });

  it("denies viewer role", () => {
    const token = encodePayload({ realm_access: { roles: ["viewer"] } });
    expect(hasAdminRole(token)).toBe(false);
  });
});
