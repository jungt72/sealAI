import { useState, type FormEvent } from "react";

import type { ParamItem } from "../contracts";
import {
  type FieldDef,
  kernelFields,
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

/** The binder is German-convention (decimal comma; dot = thousands). A PERIOD a user types as a
 * decimal separator ("0.5") would otherwise parse as number "0" + unit ".5 bar" → a wrong settle
 * (0–0.5 bar is the RWDR magnitude). PREVENT it at the source: a period→comma, EXCEPT a German
 * thousands group ("4.000") which is left as-is (the binder reads it as 4000 with the unit). Applied
 * only to NUMBER fields, never to text (an Altteil-Code "A.12" must not be rewritten). */
export function normalizeDecimal(raw: string): string {
  const v = raw.trim();
  if (/^\d{1,3}(\.\d{3})+$/.test(v)) return v; // German thousands → leave (binds as thousands)
  return v.replace(".", ","); // a period is a decimal separator → German comma
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
  if (field.type === "number") {
    return composeWert(normalizeDecimal(raw), field.unit); // prevent the period-decimal 0-parse
  }
  return composeWert(raw, field.unit); // text (unit is "" → raw passes through untouched)
}

/**
 * Schema-driven parameter entry — INPUTS ONLY. The universal renderer over a domain SCHEMA
 * (`schema/situations.ts`). It NEVER computes or displays a derived value (no formula import, no
 * arithmetic): it writes raw inputs to case-state memory (origin = user-form) via the batch
 * `onSubmit`, and the deterministic kern owns every calculated number — with provenance and
 * fail-closed framing — on the chat/briefing path.
 *
 * Two layouts over the SAME state + submit:
 *  - `variant="popover"` (default): the full grouped form (the "+" popover in chat-view).
 *  - `variant="stage"`: a COMPACT card of the kernel-critical fields (DERIVED via `kernelFields` —
 *    never a hardcoded list) + a `<details>` expander for the rest (role:"context"), grouped A–I.
 *    The compact/expander split maps onto the trust-spine boundary.
 *
 * Adding a situation or a field is a schema entry, never a change here.
 */
export function ParameterForm({
  onSubmit,
  onSubmitted,
  variant = "popover",
}: {
  /** Batch submit: every non-empty field as one payload → one settle + one recompute + one
   * deterministic confirmation (the host wires it to POST .../current/facts). */
  onSubmit: (items: ParamItem[]) => void;
  /** Pilot-ui: lets the hosting popover close itself after a submit (purely presentational). */
  onSubmitted?: () => void;
  variant?: "popover" | "stage";
}) {
  const [activeId, setActiveId] = useState<string>(SITUATIONS[0]?.id ?? "");
  const [vals, setVals] = useState<Record<string, string>>({});
  const active: SituationDef = SITUATIONS.find((s) => s.id === activeId) ?? SITUATIONS[0];

  function set(key: string, value: string) {
    setVals((s) => ({ ...s, [key]: value }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const items: ParamItem[] = [];
    for (const f of situationFields(active)) {
      const wert = resolveWert(f, vals[f.key] ?? "");
      if (wert) items.push({ feld: f.key, wert, label: f.label });
    }
    setVals({});
    onSubmit(items);
    onSubmitted?.();
  }

  const row = (f: FieldDef) => (
    <FieldRow key={f.key} field={f} value={vals[f.key] ?? ""} onChange={(v) => set(f.key, v)} />
  );

  // ── stage: compact kernel card + expander (role:context), one shared submit ──────────────────
  if (variant === "stage") {
    return (
      <section className="param-form param-stage-card" data-testid="parameter-form">
        <header className="param-head">
          <h3>Parameter direkt eingeben</h3>
        </header>
        <form onSubmit={submit}>
          <div className="param-compact" data-testid="param-compact">
            {kernelFields(active).map(row)}
          </div>
          <details className="param-expander" data-testid="param-expander">
            <summary className="param-expander-summary">
              weitere Parameter ergänzen (Medium, Werkstoff, Dynamik …)
            </summary>
            <div className="param-expander-body">
              {active.groups.map((g) => {
                const ctx = g.fields.filter((f) => f.role === "context");
                if (ctx.length === 0) return null;
                return (
                  <fieldset key={g.id} className="param-group" data-testid={`param-group-${g.id}`}>
                    <legend className="param-group-title">{g.title}</legend>
                    {ctx.map(row)}
                  </fieldset>
                );
              })}
            </div>
          </details>
          <button type="submit" data-testid="param-submit">
            Berechnen
          </button>
          <p className="muted param-stage-note">
            Eingaben werden als Fallkontext gespeichert; berechnete Werte liefert der Rechenkern.
            Leer / „Unbekannt" bleibt offen (keine Annahme).
          </p>
        </form>
      </section>
    );
  }

  // ── popover (default): the full grouped form ─────────────────────────────────────────────────
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
            {g.fields.map(row)}
          </fieldset>
        ))}
        <button type="submit" data-testid="param-submit">
          Werte übernehmen
        </button>
      </form>
    </section>
  );
}

/** One field row: label (+ required + Kern badge) + the typed control + help. Shared by both layouts. */
function FieldRow({
  field,
  value,
  onChange,
}: {
  field: FieldDef;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="param-row">
      <span className="param-label">
        {field.label}
        {field.required && (
          <span className="param-required" aria-hidden="true" title="Pflichtfeld">
            {" *"}
          </span>
        )}
        {field.role === "kernel" && (
          <span className="param-kernel-badge" title="fließt in den Rechenkern">
            {" Kern"}
          </span>
        )}
      </span>
      <Field field={field} value={value} onChange={onChange} />
      {field.help && <span className="param-help">{field.help}</span>}
    </label>
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
