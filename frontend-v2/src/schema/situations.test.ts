import { describe, expect, it } from "vitest";

import {
  coreFields,
  type FieldDef,
  KERNEL_INPUTS,
  RWDR_SITUATION,
  SITUATIONS,
  situationFields,
  UNIVERSAL_CORE,
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

  it("the situation kernel fields are the two geometry/kinematics bindings (Druck moved to the Core)", () => {
    const kernel = fields()
      .filter((f) => f.role === "kernel")
      .map((f) => [f.key, f.kernelKey]);
    // key MUST equal a backend binder _BINDINGS key; kernelKey the calc-registry input it feeds
    expect(kernel).toEqual([
      ["wellendurchmesser", "d1_mm"],
      ["drehzahl", "rpm"],
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
  });
});

describe("Universal Core (operating conditions shared across all Domain Packs)", () => {
  const core = (): FieldDef[] => coreFields();

  it("coreFields() returns the UNIVERSAL_CORE list", () => {
    expect(core()).toBe(UNIVERSAL_CORE);
    expect(core().map((f) => f.key)).toEqual([
      "medium",
      "druck",
      "druck_max",
      "betriebstemperatur",
      "spitzentemperatur",
    ]);
  });

  it("Druck (normal) keeps its kernel binding → p_bar; everything else in the Core is context", () => {
    const byKey = Object.fromEntries(core().map((f) => [f.key, f]));
    expect(byKey.druck.role).toBe("kernel");
    expect(byKey.druck.kernelKey).toBe("p_bar");
    expect(KERNEL_INPUTS).toContain(byKey.druck.kernelKey as string);
    expect(byKey.druck.unit).toBe("bar");
    // Druck max is a fail-closed context fact (no kernel guess), Temperatures are context too
    for (const k of ["druck_max", "betriebstemperatur", "spitzentemperatur", "medium"]) {
      expect(byKey[k].role).toBe("context");
      expect(byKey[k].kernelKey).toBeUndefined();
    }
  });

  it("a Core field key never collides with a situation field key", () => {
    const coreKeys = new Set(core().map((f) => f.key));
    for (const f of situationFields(RWDR_SITUATION)) {
      expect(coreKeys.has(f.key)).toBe(false);
    }
  });
});

describe("type tabs (Domain Packs)", () => {
  it("RWDR + Hydraulik are enabled; Statisch is announced-but-disabled, in order", () => {
    expect(SITUATIONS.map((s) => [s.id, Boolean(s.disabled)])).toEqual([
      ["rwdr", false],
      ["hydraulik", false],
      ["statisch", true],
    ]);
  });

  it("a disabled pack carries no fields (no empty/broken schema offered)", () => {
    for (const s of SITUATIONS.filter((s) => s.disabled)) {
      expect(situationFields(s)).toHaveLength(0);
    }
  });
});
