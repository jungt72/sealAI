import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RWDR_SITUATION, situationFields } from "../schema/situations";
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

  it("submits each filled field: number appends its unit, enum emits the readable label", () => {
    const onSubmit = vi.fn();
    render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "3000" } });
    fireEvent.change(screen.getByTestId("param-druck"), { target: { value: "5" } });
    fireEvent.change(screen.getByTestId("param-medium"), { target: { value: "oel" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    expect(onSubmit).toHaveBeenCalledWith("wellendurchmesser", "50 mm"); // binder needs number+unit
    expect(onSubmit).toHaveBeenCalledWith("drehzahl", "3000 U/min");
    expect(onSubmit).toHaveBeenCalledWith("druck", "5 bar");
    expect(onSubmit).toHaveBeenCalledWith("medium", "Öl"); // enum stores the German label, not "oel"
    expect(onSubmit).toHaveBeenCalledTimes(4); // only the four filled fields
  });

  it("does NOT submit empty / 'Unbekannt' fields (no fake default — the param stays missing)", () => {
    const onSubmit = vi.fn();
    render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    // medium left at "Unbekannt" (value ""), every other field untouched
    fireEvent.click(screen.getByTestId("param-submit"));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith("wellendurchmesser", "50 mm");
  });

  it("TRUST: emits only raw schema input felder — never a kern-owned derived quantity, no m/s", () => {
    const onSubmit = vi.fn();
    const { container } = render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "3000" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    const felder = onSubmit.mock.calls.map((c) => c[0]);
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

  it("composeWert appends the unit but never double-appends one the user typed", () => {
    expect(composeWert("50", "mm")).toBe("50 mm");
    expect(composeWert("3000", "U/min")).toBe("3000 U/min");
    expect(composeWert("50 mm", "mm")).toBe("50 mm"); // already has a unit token → no "50 mm mm"
    expect(composeWert("", "mm")).toBe(""); // empty stays empty (not submitted)
    expect(composeWert("Hydrauliköl", "")).toBe("Hydrauliköl"); // no unit field
  });
});
