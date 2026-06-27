import type { Alternativen } from "../contracts";
import { GELTUNGSRAHMEN } from "../framing";

/**
 * HERSTELLER-AUSWAHL panel (Modus F, Dim. 6) — capable manufacturers selected BY CAPABILITY only
 * (neutral, §3.9; never pay-to-rank). When the owner's Hersteller seed is still empty the backend
 * returns grounded_data=false; the panel then shows the honest "no grounded data" stance + which
 * capability axes to specify — so the feature is visible + truthful even before the data is curated.
 */
export function AlternativenPanel({ data }: { data: Alternativen }) {
  const grounded =
    data.grounded_data && !!data.hersteller && data.hersteller.length > 0;
  return (
    <section
      className="alt-panel"
      data-testid="alternativen-panel"
      aria-label="Hersteller-Auswahl"
    >
      <header className="alt-panel-head">
        <span className="alt-panel-title">HERSTELLER-AUSWAHL</span>
        <span
          className="alt-panel-badge"
          title="Auswahl rein nach Fähigkeit (Werkstoff, Bauform, Größe, Zertifikate) — nie nach Bezahlung"
        >
          neutral
        </span>
      </header>
      {grounded ? (
        <ul className="alt-panel-list">
          {data.hersteller!.map((h, i) => (
            <li key={i}>{h}</li>
          ))}
        </ul>
      ) : (
        <p className="alt-panel-empty">
          {data.hinweis ||
            "Aktuell liegen keine geerdeten Hersteller-Fähigkeitsdaten vor."}
        </p>
      )}
      {data.neutralitaet ? (
        <p className="alt-panel-note">{data.neutralitaet}</p>
      ) : null}
      <p className="alt-panel-disclaimer">{GELTUNGSRAHMEN}</p>
    </section>
  );
}
