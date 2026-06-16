import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type { ComputeResponse, ParamItem } from "../contracts";
import {
  coreFields,
  type FieldDef,
  formFields,
  kernelFields,
  SITUATIONS,
  type SituationDef,
} from "../schema/situations";
import { BerechnungenPanel } from "./BerechnungenPanel";

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

/** The exact DUAL of `resolveWert` — a committed case-state value → the raw input value, so a hydrated
 * form round-trips with NO drift: `resolveWert(field, hydrateValue(field, w)) === w`. Enum: stored
 * German LABEL → option value; boolean: "ja"/"nein" verbatim; number/text: strip the trailing
 * canonical unit token (the dual of composeWert's append). An unmatched enum label → "" (Unbekannt). */
export function hydrateValue(field: FieldDef, settledWert: string): string {
  const v = (settledWert ?? "").trim();
  if (!v) return "";
  if (field.type === "enum") return field.options?.find((o) => o.label === v)?.value ?? "";
  if (field.type === "boolean") return v === "ja" || v === "nein" ? v : "";
  if (field.unit && v.endsWith(field.unit)) return v.slice(0, -field.unit.length).trim();
  return v;
}

/** The non-empty raw inputs as batch items — the SINGLE source for both the live preview and the
 * commit (so Vorschau == Commit holds at the input level too). Only raw schema felder, never a
 * kern-owned derived quantity (the kern owns every number). */
