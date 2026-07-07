# Testing

The single production backend is `backend/sealai_v2/`. Full V2 doctrine:
`AGENTS.md § Test Commands`.

## Layers
- **V2 offline suite** (CI: `.github/workflows/v2-contracts.yml`) — the fast gate.
  Uses a **fake LLM client → no `OPENAI_API_KEY`, no runtime stack**. Run from
  `backend/`:
  ```
  python -m pytest sealai_v2/ -q
  ```
- **Import-purity keystone** (the hard-red gate, build-spec §11) — no
  `sealai_v2.* ↔ app.*` imports, both directions:
  ```
  python -m pytest ../backend/tests/architecture/test_v2_import_boundary.py --noconftest
  ```
- **Eval-REPLAY** is the **milestone acceptance instrument** (build-spec §9/§10):
  build against the eval, not gut feeling; **Schranken-Quote must → 100%** (no
  entered trap, no confident-false, no invented precision). HALT after each
  milestone with a REPLAY. See the `eval-replay-adjudication` skill for the run +
  adjudicate commands and the human-oracle discipline.
- **Formatting** (CI's `Backend ruff-format guard`) — CI pins `ruff==0.6.9`,
  matched by `.venv`; a different local ruff version WILL disagree:
  ```
  cd .. && .venv/bin/ruff format backend/
  ```

## Rules
- **Red-before-green**: a fix lands with a test / eval case that failed before it
  and passes after. No fix without a reproduced symptom.
- **Never silence, skip, or weaken a test** to get green. If green requires
  loosening a guard, catalog, or Schranke → **HALT** (see `doctrine.md`).
- Report the exact command and the real result. A failing test is reported, never
  hidden. The pytest exit code is authoritative for the pre-deploy gate
  (`ops.md`).
- **Human-oracle adjudication.** The agent runs the eval and recomputes from the
  owner's ticked `human_review_worksheet.md` (`sealai_v2/eval/adjudicate.py`); it
  **never ticks PASS/FAIL itself** and never free-corrects a factual verdict —
  divergences are surfaced as owner-final candidates (the TRAP-02 discipline).
- **Policy:** no full eval before every deploy — a **targeted** eval on the
  changed dimension + the deterministic Schranken (owner directive 2026-06-27).
- Do not install new dependencies unless the user explicitly asks.

## Retired (historical only)
The former V1 doctrine-gate suite lived under `backend/app/agent/tests/`
(`test_comparative_ranking_guard.py`, `test_rwdr_comparative_leak_golden.py`,
`v92/test_final_guard_knowledge_backstop.py`), enforced by
`ops/hooks/doctrine-gate.sh`. That V1 runtime was **retired 2026-06-28**; those
tests are historical. The live gates are the V2 offline suite + import-purity
keystone + the Eval-REPLAY.
