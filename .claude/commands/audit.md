---
description: Read-only audit of a scope before any change (Audit first, patch second)
---
You are in AUDIT mode. Do NOT modify any files.

1. Read AGENTS.md, then konzept/konzept_sealing.md, then (for UI) frontend/DESIGN.md.
   If the scope is the V2.0 green-field tree (`backend/sealai_v2/`): also read
   `AGENTS.md § "V2.0 green-field track"` and `docs/V2/*` first — for that tree the
   V2 build-spec + eval seed set are the audit standard, not the V1.8 state graph.
2. Run: git status --short  — if dirty, list open changes and stop unless the task concerns them.
3. Investigate the scope below. Cite concrete files, functions, and line ranges.
4. Output: findings, risks, smallest-useful-patch proposal. No code changes yet.

Scope: $ARGUMENTS
