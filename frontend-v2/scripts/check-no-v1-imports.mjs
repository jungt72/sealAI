#!/usr/bin/env node
/**
 * M7 frontend keystone (build-gate check 1): the V2 client must import NOTHING from the V1 app
 * (`frontend/`). This is the frontend analogue of the backend import-purity keystone — it makes the
 * clean-cutover guarantee STRUCTURAL (the build fails on a V1 import), not a convention.
 *
 * Scans frontend-v2/src for module specifiers that (a) reference V1 explicitly ("frontend/…",
 * "../frontend…", "frontend/src"), or (b) are relative imports escaping frontend-v2/. Bare npm
 * specifiers (react, etc.) are allowed. Exit 1 (with the offending file:spec) on any violation.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");
const SPEC_RE =
  /(?:import|export)[^'"]*?from\s*['"]([^'"]+)['"]|import\s*['"]([^'"]+)['"]/g;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (/\.(ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

const violations = [];
for (const file of walk(SRC)) {
  const text = readFileSync(file, "utf8");
  for (const m of text.matchAll(SPEC_RE)) {
    const spec = m[1] || m[2];
    if (!spec) continue;
    if (/(^|\/)\.\.\/frontend(\/|$)/.test(spec) || /(^|\/)frontend\/src/.test(spec)) {
      violations.push([file, spec, "explicit V1 (frontend/) reference"]);
      continue;
    }
    if (spec.startsWith(".")) {
      const resolved = resolve(dirname(file), spec);
      if (!resolved.startsWith(ROOT)) {
        violations.push([file, spec, "relative import escapes frontend-v2/"]);
      }
    }
  }
}

if (violations.length) {
  console.error("✗ V1-import boundary VIOLATED — the V2 client must not depend on V1 (frontend/):");
  for (const [f, spec, why] of violations) {
    console.error(`  ${f.replace(ROOT + "/", "")}  →  "${spec}"  (${why})`);
  }
  process.exit(1);
}
console.log("✓ V1-import boundary clean — frontend-v2 imports nothing from V1 (frontend/).");
