import { describe, expect, it } from "vitest";

import {
  isAtLiveBottom,
  isProgrammaticScroll,
  nextModeAfterUserScroll,
  shouldShowJumpToLive,
  submitAnchorBottomSpacer,
  submitAnchorOffset,
} from "./chatScroll";

function metrics(scrollTop: number, clientHeight = 500, scrollHeight = 1000) {
  return { scrollTop, clientHeight, scrollHeight } as HTMLElement;
}

describe("chatScroll", () => {
  it("treats the live end as reached only within the bottom tolerance", () => {
    expect(isAtLiveBottom(metrics(472))).toBe(true);
    expect(isAtLiveBottom(metrics(430))).toBe(false);
  });

  it("shows the jump-to-live affordance only when conversation content is below the viewport", () => {
    expect(shouldShowJumpToLive(false, metrics(100))).toBe(false);
    expect(shouldShowJumpToLive(true, metrics(100))).toBe(true);
    expect(shouldShowJumpToLive(true, metrics(500))).toBe(false);
  });

  it("switches between browsing and live-follow based on explicit user scroll position", () => {
    expect(nextModeAfterUserScroll(false)).toBe("user-browsing");
    expect(nextModeAfterUserScroll(true)).toBe("following-bottom");
  });

  it("guards programmatic scroll events from being interpreted as user intent", () => {
    expect(isProgrammaticScroll(1200, 1100)).toBe(true);
    expect(isProgrammaticScroll(1200, 1200)).toBe(false);
  });

  it("places submitted turns in the upper reading zone instead of at the hard viewport edge", () => {
    expect(submitAnchorOffset({ clientHeight: 360 } as HTMLElement)).toBe(96);
    expect(submitAnchorOffset({ clientHeight: 800 } as HTMLElement)).toBe(176);
    expect(submitAnchorOffset({ clientHeight: 1400 } as HTMLElement)).toBe(220);
  });

  it("adds temporary lower space when a submitted turn would otherwise be trapped near the bottom", () => {
    const viewport = {
      clientHeight: 500,
      scrollHeight: 1000,
      scrollTop: 500,
      getBoundingClientRect: () => ({ top: 100 }),
    } as HTMLElement;
    const latestUser = {
      getBoundingClientRect: () => ({ top: 460 }),
    } as HTMLElement;

    expect(submitAnchorBottomSpacer(viewport, latestUser)).toBe(250);
    expect(submitAnchorBottomSpacer({ ...viewport, scrollHeight: 1500 } as HTMLElement, latestUser)).toBe(0);
  });
});
