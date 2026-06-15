import type { ConfirmationResponse } from "../contracts";
import { clarifyMessage } from "../lib/clarify";

const CALC_LABELS: Record<string, string> = {
  umfangsgeschwindigkeit: "Umfangsgeschwindigkeit (v)",
  pv_wert: "PV-Wert",
  verpressung_prozent: "Verpressung",
};

/** Presentation rounding only — the authoritative value is the backend's (this never derives one). */
const fmt = (v: number): string => v.toFixed(2).replace(".", ",");

/**
 * The deterministic parameter-submit confirmation (Phase 2b) — a chat message echoing what was
 * SETTLED (post-bind values, verbatim from the backend), the kern result, and any Rückfragen for
 * clarify-pending fields. NO LLM and NO client compute: every value here is verbatim from the backend
 * confirmation, so the fact-echo can never invent or rescale a number. A clarify-triggering value is
 * shown as a Rückfrage, never as "übernommen".
 */
export function ParamConfirmation({ conf }: { conf: ConfirmationResponse }) {
  const hasKern = conf.computed.length > 0 || conf.not_computed.length > 0;
  return (
    <section className="param-confirmation" data-testid="param-confirmation">
      {conf.uebernommen.length > 0 && (
        <div data-testid="confirmation-uebernommen">
          <p className="confirmation-head">Danke, ich habe folgendes übernommen:</p>
          <ul className="confirmation-list">
            {conf.uebernommen.map((u) => (
              <li key={u.feld}>
                <span className="confirmation-label">{u.label}:</span>{" "}
                <span className="confirmation-wert">{u.wert}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {hasKern && (
        <div data-testid="confirmation-kern">
          <p className="confirmation-head">Rechenkern (deterministisch):</p>
          <ul className="confirmation-list">
            {conf.computed.map((c) => (
              <li key={c.calc_id}>
                <span className="confirmation-label">{CALC_LABELS[c.calc_id] ?? c.calc_id}:</span>{" "}
                <span className="confirmation-wert">
                  {fmt(c.value)} {c.unit}
                </span>
              </li>
            ))}
            {conf.not_computed.map((n) => (
              <li key={n.calc_id} className="confirmation-open">
                <span className="confirmation-label">{CALC_LABELS[n.calc_id] ?? n.calc_id}:</span>{" "}
                nicht berechenbar
              </li>
            ))}
          </ul>
        </div>
      )}

      {conf.rueckfragen.length > 0 && (
        <div data-testid="confirmation-rueckfragen">
          <p className="confirmation-head">Rückfragen (noch nicht übernommen):</p>
          <ul className="confirmation-list">
            {conf.rueckfragen.map((r) => (
              <li
                key={r.feld}
                className="confirmation-rueckfrage"
                data-testid="confirmation-rueckfrage"
              >
                {clarifyMessage(r.clarification)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="confirmation-foot">Orientierung, keine Freigabe.</p>
    </section>
  );
}
