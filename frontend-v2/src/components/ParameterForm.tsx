import { useState, type FormEvent } from "react";

import {
  type FieldDef,
  SITUATIONS,
  type SituationDef,
  situationFields,
} from "../schema/situations";

/** Compose the stored value for a number/text field. The kern binder is fail-closed and needs
 * number+unit, so the canonical unit is appended — UNLESS the user already typed a unit token (no
 * double "mm mm"). This is string assembly, NOT arithmetic. */
export function composeWert(raw: string, unit: string): string {
  const v = raw.trim();
  if (!v || !unit) return v;
  return /[a-zA-Z°⁻]/.test(v) ? v : `${v} ${unit}`;
}

/** The wert a field contributes on submit, by type. Empty / "Unbekannt" ⇒ "" ⇒ NOT submitted (the
 * param stays MISSING — no fake default). Enums store the readable German LABEL (it informs L1 and
 * shows in the chips/confirmation); booleans store "ja"/"nein"; number/text go through composeWert.
 * NEVER a derived/computed quantity — the form emits only raw inputs (the kern owns every number). */
export function resolveWert(field: FieldDef, raw: string): string {
  if (field.type === "enum") {
    return field.options?.find((o) => o.value === raw)?.label ?? "";
  }
  if (field.type === "boolean") {
    return raw === "ja" || raw === "nein" ? raw : "";
  }
  return composeWert(raw, field.unit); // number | text
}

/**
 * Schema-driven parameter entry — INPUTS ONLY. The universal renderer over a domain SCHEMA
 * (`schema/situations.ts`): tab per situation → groups → fields by type. It NEVER computes or
 * displays a derived value (no formula import, no arithmetic): it writes raw inputs to case-state
 * memory (origin = user-form) via `onSubmit`, and the deterministic kern owns every calculated
 * number — with provenance and fail-closed framing — on the chat/briefing path. A client-side number
 * here would re-create the false-provenance calc-leak, so it is structurally absent.
 *
 * Adding a situation or a field is a schema entry, never a change here.
 */
export function ParameterForm({
  onSubmit,
  onSubmitted,
}: {
  onSubmit: (feld: string, wert: string) => void;
  /** Pilot-ui: lets the hosting popover close itself after a submit (purely presentational). */
  onSubmitted?: () => void;
}) {
  const [activeId, setActiveId] = useState<string>(SITUATIONS[0]?.id ?? "");
  const [vals, setVals] = useState<Record<string, string>>({});
  const active: SituationDef = SITUATIONS.find((s) => s.id === activeId) ?? SITUATIONS[0];

  function set(key: string, value: string) {
    setVals((s) => ({ ...s, [key]: value }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    for (const f of situationFields(active)) {
      const wert = resolveWert(f, vals[f.key] ?? "");
      if (wert) onSubmit(f.key, wert);
    }
    setVals({});
    onSubmitted?.();
  }

  return (
    <section className="param-form" data-testid="parameter-form">
      <header className="param-head">
        <h3>Parameter eingeben</h3>
      </header>

      {SITUATIONS.length > 1 && (
        <div className="param-tabs" role="tablist" aria-label="Anwendungsfall">
          {SITUATIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={s.id === activeId}
              className={`param-tab${s.id === activeId ? " is-active" : ""}`}
              onClick={() => setActiveId(s.id)}
              data-testid={`param-tab-${s.id}`}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}

      <p className="muted">
        Eingaben werden als Fallkontext gespeichert. Berechnete Werte (z. B. Umfangsgeschwindigkeit)
        liefert ausschließlich der Rechenkern im Chat — nicht dieses Formular. Felder ohne Angabe
        bleiben offen (keine Annahme).
      </p>

      <form onSubmit={submit}>
        {active.groups.map((g) => (
          <fieldset key={g.id} className="param-group" data-testid={`param-group-${g.id}`}>
            <legend className="param-group-title">{g.title}</legend>
            {g.fields.map((f) => (
              <label key={f.key} className="param-row">
                <span className="param-label">
                  {f.label}
                  {f.required && (
                    <span className="param-required" aria-hidden="true" title="Pflichtfeld">
                      {" *"}
                    </span>
                  )}
                  {f.role === "kernel" && (
                    <span className="param-kernel-badge" title="fließt in den Rechenkern">
                      {" Kern"}
                    </span>
                  )}
                </span>
                <Field field={f} value={vals[f.key] ?? ""} onChange={(v) => set(f.key, v)} />
                {f.help && <span className="param-help">{f.help}</span>}
              </label>
            ))}
          </fieldset>
        ))}
        <button type="submit" data-testid="param-submit">
          Werte übernehmen
        </button>
      </form>
    </section>
  );
}

/** One field control, by type. "Unbekannt" is the first-class empty state for enum/boolean. */
function Field({
  field,
  value,
  onChange,
}: {
  field: FieldDef;
  value: string;
  onChange: (v: string) => void;
}) {
  const testId = `param-${field.key}`;

  if (field.type === "enum") {
    return (
      <span className="param-input">
        <select
          className="param-select"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          data-testid={testId}
        >
          <option value="">— Unbekannt —</option>
          {field.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </span>
    );
  }

  if (field.type === "boolean") {
    return (
      <span className="param-input">
        <select
          className="param-select"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          data-testid={testId}
        >
          <option value="">— Unbekannt —</option>
          <option value="ja">ja</option>
          <option value="nein">nein</option>
        </select>
      </span>
    );
  }

  // number | text
  return (
    <span className="param-input">
      <input
        inputMode={field.type === "number" ? "decimal" : "text"}
        value={value}
        placeholder={field.type === "number" ? "Wert" : ""}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testId}
      />
      {field.unit && <span className="param-unit">{field.unit}</span>}
    </span>
  );
}
