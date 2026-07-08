import { jsPDF } from "jspdf";

import type { Briefing } from "../contracts";
import { GELTUNGSRAHMEN } from "../framing";
import { hasRiskFlags, RISK_WARNING_TEXT } from "./safety/riskFlags";

// Legal-by-Design Phase E (Goal 9): the export title + top disclaimer, so a downloaded/printed/
// forwarded document never reads as a technical approval by itself, independent of any in-app
// framing. NEVER "Prüfbericht"/"Gutachten"/"Freigabe"/"Eignungsnachweis"/"Auslegung" — this exact
// title is the one owner-specified wording; do not localize/shorten it per-callsite.
const EXPORT_TITLE = "Technisches Arbeitsblatt / Anfrageentwurf";
const EXPORT_DISCLAIMER =
  "Dieses Dokument ist ein automatisiert erzeugter Arbeitsentwurf auf Basis der eingegebenen " +
  "Angaben — keine technische Freigabe, keine verbindliche Auslegung und kein Prüfgutachten. " +
  "Die finale Werkstoff- und Auslegungsentscheidung sowie jede Freigabe trifft der Hersteller " +
  "bzw. die verantwortliche Fachperson.";

/**
 * Client-side PDF of the Anfrage briefing — lets the user keep or share the worked-out sealing
 * situation WITHOUT sending it to a manufacturer. Deterministic A4 layout (title, disclaimer, an
 * optional risk-flags warning, the claim-boundary note, the briefing body wrapped + paginated,
 * sources footer). No network — the briefing is already in hand. The same claim-boundary framing
 * as every other surface travels with the document.
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

  write(EXPORT_TITLE, 16, { bold: true, gap: 4 });
  write(EXPORT_DISCLAIMER, 9, { color: 90, gap: 12 });
  if (hasRiskFlags(briefing.risk_flags)) {
    write(`${RISK_WARNING_TEXT} (Erkannt: ${briefing.risk_flags.join(", ")})`, 9, {
      bold: true,
      color: 130,
      gap: 12,
    });
  }
  write(briefing.title || "Briefing", 12, { bold: true, color: 90, gap: 12 });
  write(GELTUNGSRAHMEN, 8, { color: 130, gap: 16 });
  write(briefing.body || "", 10.5, { gap: 16 });
  if (briefing.provenance.length > 0) {
    write(`Quellen: ${briefing.provenance.join("  ·  ")}`, 8, { color: 130 });
  }

  doc.save(filename);
}
