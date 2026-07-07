---
description: Read-only audit of a scope before any change (Audit first, patch second)
---
You are in AUDIT mode. Do NOT modify any files.

1. Read `AGENTS.md` (contract + Leitbild V3), then the `docs/V2/*` sources it
   points to for the touched area — at minimum the build-spec
   (`docs/V2/sealingai_v2_build_spec.md`, §11 boundary / §12 guardrails) and the
   eval seed set (`docs/V2/sealingai_eval_seed_set_v0.md`). For calibration work
   also read the V2.1 Produkt-/Implementierungs-Konzept. For dashboard work read
   `frontend-v2/`.
2. Run: git status --short  — if dirty, list open changes and stop unless the task concerns them.
3. Investigate the scope below. Cite concrete files, functions, and line ranges
   (evidence = path + line). The single active backend is `backend/sealai_v2/`;
   `backend/app/` is retired — do not audit against it.
4. Output: findings, risks, smallest-useful-patch proposal. No code changes yet.

Scope: $ARGUMENTS
