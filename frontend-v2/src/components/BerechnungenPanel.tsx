import type { ComputeResponse } from "../contracts";

/** The KERNEL channel (M8): deterministic values from the backend Rechenkern, rendered next to the
 * input chips. The browser NEVER computes — like ParameterForm, there is no formula import and no
 * arithmetic here; every number comes verbatim from /api/v2/compute (or a chat turn's in-band kern
 * result). A client-side number would re-create the false-provenance calc-leak, so it is
 * structurally absent. Open points ("nicht berechenbar") are shown honestly, with NO number. */

const LABELS: Record<string, string> = {
  umfangsgeschwindigkeit: "Umfangsgeschwindigkeit (v)",
  pv_wert: "PV-Wert",
  verpressung_prozent: "Verpressung",
};

const label = (calcId: string): string => LABELS[calcId] ?? calcId;

/** Display-format the kern's value: German decimal comma, presentation rounding only (the
 * authoritative value is the backend's — this never alters or derives a number). */
const fmt = (v: number): string => v.toFixed(2).replace(".", ",");

export function BerechnungenPanel({ compute }: { compute: ComputeResponse | null }) {
  const computed = compute?.computed ?? [];
  const notComputed = compute?.not_computed ?? [];
  const notes = compute?.notes ?? [];
  if (computed.length === 0 && notComputed.length === 0 && notes.length === 0) return null;

  return (
    <section
      className="fact-chips kernel-panel"
      data-testid="berechnungen-panel"
      aria-label="Berechnungen vom deterministischen Rechenkern"
    >
      <span className="chips-label">Berechnungen · deterministischer Rechenkern</span>
      <ul className="chips-row kernel-row">
        {computed.map((c) => (
          <li
            key={c.calc_id}
            className="fact-chip kernel-value"
            data-testid="kernel-value"
            title={c.input_origins.join(" · ")}
          >
            <span className="fact-feld">{label(c.calc_id)}</span>
            <span className="fact-wert">
              {fmt(c.value)} {c.unit}
            </span>
            <span className="kernel-meta">{c.formula}</span>
            <span className="kernel-prov">
              deterministisch berechnet
              {c.parent_fields.length ? ` aus ${c.parent_fields.join(", ")}` : ""}
            </span>
          </li>
        ))}
        {notComputed.map((n) => (
          <li
            key={n.calc_id}
            className="fact-chip kernel-open"
            data-testid="kernel-not-computed"
          >
            <span className="fact-feld">{label(n.calc_id)}</span>
            <span className="fact-wert">nicht berechenbar</span>
            <span className="kernel-meta">{n.reason}</span>
          </li>
        ))}
      </ul>
      {notes.map((note, i) => (
        <p key={i} className="kernel-note" data-testid="kernel-note">
          {note}
        </p>
      ))}
      <span className="chips-label kernel-hint">
        Orientierung, keine Freigabe — Werte vom Rechenkern; Eingaben bei Bedarf bestätigen.
      </span>
    </section>
  );
}
