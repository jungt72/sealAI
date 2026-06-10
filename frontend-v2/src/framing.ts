/* The safety-framing surface of the SPA (M7 build-gate check 3). Since the cutover arc (Phase 1a)
 * the SINGLE SOURCE of these texts is the backend: sealai_v2/core/framing.py, served at
 * GET /api/v2/framing. The constants below are the build-time FALLBACK so the framing is never
 * blank if that fetch fails — contract-pinned to contracts/framing.v2.json (framing.contract.test
 * here, test_api_framing.py on the backend), so fallback and server text cannot drift while both
 * suites are green. Components consume the resolved values via useFraming() (framing-context). */

export type Framing = {
  claim_boundary: string;
  vorlaeufig: string;
  remembered_hint: string;
  candidate: string;
  geltungsrahmen: string;
};

export const CLAIM_BOUNDARY =
  "Orientierung, keine Freigabe — finale Auswahl, Validierung und Freigabe liegen beim Hersteller / verantwortlichen Ingenieur.";

/** Shown on any answer that is NOT backed by reviewed grounding (ChatResponse.grounded === false). */
export const VORLAEUFIG = "vorläufig — gegen Datenblatt / Hersteller verifizieren";

/** Frames a remembered (distilled) fact as unverified — the re-ask-keystone honesty hint. */
export const REMEMBERED_HINT = "zuvor genannt — bei Bedarf bestätigen";

/** Recommendations are candidates, never a final decision. */
export const CANDIDATE = "Kandidat, nicht final";

/** The briefing's long Geltungsrahmen note (rendered server-side into briefing bodies; carried
 * here only so the fallback covers the full contract). */
export const GELTUNGSRAHMEN =
  "**Hinweis (Geltungsrahmen):** Diese Zusammenstellung ist eine technische **Orientierung/Screening** auf Basis der aktuell vorliegenden Angaben und Richtwerte — **keine** verbindliche Auslegung, **keine** Freigabe und **keine** Eignungs-, Zulassungs- oder Konformitätszusage. Sie ist eine **Hersteller-Prüfgrundlage**: die finale Werkstoff- und Auslegungsentscheidung sowie die Freigabe trifft der Hersteller bzw. die verantwortliche Fachperson anhand des konkreten Datenblatts.";

export const FALLBACK_FRAMING: Framing = {
  claim_boundary: CLAIM_BOUNDARY,
  vorlaeufig: VORLAEUFIG,
  remembered_hint: REMEMBERED_HINT,
  candidate: CANDIDATE,
  geltungsrahmen: GELTUNGSRAHMEN,
};
