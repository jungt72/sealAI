import { useCallback, useEffect, useRef } from "react";

/** Pure decision: is the scroll container within `slack` px of the bottom? Extracted so it is
 * unit-testable without layout (jsdom has none). */
export function isNearBottom(
  m: { scrollHeight: number; scrollTop: number; clientHeight: number },
  slack = 24,
): boolean {
  return m.scrollHeight - m.scrollTop - m.clientHeight <= slack;
}

/** Keeps a scroll container pinned to the bottom as new content arrives — UNLESS the user has
 * scrolled up, in which case their position is preserved. Native re-implementation of the V1 chat
 * auto-scroll behavior; imports no V1 code. Attach `ref` to the scroll element and `onScroll` to its
 * onScroll; bump `trigger` (e.g. message count) whenever new content is appended. */
export function useStickToBottom<T extends HTMLElement>(trigger: unknown) {
  const ref = useRef<T | null>(null);
  const pinned = useRef(true); // currently following the bottom?

  const onScroll = useCallback(() => {
    if (ref.current) pinned.current = isNearBottom(ref.current);
  }, []);

  useEffect(() => {
    if (ref.current && pinned.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [trigger]);

  return { ref, onScroll };
}
