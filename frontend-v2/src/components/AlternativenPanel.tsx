import { useState } from "react";

import type { Alternativen, AnfrageResponse } from "../contracts";
import { GELTUNGSRAHMEN } from "../framing";

/**
 * HERSTELLER-AUSWAHL panel (Modus F, Dim. 6) — the PARTNER POOL (owner business model). Manufacturers
 * are selected BY CAPABILITY only (neutral, §3.9): payment gates pool MEMBERSHIP, never the ranking.
 * The pool is a paid listing, so it is TRANSPARENTLY labelled "Partner · Anzeige" — never disguised as
 * neutral merit. The user can trigger an Anfrage: the backend renders a structured RFQ briefing from
 * the session and routes it to the partner; the briefing preview is shown back (transparency). The
 * final clarification + offer happen between the manufacturer and the user OUTSIDE sealingAI.
 *
 * When the owner's partner pool is still empty the backend returns grounded_data=false; the panel then
 * shows the honest "no grounded data" stance — visible + truthful even before the pool is curated.
 */
type AnfrageState =
  | { phase: "idle" }
  | { phase: "sending" }
  | { phase: "sent"; res: AnfrageResponse }
  | { phase: "error" };

export function AlternativenPanel({
  data,
  onAnfrage,
}: {
  data: Alternativen;
  /** Fire the Anfrage for one partner (the host injects the session message + talks to /api/v2). */
  onAnfrage?: (partnerId: string) => Promise<AnfrageResponse>;
}) {
  const partners = data.grounded_data && data.hersteller ? data.hersteller : [];
  const grounded = partners.length > 0;
  const [states, setStates] = useState<Record<string, AnfrageState>>({});

  async function fire(partnerId: string) {
    if (!onAnfrage) return;
    setStates((s) => ({ ...s, [partnerId]: { phase: "sending" } }));
    try {
      const res = await onAnfrage(partnerId);
      setStates((s) => ({ ...s, [partnerId]: { phase: "sent", res } }));
    } catch {
      setStates((s) => ({ ...s, [partnerId]: { phase: "error" } }));
    }
  }

  return (
    <section
      className="alt-panel"
      data-testid="alternativen-panel"
      aria-label="Hersteller-Auswahl"
    >
      <header className="alt-panel-head">
        <span className="alt-panel-title">HERSTELLER-AUSWAHL</span>
        {grounded && data.partner ? (
          <span
            className="alt-panel-badge alt-panel-badge--partner"
            title="Bezahlte Partner-Listung. Die AUSWAHL erfolgt rein nach Fähigkeit (Werkstoff, Bauform, Größe, Zertifikate) — die Bezahlung bestimmt nur die Aufnahme in den Pool, nie die Reihenfolge."
          >
            Partner · Anzeige
          </span>
        ) : (
          <span
            className="alt-panel-badge"
            title="Auswahl rein nach Fähigkeit (Werkstoff, Bauform, Größe, Zertifikate) — nie nach Bezahlung"
          >
            neutral
          </span>
        )}
      </header>

      {grounded ? (
        <ul className="alt-panel-list">
          {partners.map((h) => {
            const st: AnfrageState = states[h.id] ?? { phase: "idle" };
            return (
              <li key={h.id} className="alt-partner">
                <div className="alt-partner-name">{h.firmenname}</div>
                {h.standort ? (
                  <div className="alt-partner-standort">{h.standort}</div>
                ) : null}
                {h.beschreibung ? (
                  <p className="alt-partner-desc">{h.beschreibung}</p>
                ) : null}
                {h.werkstoffe && h.werkstoffe.length > 0 ? (
                  <div className="alt-partner-tags">
                    {h.werkstoffe.map((w) => (
                      <span key={w} className="alt-tag">
                        {w}
                      </span>
                    ))}
                  </div>
                ) : null}
                {h.zertifikate && h.zertifikate.length > 0 ? (
                  <div className="alt-partner-tags">
                    {h.zertifikate.map((z) => (
                      <span key={z} className="alt-tag alt-tag--cert">
                        {z}
                      </span>
                    ))}
                  </div>
                ) : null}
                {h.website ? (
                  <a
                    className="alt-partner-web"
                    href={h.website}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {h.website.replace(/^https?:\/\//, "")}
                  </a>
                ) : null}

                {onAnfrage ? (
                  <div className="alt-partner-action">
                    {st.phase === "sent" ? (
                      <div className="alt-anfrage-done" data-testid="anfrage-done">
                        <strong className="alt-anfrage-ok">✓ Anfrage übermittelt</strong>
                        <p className="alt-anfrage-hinweis">{st.res.hinweis}</p>
                        <details className="alt-anfrage-briefing">
                          <summary>Übermitteltes Briefing ansehen</summary>
                          <pre className="alt-anfrage-briefing-body">
                            {st.res.briefing.body}
                          </pre>
                        </details>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="alt-anfrage-btn"
                        data-testid={`anfrage-${h.id}`}
                        disabled={st.phase === "sending"}
                        onClick={() => void fire(h.id)}
                      >
                        {st.phase === "sending" ? "Wird gesendet…" : "Anfrage senden"}
                      </button>
                    )}
                    {st.phase === "error" ? (
                      <p className="alt-anfrage-error">
                        Anfrage fehlgeschlagen — bitte erneut versuchen.
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
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
