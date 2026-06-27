import type { Briefing } from "../contracts";
import { downloadBriefingPdf } from "../lib/pdf";
import { ClaimBoundaryNote } from "./SafetyBanner";

/** The M4b briefing render. It carries the SAME claim-boundary framing as the chat view (build-gate
 * check 3 — ubiquity across surfaces: a briefing is domain content, so it is candidate/orientation,
 * not a release). Provenance lists the primary sources the render rested on. The briefing can be
 * downloaded as a PDF (the Anfrage document) WITHOUT sending it to any manufacturer. */
export function BriefingPane({ briefing }: { briefing: Briefing | null }) {
  if (!briefing) return null;
  return (
    <section className="briefing-pane" data-testid="briefing-pane">
      <header className="cockpit-head briefing-head">
        <h3>{briefing.title || "Briefing"}</h3>
        <button
          type="button"
          className="briefing-pdf-btn"
          data-testid="briefing-pdf"
          onClick={() => downloadBriefingPdf(briefing)}
        >
          Als PDF herunterladen
        </button>
      </header>
      <ClaimBoundaryNote />
      <pre className="briefing-body" data-testid="briefing-body">
        {briefing.body}
      </pre>
      {briefing.provenance.length > 0 && (
        <div className="briefing-provenance" data-testid="briefing-provenance">
          Quellen: {briefing.provenance.join(" · ")}
        </div>
      )}
    </section>
  );
}
