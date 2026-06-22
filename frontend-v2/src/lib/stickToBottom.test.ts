import { describe, expect, it } from "vitest";

import { isNearBottom } from "./stickToBottom";

describe("isNearBottom (auto-scroll decision)", () => {
  it("true when scrolled to the bottom", () => {
    expect(isNearBottom({ scrollHeight: 100, scrollTop: 50, clientHeight: 50 })).toBe(true);
  });
  it("true within the slack band just above the bottom", () => {
    expect(isNearBottom({ scrollHeight: 100, scrollTop: 30, clientHeight: 50 }, 24)).toBe(true); // 20 ≤ 24
  });
  it("false when the user has scrolled up past the slack", () => {
    expect(isNearBottom({ scrollHeight: 100, scrollTop: 0, clientHeight: 50 }, 24)).toBe(false); // 50 > 24
  });
});
