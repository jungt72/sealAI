import { describe, expect, it } from "vitest";

import { hasKnowledgeAccess } from "../src/lib/authz";

const encodePayload = (payload: Record<string, unknown>) => {
  const json = JSON.stringify(payload);
  const base64 = Buffer.from(json, "utf-8")
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `xxx.${base64}.yyy`;
};

describe("authz knowledge access", () => {
  it("allows admin role", () => {
    const token = encodePayload({ realm_access: { roles: ["admin"] } });
    expect(hasKnowledgeAccess(token)).toBe(true);
  });

  it("allows editor role", () => {
    const token = encodePayload({ realm_access: { roles: ["editor"] } });
    expect(hasKnowledgeAccess(token)).toBe(true);
  });

  it("denies viewer role", () => {
    const token = encodePayload({ realm_access: { roles: ["viewer"] } });
    expect(hasKnowledgeAccess(token)).toBe(false);
  });
});
