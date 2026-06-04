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
