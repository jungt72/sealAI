import type { ComputeResponse } from "../contracts";
import { clarifyMessage } from "../lib/clarify";

/** The KERNEL channel (M8): deterministic values from the backend Rechenkern, rendered next to the
 * input chips. The browser NEVER computes — like ParameterForm, there is no formula import and no
 * arithmetic here; every number comes verbatim from /api/v2/compute (or a chat turn's in-band kern
 * result). A client-side number would re-create the false-provenance calc-leak, so it is
 * structurally absent.
 *
 * Calm cockpit: this is a quiet RESULTS surface — only computed values render as rows; the
 * not_computed "nicht berechenbar" open points are SUPPRESSED (the form already shows what is
 * still missing). The panel stays absent until there is something to show — it appears once ≥1
 * value is computed OR an actionable unit-clarification / conflict-note exists.
 *
 * Unit-recovery (clarifications): the binder owns the decision; the panel only renders it. The
 * confirm button appears STRICTLY when `one_click` is true (a SAFE canonical append) — never on
 * `unit_known_other` (where appending "mm" to "50 cm" would be a silent 10× wrong-bind). Confirming
 * re-settles the value through the existing edit channel (`onConfirmUnit`), never a client-side bind. */

const LABELS: Record<string, string> = {
  umfangsgeschwindigkeit: "Umfangsgeschwindigkeit (v)",
  pv_wert: "PV-Wert",
  verpressung_prozent: "Verpressung",
};

const label = (calcId: string): string => LABELS[calcId] ?? calcId;

/** Display-format the kern's value: German decimal comma, presentation rounding only (the
 * authoritative value is the backend's — this never alters or derives a number). */
const fmt = (v: number): string => v.toFixed(2).replace(".", ",");

export function BerechnungenPanel({
  compute,
  onConfirmUnit,
}: {
  compute: ComputeResponse | null;
  onConfirmUnit?: (feld: string, value: string) => void;
}) {
  const computed = compute?.computed ?? [];
  const clarifications = compute?.clarifications ?? [];
  // A clarification is the structured recovery surface; drop the free-text note that duplicates it
  // (same feld). Conflict/advisory notes (no clarification for that feld) stay visible.
  const notes = (compute?.notes ?? []).filter(
    (n) => !clarifications.some((c) => n.startsWith(`${c.feld}:`)),
  );
  // Calm visibility: a not_computed-only kern shows nothing here (open points live in the form).
  if (computed.length === 0 && clarifications.length === 0 && notes.length === 0) return null;

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
      </ul>
      {clarifications.map((c) => (
        <p
          key={`${c.feld}:${c.raw_unit}:${c.reason}`}
          className="kernel-note kernel-clarify"
          data-testid="kernel-clarify"
        >
          <span>{clarifyMessage(c)}</span>
          {c.one_click && onConfirmUnit ? (
            <button
              type="button"
              className="kernel-clarify-confirm"
              data-testid="kernel-clarify-confirm"
              onClick={() => onConfirmUnit(c.feld, `${c.raw_value} ${c.suggested_unit}`)}
            >
              bestätigen
            </button>
          ) : null}
        </p>
      ))}
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
