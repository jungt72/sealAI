import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ComputeResponse } from "../contracts";
import { formFields, kernelFields, RWDR_SITUATION, situationFields } from "../schema/situations";
import { composeWert, hydrateValue, ParameterForm, resolveWert } from "./ParameterForm";

afterEach(cleanup);

/** A minimal /compute-shaped preview payload carrying one kern value (v). */
const makeCompute = (value: number): ComputeResponse => ({
  computed: [
    {
      calc_id: "umfangsgeschwindigkeit",
      name: "Umfangsgeschwindigkeit",
      value,
      unit: "m/s",
      formula: "v = π·d·n",
      parent_fields: [],
      input_origins: [],
      provenance: "kernel_computed",
    },
  ],
  not_computed: [],
  notes: [],
  clarifications: [],
});

describe("ParameterForm (schema-driven; inputs only — the kern owns every number)", () => {
  it("renders the schema's groups and fields (number, enum, boolean)", () => {
    render(<ParameterForm onSubmit={vi.fn()} />);
    expect(screen.getByTestId("param-group-A")).toBeTruthy(); // Wellengeometrie
    expect(screen.getByText("Wellengeometrie")).toBeTruthy();
    expect(screen.getByTestId("param-wellendurchmesser")).toBeTruthy(); // number (kernel)
    expect((screen.getByTestId("param-medium") as HTMLSelectElement).tagName).toBe("SELECT"); // enum
    expect((screen.getByTestId("param-spritzwasser") as HTMLSelectElement).tagName).toBe("SELECT"); // boolean
  });

  it("batch-submits each filled field once: number appends its unit, enum emits the readable label", () => {
    const onSubmit = vi.fn();
    render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "3000" } });
    fireEvent.change(screen.getByTestId("param-druck"), { target: { value: "5" } });
    fireEvent.change(screen.getByTestId("param-medium"), { target: { value: "oel" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    expect(onSubmit).toHaveBeenCalledTimes(1); // ONE batch, not N per-field calls
    const items = onSubmit.mock.calls[0][0];
    expect(items).toContainEqual({ feld: "wellendurchmesser", wert: "50 mm", label: "Wellendurchmesser d₁" });
    expect(items).toContainEqual({ feld: "drehzahl", wert: "3000 U/min", label: "Drehzahl n" });
    expect(items).toContainEqual({ feld: "druck", wert: "5 bar", label: "Druck (normal)" });
    expect(items).toContainEqual({ feld: "medium", wert: "Öl", label: "Medium" }); // enum → German label
    expect(items).toHaveLength(4);
  });

  it("does NOT submit empty / 'Unbekannt' fields (no fake default — the param stays missing)", () => {
    const onSubmit = vi.fn();
    render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    // medium left at "Unbekannt" (value ""), every other field untouched
    fireEvent.click(screen.getByTestId("param-submit"));
    expect(onSubmit.mock.calls[0][0]).toEqual([
      { feld: "wellendurchmesser", wert: "50 mm", label: "Wellendurchmesser d₁" },
    ]);
  });

  it("TRUST: emits only raw schema input felder — never a kern-owned derived quantity, no m/s", () => {
    const onSubmit = vi.fn();
    const { container } = render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "3000" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    const felder = (onSubmit.mock.calls[0][0] as { feld: string }[]).map((it) => it.feld);
    const schemaKeys = situationFields(RWDR_SITUATION).map((f) => f.key);
    expect(felder).not.toContain("umfangsgeschwindigkeit");
    expect(felder.every((f) => schemaKeys.includes(f))).toBe(true);
    // π·50·3000/60000 ≈ 7.85 m/s must NOT be computed/rendered anywhere
    expect(container.textContent ?? "").not.toMatch(/m\/s/);
    expect(container.textContent ?? "").not.toContain("7.85");
  });

  it("resolveWert: number→unit, enum→label, boolean→ja/nein, empty/Unbekannt→'' (omitted)", () => {
    const byKey = Object.fromEntries(formFields(RWDR_SITUATION).map((f) => [f.key, f]));
    expect(resolveWert(byKey.wellendurchmesser, "50")).toBe("50 mm");
    expect(resolveWert(byKey.medium, "oel")).toBe("Öl");
    expect(resolveWert(byKey.medium, "")).toBe(""); // Unbekannt → omitted
    expect(resolveWert(byKey.spritzwasser, "ja")).toBe("ja");
    expect(resolveWert(byKey.spritzwasser, "")).toBe(""); // Unbekannt → omitted
    expect(resolveWert(byKey.additive, "Mineralöl-Additiv")).toBe("Mineralöl-Additiv"); // text, no unit
  });

  it("number path normalizes a period decimal to the German comma (0.5 → 0,5) — prevents the 0-parse", () => {
    const byKey = Object.fromEntries(formFields(RWDR_SITUATION).map((f) => [f.key, f]));
    // the acute pressure case: "0.5 bar" must bind 0.5 (not the parse artifact 0)
    expect(resolveWert(byKey.druck, "0.5")).toBe("0,5 bar");
    expect(resolveWert(byKey.druck, "0,5")).toBe("0,5 bar");
    expect(resolveWert(byKey.wellendurchmesser, "50.5")).toBe("50,5 mm");
    // a German thousands group is LEFT as-is (the binder reads it as thousands with the unit)
    expect(resolveWert(byKey.wellendurchmesser, "4.000")).toBe("4.000 mm");
  });

  it("composeWert appends the unit but never double-appends one the user typed", () => {
    expect(composeWert("50", "mm")).toBe("50 mm");
    expect(composeWert("3000", "U/min")).toBe("3000 U/min");
    expect(composeWert("50 mm", "mm")).toBe("50 mm"); // already has a unit token → no "50 mm mm"
    expect(composeWert("", "mm")).toBe(""); // empty stays empty (not submitted)
    expect(composeWert("Hydrauliköl", "")).toBe("Hydrauliköl"); // no unit field
  });
});

