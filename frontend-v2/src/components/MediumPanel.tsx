import type { MediumIntelligence } from "../contracts";

function Section({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="medium-panel-section">
      <span className="medium-panel-section-title">{title}</span>
      <ul className="medium-panel-list">
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * MEDIUM panel (Medium Intelligence, Phase 2) — the researched, ALWAYS-vorläufig properties +
 * sealing challenges of the stated medium. Render-only; the data is helper-LLM knowledge (never
 * reviewed), so the "vorläufig" badge is mandatory and the copy steers to datasheet/manufacturer.
 */
export function MediumPanel({ data }: { data: MediumIntelligence }) {
  return (
    <section className="medium-panel" data-testid="medium-panel" aria-label="Medium">
      <header className="medium-panel-head">
        <span className="medium-panel-title">
          MEDIUM · {data.medium}
          {data.kategorie ? (
            <span className="medium-panel-kat"> ({data.kategorie})</span>
          ) : null}
        </span>
        <span
          className="medium-panel-badge"
          title="Automatische Recherche (LLM-Wissen) — nicht gegen Datenblatt/Hersteller geprüft"
        >
          vorläufig
        </span>
      </header>
      <Section title="Eigenschaften" items={data.eigenschaften} />
      <Section
        title="Herausforderungen für die Dichtung"
        items={data.herausforderungen}
      />
      {data.unsicher ? (
        <p className="medium-panel-unsicher">
          Ungewöhnliches Medium — diese Angaben sind besonders unsicher; unbedingt gegen
          Datenblatt/Hersteller verifizieren.
        </p>
      ) : null}
    </section>
  );
}
