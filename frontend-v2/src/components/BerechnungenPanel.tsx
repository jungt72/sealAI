import type { ComputeResponse } from "../contracts";
import { clarifyMessage } from "../lib/clarify";

/** The KERNEL channel (M8): deterministic values from the backend Rechenkern. The browser NEVER
 * computes — every number comes verbatim from /api/v2/compute (or a chat turn's in-band kern
 * result). A client-side number would re-create the false-provenance calc-leak, so it is
 * structurally absent.
 *
 * `view` splits the surface for the two-column cockpit:
 *  - "results"  → ONLY the computed values (the deterministic calculator results, left column).
 *  - "critical" → ONLY the critical points (clarifications + conflict/advisory notes + open points
 *                 the kern could not compute), right column. All backend-sourced — never invented.
 *  - "full"     → the original single panel (computed + clarifications + notes + hint). Default. */

const LABELS: Record<string, string> = {
  umfangsgeschwindigkeit: "Umfangsgeschwindigkeit (v)",
  pv_wert: "PV-Wert",
  verpressung_prozent: "Verpressung",
};
const label = (calcId: string): string => LABELS[calcId] ?? calcId;

/** Display-format the kern's value: German decimal comma, presentation rounding only (the
 * authoritative value is the backend's — this never alters or derives a number). */
const fmt = (v: number): string => v.toFixed(2).replace(".", ",");

/** A not-computed entry that is merely "nicht anwendbar" (the calc does not apply to this seal
 * type) is noise on the critical surface, not an open point. Shared by the panel + the cockpit
 * "kritische Punkte" gate so both agree on what counts as critical. */
export const isNotApplicable = (n: { reason: string }): boolean =>
  /nicht anwendbar/i.test(n.reason);

export function BerechnungenPanel({
  compute,
  onConfirmUnit,
  variant = "committed",
  loading = false,
  view = "full",
}: {
  compute: ComputeResponse | null;
  onConfirmUnit?: (feld: string, value: string) => void;
  variant?: "committed" | "preview";
  loading?: boolean;
  /** Which slice of the kern channel to render — see the file header. */
  view?: "full" | "results" | "critical";
}) {
  const isPreview = variant === "preview";
  const computed = compute?.computed ?? [];
  const clarifications = compute?.clarifications ?? [];
  // A clarification is the structured recovery surface; drop the free-text note that duplicates it.
  const notes = (compute?.notes ?? []).filter(
    (n) => !clarifications.some((c) => n.startsWith(`${c.feld}:`)),
  );
  // A type-mismatch ("nicht anwendbar" — e.g. an RWDR-only calc on a hydraulic case) is NOT an
  // open point the user should resolve; only genuinely missing/invalid inputs of APPLICABLE calcs
  // are critical. Filter the not-applicable ones out of the critical surface.
  const notComputed = (compute?.not_computed ?? []).filter((n) => !isNotApplicable(n));

  // Preview in-flight: show only „rechnet…" — never repaint a prior value as if it were current.
  if (isPreview && loading) {
    return (
      <section
        className="fact-chips kernel-panel kernel-panel--preview"
        data-testid="preview-panel"
        aria-label="Vorschau-Berechnung (nicht übernommen)"
        aria-busy="true"
      >
        <span className="chips-label">Vorschau · nicht übernommen</span>
        <p className="kernel-note" data-testid="preview-rechnet">
          rechnet…
        </p>
      </section>
    );
  }

  const computedRows = (
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
  );

  const clarifyRows = clarifications.map((c) => (
    <p
      key={`${c.feld}:${c.raw_unit}:${c.reason}`}
      className="kernel-note kernel-clarify"
      data-testid="kernel-clarify"
    >
      <span>{clarifyMessage(c)}</span>
      {c.one_click && onConfirmUnit && !isPreview ? (
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
  ));

  const noteRows = notes.map((note, i) => (
    <p key={i} className="kernel-note" data-testid="kernel-note">
      {note}
    </p>
  ));

  // ── view: results — only the deterministic calculator values ──────────────────────────────────
  if (view === "results") {
    if (computed.length === 0) return null;
    return (
      <section
        className="fact-chips kernel-panel"
        data-testid="berechnungen-panel"
        aria-label="Berechnungen vom deterministischen Rechenkern"
      >
        {computedRows}
      </section>
    );
  }

  // ── view: critical — clarifications + conflict notes + open (not-computed) points ──────────────
  if (view === "critical") {
    if (clarifications.length === 0 && notes.length === 0 && notComputed.length === 0) return null;
    return (
      <section
        className="fact-chips kernel-panel kernel-panel--critical"
        data-testid="kritische-punkte-panel"
        aria-label="Kritische Punkte zur Dichtungsauswahl"
      >
        {clarifyRows}
        {noteRows}
        {notComputed.map((nc) => (
          <p key={nc.calc_id} className="kernel-note kernel-open" data-testid="kernel-open">
            <span className="fact-feld">{label(nc.calc_id)}</span> {nc.reason}
          </p>
        ))}
      </section>
    );
  }

  // ── view: full (default, unchanged) ───────────────────────────────────────────────────────────
  if (computed.length === 0 && clarifications.length === 0 && notes.length === 0) return null;
  return (
    <section
      className={`fact-chips kernel-panel${isPreview ? " kernel-panel--preview" : ""}`}
      data-testid={isPreview ? "preview-panel" : "berechnungen-panel"}
      aria-label={
        isPreview
          ? "Vorschau-Berechnung (nicht übernommen)"
          : "Berechnungen vom deterministischen Rechenkern"
      }
    >
      <span className="chips-label">
        {isPreview ? "Vorschau · nicht übernommen" : "Berechnungen · deterministischer Rechenkern"}
      </span>
      {computed.length > 0 ? computedRows : null}
      {clarifyRows}
      {noteRows}
      <span className="chips-label kernel-hint">
        {isPreview
          ? "Vorschau — noch nicht übernommen; Übernehmen schreibt die Werte in den Fallkontext."
          : "Orientierung, keine Freigabe — Werte vom Rechenkern; Eingaben bei Bedarf bestätigen."}
      </span>
    </section>
  );
}
