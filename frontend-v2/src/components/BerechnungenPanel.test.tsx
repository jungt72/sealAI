import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Clarification, ComputeResponse } from "../contracts";
import { BerechnungenPanel } from "./BerechnungenPanel";

afterEach(cleanup);

const V: ComputeResponse = {
  computed: [
    {
      calc_id: "umfangsgeschwindigkeit",
      name: "v_m_s",
      value: 16.7552,
      unit: "m/s",
      formula: "v = π·d1·n/60000",
      parent_fields: ["wellendurchmesser", "drehzahl"],
      input_origins: [
        "vom Nutzer im Formular eingegeben (wellendurchmesser: »40 mm«, user-form)",
        "vom Nutzer im Formular eingegeben (drehzahl: »8000 U/min«, user-form)",
      ],
      provenance: "kernel_computed",
    },
  ],
  not_computed: [],
  notes: [],
};

const OPEN: ComputeResponse = {
  computed: [],
  not_computed: [
    { calc_id: "umfangsgeschwindigkeit", reason: "nicht berechenbar: Eingaben fehlen (rpm)" },
  ],
  notes: ["drehzahl: Wert »8000« nicht eindeutig bindbar — nicht gebunden"],
};

describe("BerechnungenPanel (the kernel channel — backend values only)", () => {
  it("renders the deterministic kern value, unit, formula and honest provenance", () => {
    render(<BerechnungenPanel compute={V} />);
    const panel = screen.getByTestId("berechnungen-panel");
    expect(panel).toBeInTheDocument();
    const row = screen.getByTestId("kernel-value");
    expect(row).toHaveTextContent("Umfangsgeschwindigkeit");
    expect(row).toHaveTextContent("16,76 m/s"); // German comma; the kern's value, display-rounded
    expect(row).toHaveTextContent("v = π·d1·n/60000");
    // provenance is honest: computed from the named input felder (orientation ≠ Freigabe)
    expect(row).toHaveTextContent(/deterministisch berechnet/i);
    expect(row).toHaveTextContent("wellendurchmesser");
    expect(panel).toHaveTextContent(/Orientierung, keine Freigabe/i);
  });

  it("calm cockpit: suppresses every 'nicht berechenbar' row (panel still shows the conflict note)", () => {
    render(<BerechnungenPanel compute={OPEN} />);
    // the panel is visible because OPEN carries a conflict/advisory note…
    expect(screen.getByTestId("berechnungen-panel")).toBeInTheDocument();
    // …but the not_computed "nicht berechenbar" row is suppressed (calm = computed rows only)
    expect(screen.queryByTestId("kernel-not-computed")).toBeNull();
    // the honest conflict note still renders
    expect(screen.getByTestId("kernel-note")).toHaveTextContent("nicht eindeutig bindbar");
  });

  it("with v computed and a not_computed PV alongside, ONLY the v row renders (calm)", () => {
    const mixed: ComputeResponse = {
      computed: V.computed,
      not_computed: [{ calc_id: "pv_wert", reason: "nicht berechenbar: Eingaben fehlen (druck)" }],
      notes: [],
    };
    render(<BerechnungenPanel compute={mixed} />);
    expect(screen.getByTestId("kernel-value")).toHaveTextContent("16,76 m/s");
    expect(screen.queryByTestId("kernel-not-computed")).toBeNull(); // the PV open point is suppressed
  });

  it("TRUST: never shows a computed number when the kern reported none (no client compute)", () => {
    const { container } = render(<BerechnungenPanel compute={OPEN} />);
    // even though the inputs are present elsewhere, the panel shows NO velocity value/unit
    expect(container.textContent ?? "").not.toMatch(/m\/s/);
    expect(container.textContent ?? "").not.toMatch(/\d+[.,]\d+\s*m/);
  });

  it("renders nothing when there is no kern output at all (clean stage)", () => {
    const { container } = render(<BerechnungenPanel compute={null} />);
    expect(container.firstChild).toBeNull();
    cleanup();
    const empty: ComputeResponse = { computed: [], not_computed: [], notes: [] };
    const { container: c2 } = render(<BerechnungenPanel compute={empty} />);
    expect(c2.firstChild).toBeNull();
  });

  it("panel absent when only a not_computed row exists (nothing computed, no note/clarification)", () => {
    const onlyOpen: ComputeResponse = {
      computed: [],
      not_computed: [
        { calc_id: "umfangsgeschwindigkeit", reason: "nicht berechenbar: Eingaben fehlen (rpm)" },
      ],
      notes: [],
      clarifications: [],
    };
    const { container } = render(<BerechnungenPanel compute={onlyOpen} />);
    expect(container.firstChild).toBeNull(); // not_computed alone no longer surfaces the panel
  });
});

