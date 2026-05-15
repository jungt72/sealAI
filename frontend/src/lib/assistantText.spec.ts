import { describe, expect, it } from "vitest";

import { appendAssistantText, normalizeAssistantMarkdown } from "./assistantText.ts";

describe("assistantText", () => {
  it("appendAssistantText preserves spaces and newlines exactly across chunks", () => {
    const combined = [
      "Hallo",
      "! ",
      "Wie kann",
      " ich Ihnen",
      "\n\n- Absatz eins",
      "\n- **Punkt** zwei",
    ].reduce(appendAssistantText, "");

    expect(combined).toBe("Hallo! Wie kann ich Ihnen\n\n- Absatz eins\n- **Punkt** zwei");
  });

  it("appendAssistantText keeps whitespace-only chunks instead of trimming them away", () => {
    const combined = appendAssistantText("RFQ", " ready");
    expect(combined).toBe("RFQ ready");
  });

  it("normalizeAssistantMarkdown keeps content intact while normalizing CRLF line endings", () => {
    expect(normalizeAssistantMarkdown("Hallo!\r\n\r\n- Punkt 1\r\n- Punkt 2")).toBe(
      "Hallo!\n\n- Punkt 1\n- Punkt 2",
    );
  });

  it("normalizeAssistantMarkdown normalizes visible German ASCII spellings", () => {
    expect(
      normalizeAssistantMarkdown(
        "Welche Gegenlaufflaeche ist bekannt, Haerte, Huelse oder Dichtlippenbeschaedigung ueber der Dichtung?",
      ),
    ).toBe("Welche Gegenlauffläche ist bekannt, Härte, Hülse oder Dichtlippenbeschädigung über der Dichtung?");
  });

  it("normalizeAssistantMarkdown preserves markdown structure instead of collapsing it", () => {
    const normalized = normalizeAssistantMarkdown(
      "Absatz eins\r\n\r\n- Punkt 1\r\n- **Punkt 2**\r\n\r\nRFQ-ready",
    );

    expect(normalized).toBe("Absatz eins\n\n- Punkt 1\n- **Punkt 2**\n\nRFQ-ready");
  });

  it("normalizeAssistantMarkdown removes accidental full-paragraph quotes", () => {
    expect(
      normalizeAssistantMarkdown(
        '"Die wichtigste Rueckfrage ist: Meinst du den Druckunterschied ueber der Dichtung?"',
      ),
    ).toBe("Die wichtigste Rückfrage ist: Meinst du den Druckunterschied über der Dichtung?");
  });

  it("governed RFQ-ready answers keep readable paragraph and list boundaries", () => {
    const chunks = [
      "**Requirement Class:** PTFE10\n\n",
      "Die Auslegung ist RFQ-ready.\n",
      "- Medium: Steam\n",
      "- Temperatur: 180 C\n\n",
      "Herstellervalidierung bleibt erforderlich.",
    ];

    const combined = chunks.reduce(appendAssistantText, "");

    expect(combined).toBe(
      "**Requirement Class:** PTFE10\n\nDie Auslegung ist RFQ-ready.\n- Medium: Steam\n- Temperatur: 180 C\n\nHerstellervalidierung bleibt erforderlich.",
    );
    expect(normalizeAssistantMarkdown(combined)).toBe(combined);
  });
});
