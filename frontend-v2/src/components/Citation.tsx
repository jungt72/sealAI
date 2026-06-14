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

export function Citations({ cites }: { cites: CitationT[] }) {
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