const clar = (over: Partial<Clarification>): Clarification => ({
  feld: "drehzahl",
  input_name: "rpm",
  raw_value: "5000",
  raw_unit: "u/mon",
  reason: "unit_unrecognized",
  suggested_unit: "U/min",
  known_dimension: "",
  expected_dimension: "frequency",
  one_click: true,
  ...over,
});

const withClar = (c: Clarification, notes: string[] = []): ComputeResponse => ({
  computed: [],
  not_computed: [],
  notes,
  clarifications: [c],
});

describe("BerechnungenPanel — unit clarifications (one-click strictly from the backend flag)", () => {
  it("one-click confirm for an unrecognized unit re-settles via onConfirmUnit", () => {
    const onConfirmUnit = vi.fn();
    render(<BerechnungenPanel compute={withClar(clar({}))} onConfirmUnit={onConfirmUnit} />);
    expect(screen.getByTestId("kernel-clarify")).toHaveTextContent(/meintest du U\/min/i);
    fireEvent.click(screen.getByTestId("kernel-clarify-confirm"));
    expect(onConfirmUnit).toHaveBeenCalledWith("drehzahl", "5000 U/min");
  });

  it("one-click confirm for a MISSING unit appends the canonical to the bare number", () => {
    const onConfirmUnit = vi.fn();
    const c = clar({ raw_unit: "", reason: "unit_missing", one_click: true });
    render(<BerechnungenPanel compute={withClar(c)} onConfirmUnit={onConfirmUnit} />);
    fireEvent.click(screen.getByTestId("kernel-clarify-confirm"));
    expect(onConfirmUnit).toHaveBeenCalledWith("drehzahl", "5000 U/min");
  });

  it("TRUST: a known-other unit (cm) shows a re-enter message and NO one-click (no silent 10× rescale)", () => {
    const onConfirmUnit = vi.fn();
    const c = clar({
      feld: "wellendurchmesser",
      input_name: "d1_mm",
      raw_value: "50",
      raw_unit: "cm",
      reason: "unit_known_other",
      suggested_unit: "mm",
      known_dimension: "length",
      expected_dimension: "length",
      one_click: false,
    });
    render(<BerechnungenPanel compute={withClar(c)} onConfirmUnit={onConfirmUnit} />);
    expect(screen.getByTestId("kernel-clarify")).toHaveTextContent(/bitte in mm angeben/i);
    expect(screen.queryByTestId("kernel-clarify-confirm")).toBeNull(); // the guard, at the UI
    expect(onConfirmUnit).not.toHaveBeenCalled();
  });

  it("a DIMENSION mismatch (grad on a length field) is named the wrong kind of quantity", () => {
    const c = clar({
      feld: "wellendurchmesser",
      input_name: "d1_mm",
      raw_value: "50",
      raw_unit: "grad",
      reason: "unit_known_other",
      suggested_unit: "mm",
      known_dimension: "angle",
      expected_dimension: "length",
      one_click: false,
    });
    render(<BerechnungenPanel compute={withClar(c)} />);
    const el = screen.getByTestId("kernel-clarify");
    expect(el).toHaveTextContent(/Winkel/); // it's a Winkel-Angabe…
    expect(el).toHaveTextContent(/Längen-Angabe/); // …where a Längen-Angabe is expected
    expect(screen.queryByTestId("kernel-clarify-confirm")).toBeNull();
  });

  it("no_value shows re-enter guidance and offers no one-click", () => {
    const c = clar({ raw_value: "groß", raw_unit: "", reason: "no_value", one_click: false });
    render(<BerechnungenPanel compute={withClar(c)} onConfirmUnit={vi.fn()} />);
    expect(screen.getByTestId("kernel-clarify")).toHaveTextContent(/kein Wert erkannt/i);
    expect(screen.queryByTestId("kernel-clarify-confirm")).toBeNull();
  });

  it("suppresses the free-text note a clarification replaces, but keeps other notes", () => {
    const compute = withClar(clar({}), [
      "drehzahl: Einheit »u/mon« unklar — meintest du »U/min«? (»5000 u/mon«) — nicht gebunden",
      "Quellung: Nutfüllung-Reserve lassen",
    ]);
    render(<BerechnungenPanel compute={compute} onConfirmUnit={vi.fn()} />);
    const notes = screen.queryAllByTestId("kernel-note");
    expect(notes.every((n) => !(n.textContent ?? "").includes("u/mon"))).toBe(true);
    expect(screen.getByText(/Quellung: Nutfüllung-Reserve lassen/)).toBeInTheDocument();
  });
});
