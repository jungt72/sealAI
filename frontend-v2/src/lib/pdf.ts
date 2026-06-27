import { jsPDF } from "jspdf";

import type { Briefing } from "../contracts";
import { GELTUNGSRAHMEN } from "../framing";

/**
 * Client-side PDF of the Anfrage briefing — lets the user keep or share the worked-out sealing
 * situation WITHOUT sending it to a manufacturer. Deterministic A4 layout (title, the claim-boundary
 * note, the briefing body wrapped + paginated, sources footer). No network — the briefing is already
 * in hand. The same claim-boundary framing as every other surface travels with the document.
 */
export function downloadBriefingPdf(
  briefing: Briefing,
  filename = "sealingAI-Anfrage-Briefing.pdf",
): void {
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const margin = 56;
  const contentW = pageW - margin * 2;
  let y = margin;

  const write = (
    text: string,
    size: number,
    opts: { bold?: boolean; color?: number; gap?: number } = {},
  ) => {
    if (!text) return;
    doc.setFont("helvetica", opts.bold ? "bold" : "normal");
    doc.setFontSize(size);
    doc.setTextColor(opts.color ?? 30);
    const lineH = size * 1.4;
    const lines = doc.splitTextToSize(text, contentW) as string[];
    for (const line of lines) {
      if (y + lineH > pageH - margin) {
        doc.addPage();
        y = margin;
      }
      doc.text(line, margin, y);
      y += lineH;
    }
    y += opts.gap ?? 0;
  };

  write("sealingAI – Technische Anfrage (Briefing)", 16, { bold: true, gap: 4 });
  write(briefing.title || "Briefing", 12, { bold: true, color: 90, gap: 12 });
  write(GELTUNGSRAHMEN, 8, { color: 130, gap: 16 });
  write(briefing.body || "", 10.5, { gap: 16 });
  if (briefing.provenance.length > 0) {
    write(`Quellen: ${briefing.provenance.join("  ·  ")}`, 8, { color: 130 });
  }

  doc.save(filename);
}
