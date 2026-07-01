import { useCallback, useLayoutEffect, useRef, useState } from "react";

/** Pure decision: is the scroll container within `slack` px of the bottom? Extracted so it is
 * unit-testable without layout (jsdom has none). */
export function isNearBottom(
  m: { scrollHeight: number; scrollTop: number; clientHeight: number },
  slack = 24,
): boolean {
  return m.scrollHeight - m.scrollTop - m.clientHeight <= slack;
}

/** The chat log's scroll model — deliberately NO auto-follow. The log never fights the user's own
 * scroll position, and never chases new content on its own; the ONLY programmatic scroll is the
 * one-shot "the user's new message goes near the top" move the caller triggers explicitly via
 * `scrollElementToTop` right after a submit (see ChatPane.send). Everything else is either the
 * user's own wheel/trackpad/keyboard scrolling, or an explicit click on the jump-to-latest button.
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

  /** Positions one element's top edge just below the container's top edge — used ONCE, right
   * after the user submits, so their new message (and the full reading room below it for the
   * answer) is immediately visible without following any further. Relies on the container's own
   * `scroll-behavior: smooth` (app.css) for the animation; a plain property assignment is enough. */
  const scrollElementToTop = useCallback((el: HTMLElement | null, offset = 8) => {
    const container = ref.current;
    if (el && container) container.scrollTop = Math.max(0, el.offsetTop - offset);
  }, []);

  return { ref, onScroll, showJumpButton, scrollToBottom, scrollElementToTop };
}
