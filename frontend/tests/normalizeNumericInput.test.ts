import { describe, expect, it } from "vitest";
import { normalizeNumericInput } from "../src/lib/normalizeNumericInput";

describe("normalizeNumericInput", () => {
  it("parses numbers with units and comma decimals", () => {
    expect(normalizeNumericInput("10 bar")).toBe(10);
    expect(normalizeNumericInput("0,5")).toBe(0.5);
    expect(normalizeNumericInput("80 °C")).toBe(80);
  });

  it("returns undefined for empty or invalid input", () => {
    expect(normalizeNumericInput("")).toBeUndefined();
    expect(normalizeNumericInput("kein wert")).toBeUndefined();
  });
});
