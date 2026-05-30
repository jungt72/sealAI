"use client";

import { useEffect, useState } from "react";

/**
 * SSR-safe media-query hook.
 *
 * The initial value is a stable `false` on the server AND on the first client
 * render, so server and client markup match (no Next.js hydration mismatch).
 * The real match is read in `useEffect` after mount and kept in sync via a
 * `change` listener.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(query);
    const update = () => setMatches(mql.matches);
    update();

    // Modern + legacy Safari listener APIs.
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", update);
      return () => mql.removeEventListener("change", update);
    }
    mql.addListener(update);
    return () => mql.removeListener(update);
  }, [query]);

  return matches;
}

/** Pocket-cockpit breakpoint — below the desktop cockpit layout (lg = 1024px). */
export const MOBILE_MEDIA_QUERY = "(max-width: 1023px)";

export function useIsMobile(query: string = MOBILE_MEDIA_QUERY): boolean {
  return useMediaQuery(query);
}
