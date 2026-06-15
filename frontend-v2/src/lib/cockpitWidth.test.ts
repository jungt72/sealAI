import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { clampCockpitPx, clearCockpitPx, COCKPIT_W_KEY, loadCockpitPx, saveCockpitPx } from "./cockpitWidth";

describe("cockpitWidth — clamp + persistence (the resizable 60/40 split)", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("clamps to [min 360px, max 55% of the workspace width]", () => {
    expect(clampCockpitPx(300, 1200)).toBe(360); // below min → min
    expect(clampCockpitPx(900, 1200)).toBe(660); // above max (0.55·1200 = 660) → max
    expect(clampCockpitPx(480, 1200)).toBe(480); // in range → unchanged
    expect(clampCockpitPx(440.4, 1200)).toBe(440); // rounds to integer px
  });

  it("keeps min as the effective bound when 55% would fall below it (tiny workspace)", () => {
    expect(clampCockpitPx(400, 500)).toBe(360); // 0.55·500 = 275 < 360 → min wins
  });

  it("round-trips save → load and clear", () => {
    expect(loadCockpitPx()).toBeNull();
    saveCockpitPx(440);
    expect(localStorage.getItem(COCKPIT_W_KEY)).toBe("440");
    expect(loadCockpitPx()).toBe(440);
    clearCockpitPx();
    expect(loadCockpitPx()).toBeNull();
  });

  it("load returns null on empty / non-numeric storage", () => {
    localStorage.setItem(COCKPIT_W_KEY, "");
    expect(loadCockpitPx()).toBeNull();
    localStorage.setItem(COCKPIT_W_KEY, "abc");
    expect(loadCockpitPx()).toBeNull();
  });
});
