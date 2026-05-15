export type ChatScrollMode = "following-bottom" | "submit-anchor" | "frozen" | "user-browsing";

export const LIVE_BOTTOM_THRESHOLD_PX = 28;

type ScrollMetrics = Pick<HTMLElement, "clientHeight" | "scrollHeight" | "scrollTop">;

export function isAtLiveBottom(
  element: ScrollMetrics,
  threshold = LIVE_BOTTOM_THRESHOLD_PX,
): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
}

export function shouldShowJumpToLive(hasConversation: boolean, element: ScrollMetrics): boolean {
  return hasConversation && !isAtLiveBottom(element);
}

export function nextModeAfterUserScroll(atLiveBottom: boolean): ChatScrollMode {
  return atLiveBottom ? "following-bottom" : "user-browsing";
}

export function isProgrammaticScroll(untilMs: number, nowMs: number): boolean {
  return nowMs < untilMs;
}
