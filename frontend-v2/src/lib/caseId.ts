// "Fälle"-Sidebar: the active case is persisted in the URL's ?case= query param — no router
// dependency (this codebase deliberately has none, and only ONE param needs persisting). Mirrors
// lib/navSidebar.ts's small-focused-module style, but reads/writes the URL instead of localStorage
// (case_id must survive a hard reload AND be shareable/bookmarkable, which localStorage alone can't
// give — see the ChatGPT-style sidebar request this implements).

const CASE_PARAM = "case";

/** The case_id from the current URL, or null if absent/blank. */
export function getCaseIdFromUrl(): string | null {
  const v = new URLSearchParams(window.location.search).get(CASE_PARAM);
  return v && v.trim() ? v : null;
}

/** Write case_id into the URL. `replace` (default true) never adds a browser-history entry — used
 * for the initial auto-generated id on load. Pass `replace: false` for an explicit user action
 * (switching cases, "Neue Frage") so the back button steps between cases, matching how ChatGPT's
 * own case switching behaves. */
export function setCaseIdInUrl(caseId: string, opts: { replace?: boolean } = {}): void {
  const { replace = true } = opts;
  const url = new URL(window.location.href);
  url.searchParams.set(CASE_PARAM, caseId);
  const target = url.pathname + url.search;
  if (replace) window.history.replaceState({}, "", target);
  else window.history.pushState({}, "", target);
}

/** A fresh, client-generated case id. Lazy by design — no backend call here; the actual
 * v2_sessions row is created server-side on the first real message (record_turn), matching the
 * existing behavior. Generating the id client-side is what lets the URL be reload-safe from the
 * very first visit, even before any message is sent. */
export function newCaseId(): string {
  return crypto.randomUUID();
}
