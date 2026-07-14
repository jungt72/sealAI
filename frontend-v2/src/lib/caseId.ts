// Active case routing deliberately avoids query strings. The case identifier lives in the
// browser history entry (for Back/Forward) with a tab-scoped sessionStorage fallback (for reload).
// It is still an untrusted selector: the backend re-authorizes it against tenant + subject.

const LEGACY_CASE_PARAM = "case";
const HISTORY_CASE_KEY = "sealaiCaseId";
const CURRENT_CASE_KEY = "sealai.v2.current_case.v1";
const PENDING_CASE_KEY = "sealai.v2.pending_auth_case.v1";
const CASE_ID_RE = /^[A-Za-z0-9._~-]{1,255}$/;

function validCaseId(value: unknown): value is string {
  return typeof value === "string" && CASE_ID_RE.test(value);
}

function historyCaseId(): string | null {
  const state = window.history.state as Record<string, unknown> | null;
  return validCaseId(state?.[HISTORY_CASE_KEY]) ? state[HISTORY_CASE_KEY] : null;
}

/** Return the current case without leaving it in a URL. A legacy ``?case=`` is imported once and
 * synchronously scrubbed, so old bookmarks remain usable without perpetuating log/referrer leaks. */
export function getCaseIdFromUrl(): string | null {
  const fromState = historyCaseId();
  if (fromState) return fromState;

  const url = new URL(window.location.href);
  const legacy = url.searchParams.get(LEGACY_CASE_PARAM);
  if (legacy !== null) {
    url.searchParams.delete(LEGACY_CASE_PARAM);
    const state = { ...(window.history.state ?? {}) } as Record<string, unknown>;
    if (validCaseId(legacy)) state[HISTORY_CASE_KEY] = legacy;
    window.history.replaceState(state, "", url.pathname + url.search + url.hash);
    if (validCaseId(legacy)) {
      sessionStorage.setItem(CURRENT_CASE_KEY, legacy);
      return legacy;
    }
  }

  const stored = sessionStorage.getItem(CURRENT_CASE_KEY);
  return validCaseId(stored) ? stored : null;
}

/** Persist a case in history state, never in the address bar or a request target. */
export function setCaseIdInUrl(caseId: string, opts: { replace?: boolean } = {}): void {
  if (!validCaseId(caseId)) throw new Error("invalid case id");
  const { replace = true } = opts;
  const state = {
    ...(window.history.state ?? {}),
    [HISTORY_CASE_KEY]: caseId,
  } as Record<string, unknown>;
  sessionStorage.setItem(CURRENT_CASE_KEY, caseId);
  const target = window.location.pathname + window.location.search + window.location.hash;
  if (replace) window.history.replaceState(state, "", target);
  else window.history.pushState(state, "", target);
}

export function newCaseId(): string {
  return crypto.randomUUID();
}

export function stashCaseIdForAuthRedirect(caseId: string): void {
  if (!validCaseId(caseId)) throw new Error("invalid case id");
  sessionStorage.setItem(PENDING_CASE_KEY, caseId);
}

export function takeStashedCaseId(): string | null {
  const value = sessionStorage.getItem(PENDING_CASE_KEY);
  sessionStorage.removeItem(PENDING_CASE_KEY);
  return validCaseId(value) ? value : null;
}
