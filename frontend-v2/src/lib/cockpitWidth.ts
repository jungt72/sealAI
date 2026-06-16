// Cockpit width: the resizable inner Parameter|Readout split (cockpit-focus, ≥1024px). The chosen
// Readout width is held in the `--readout-w` CSS var (grid track); this module owns the clamp + the
// localStorage persistence. Pure + storage-only — NO DOM, no React. Mirrors `lib/stickToBottom.ts`.

export const COCKPIT_W_KEY = "sealai-v2:cockpit-w"; // namespaced — must NOT collide with auth (no-storage invariant)
export const COCKPIT_MIN_PX = 360; // the cockpit can't collapse below this
export const COCKPIT_MAX_FRAC = 0.55; // …nor exceed this fraction of the workspace width

/** Clamp a desired cockpit width (px) to [min, max], where max = COCKPIT_MAX_FRAC · workspace width.
 *  Guards tiny workspaces (max never drops below min). Returns a rounded integer px. */
export function clampCockpitPx(desiredPx: number, workspaceWidthPx: number): number {
  const hi = Math.max(COCKPIT_MIN_PX, Math.round(workspaceWidthPx * COCKPIT_MAX_FRAC));
  return Math.round(Math.min(Math.max(desiredPx, COCKPIT_MIN_PX), hi));
}

/** The persisted width (integer px), or null when none/garbage. Fail-soft on storage errors. */
export function loadCockpitPx(): number | null {
  try {
    const raw = localStorage.getItem(COCKPIT_W_KEY);
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

export function saveCockpitPx(px: number): void {
  try {
    localStorage.setItem(COCKPIT_W_KEY, String(Math.round(px)));
  } catch {
    /* storage unavailable (private mode / quota) — width simply isn't remembered */
  }
}

export function clearCockpitPx(): void {
  try {
    localStorage.removeItem(COCKPIT_W_KEY);
  } catch {
    /* no-op */
  }
}
