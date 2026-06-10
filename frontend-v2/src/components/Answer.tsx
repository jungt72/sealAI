import type { ChatResponse } from "../contracts";
import { CANDIDATE, VORLAEUFIG } from "../framing";
import { Citations } from "./Citation";

/** An assistant answer + its honesty framing: a `vorläufig` badge when NOT grounded, a candidate
 * label (orientation, not a final decision), and primary-source citations. */
export function Answer({ res }: { res: ChatResponse }) {
  return (
    <div className="answer" data-testid="answer">
      <div className="answer-badges">
        <span className="badge badge-candidate" data-testid="candidate-label">
          {CANDIDATE}
        </span>
        {!res.grounded && (
          <span className="badge badge-vorlaeufig" data-testid="vorlaeufig-label">
            {VORLAEUFIG}
          </span>
        )}
      </div>
      <div className="answer-text">{res.answer}</div>
      <Citations cites={res.citations} />
    </div>
  );
}
