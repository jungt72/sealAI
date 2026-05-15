import { describe, expect, it } from "vitest";

import {
  isAtLiveBottom,
  isProgrammaticScroll,
  nextModeAfterUserScroll,
  shouldShowJumpToLive,
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
});
