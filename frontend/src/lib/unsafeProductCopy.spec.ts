import { readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const productionCopyFiles = [
  "components/dashboard/CaseScreen.tsx",
  "components/dashboard/ChatPane.tsx",
  "components/dashboard/DecisionUnderstandingPanel.tsx",
  "components/dashboard/ManufacturerFitPanel.tsx",
  "components/dashboard/RfqPane.tsx",
  "components/rag/RagDocumentGrid.tsx",
  "lib/mapping/workspace.ts",
].map((path) => resolve(root, path));

const forbiddenCopy = [
  ["Technische", "Validierung"],
  ["Finalisieren", "und", "versenden"],
  ["Anfrage", "erfolgreich", "versendet"],
  ["An", "Hersteller", "senden"],
  ["Empfehlung", "ableiten"],
  ["neutral", "gepruefte", "Auswahl"],
  ["neutral", "geprüfte", "Auswahl"],
  ["freigegeben"],
  ["validiert"],
  ["geeignet"],
  ["zertifiziert"],
  ["compliant"],
  ["garantiert"],
  ["final", "release"],
].map((parts) => parts.join(" "));

const allowedCopy = [
  "noch nicht final freigegeben",
  "nicht validiert",
];

function withoutAllowedCopy(source: string): string {
  return allowedCopy.reduce(
    (current, allowedPhrase) => current.replaceAll(allowedPhrase.toLowerCase(), ""),
    source,
  );
}

it("main frontend copy avoids final recommendation, release, dispatch and matching claims", () => {
  const violations: string[] = [];

  for (const file of productionCopyFiles) {
    const source = readFileSync(file, "utf8");
    const normalized = withoutAllowedCopy(source.toLowerCase());

    for (const phrase of forbiddenCopy) {
      const needle = phrase.toLowerCase();
      if (!normalized.includes(needle)) {
        continue;
      }

      violations.push(`${relative(root, file)}: ${phrase}`);
    }
  }

  expect(violations).toEqual([]);
});
