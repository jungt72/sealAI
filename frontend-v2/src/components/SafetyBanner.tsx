import { CLAIM_BOUNDARY } from "../framing";

/** Persistent, always-mounted claim-boundary (Orientierung≠Freigabe). Lives in the Shell so it shows
 * regardless of content/error state — the framing is never dropped (build-gate check 5). */
export function SafetyBanner() {
  return (
    <div className="safety-banner" role="note" data-testid="claim-boundary">
      {CLAIM_BOUNDARY}
    </div>
  );
}

/** Embeddable claim-boundary note — reused inside recommendations / briefing so the same framing
 * appears on EVERY domain-content surface (build-gate check 3 ubiquity), not only the chat view. */
export function ClaimBoundaryNote() {
  return (
    <p className="claim-boundary-note" data-testid="claim-boundary">
      {CLAIM_BOUNDARY}
    </p>
  );
}
