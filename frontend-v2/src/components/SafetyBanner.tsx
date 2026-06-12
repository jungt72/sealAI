import { useFraming } from "../framing-context";

/** Persistent, always-mounted claim-boundary (Orientierung≠Freigabe). In the pilot-ui it renders as
 * the fixed doctrine line at the bottom of the stage — small and quiet, but always present,
 * regardless of content/error state — the framing is never dropped (build-gate check 5). */
export function SafetyBanner() {
  const { claim_boundary } = useFraming();
  return (
    <div className="doctrine-line" role="note" data-testid="claim-boundary">
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