export function buildItems(vals: Record<string, string>, active: SituationDef): ParamItem[] {
  const items: ParamItem[] = [];
  for (const f of formFields(active)) {
    const wert = resolveWert(f, vals[f.key] ?? "");
    if (wert) items.push({ feld: f.key, wert, label: f.label });
  }
  return items;
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
  onPreview,
  committed,
  onSubmitted,
  variant = "popover",
}: {
  /** Adopt („Übernehmen"): the non-empty fields as one batch + the reconcile `deletes` (managed
   * felder that WERE committed and are now empty) → the host commits (POST /facts) + forgets the
   * deletes. The form does NOT reset — values stay editable (Modell R2). */
  onSubmit: (items: ParamItem[], deletes?: string[]) => void;
  /** R2 live preview: the host runs the read-only backend kern over the DRAFT and resolves the
   * Berechnete Werte (or null on error/empty). Absent → no preview surface (pre-R2 behaviour). */
  onPreview?: (items: ParamItem[]) => Promise<ComputeResponse | null>;
  /** The committed case-state as feld → settled value: hydrates the fields (the form is the single
   * editable surface) and is the baseline for the empty-field reconcile on „Übernehmen". */
  committed?: Record<string, string>;
  /** Pilot-ui: lets the hosting popover close itself after a submit (purely presentational). */
  onSubmitted?: () => void;
  variant?: "popover" | "stage";
}) {
  const firstEnabled = SITUATIONS.find((s) => !s.disabled) ?? SITUATIONS[0];
  const [activeId, setActiveId] = useState<string>(firstEnabled?.id ?? "");
  const [vals, setVals] = useState<Record<string, string>>({});
  // only an ENABLED pack can be active; a disabled tab is never selectable (see the tab bar below)
  const active: SituationDef =
    SITUATIONS.find((s) => s.id === activeId && !s.disabled) ?? firstEnabled;

  // ── R2 hydration: seed the fields from the committed case-state; re-hydrate when it changes from
  // another source (e.g. a chat turn), but never clobber an in-progress edit (a field the user has
  // changed away from the last applied baseline — including an intentional clear).
  const committedKey = useMemo(() => JSON.stringify(committed ?? {}), [committed]);
  const baselineRef = useRef<Record<string, string>>({});
  useEffect(() => {
    const hydrated: Record<string, string> = {};
    for (const f of formFields(active)) {
      const c = committed?.[f.key];
      if (c != null && c !== "") hydrated[f.key] = hydrateValue(f, c);
    }
    setVals((prev) => {
      const next: Record<string, string> = { ...hydrated };
      for (const f of formFields(active)) {
        const k = f.key;
        if ((prev[k] ?? "") !== (baselineRef.current[k] ?? "")) {
          if ((prev[k] ?? "") === "") delete next[k]; // user cleared it → stays cleared
          else next[k] = prev[k]; // in-progress edit → preserved
        }
      }
      return next;
    });
    baselineRef.current = hydrated;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [committedKey, activeId]);

  // ── R2 live preview (debounced ~350 ms, latest-wins): a field change recomputes the DRAFT via the
  // backend kern. A monotonic request id discards an out-of-order (stale) response; while the latest
  // is in flight the panel shows „rechnet…", never a prior value as if it were current.
  const items = useMemo(() => buildItems(vals, active), [vals, active]);
  const itemsKey = useMemo(() => JSON.stringify(items), [items]);
  const [preview, setPreview] = useState<ComputeResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const reqIdRef = useRef(0);
  // keep the latest callback without making it a dep (the effect fires on item changes only, never
  // on a parent re-render that hands a fresh callback identity).
  const onPreviewRef = useRef(onPreview);
  onPreviewRef.current = onPreview;
  useEffect(() => {
    const fn = onPreviewRef.current;
    if (!fn) return;
    if (items.length === 0) {
      reqIdRef.current += 1; // invalidate any in-flight response
      setPreview(null);
      setPreviewLoading(false);
      return;
    }
    const id = (reqIdRef.current += 1);
    setPreviewLoading(true);
    const t = setTimeout(() => {
      fn(items)
        .then((res) => {
          if (id === reqIdRef.current) {
            setPreview(res);
            setPreviewLoading(false);
          }
        })
        .catch(() => {
          if (id === reqIdRef.current) {
            setPreview(null); // never leave a stale value; the host surfaces the error
            setPreviewLoading(false);
          }
        });
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemsKey]);

  // reconcile: a managed field that WAS committed and is now empty/absent → delete (no stale fact).
  const present = new Set(items.map((it) => it.feld));
  const deletes = formFields(active)
    .map((f) => f.key)
    .filter((k) => committed?.[k] != null && committed[k] !== "" && !present.has(k));
  // Dirty = the draft differs from the committed case-state, compared at the RESOLVED-value level
  // (reuse the commit comparison, NOT raw `vals`, so a decimal normalization "0.5"→"0,5 bar" never
  // reads as a phantom edit). At rest (hydrated / just after Übernehmen) → not dirty → no Vorschau;
  // no committed value yet → dirty as soon as the user types. The committed panel lives in the host.
  const isDirty = items.some((it) => (committed?.[it.feld] ?? "") !== it.wert) || deletes.length > 0;

  function set(key: string, value: string) {
    setVals((s) => ({ ...s, [key]: value }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit(items, deletes);
    onSubmitted?.();
    // NO reset — values stay (Modell R2: the form is the persistent editable surface)
  }

  // The Vorschau renders ONLY while the form is dirty (R1): at rest the committed panel alone shows
  // (no side-by-side doubling); while editing the draft delta appears, marked „nicht übernommen".
  const previewPanel = onPreview && isDirty ? (
    <BerechnungenPanel compute={preview} variant="preview" loading={previewLoading} />
  ) : null;

  const row = (f: FieldDef) => (
    <FieldRow key={f.key} field={f} value={vals[f.key] ?? ""} onChange={(v) => set(f.key, v)} />
  );

  // Universal Core — operating conditions shared across all types; rendered ABOVE the tabs.
  const coreSection = (
    <section className="param-core" data-testid="param-core" aria-label="Betriebsbedingungen (typübergreifend)">
      <span className="param-core-label">Betriebsbedingungen</span>
      <div className="param-core-grid">{coreFields().map(row)}</div>
    </section>
  );

  // Type tabs (Domain Packs). RWDR is enabled; announced packs render grayed and are not selectable.
  const tabBar = (
    <div className="param-tabs" role="tablist" aria-label="Dichtungstyp">
      {SITUATIONS.map((s) => (
        <button
          key={s.id}
          type="button"
          role="tab"
          aria-selected={s.id === active.id}
          aria-disabled={s.disabled || undefined}
          disabled={s.disabled}
          className={`param-tab${s.id === active.id ? " is-active" : ""}${s.disabled ? " is-soon" : ""}`}
          onClick={() => {
            if (!s.disabled) setActiveId(s.id);
          }}
          title={s.disabled ? "kommt bald" : undefined}
          data-testid={`param-tab-${s.id}`}
        >
          {s.label}
          {s.disabled && <span className="param-tab-soon"> · bald</span>}
        </button>
      ))}
    </div>
  );

  // ── stage: compact kernel card + expander (role:context), one shared submit ──────────────────
  if (variant === "stage") {
    return (
      <section className="param-form param-stage-card" data-testid="parameter-form">
        <header className="param-head">
          <h3>Parameter direkt eingeben</h3>
        </header>
        <form onSubmit={submit}>
          {coreSection}
          {tabBar}
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
                    <div className="param-group-grid" data-testid={`param-group-grid-${g.id}`}>
                      {ctx.map(row)}
                    </div>
                  </fieldset>
                );
              })}
            </div>
          </details>
          <button type="submit" data-testid="param-submit">
            Übernehmen
          </button>
          <p className="muted param-stage-note">
            Eingaben ändern rechnet live eine Vorschau; „Übernehmen" speichert sie als Fallkontext.
            Leer / „Unbekannt" bleibt offen (keine Annahme).
          </p>
          {previewPanel}
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

      <p className="muted">
        Eingaben werden als Fallkontext gespeichert. Berechnete Werte (z. B. Umfangsgeschwindigkeit)
        liefert ausschließlich der Rechenkern im Chat — nicht dieses Formular. Felder ohne Angabe
        bleiben offen (keine Annahme).
      </p>

      <form onSubmit={submit}>
        {coreSection}
        {tabBar}
        {active.groups.map((g) => (
          <fieldset key={g.id} className="param-group" data-testid={`param-group-${g.id}`}>
            <legend className="param-group-title">{g.title}</legend>
            {g.fields.map(row)}
          </fieldset>
        ))}
        <button type="submit" data-testid="param-submit">
          Werte übernehmen
        </button>
        {previewPanel}
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
