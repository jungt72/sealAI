import type { ChatResponse } from "../contracts";
import { useFraming } from "../framing-context";
import { hasRiskFlags, RISK_WARNING_TEXT } from "../lib/safety/riskFlags";
import { Citations } from "./Citation";
import { Markdown } from "./Markdown";

/** Legal-by-Design Phase D (Goal 6): an unmissable warning when the QUESTION matched a regulated/
 * safety-critical term (ATEX, FDA, Sauerstoff, ...) — reuses the Gegencheck note's exact visual
 * treatment (same severity tier, same warning tokens, see app.css's .gegencheck-note comment) and
 * the same "rendered OUTSIDE the collapsed meta" placement, for the identical reason: this must not
 * require a click to see. Detection is backend-only + deterministic (safety/risk_flags.py) — this
 * component only renders what the server already decided, never re-detects client-side. */
function RiskFlagsNote({ riskFlags }: { riskFlags: ChatResponse["risk_flags"] }) {
  if (!hasRiskFlags(riskFlags)) return null;
  return (
    <div className="gegencheck-note" data-testid="risk-flags-note">
      <span className="gegencheck-label">Regulierter/sicherheitskritischer Bereich erkannt</span>
      <p className="gegencheck-text">{RISK_WARNING_TEXT}</p>
      <p className="gegencheck-source">Erkannt: {riskFlags.join(", ")}</p>
    </div>
  );
}

/** Modus E (Gegencheck): a DISQUALIFY-ONLY verdict (owner doctrine E4-1) — never render an
 * affirmative "passt/geeignet" for a non-disqualifying basis. Only the two attention-worthy states
 * surface (hard incompatibility / bedingt); "matrix_compatible"/"no_matrix_data"/"no_medium" stay
 * silent, because the absence of a documented incompatibility is not itself a suitability claim.
 * Rendered OUTSIDE the collapsed answer-meta details (unlike the other badges below): a
 * disqualifying or conditional verdict must not require a click to see (audit L5, "was das System
 * nicht weiß, sagt es zuerst"). Text is the grounded matrix cell content verbatim — never invented. */
function GegencheckNote({ gegencheck }: { gegencheck: ChatResponse["gegencheck"] }) {
  if (!gegencheck) return null;
  if (gegencheck.disqualified) {
    return (
      <div className="gegencheck-note" data-testid="gegencheck-disqualified">
        <span className="gegencheck-label">Gegencheck: Unverträglichkeit</span>
        <p className="gegencheck-text">{gegencheck.reason}</p>
        {gegencheck.source && <p className="gegencheck-source">{gegencheck.source}</p>}
      </div>
    );
  }
  if (gegencheck.basis === "matrix_conditional") {
    return (
      <div className="gegencheck-note" data-testid="gegencheck-conditional">
        <span className="gegencheck-label">Gegencheck: bedingt</span>
        <p className="gegencheck-text">{gegencheck.condition}</p>
        {gegencheck.source && <p className="gegencheck-source">{gegencheck.source}</p>}
      </div>
    );
  }
  return null; // matrix_compatible / no_matrix_data / no_medium — E4-1: never an affirmative badge
}

/** L3 trust status (audit L3 "Unsicherheit ist ein Zustand, kein Textbaustein"): lets the user tell
 * a confidently-checked answer from one the safety check adjusted, or one that was never confidently
 * checked at all — instead of every answer looking equally trustworthy. `verified` already folds
 * PASS/FLAG/CORRECTED into one honest signal (see api/serializers.py::_verification); `hedged` takes
 * priority since it means THIS answer's draft was blocked and replaced. */
function VerificationBadge({ res }: { res: ChatResponse }) {
  if (res.verification?.hedged) {
    return (
      <span className="badge badge-hedged" data-testid="verification-hedged">
        Antwort durch interne Prüfung angepasst
      </span>
    );
  }
  if (res.verified) {
    return (
      <span className="badge badge-verified" data-testid="verification-verified">
        geprüft
      </span>
    );
  }
  if (res.verification && (res.verification.ran === false || res.verification.parse_ok === false)) {
    return (
      <span className="badge badge-unverified" data-testid="verification-unverified">
        nicht geprüft
      </span>
    );
  }
  return null; // no verification block on this payload at all (older/hand-built response)
}

function NextQuestion({ res }: { res: ChatResponse }) {
  const question = res.next_question;
  if (!question) return null;
  return (
    <section className="next-question" data-testid="next-question" aria-label="Nächste fachliche Klärung">
      <span className="next-question-label">Nächste fachliche Klärung</span>
      <p>{question.question_text}</p>
      {(question.allowed_unknown || question.allowed_unobtainable) && (
        <small>„Unbekannt“ oder „nicht ermittelbar“ kann ausdrücklich angegeben werden.</small>
      )}
    </section>
  );
}

/** An assistant answer + its honesty framing: a `vorläufig` badge when NOT grounded, a candidate
 * label (orientation, not a final decision), the L3 trust status, primary-source citations, and —
 * outside the collapsed meta — a Gegencheck note when Modus E found an incompatibility or condition. */
export function Answer({ res }: { res: ChatResponse }) {
  const { candidate, vorlaeufig } = useFraming();
  return (
    <div className="answer" data-testid="answer">
      <RiskFlagsNote riskFlags={res.risk_flags} />
      <GegencheckNote gegencheck={res.gegencheck} />
      {/* Phase 2B route-aware display: the "Technische Vorbewertung" meta block is render-only
          scaffolding and makes no sense on smalltalk/off-topic turns. Hide it ONLY when the backend
          explicitly says so (show_technical_preassessment === false); `undefined`/`true` keep the
          pre-existing always-show behavior (older payloads / route optimization off). */}
      {res.show_technical_preassessment !== false && (
        <details className="answer-meta" data-testid="technical-preassessment">
          <summary>Technische Vorbewertung</summary>
          <span className="badge badge-candidate" data-testid="candidate-label">
            {candidate}
          </span>
          {!res.grounded && (
            <span className="badge badge-vorlaeufig" data-testid="vorlaeufig-label">
              {vorlaeufig}
            </span>
          )}
          <VerificationBadge res={res} />
        </details>
      )}
      <div className="answer-text">
        <Markdown source={res.answer} />
      </div>
      {/* Belege: `show_evidence` is threaded as an INDEPENDENT guard, ANDed with Citations' own
          empty-citations check (so it can only hide, never invent citations). */}
      <Citations cites={res.citations} showEvidence={res.show_evidence} />
      <NextQuestion res={res} />
    </div>
  );
}
