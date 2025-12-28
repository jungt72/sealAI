import { describe, expect, it } from "vitest";
import {
  areParamValuesEquivalent,
  buildDirtyPatch,
  cleanParameterPatch,
  mergeServerParameters,
  reconcileDirtyWithServer,
} from "../src/lib/parameterSync";
import type { SealParameters } from "../src/lib/types/sealParameters";

type ParametersPatchInput = Partial<Record<keyof SealParameters, unknown>>;

describe("parameter sync helpers", () => {
  it("merges server parameters without overwriting dirty fields", () => {
    const current = { pressure_bar: 5, medium: "oil" };
    const incoming = { pressure_bar: 10, speed_rpm: 1500 };
    const dirty = new Set(["pressure_bar"] as const);

    const merged = mergeServerParameters(current, incoming, dirty);

    expect(merged).toEqual({
      pressure_bar: 5,
      medium: "oil",
      speed_rpm: 1500,
    });
  });

  it("builds and cleans a dirty patch", () => {
    const values = { pressure_bar: 5, medium: "" };
    const dirty = new Set(["pressure_bar", "medium"] as const);

    const patch = buildDirtyPatch(values, dirty);
    const cleaned = cleanParameterPatch(patch as unknown as Partial<SealParameters>);

    expect(cleaned).toEqual({ pressure_bar: 5 });
  });

  it("builds dirty patch from only dirty keys", () => {
    const values = { pressure_bar: 3, medium: "oil", speed_rpm: 1200 };
    const dirty = new Set(["medium"] as const);

    const patch = buildDirtyPatch(values, dirty);

    expect(patch).toEqual({ medium: "oil" });
  });

  it("keeps 0 and false while cleaning", () => {
    const patch = {
      pressure_bar: 0,
      medium: "",
      pressure_min: null,
      speed_rpm: 0,
      contamination: false,
    } as unknown as ParametersPatchInput;

    const cleaned = cleanParameterPatch(patch);

    expect(cleaned).toEqual({ pressure_bar: 0, speed_rpm: 0, contamination: false });
  });

  it("normalizes numeric strings with units", () => {
    const patch = {
      pressure_bar: "10 bar",
      temperature_C: "80 °C",
      medium: "oil",
    } as unknown as ParametersPatchInput;

    const cleaned = cleanParameterPatch(patch);

    expect(cleaned).toEqual({ pressure_bar: 10, temperature_C: 80, medium: "oil" });
  });

  it("treats numeric strings and numbers as equivalent for dirty reconciliation", () => {
    const current = { pressure_bar: "5" } as unknown as SealParameters;
    const incoming = { pressure_bar: 5 } as SealParameters;
    const dirty = new Set(["pressure_bar"] as const);

    const nextDirty = reconcileDirtyWithServer(current, incoming, dirty);

    expect(nextDirty.has("pressure_bar")).toBe(false);
    expect(areParamValuesEquivalent("pressure_bar", current.pressure_bar, incoming.pressure_bar)).toBe(true);
  });
});
