import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { kernelFields, RWDR_SITUATION, situationFields } from "../schema/situations";
import { composeWert, ParameterForm, resolveWert } from "./ParameterForm";

afterEach(cleanup);

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
    expect(items).toContainEqual({ feld: "druck", wert: "5 bar", label: "Druck p" });
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
    const byKey = Object.fromEntries(situationFields(RWDR_SITUATION).map((f) => [f.key, f]));
    expect(resolveWert(byKey.wellendurchmesser, "50")).toBe("50 mm");
    expect(resolveWert(byKey.medium, "oel")).toBe("Öl");
    expect(resolveWert(byKey.medium, "")).toBe(""); // Unbekannt → omitted
    expect(resolveWert(byKey.spritzwasser, "ja")).toBe("ja");
    expect(resolveWert(byKey.spritzwasser, "")).toBe(""); // Unbekannt → omitted
    expect(resolveWert(byKey.additive, "Mineralöl-Additiv")).toBe("Mineralöl-Additiv"); // text, no unit
  });

  it("number path normalizes a period decimal to the German comma (0.5 → 0,5) — prevents the 0-parse", () => {
    const byKey = Object.fromEntries(situationFields(RWDR_SITUATION).map((f) => [f.key, f]));
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

  it("the expander holds the role:context fields (full A–I), separate from the compact kernel card", () => {
    render(<ParameterForm variant="stage" onSubmit={vi.fn()} />);
    const exp = screen.getByTestId("param-expander");
    expect(within(exp).getByTestId("param-medium")).toBeTruthy(); // a context field
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
    expect(within(exp).getByTestId("param-medium").closest(".param-group-grid")).not.toBeNull();
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
    expect(items).toContainEqual({ feld: "druck", wert: "0,5 bar", label: "Druck p" }); // 0.5 → 0,5
    expect(items).toContainEqual({ feld: "medium", wert: "Öl", label: "Medium" });
    expect(items).toHaveLength(3); // drehzahl left empty → omitted (no fake default)
  });
});
