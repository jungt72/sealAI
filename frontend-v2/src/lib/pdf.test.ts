import { beforeEach, describe, expect, it, vi } from "vitest";

// vi.hoisted: the spies must exist when the (hoisted) vi.mock factory runs. A class guarantees the
// mock is a real constructor (`new jsPDF()`), unlike an arrow-returning fn.
const { saveSpy, textSpy } = vi.hoisted(() => ({
  saveSpy: vi.fn(),
  textSpy: vi.fn(),
}));

vi.mock("jspdf", () => ({
  jsPDF: class {
    internal = { pageSize: { getWidth: () => 595, getHeight: () => 842 } };
    setFont = vi.fn();
    setFontSize = vi.fn();
    setTextColor = vi.fn();
    splitTextToSize = (t: string) => t.split("\n");
    text = textSpy;
    addPage = vi.fn();
    save = saveSpy;
  },
}));

import { downloadBriefingPdf } from "./pdf";

beforeEach(() => {
  textSpy.mockClear();
  saveSpy.mockClear();
});

describe("downloadBriefingPdf", () => {
  it("writes the briefing + triggers a named download", () => {
    downloadBriefingPdf({
      kind: "briefing",
      title: "Mein Briefing",
      body: "Zeile A\nZeile B",
      provenance: ["FK-1"],
    });
    expect(saveSpy).toHaveBeenCalledWith("sealingAI-Anfrage-Briefing.pdf");
    const written = textSpy.mock.calls.map((c) => c[0] as string).join(" | ");
    expect(written).toContain("Mein Briefing");
    expect(written).toContain("Zeile A");
    expect(written).toContain("Zeile B");
    expect(written).toContain("Quellen:");
  });

  it("does not crash on an empty briefing", () => {
    expect(() =>
      downloadBriefingPdf({ kind: "briefing", title: "", body: "", provenance: [] }),
    ).not.toThrow();
  });
});

describe("downloadBriefingPdf — Legal-by-Design Phase E (Goal 9)", () => {
  it("always titles the export 'Technisches Arbeitsblatt / Anfrageentwurf' + the disclaimer", () => {
    downloadBriefingPdf({ kind: "briefing", title: "x", body: "y", provenance: [] });
    const written = textSpy.mock.calls.map((c) => c[0] as string).join(" | ");
    expect(written).toContain("Technisches Arbeitsblatt / Anfrageentwurf");
    expect(written).toContain("keine technische Freigabe");
    expect(written).toContain("trifft der Hersteller");
  });

  it("never titles the export Prüfbericht/Gutachten/Freigabe/Eignungsnachweis/Auslegung", () => {
    downloadBriefingPdf({ kind: "briefing", title: "x", body: "y", provenance: [] });
    const written = textSpy.mock.calls.map((c) => c[0] as string).join(" | ");
    for (const forbidden of ["Prüfbericht", "Gutachten", "Eignungsnachweis"]) {
      expect(written).not.toContain(forbidden);
    }
  });

  it("omits the risk warning when risk_flags is absent or empty", () => {
    downloadBriefingPdf({ kind: "briefing", title: "x", body: "y", provenance: [] });
    let written = textSpy.mock.calls.map((c) => c[0] as string).join(" | ");
    expect(written).not.toContain("Potenziell regulierter");
    textSpy.mockClear();
    downloadBriefingPdf({ kind: "briefing", title: "x", body: "y", provenance: [], risk_flags: [] });
    written = textSpy.mock.calls.map((c) => c[0] as string).join(" | ");
    expect(written).not.toContain("Potenziell regulierter");
  });

  it("shows the same warning badge as the chat UI when risk_flags is present", () => {
    downloadBriefingPdf({
      kind: "briefing",
      title: "x",
      body: "y",
      provenance: [],
      risk_flags: ["ATEX", "Sauerstoff"],
    });
    const written = textSpy.mock.calls.map((c) => c[0] as string).join(" | ");
    expect(written).toContain("Potenziell regulierter");
    expect(written).toContain("ATEX, Sauerstoff");
  });
});