describe("ParameterForm variant='stage' (form-first landing — compact kernel + expander)", () => {
  it("INVARIANT: the compact card renders EXACTLY the schema's role:kernel fields (derived, not hardcoded)", () => {
    render(<ParameterForm variant="stage" onSubmit={vi.fn()} />);
    const card = screen.getByTestId("param-compact");
    const kernel = kernelFields(RWDR_SITUATION); // SAME source the component derives from
    for (const f of kernel) {
      expect(within(card).getByTestId(`param-${f.key}`)).toBeTruthy();
    }
    // exactly the kernel set — count matches, and a context field is NOT in the compact card
    expect(within(card).queryAllByTestId(/^param-/)).toHaveLength(kernel.length);
    expect(within(card).queryByTestId("param-medium")).toBeNull();
  });

  it("the expander holds the role:context fields, separate from the compact kernel card and the Core", () => {
    render(<ParameterForm variant="stage" onSubmit={vi.fn()} />);
    const exp = screen.getByTestId("param-expander");
    expect(within(exp).getByTestId("param-wellenwerkstoff")).toBeTruthy(); // a context field (group E)
    expect(within(exp).queryByTestId("param-medium")).toBeNull(); // medium moved to the Universal Core
    expect(within(screen.getByTestId("param-core")).getByTestId("param-medium")).toBeTruthy();
    expect(within(exp).queryByTestId("param-wellendurchmesser")).toBeNull(); // kernel stays in the card
    expect(screen.getAllByTestId("param-wellendurchmesser")).toHaveLength(1); // never duplicated
  });

  it("lays the expander's group fields out in an auto-fit grid (headers stay, fields inside the grid)", () => {
    render(<ParameterForm variant="stage" onSubmit={vi.fn()} />);
    const exp = screen.getByTestId("param-expander");
    // each rendered context group wraps its fields in a .param-group-grid container
    expect(within(exp).getAllByTestId(/^param-group-grid-/).length).toBeGreaterThan(0);
    // the group legends stay as section labels (fieldset → role group)
    expect(within(exp).getAllByRole("group").length).toBeGreaterThan(0);
    // a context field renders INSIDE the grid, not stacked loose
    expect(within(exp).getByTestId("param-wellenwerkstoff").closest(".param-group-grid")).not.toBeNull();
  });

  it("renders the Universal Core (Medium, Druck normal/max, Temperaturen) ABOVE the type tabs", () => {
    render(<ParameterForm variant="stage" onSubmit={vi.fn()} />);
    const core = screen.getByTestId("param-core");
    for (const k of ["medium", "druck", "druck_max", "betriebstemperatur", "spitzentemperatur"]) {
      expect(within(core).getByTestId(`param-${k}`)).toBeTruthy();
    }
    // a type-specific field is NOT in the Core
    expect(within(core).queryByTestId("param-wellendurchmesser")).toBeNull();
  });

  it("type tabs: RWDR active, Hydraulik/Statisch grayed and NOT selectable (no empty pack)", () => {
    render(<ParameterForm variant="stage" onSubmit={vi.fn()} />);
    const rwdr = screen.getByTestId("param-tab-rwdr");
    const hyd = screen.getByTestId("param-tab-hydraulik") as HTMLButtonElement;
    expect(rwdr).toHaveAttribute("aria-selected", "true");
    expect(hyd.disabled).toBe(true);
    // clicking a disabled pack does NOT switch the active schema (RWDR fields stay)
    fireEvent.click(hyd);
    expect(screen.getByTestId("param-tab-rwdr")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("param-wellendurchmesser")).toBeTruthy();
  });

  it("sticky anchors: tabs are sticky-wrapped and Übernehmen sits in a sticky action bar", () => {
    render(<ParameterForm variant="stage" onSubmit={vi.fn()} />);
    // the type tabs live inside the sticky-top wrapper (reachable while the form scrolls)
    expect(screen.getByTestId("param-tab-rwdr").closest(".param-tabs-sticky")).not.toBeNull();
    // Übernehmen lives inside the sticky-bottom action bar
    const bar = screen.getByTestId("param-actionbar");
    expect(within(bar).getByTestId("param-submit")).toBeInTheDocument();
  });

  it("'Berechnen' batch-submits filled fields (kernel + context); decimal normalized; Unbekannt/empty omitted", () => {
    const onSubmit = vi.fn();
    render(<ParameterForm variant="stage" onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("param-druck"), { target: { value: "0.5" } }); // period decimal
    fireEvent.change(screen.getByTestId("param-medium"), { target: { value: "oel" } }); // context (in expander)
    fireEvent.click(screen.getByTestId("param-submit"));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const items = onSubmit.mock.calls[0][0];
    expect(items).toContainEqual({ feld: "wellendurchmesser", wert: "50 mm", label: "Wellendurchmesser d₁" });
    expect(items).toContainEqual({ feld: "druck", wert: "0,5 bar", label: "Druck (normal)" }); // 0.5 → 0,5
    expect(items).toContainEqual({ feld: "medium", wert: "Öl", label: "Medium" });
    expect(items).toHaveLength(3); // drehzahl left empty → omitted (no fake default)
  });
});

