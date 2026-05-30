import { describe, expect, it } from "vitest";

import { buildPocketCockpitView, MAX_CRITICAL, MAX_RECOGNIZED } from "@/lib/pocketCockpit";

describe("buildPocketCockpitView", () => {
  it("compresses recognized facts to the mobile cap and drops placeholders", () => {
    const { patch } = buildPocketCockpitView({
      recognizedFacts: [
        { label: "Medium", value: "Öl" },
        { label: "Temperatur", value: "Noch offen" }, // placeholder → dropped
        { label: "Drehzahl", value: "1500 rpm" },
        { label: "Wellendurchmesser", value: "45 mm" },
        { label: "Druck", value: "6 bar" },
        { label: "Geometrie", value: "—" }, // placeholder → dropped
        { label: "Extra", value: "x" },
      ],
    });

    expect(patch.recognized?.length).toBe(MAX_RECOGNIZED);
    const labels = patch.recognized?.map((r) => r.label);
    expect(labels).not.toContain("Temperatur");
    expect(labels).not.toContain("Geometrie");
    expect(patch.recognized?.[0]).toEqual({ label: "Medium", value: "Öl", status: "confirmed" });
  });

  it("caps critical items and defaults severity to high", () => {
    const { patch } = buildPocketCockpitView({
      criticalItems: [
        { label: "Wellenlauffläche prüfen" },
        { label: "Staubschutz prüfen", severity: "medium" },
        { label: "Druckdifferenz" },
        { label: "Vierter" },
      ],
    });
    expect(patch.critical?.length).toBe(MAX_CRITICAL);
    expect(patch.critical?.[0]).toEqual({ label: "Wellenlauffläche prüfen", severity: "high" });
    expect(patch.critical?.[1].severity).toBe("medium");
  });

  it("derives next_step + default action chips from the active question", () => {
    const { patch, chips } = buildPocketCockpitView({
      nextQuestion: { question: "Dreht sich die Welle?", field: "shaft_rotates" },
    });
    expect(patch.next_step).toEqual({ question: "Dreht sich die Welle?", field: "shaft_rotates" });
    expect(chips.map((c) => c.label)).toEqual(["Weiß ich nicht", "Foto senden"]);
    expect(chips[1].action).toBe("upload_photo");
  });

  it("emits no chips and DRAFT status when no question and not RFQ-ready", () => {
    const { patch, chips } = buildPocketCockpitView({});
    expect(chips).toEqual([]);
    expect(patch.next_step).toBeNull();
    expect(patch.rfq_status).toBe("DRAFT");
    expect(patch.collapsed_by_default).toBe(true);
  });

  it("maps RFQ-ready to manufacturer review status", () => {
    const { patch } = buildPocketCockpitView({ isRfqReady: true });
    expect(patch.rfq_status).toBe("MANUFACTURER_REVIEW_READY");
  });
});
