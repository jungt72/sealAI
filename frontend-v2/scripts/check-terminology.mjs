#!/usr/bin/env node
/**
 * Legal-by-Design Phase E (Goal 10): a terminology lint over frontend-v2/src, mirroring
 * backend/sealai_v2/tests/test_terminology_lint.py term-for-term (both read the SAME doctrine —
 * see that file's docstring for why "sicher" is excluded from the scanned subset and why eval/
 * fixtures don't apply on this side at all).
 *
 * Structural script (like check-no-v1-imports.mjs), not a vitest test — this repo's own
 * precedent for a build-gate lint is a standalone script wired into `npm run verify`.
 *
 * ALLOWLIST_FILES: every current hit in frontend-v2/src, individually reviewed (Legal-by-Design
 * Phase E audit, 2026-07-08) and confirmed safe — each either negates the term, is a structural
 * field hardcoded to false (produktspec's G1 `freigegeben` invariant), is an owner-only admin
 * review-queue label for a stored data field (not a customer-facing sealingAI claim), or is this
 * lint's own doctrine text. A NEW hit outside this allowlist fails the check — that is the point.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");

const SCANNED_TERMS = [
  "geeignet",
  "freigegeben",
  "bestanden",
  "approved",
  "validiert",
  "empfehlung",
  "prüfbericht",
];

const ALLOWLIST_FILES = new Set([
  "components/Answer.tsx", // negated comment: 'never an affirmative "passt/geeignet"'
  "components/KandidatenSpecPanel.tsx", // negated comment: `freigegeben` false (G1)
  "contracts.ts", // `freigegeben: boolean; // always false (G1)` structural field
  "components/ContributePanel.tsx", // negated: "fließt nie automatisch in eine Empfehlung"
  "components/AdminPane.tsx", // negated hit + an owner-only admin label for the stored
  // Contribution.recommendation field (review-queue tool, not a customer-facing claim)
  "lib/safety/riskFlags.ts", // negated warning text: "keine Empfehlung, keine Eignungs-, ..."
  "lib/pdf.ts", // comment listing the forbidden export titles to avoid (self-referential)
]);

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

const violations = [];
for (const file of walk(SRC)) {
  const rel = relative(SRC, file);
  if (ALLOWLIST_FILES.has(rel)) continue;
  const lower = readFileSync(file, "utf8").toLowerCase();
  for (const term of SCANNED_TERMS) {
    if (lower.includes(term)) {
      violations.push(`${rel}: contains forbidden term "${term}"`);
    }
  }
}

if (violations.length) {
  console.error("✗ Terminology lint VIOLATED — risky status term(s) outside the reviewed allowlist:");
  for (const v of violations) console.error(`  ${v}`);
  console.error(
    "Use the safe replacement from FORBIDDEN_STATUS_TERMS (backend core/legal_doctrine.py), " +
      "or, if this is a genuinely reviewed-safe negated/structural usage, add the file to " +
      "ALLOWLIST_FILES in this script with a one-line justification.",
  );
  process.exit(1);
}

// Inverse guard: an allowlisted file that no longer contains ANY scanned term is stale.
const stale = [];
for (const rel of ALLOWLIST_FILES) {
  const p = join(SRC, rel);
  let text;
  try {
    text = readFileSync(p, "utf8").toLowerCase();
  } catch {
    stale.push(`${rel}: file no longer exists`);
    continue;
  }
  if (!SCANNED_TERMS.some((t) => text.includes(t))) {
    stale.push(`${rel}: no longer contains any scanned term`);
  }
}
if (stale.length) {
  console.error("✗ Stale ALLOWLIST_FILES entries (remove them):");
  for (const s of stale) console.error(`  ${s}`);
  process.exit(1);
}

console.log("✓ Terminology lint clean — no risky status terms outside the reviewed allowlist.");