describe("ParameterForm — Modell R2 (hydrate · live preview · adopt, no wipe)", () => {
  it("hydrateValue is the EXACT inverse of resolveWert — a Hydrate→Übernehmen round-trip never drifts", () => {
    const byKey = Object.fromEntries(formFields(RWDR_SITUATION).map((f) => [f.key, f]));
    // number-with-unit: "40 mm" stays "40 mm" (never "40" or a doubled "40 mm mm")
    expect(resolveWert(byKey.wellendurchmesser, hydrateValue(byKey.wellendurchmesser, "40 mm"))).toBe("40 mm");
    expect(resolveWert(byKey.druck, hydrateValue(byKey.druck, "0,5 bar"))).toBe("0,5 bar");
    // enum: stored German LABEL ↔ option value
    expect(resolveWert(byKey.medium, hydrateValue(byKey.medium, "Öl"))).toBe("Öl");
    // boolean
    expect(resolveWert(byKey.spritzwasser, hydrateValue(byKey.spritzwasser, "ja"))).toBe("ja");
  });

  it("hydrates the fields from the committed case-state on mount (form is the editable surface)", () => {
    render(
      <ParameterForm
        variant="stage"
        onSubmit={vi.fn()}
        committed={{ wellendurchmesser: "40 mm", drehzahl: "5000 U/min" }}
      />,
    );
    expect((screen.getByTestId("param-wellendurchmesser") as HTMLInputElement).value).toBe("40");
    expect((screen.getByTestId("param-drehzahl") as HTMLInputElement).value).toBe("5000");
  });

  it("Uebernehmen keeps the values (no wipe) and DELETES a previously-committed, now-empty field", () => {
    const onSubmit = vi.fn();
    render(
      <ParameterForm
        variant="stage"
        onSubmit={onSubmit}
        committed={{ wellendurchmesser: "40 mm", drehzahl: "5000 U/min" }}
      />,
    );
    fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "" } }); // clear a committed field
    fireEvent.click(screen.getByTestId("param-submit"));
    const [items, deletes] = onSubmit.mock.calls[0];
    expect(items).toContainEqual({ feld: "wellendurchmesser", wert: "40 mm", label: "Wellendurchmesser d₁" });
    expect(items.some((i: { feld: string }) => i.feld === "drehzahl")).toBe(false); // emptied → not submitted
    expect(deletes).toContain("drehzahl"); // was committed, now empty → reconcile DELETE
    // no wipe: the value stays in the field, editable
    expect((screen.getByTestId("param-wellendurchmesser") as HTMLInputElement).value).toBe("40");
  });

  it("does NOT reset the form on submit — values stay editable (Modell R2)", () => {
    render(<ParameterForm variant="stage" onSubmit={vi.fn()} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "40" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    expect((screen.getByTestId("param-wellendurchmesser") as HTMLInputElement).value).toBe("40");
  });

  it("R1: a freshly hydrated form (draft == committed) shows NO Vorschau (no side-by-side doubling)", async () => {
    vi.useFakeTimers();
    try {
      const onPreview = vi.fn(async () => makeCompute(10.472));
      render(
        <ParameterForm
          variant="stage"
          onSubmit={vi.fn()}
          onPreview={onPreview}
          committed={{ wellendurchmesser: "40 mm", drehzahl: "5000 U/min" }}
        />,
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      // at rest the committed panel (in the host) carries the value; the form shows no Vorschau
      expect(screen.queryByTestId("preview-panel")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("R1: editing makes the form dirty → the Vorschau appears, marked nicht übernommen", async () => {
    vi.useFakeTimers();
    try {
      const onPreview = vi.fn(async () => makeCompute(11.78));
      render(
        <ParameterForm
          variant="stage"
          onSubmit={vi.fn()}
          onPreview={onPreview}
          committed={{ wellendurchmesser: "40 mm", drehzahl: "5000 U/min" }}
        />,
      );
      fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "45" } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      const panel = screen.getByTestId("preview-panel");
      expect(panel).toHaveTextContent("Vorschau · nicht übernommen");
      expect(panel).toHaveTextContent("11,78");
    } finally {
      vi.useRealTimers();
    }
  });

  it("R1: once committed catches up to the draft (after Übernehmen) the Vorschau disappears", async () => {
    vi.useFakeTimers();
    try {
      const onPreview = vi.fn(async () => makeCompute(11.78));
      const { rerender } = render(
        <ParameterForm
          variant="stage"
          onSubmit={vi.fn()}
          onPreview={onPreview}
          committed={{ wellendurchmesser: "40 mm", drehzahl: "5000 U/min" }}
        />,
      );
      fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "45" } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      expect(screen.getByTestId("preview-panel")).toBeTruthy(); // dirty → shown
      // Übernehmen: the host re-commits; committed now equals the draft → clean again
      rerender(
        <ParameterForm
          variant="stage"
          onSubmit={vi.fn()}
          onPreview={onPreview}
          committed={{ wellendurchmesser: "45 mm", drehzahl: "5000 U/min" }}
        />,
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      expect(screen.queryByTestId("preview-panel")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("a field change shows a debounced backend Vorschau, clearly marked nicht übernommen", async () => {
    vi.useFakeTimers();
    try {
      const onPreview = vi.fn(async () => makeCompute(10.472));
      render(<ParameterForm variant="stage" onSubmit={vi.fn()} onPreview={onPreview} />);
      fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "40" } });
      fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "5000" } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      expect(onPreview).toHaveBeenCalledTimes(1); // debounce collapsed the two changes into ONE call
      const panel = screen.getByTestId("preview-panel");
      expect(panel).toHaveTextContent("Vorschau · nicht übernommen");
      expect(panel).toHaveTextContent("10,47"); // German format, kern value (10,47 m/s)
    } finally {
      vi.useRealTimers();
    }
  });

  it("preview is LATEST-WINS: a delayed EARLIER response never overwrites a NEWER one", async () => {
    vi.useFakeTimers();
    try {
      let resolveA: (v: ComputeResponse) => void = () => {};
      let resolveB: (v: ComputeResponse) => void = () => {};
      const onPreview = vi
        .fn()
        .mockImplementationOnce(() => new Promise<ComputeResponse>((r) => (resolveA = r)))
        .mockImplementationOnce(() => new Promise<ComputeResponse>((r) => (resolveB = r)));
      render(<ParameterForm variant="stage" onSubmit={vi.fn()} onPreview={onPreview} />);
      // request A (d=40)
      fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "40" } });
      fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "5000" } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      // request B (d=45) — the NEWER
      fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "45" } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      expect(onPreview).toHaveBeenCalledTimes(2);
      // resolve the NEWER (B) first, then the stale EARLIER (A) — A must be discarded
      await act(async () => {
        resolveB(makeCompute(11.78));
      });
      await act(async () => {
        resolveA(makeCompute(10.47));
      });
      const panel = screen.getByTestId("preview-panel");
      expect(panel).toHaveTextContent("11,78"); // the newer result
      expect(panel).not.toHaveTextContent("10,47"); // the stale earlier response did not win
    } finally {
      vi.useRealTimers();
    }
  });
});
