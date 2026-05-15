export type ChatScrollMode = "following-bottom" | "submit-anchor" | "frozen" | "user-browsing";

export const LIVE_BOTTOM_THRESHOLD_PX = 28;
export const SUBMIT_ANCHOR_VIEWPORT_RATIO = 0.22;
export const SUBMIT_ANCHOR_MIN_PX = 96;
export const SUBMIT_ANCHOR_MAX_PX = 220;

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

export function submitAnchorOffset(element: Pick<HTMLElement, "clientHeight">): number {
  return Math.min(
    SUBMIT_ANCHOR_MAX_PX,
    Math.max(SUBMIT_ANCHOR_MIN_PX, element.clientHeight * SUBMIT_ANCHOR_VIEWPORT_RATIO),
  );
}

export function submitAnchorBottomSpacer(
  viewport: Pick<HTMLElement, "clientHeight" | "scrollHeight" | "scrollTop" | "getBoundingClientRect">,
  target: Pick<HTMLElement, "getBoundingClientRect">,
  currentSpacerPx = 0,
): number {
  const viewportBox = viewport.getBoundingClientRect();
  const targetBox = target.getBoundingClientRect();
  const desiredTop =
    viewport.scrollTop + targetBox.top - viewportBox.top - submitAnchorOffset(viewport as HTMLElement);
  const scrollHeightWithoutSpacer = Math.max(0, viewport.scrollHeight - currentSpacerPx);
  const maxTopWithoutSpacer = Math.max(0, scrollHeightWithoutSpacer - viewport.clientHeight);

  return Math.ceil(Math.max(0, desiredTop - maxTopWithoutSpacer));
}
