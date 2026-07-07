import { describe, expect, it } from "vitest";

import {
  calculateCircumferentialSpeedMs,
  evaluatePrecheck,
  formatSpeedDe,
} from "./precheck";

describe("calculateCircumferentialSpeedMs", () => {
  it("computes v = π·d·n/60000 (45 mm, 1500 rpm ≈ 3.53 m/s)", () => {
    const v = calculateCircumferentialSpeedMs(45, 1500);
    expect(v).toBeCloseTo(3.53, 2);
  });

  it("scales linearly with diameter and rpm", () => {
    expect(calculateCircumferentialSpeedMs(90, 1500)).toBeCloseTo(2 * 3.5343, 2);
    expect(calculateCircumferentialSpeedMs(45, 3000)).toBeCloseTo(2 * 3.5343, 2);
  });
});

describe("evaluatePrecheck", () => {
  it("initial: no input yields no calculation and no open points", () => {
    const r = evaluatePrecheck({});
    expect(r.status).toBe("initial");
    expect(r.circumferentialSpeedMs).toBeUndefined();
    expect(r.missingPoints).toHaveLength(0);
  });

  it("insufficient: only a seal type, no calculation", () => {
    const r = evaluatePrecheck({ sealType: "rwdr" });
    expect(r.status).toBe("insufficient");
    expect(r.circumferentialSpeedMs).toBeUndefined();
    expect(r.dataQualityLabel).toBe("Niedrig");
  });

  it("critical_unknowns: RWDR + medium but shaft diameter missing", () => {
    const r = evaluatePrecheck({ sealType: "rwdr", medium: "Hydrauliköl", rpm: 1500 });
    expect(r.status).toBe("critical_unknowns");
    expect(r.circumferentialSpeedMs).toBeUndefined();
    expect(r.missingPoints).toContain("Wellendurchmesser");
    expect(r.missingPoints.length).toBeLessThanOrEqual(3);
  });

  it("critical_unknowns: RWDR + medium but rpm missing", () => {
    const r = evaluatePrecheck({ sealType: "rwdr", medium: "Hydrauliköl", shaftDiameterMm: 45 });
    expect(r.status).toBe("critical_unknowns");
    expect(r.missingPoints).toContain("Drehzahl");
  });

  it("actionable: RWDR + medium + shaft + rpm computes v and shows ≤3 open points", () => {
    const r = evaluatePrecheck({
      sealType: "rwdr",
      situation: "leakage",
      medium: "Hydrauliköl",
      shaftDiameterMm: 45,
      rpm: 1500,
    });
    expect(r.status).toBe("actionable");
    expect(r.circumferentialSpeedMs).toBeCloseTo(3.53, 2);
    expect(r.missingPoints.length).toBeGreaterThan(0);
    expect(r.missingPoints.length).toBeLessThanOrEqual(3);
    expect(r.dataQualityLabel).toBe("Gut");
  });

  it("preliminary: non-RWDR with medium and a technical value (no rotary calc)", () => {
    const r = evaluatePrecheck({ sealType: "hydraulic_seal", medium: "Hydrauliköl", shaftDiameterMm: 40 });
    expect(r.status).toBe("preliminary");
    expect(r.circumferentialSpeedMs).toBeUndefined();
  });

  it("never returns more than 3 open points in any state", () => {
    const r = evaluatePrecheck({ sealType: "rwdr" });
    expect(r.missingPoints.length).toBeLessThanOrEqual(3);
  });
});

describe("formatSpeedDe", () => {
  it("formats with a German decimal comma and two digits", () => {
    expect(formatSpeedDe(3.53)).toBe("3,53");
  });
});
