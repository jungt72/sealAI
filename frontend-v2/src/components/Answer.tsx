import type { ChatResponse } from "../contracts";
import { useFraming } from "../framing-context";
import { Citations } from "./Citation";
import { Markdown } from "./Markdown";

/** An assistant answer + its honesty framing: a `vorläufig` badge when NOT grounded, a candidate
 * label (orientation, not a final decision), and primary-source citations. */
export function Answer({ res }: { res: ChatResponse }) {
  const { candidate, vorlaeufig } = useFraming();
  return (
    <div className="answer" data-testid="answer">
      <details className="answer-meta">
        <summary>Technische Vorbewertung</summary>
        <span className="badge badge-candidate" data-testid="candidate-label">
          {candidate}
        </span>
        {!res.grounded && (
          <span className="badge badge-vorlaeufig" data-testid="vorlaeufig-label">
            {vorlaeufig}
          </span>
        )}
      </details>
      <div className="answer-text">
        <Markdown source={res.answer} />
      </div>
      <Citations cites={res.citations} />
    </div>
  );
}
