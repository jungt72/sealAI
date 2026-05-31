import { describe, expect, it } from "vitest";

import type { ActionChip, PocketCockpitPatch } from "@/lib/contracts/agent";
import {
  actionChipChatMessage,
  buildPocketCockpitView,
  MAX_CRITICAL,
  MAX_RECOGNIZED,
  resolvePocketCockpitView,
} from "@/lib/pocketCockpit";

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

describe("resolvePocketCockpitView", () => {
  const BACKEND_PATCH: PocketCockpitPatch = {
    recognized: [{ label: "Fall", value: "Leckage / Dichtstelle unklar", status: "candidate" }],
    critical: [{ label: "Dichtungstyp und Wellenbewegung klären", severity: "high" }],
    next_step: { question: "Dreht sich die Welle?", field: "shaft_rotates" },
    rfq_status: "DRAFT",
  };
  const BACKEND_CHIPS: ActionChip[] = [
    { label: "Ja", value: "yes", field: "shaft_rotates" },
    { label: "Nein", value: "no", field: "shaft_rotates" },
  ];

  it("prefers the backend pocket_cockpit_patch / action_chips when present", () => {
    const resolved = resolvePocketCockpitView(
      { patch: BACKEND_PATCH, chips: BACKEND_CHIPS },
      // A divergent client-derived fallback that must be ignored.
      { recognizedFacts: [{ label: "Medium", value: "Öl" }], isRfqReady: true },
    );

    expect(resolved.source).toBe("backend");
    expect(resolved.patch).toBe(BACKEND_PATCH); // rendered verbatim, not re-derived
    expect(resolved.patch.rfq_status).toBe("DRAFT");
    expect(resolved.chips).toEqual(BACKEND_CHIPS);
  });

  it("falls back to buildPocketCockpitView when no backend patch is present", () => {
    const fallbackInput = {
      recognizedFacts: [{ label: "Medium", value: "Öl" }],
      nextQuestion: { question: "Welcher Druck liegt an?" },
      isRfqReady: false,
    };
    const expected = buildPocketCockpitView(fallbackInput);

    const resolvedNull = resolvePocketCockpitView(null, fallbackInput);
    expect(resolvedNull.source).toBe("client_derived");
    expect(resolvedNull.patch).toEqual(expected.patch);
    expect(resolvedNull.chips).toEqual(expected.chips);

    // An object without a patch also falls back (chips alone are not enough).
    const resolvedNoPatch = resolvePocketCockpitView({ patch: null, chips: BACKEND_CHIPS }, fallbackInput);
    expect(resolvedNoPatch.source).toBe("client_derived");
  });
});

describe("actionChipChatMessage", () => {
  it("submits the chip label through the chat path (user answer, not truth)", () => {
    expect(actionChipChatMessage({ label: "Ja", value: "yes", field: "shaft_rotates" })).toBe("Ja");
    expect(actionChipChatMessage({ label: "Weiß ich nicht", value: "unknown" })).toBe("Weiß ich nicht");
  });

  it("falls back to the value when no label is present", () => {
    expect(actionChipChatMessage({ label: "", value: "no", field: "shaft_rotates" })).toBe("no");
  });

  it("does not submit upload affordances or empty chips", () => {
    expect(actionChipChatMessage({ label: "Foto senden", action: "upload_photo" })).toBeNull();
    expect(actionChipChatMessage({ label: "   " })).toBeNull();
    expect(actionChipChatMessage({ label: "", value: null })).toBeNull();
  });
});
