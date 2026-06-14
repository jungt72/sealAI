import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { composeWert, ParameterForm } from "./ParameterForm";

afterEach(cleanup);

describe("ParameterForm (inputs only — the kern owns every number)", () => {
  it("submits each non-empty field with the canonical unit appended", () => {
    const onSubmit = vi.fn();
    render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "3000" } });
    fireEvent.change(screen.getByTestId("param-medium"), { target: { value: "Hydrauliköl" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    expect(onSubmit).toHaveBeenCalledWith("wellendurchmesser", "50 mm"); // binder needs number+unit
    expect(onSubmit).toHaveBeenCalledWith("drehzahl", "3000 U/min");
    expect(onSubmit).toHaveBeenCalledWith("medium", "Hydrauliköl"); // context fact, no unit
  });

  it("does not submit empty fields", () => {
    const onSubmit = vi.fn();
    render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    expect(onSubmit).toHaveBeenCalledTimes(1); // only the one filled field
    expect(onSubmit).toHaveBeenCalledWith("wellendurchmesser", "50 mm");
  });

  it("TRUST: never computes or renders a derived number (no velocity, no m/s)", () => {
    const onSubmit = vi.fn();
    const { container } = render(<ParameterForm onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("param-drehzahl"), { target: { value: "3000" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    // the form emits ONLY raw input felder — never a kern-owned derived quantity
    const felder = onSubmit.mock.calls.map((c) => c[0]);
    expect(felder).not.toContain("umfangsgeschwindigkeit");
    expect(felder.every((f) => ["wellendurchmesser", "drehzahl", "medium", "temperatur"].includes(f))).toBe(true);
    // and renders no velocity value / unit anywhere (π·50·3000/60000 ≈ 7.85 m/s must NOT appear)
    expect(container.textContent ?? "").not.toMatch(/m\/s/);
    expect(container.textContent ?? "").not.toContain("7.85");
  });

  it("composeWert appends the unit but never double-appends one the user typed", () => {
    expect(composeWert("50", "mm")).toBe("50 mm");
    expect(composeWert("3000", "U/min")).toBe("3000 U/min");
    expect(composeWert("50 mm", "mm")).toBe("50 mm"); // already has a unit token → no "50 mm mm"
    expect(composeWert("", "mm")).toBe(""); // empty stays empty (not submitted)
    expect(composeWert("Hydrauliköl", "")).toBe("Hydrauliköl"); // no unit field
  });
});
