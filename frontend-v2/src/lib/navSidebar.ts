// Navigation sidebar expand/collapse state (claude.ai-style). Persisted in localStorage so the
// chosen width survives reloads. Pure + storage-only — NO DOM, no React. Mirrors `lib/cockpitWidth.ts`.

export const NAV_EXPANDED_KEY = "sealai-v2:nav-expanded"; // namespaced — no collision with auth/cockpit

/** The persisted expanded state; defaults to collapsed (the calm icon rail) when unset/garbage. */
export function loadNavExpanded(): boolean {
  try {
    return localStorage.getItem(NAV_EXPANDED_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveNavExpanded(expanded: boolean): void {
  try {
    localStorage.setItem(NAV_EXPANDED_KEY, expanded ? "1" : "0");
  } catch {
    /* storage unavailable (private mode / quota) — the choice simply isn't remembered */
  }
}
