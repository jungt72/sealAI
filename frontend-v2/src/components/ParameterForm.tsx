import { useState, type FormEvent } from "react";

type FieldDef = {
  feld: string;
  label: string;
  unit: string;
  inputMode: "decimal" | "text";
  placeholder: string;
};

/** v1 fields: d1/rpm feed the velocity kern (binder requires number+unit); medium/temperatur are
 * captured as context facts (not calc-bound). Extending this is an owner/binder decision. */
const FIELDS: FieldDef[] = [
  { feld: "wellendurchmesser", label: "Wellendurchmesser d", unit: "mm", inputMode: "decimal", placeholder: "z. B. 50" },
  { feld: "drehzahl", label: "Drehzahl n", unit: "U/min", inputMode: "decimal", placeholder: "z. B. 3000" },
  { feld: "medium", label: "Medium", unit: "", inputMode: "text", placeholder: "z. B. Hydrauliköl" },
  { feld: "temperatur", label: "Temperatur", unit: "°C", inputMode: "decimal", placeholder: "z. B. 80" },
];

/** Compose the stored value. The kern binder is fail-closed and needs number+unit, so the canonical
 * unit is appended — UNLESS the user already typed a unit token (no double "mm mm"). This is string
 * assembly, NOT arithmetic. */
export function composeWert(raw: string, unit: string): string {
  const v = raw.trim();
  if (!v || !unit) return v;
  return /[a-zA-Z°⁻]/.test(v) ? v : `${v} ${unit}`;
}

/**
 * Direct parameter entry — INPUTS ONLY. This form NEVER computes or displays a derived value (e.g.
 * Umfangsgeschwindigkeit): no formula import, no arithmetic. It writes raw inputs to case-state
 * memory (origin = user-form); the deterministic kern owns every calculated number, with provenance
 * and fail-closed framing, on the chat/briefing path. A client-side number here would re-create the
 * false-provenance calc-leak — so it is structurally absent.
 */
export function ParameterForm({ onSubmit }: { onSubmit: (feld: string, wert: string) => void }) {
  const [vals, setVals] = useState<Record<string, string>>({});

  function submit(e: FormEvent) {
    e.preventDefault();
    for (const f of FIELDS) {
      const wert = composeWert(vals[f.feld] ?? "", f.unit);
      if (wert) onSubmit(f.feld, wert);
    }
    setVals({});
  }

  return (
    <section className="param-form" data-testid="parameter-form">
      <header className="cockpit-head">
        <h3>Parameter eingeben</h3>
      </header>
      <p className="muted">
        Eingaben werden als Fallkontext gespeichert. Berechnete Werte (z. B. Umfangsgeschwindigkeit)
        liefert ausschließlich der Rechenkern im Chat — nicht dieses Formular.
      </p>
      <form onSubmit={submit}>
        {FIELDS.map((f) => (
          <label key={f.feld} className="param-row">
            <span className="param-label">{f.label}</span>
            <span className="param-input">
              <input
                inputMode={f.inputMode}
                value={vals[f.feld] ?? ""}
                placeholder={f.placeholder}
                onChange={(e) => setVals((s) => ({ ...s, [f.feld]: e.target.value }))}
                data-testid={`param-${f.feld}`}
              />
              {f.unit && <span className="param-unit">{f.unit}</span>}
            </span>
          </label>
        ))}
        <button type="submit" data-testid="param-submit">
          Werte übernehmen
        </button>
      </form>
    </section>
  );
}
