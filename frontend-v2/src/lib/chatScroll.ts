import { useCallback, useLayoutEffect, useRef, useState } from "react";

/** Pure decision: is the scroll container within `slack` px of the bottom? Extracted so it is
 * unit-testable without layout (jsdom has none). */
export function isNearBottom(
  m: { scrollHeight: number; scrollTop: number; clientHeight: number },
  slack = 24,
): boolean {
  return m.scrollHeight - m.scrollTop - m.clientHeight <= slack;
}

/** The chat log's scroll model — deliberately NO auto-follow, matching the pattern the major LLM
 * chat UIs converged on (ChatGPT, Claude, Gemini): the log never fights the user's own scroll
 * position, and never chases new content as it renders. The ONLY programmatic scroll is the one-shot
 * `pinNewTurn` move the caller triggers explicitly right after a submit (see ChatPane.send).
 * Everything else is either the user's own wheel/trackpad/keyboard scrolling, or an explicit click
 * on the jump-to-latest button.
 *
 * Attach `ref`/`onScroll` to the scroll container. `watch` (e.g. message count) re-checks
 * `showJumpButton` whenever new content lands, since a taller log can silently leave "the bottom"
 * without a scroll EVENT ever firing (no user action happened, only the content grew). */
export function useChatScroll<T extends HTMLElement>(watch: unknown) {
  const ref = useRef<T | null>(null);
  const [showJumpButton, setShowJumpButton] = useState(false);

  const recompute = useCallback(() => {
    if (ref.current) setShowJumpButton(!isNearBottom(ref.current));
  }, []);

  const onScroll = useCallback(() => recompute(), [recompute]);

  useLayoutEffect(() => {
    recompute();
  }, [watch, recompute]);

  const scrollToBottom = useCallback(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, []);

  return { ref, onScroll, showJumpButton, scrollToBottom };
}

/** Positions `el`'s top edge at `fraction` of the container's height from the top — the "pin the new
 * turn near the top, answer fills in below" pattern (ChatGPT/Claude/Gemini all converge on ~1/3, not
 * flush against the edge: it reads calmer and survives short answers without the message looking
 * awkwardly glued to the top chrome). Used ONCE, right after a submit; nothing re-invokes it while
 * the answer renders, so the pinned position never drifts once set.
 *
 * The turn is too short on its own (a user bubble + "thinking" indicator, before the answer lands)
 * for that scroll position to be reachable — the browser would clamp `scrollTop` to whatever content
 * exists below, landing the message lower than intended, and it would silently STAY there once the
   * (non-streaming) answer arrives, because nothing re-scrolls afterward. So `spacer` — an always-present
   * trailing element in the log — is grown to one full container height first, guaranteeing headroom
   * while the response is pending. Once the turn settles, `settleNewTurnSpacer` trims that temporary
   * headroom to the minimum required to preserve the current reading position. Direct DOM writes (not
   * React state) so the browser's layout reflects the new spacer height the instant `scrollTop` is
   * read/written after it, in one paint. */
export function pinNewTurn(
  container: HTMLElement | null,
  el: HTMLElement | null,
  spacer: HTMLElement | null,
  fraction = 1 / 3,
) {
  if (!container || !el) return;
  if (spacer) spacer.style.minHeight = `${Math.round(container.clientHeight)}px`;
  const targetOffset = Math.round(container.clientHeight * fraction);
  container.scrollTop = Math.max(0, el.offsetTop - targetOffset);
}

function spacerBlockSize(spacer: HTMLElement): number {
  const measured = spacer.offsetHeight || spacer.getBoundingClientRect().height;
  if (measured > 0) return measured;
  return Number.parseFloat(spacer.style.minHeight || "0") || 0;
}

export function settleNewTurnSpacer(container: HTMLElement | null, spacer: HTMLElement | null) {
  if (!container || !spacer) return;
  const currentTop = container.scrollTop;
  const naturalScrollHeight = Math.max(0, container.scrollHeight - spacerBlockSize(spacer));
  const requiredSpacer = Math.max(0, currentTop + container.clientHeight - naturalScrollHeight);
  spacer.style.minHeight = `${Math.ceil(requiredSpacer)}px`;
  container.scrollTop = currentTop;
}
