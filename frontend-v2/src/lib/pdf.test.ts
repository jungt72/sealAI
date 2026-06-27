import { describe, expect, it, vi } from "vitest";

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
