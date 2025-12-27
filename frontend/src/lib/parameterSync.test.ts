import { describe, it, expect } from "vitest";
import { mergeServerParameters } from "./parameterSync";

describe("mergeServerParameters", () => {
  it("hydrates non-dirty fields while preserving dirty ones", () => {
    const current = {
      pressure_bar: "5",
      medium: "oil",
    } as const;
    const incoming = {
      pressure_bar: 6,
      medium: "water",
      temperature_C: 80,
    } as const;
    const dirty = new Set(["pressure_bar" as const]);

    const merged = mergeServerParameters(current, incoming, dirty);

    expect(merged.pressure_bar).toBe("5");
    expect(merged.medium).toBe("water");
    expect(merged.temperature_C).toBe(80);
  });

  it("updates pressure_bar when server changes and field is not dirty", () => {
    const current = { pressure_bar: 10 } as const;
    const incoming = { pressure_bar: 7 } as const;
    const dirty = new Set([]);

    const merged = mergeServerParameters(current, incoming, dirty);

    expect(merged.pressure_bar).toBe(7);
  });
});
