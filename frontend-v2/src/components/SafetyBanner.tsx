import { useFraming } from "../framing-context";

/** Persistent, always-mounted claim-boundary (Orientierung≠Freigabe). Lives in the Shell so it shows
 * regardless of content/error state — the framing is never dropped (build-gate check 5). */
export function SafetyBanner() {
  const { claim_boundary } = useFraming();
  return (
    <div className="safety-banner" role="note" data-testid="claim-boundary">
      {claim_boundary}
    </div>
  );
}

/** Embeddable claim-boundary note — reused inside recommendations / briefing so the same framing
 * appears on EVERY domain-content surface (build-gate check 3 ubiquity), not only the chat view. */
export function ClaimBoundaryNote() {
  const { claim_boundary } = useFraming();
  return (
    <p className="claim-boundary-note" data-testid="claim-boundary">
      {claim_boundary}
    </p>
  );
}
