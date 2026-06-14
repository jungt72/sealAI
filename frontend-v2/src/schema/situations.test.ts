import { describe, expect, it } from "vitest";

import {
  type FieldDef,
  KERNEL_INPUTS,
  RWDR_SITUATION,
  SITUATIONS,
  situationFields,
} from "./situations";

const fields = (): FieldDef[] => situationFields(RWDR_SITUATION);

describe("RWDR situation schema (the trust-spine boundary lives in the schema)", () => {
  it("RWDR is the registered first situation", () => {
    expect(SITUATIONS[0]).toBe(RWDR_SITUATION);
    expect(RWDR_SITUATION.id).toBe("rwdr");
    // groups A..I present and ordered
    expect(RWDR_SITUATION.groups.map((g) => g.id)).toEqual(["A", "B", "C", "D", "E", "F", "G", "H", "I"]);
  });

  it("every field key is unique across the situation", () => {
    const keys = fields().map((f) => f.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("KERNEL boundary: a kernel field has a kernelKey in the verified calc-input set; context fields do not", () => {
    for (const f of fields()) {
      if (f.role === "kernel") {
        expect(f.kernelKey).toBeDefined();
        expect(KERNEL_INPUTS).toContain(f.kernelKey as string);
      } else {
        expect(f.kernelKey).toBeUndefined();
      }
    }
  });

  it("the kernel fields are exactly the three verified bindings", () => {
    const kernel = fields()
      .filter((f) => f.role === "kernel")
      .map((f) => [f.key, f.kernelKey]);
    // key MUST equal a backend binder _BINDINGS key; kernelKey the calc-registry input it feeds
    expect(kernel).toEqual([
      ["wellendurchmesser", "d1_mm"],
      ["drehzahl", "rpm"],
      ["druck", "p_bar"],
    ]);
  });

  it("required = only d₁ and n (every other field has Unbekannt as a first-class state)", () => {
    expect(fields().filter((f) => f.required).map((f) => f.key)).toEqual([
      "wellendurchmesser",
      "drehzahl",
    ]);
  });

  it("enum fields carry options; non-enum fields do not", () => {
    for (const f of fields()) {
      if (f.type === "enum") {
        expect(f.options && f.options.length).toBeGreaterThan(0);
      } else {
        expect(f.options).toBeUndefined();
      }
    }
  });

  it("number fields carry a unit; the kernel ones carry the binder's canonical unit", () => {
    const byKey = Object.fromEntries(fields().map((f) => [f.key, f]));
    expect(byKey.wellendurchmesser.unit).toBe("mm");
    expect(byKey.drehzahl.unit).toBe("U/min");
    expect(byKey.druck.unit).toBe("bar");
  });
});
