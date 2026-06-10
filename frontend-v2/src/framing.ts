/* The safety-framing single source of truth (M7 build-gate check 3). EVERY domain-content surface
 * (chat, history, briefing) renders this same framing — by reusing these constants + the
 * <ClaimBoundary/> component — so the liability framing is consistent and ubiquitous, never only on
 * the main chat view. This is the UI end of the backend's "Erklärung ≠ Freigabe" honesty spine. */

export const CLAIM_BOUNDARY =
  "Orientierung, keine Freigabe — finale Auswahl, Validierung und Freigabe liegen beim Hersteller / verantwortlichen Ingenieur.";

/** Shown on any answer that is NOT backed by reviewed grounding (ChatResponse.grounded === false). */
export const VORLAEUFIG = "vorläufig — gegen Datenblatt / Hersteller verifizieren";

/** Frames a remembered (distilled) fact as unverified — the re-ask-keystone honesty hint. */
export const REMEMBERED_HINT = "zuvor genannt — bei Bedarf bestätigen";

/** Recommendations are candidates, never a final decision. */
export const CANDIDATE = "Kandidat, nicht final";
