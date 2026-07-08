import { describe, expect, it } from "vitest";

import { hasRiskFlags, RISK_WARNING_TEXT } from "./riskFlags";

describe("hasRiskFlags", () => {
  it("is false for undefined/null/empty", () => {
    expect(hasRiskFlags(undefined)).toBe(false);
    expect(hasRiskFlags(null)).toBe(false);
    expect(hasRiskFlags([])).toBe(false);
  });

  it("is true for a non-empty array", () => {
    expect(hasRiskFlags(["ATEX"])).toBe(true);
  });
});

describe("RISK_WARNING_TEXT", () => {
  it("never claims approval/suitability language", () => {
    expect(RISK_WARNING_TEXT).toContain("keine Empfehlung");
    expect(RISK_WARNING_TEXT).not.toMatch(/ist geeignet|freigegeben/i);
  });
});
