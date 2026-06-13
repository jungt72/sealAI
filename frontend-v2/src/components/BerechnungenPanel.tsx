import type { Clarification, ComputeResponse } from "../contracts";

/** The KERNEL channel (M8): deterministic values from the backend Rechenkern, rendered next to the
 * input chips. The browser NEVER computes — like ParameterForm, there is no formula import and no
 * arithmetic here; every number comes verbatim from /api/v2/compute (or a chat turn's in-band kern
 * result). A client-side number would re-create the false-provenance calc-leak, so it is
 * structurally absent. Open points ("nicht berechenbar") are shown honestly, with NO number.
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

/** German label for a physical dimension (used only in the honest "wrong kind of quantity" message). */
const DIM_LABEL: Record<string, string> = {
  length: "Längen",
  frequency: "Drehzahl",
  angle: "Winkel",
};

/** The honest recovery wording. Scale mismatch (cm on a mm field) → "bitte in mm angeben"; a
 * DIMENSION mismatch (grad on a length field) → name it the wrong kind of quantity. */
function clarifyMessage(c: Clarification): string {
  if (c.reason === "no_value") {
    return `${c.feld}: kein Wert erkannt — bitte Zahl + Einheit in ${c.suggested_unit} angeben.`;
  }
  if (c.reason === "unit_known_other") {
    const dimensionMismatch =
      Boolean(c.known_dimension) &&
      Boolean(c.expected_dimension) &&
      c.known_dimension !== c.expected_dimension;
    if (dimensionMismatch) {
      const got = DIM_LABEL[c.known_dimension] ?? c.known_dimension;
      const want = DIM_LABEL[c.expected_dimension] ?? c.expected_dimension;
      return `${c.feld}: »${c.raw_unit}« ist eine ${got}-Angabe — hier wird eine ${want}-Angabe in ${c.suggested_unit} erwartet.`;
    }
    return `${c.feld}: »${c.raw_unit}« wird hier nicht unterstützt — bitte in ${c.suggested_unit} angeben.`;
  }
  if (c.reason === "unit_missing") {
    return `${c.feld}: Einheit fehlt — meintest du ${c.raw_value} ${c.suggested_unit}?`;
  }
  return `${c.feld}: Einheit »${c.raw_unit}« unklar — meintest du ${c.suggested_unit}?`;
}

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
  const notComputed = compute?.not_computed ?? [];
  const clarifications = compute?.clarifications ?? [];
  // A clarification is the structured recovery surface; drop the free-text note that duplicates it
  // (same feld). Conflict/advisory notes (no clarification for that feld) stay visible.
  const notes = (compute?.notes ?? []).filter(
    (n) => !clarifications.some((c) => n.startsWith(`${c.feld}:`)),
  );
  if (
    computed.length === 0 &&
    notComputed.length === 0 &&
    clarifications.length === 0 &&
    notes.length === 0
  )
    return null;

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
