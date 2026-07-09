import type { Citation as CitationT } from "../contracts";

/** Renders a citation surfacing the owner-verified PRIMARY source(s) (Parker / ISO 3601-2) — never
 * the internal card_id (which the API does not send to the client). */
export function Citation({ cite }: { cite: CitationT }) {
  return (
    <li className="citation" data-testid="citation">
      <span className="citation-text">{cite.text}</span>
      <span className="citation-source" data-testid="citation-source">
        {cite.sources.join(" · ")}
      </span>
    </li>
  );
}

/** The "Belege" (evidence/citations) section. Two INDEPENDENT guards each hide it:
 *  1. `showEvidence === false` — the route-aware display flag (Phase 2B); off-topic/smalltalk routes
 *     pass `false` so citations never surface where they make no sense. `undefined`/`true` → allowed
 *     (backward compat: older payloads without the flag behave exactly as before).
 *  2. `cites.length === 0` — the pre-existing empty check. `showEvidence` is ANDed with this, NOT an
 *     override: a technical route with no real citations still renders nothing. */
export function Citations({
  cites,
  showEvidence,
}: {
  cites: CitationT[];
  showEvidence?: boolean;
}) {
  if (showEvidence === false) return null;
  if (cites.length === 0) return null;
  return (
    <details className="citations">
      <summary>Belege ({cites.length})</summary>
      <ul>
        {cites.map((c, i) => (
          <Citation key={i} cite={c} />
        ))}
      </ul>
    </details>
  );
}
