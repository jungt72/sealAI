# Testing

## Layers
- **Fast doctrine guard suite** (the pre-commit gate, `ops/hooks/doctrine-gate.sh`):
  ```
  backend/app/agent/tests/test_comparative_ranking_guard.py
  backend/app/agent/tests/test_rwdr_comparative_leak_golden.py
  backend/app/agent/tests/v92/test_final_guard_knowledge_backstop.py
  ```
  These are the executable contract for the output doctrine. They must be green
  before any `git commit` / `git push`.
- **Full backend pre-deploy gate** (`ops.md`): `.venv/bin/python -m pytest
  backend -q -rf`, exit code authoritative.

## How to run
- Focused first: `cd backend && python -m pytest <path>::<test> -q`.
- Affected-area sweep before a PR, e.g. for streaming/guard work:
  `cd backend && python -m pytest app/agent/tests/test_phase_f_streaming_cut.py
  app/agent/tests/v92 app/agent/tests/test_rwdr_comparative_leak_golden.py
  app/agent/tests/test_comparative_ranking_guard.py -q`.

## Rules
- **Red-before-green**: a fix lands with a test that failed before it and passes
  after. No fix without a reproduced symptom.
- **Never silence, skip, or weaken a test** to get green. If green requires
  loosening a guard → HALT (see `doctrine.md`).
- Report the exact command and the real result. A failing test is reported, never
  hidden.
- New guard/lexicon work carries a **zero-false-positive** proof against the
  `material_comparison.py` corpus, the existing negative fixtures, and the golden
  cases.

## V2 layers (`backend/sealai_v2/` — green-field, `feat/v2*`, not cut over)

> Applies to the V2 tree only. The V1 doctrine-gate suite + full pre-deploy gate
> above are unchanged. Full V2 doctrine: `AGENTS.md § "V2.0 green-field track"`.

- **V2 offline suite** (CI: `.github/workflows/v2-contracts.yml`) — uses a **fake LLM
  client → no `OPENAI_API_KEY`, no runtime stack**:
  ```
  PYTHONPATH=backend python -m pytest backend/sealai_v2 --noconftest -q
  ```
- **Import-purity keystone** (the hard-red gate, build-spec §11) — no
  `sealai_v2.* ↔ app.*` imports, both directions:
  ```
  python -m pytest backend/tests/architecture/test_v2_import_boundary.py --noconftest
  ```
- **Eval-REPLAY is the milestone acceptance instrument** (build-spec §9/§10): build
  against the eval, not gut feeling; **Schranken-Quote must → 100 %** (no entered
  trap, no confident-false, no invented precision). HALT after each milestone with a
  REPLAY. Red-before-green here = a failing eval case / unit test first.
- **Human-oracle adjudication.** The agent runs the eval and recomputes from the
  owner's ticked `human_review_worksheet.md` (`sealai_v2/eval/adjudicate.py`); it
  **never ticks PASS/FAIL itself** and never free-corrects a factual verdict —
  divergences are surfaced as owner-final candidates (the TRAP-02 discipline).
