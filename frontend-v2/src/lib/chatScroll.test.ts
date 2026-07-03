import { describe, expect, it } from "vitest";

import { isNearBottom, pinNewTurn, settleNewTurnSpacer } from "./chatScroll";

describe("isNearBottom (jump-button visibility decision)", () => {
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

// Plain mutable objects standing in for DOM nodes — pinNewTurn only touches offsetTop/clientHeight/
// scrollTop/style.minHeight, none of which need real layout (jsdom has none).
function fakeContainer(clientHeight: number) {
  return { clientHeight, scrollHeight: clientHeight, scrollTop: 0 } as unknown as HTMLElement;
}
function fakeEl(offsetTop: number) {
  return { offsetTop } as unknown as HTMLElement;
}
function fakeSpacer() {
  return { style: {} } as unknown as HTMLElement;
}

describe("pinNewTurn (pin the new turn ~1/3 down, ChatGPT/Claude/Gemini pattern)", () => {
  it("scrolls so the element lands at 1/3 of the container height from the top", () => {
    const container = fakeContainer(900);
    const el = fakeEl(2000);
    pinNewTurn(container, el, null);
    expect(container.scrollTop).toBe(2000 - Math.round(900 / 3)); // 1700
  });
  it("clamps to 0 rather than a negative scrollTop for an element near the very start", () => {
    const container = fakeContainer(900);
    const el = fakeEl(50);
    pinNewTurn(container, el, null);
    expect(container.scrollTop).toBe(0);
  });
  it("grows the spacer to a full container height, guaranteeing the position is reachable", () => {
    const container = fakeContainer(900);
    const spacer = fakeSpacer();
    pinNewTurn(container, fakeEl(2000), spacer);
    expect(spacer.style.minHeight).toBe("900px");
  });
  it("respects a custom fraction (e.g. flush-to-top for a narrow viewport)", () => {
    const container = fakeContainer(900);
    const el = fakeEl(2000);
    pinNewTurn(container, el, null, 0.1);
    expect(container.scrollTop).toBe(2000 - Math.round(900 * 0.1));
  });
  it("no-ops without throwing when the container or element is not yet mounted", () => {
    expect(() => pinNewTurn(null, fakeEl(100), fakeSpacer())).not.toThrow();
    expect(() => pinNewTurn(fakeContainer(900), null, fakeSpacer())).not.toThrow();
  });

  it("trims the spacer to preserve the current reading position after a short answer settles", () => {
    const container = fakeContainer(900);
    const spacer = fakeSpacer();
    Object.defineProperty(spacer, "offsetHeight", { configurable: true, value: 900 });
    Object.defineProperty(container, "scrollHeight", { configurable: true, value: 1600 });
    container.scrollTop = 500;
    spacer.style.minHeight = "900px";

    settleNewTurnSpacer(container, spacer);

    expect(spacer.style.minHeight).toBe("700px");
    expect(container.scrollTop).toBe(500);
  });

  it("removes the spacer entirely when the settled answer is already tall enough", () => {
    const container = fakeContainer(900);
    const spacer = fakeSpacer();
    Object.defineProperty(spacer, "offsetHeight", { configurable: true, value: 900 });
    Object.defineProperty(container, "scrollHeight", { configurable: true, value: 2400 });
    container.scrollTop = 500;
    spacer.style.minHeight = "900px";

    settleNewTurnSpacer(container, spacer);

    expect(spacer.style.minHeight).toBe("0px");
    expect(container.scrollTop).toBe(500);
  });
});
