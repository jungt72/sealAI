import assert from "node:assert/strict";
import test from "node:test";

import { appendAssistantText, normalizeAssistantMarkdown } from "./assistantText.ts";

test("appendAssistantText preserves spaces and newlines exactly across chunks", () => {
  const combined = [
    "Hallo",
    "! ",
    "Wie kann",
    " ich Ihnen",
    "\n\n- Absatz eins",
    "\n- **Punkt** zwei",
  ].reduce(appendAssistantText, "");

  assert.equal(
    combined,
    "Hallo! Wie kann ich Ihnen\n\n- Absatz eins\n- **Punkt** zwei",
  );
});

test("appendAssistantText keeps whitespace-only chunks instead of trimming them away", () => {
  const combined = appendAssistantText("RFQ", " ready");
  assert.equal(combined, "RFQ ready");
});

test("normalizeAssistantMarkdown keeps content intact while normalizing CRLF line endings", () => {
  assert.equal(
    normalizeAssistantMarkdown("Hallo!\r\n\r\n- Punkt 1\r\n- Punkt 2"),
    "Hallo!\n\n- Punkt 1\n- Punkt 2",
  );
});

test("normalizeAssistantMarkdown preserves markdown structure instead of collapsing it", () => {
  const normalized = normalizeAssistantMarkdown(
    "Absatz eins\r\n\r\n- Punkt 1\r\n- **Punkt 2**\r\n\r\nRFQ-ready",
  );

  assert.equal(normalized, "Absatz eins\n\n- Punkt 1\n- **Punkt 2**\n\nRFQ-ready");
});

test("governed RFQ-ready answers keep readable paragraph and list boundaries", () => {
  const chunks = [
    "**Requirement Class:** PTFE10\n\n",
    "Die Auslegung ist RFQ-ready.\n",
    "- Medium: Steam\n",
    "- Temperatur: 180 C\n\n",
    "Herstellervalidierung bleibt erforderlich.",
  ];

  const combined = chunks.reduce(appendAssistantText, "");

  assert.equal(
    combined,
    "**Requirement Class:** PTFE10\n\nDie Auslegung ist RFQ-ready.\n- Medium: Steam\n- Temperatur: 180 C\n\nHerstellervalidierung bleibt erforderlich.",
  );
  assert.equal(normalizeAssistantMarkdown(combined), combined);
});
