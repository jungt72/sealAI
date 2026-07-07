---
name: eval-replay-adjudication
description: >-
  Run the sealingAI V2 live Eval-REPLAY and fold the owner's ticked adjudication
  worksheet. Use when a task asks to run the eval, validate a milestone against
  the eval seed set, check Schranken-Quote, adjudicate eval verdicts, or produce
  an Eval-REPLAY before a backend-v2 deploy. Encodes the human-is-oracle rule,
  targeted-not-full policy, secret hygiene for the transient OPENAI_API_KEY, and
  the model-cost guardrails.
---

# Eval-REPLAY + owner adjudication (`backend/sealai_v2/eval/`)

The eval seed set (`docs/V2/sealingai_eval_seed_set_v0.md`) is both the build
target and the regression guard. It has **7 axes + hard Schranken**. This skill is
the procedure for running it correctly. Read `AGENTS.md § Test Commands` and
`.claude/rules/testing.md § V2 layers` alongside this.

## The one hard rule: the human is the factual-correctness ORACLE

The agent **never self-adjudicates**. It runs the eval, surfaces divergences as
owner-final *candidates*, and **recomputes** from the owner's ticked worksheet. It
never ticks PASS/FAIL itself and never free-corrects a factual verdict. This is
the TRAP-02 discipline — violating it silently corrupts the only ground truth the
project has.

- Do **not** author "owner-adjudiziert" notes.
- Do **not** auto-tick the worksheet.
- Axis-1 (factual) FAIL does **not** gate deploy on its own; only the hard-gate
  **Schranken** do. The authoritative gated set is `ops/v2_deploy_gate.py`'s
  `GATED` columns — the seed-v0 trio (no entered trap, no confident-false, no
  invented precision) **plus** the memory, exfiltration, and parametric
  (multiturn/singleturn) quotas — each at `schranken_quota_final == 1.0`. Do not
  reason from the trio alone. See `.claude/rules/doctrine.md` and the deploy skill.

## Commands

Run from `backend/`. Live REPLAY needs `OPENAI_API_KEY` **transiently** from
`~/sealai/.env` — for that run only, never into logs, never committed.

```bash
# Live REPLAY (real model calls) — produces a run under sealai_v2/eval/runs/
PYTHONPATH=. python -m sealai_v2.eval --label <run-label>

# Owner adjudication recompute — NO LLM call; folds the ticked
# human_review_worksheet.md into the verdict
PYTHONPATH=. python -m sealai_v2.eval --adjudicate --label <run-label>
```

Offline unit/contract suite (fake LLM client, no key, no runtime stack) — run this
first; it is free and catches most regressions:

```bash
python -m pytest sealai_v2/ -q
```

## Policy: targeted, not full

Owner directive (2026-06-27): **no full eval before every deploy.** Run a
**targeted** eval against the dimension you changed **plus** the deterministic
Schranken. A full REPLAY is expensive and is owner-initiated, not a reflex.

## Cost + model guardrails

- L1 = `gpt-5.1` is the only model that holds calibration — but it is expensive.
  **Never run dual-role, uncached `gpt-5.1` evals** — that is what caused the ~$10
  burn (the cost was the eval process, not prod).
- Prefer the offline suite for iteration; reserve the live REPLAY for milestone
  acceptance and owner-gated checks.
- Model tiers/flags live in `config/settings.py`.

## Where things live

- Harness / scorer / judge / adjudicate: `sealai_v2/eval/harness.py`,
  `scorer.py`, `judge.py`, `adjudicate.py`, `__main__.py`.
- Runs: `sealai_v2/eval/runs/`.
- Worksheet the owner ticks: `human_review_worksheet.md` in the run dir.
- Acceptance ruler: `docs/V2/sealingai_eval_seed_set_v0.md`.

## Milestone rhythm

The HALT-after-every-milestone-with-a-REPLAY gate is `.claude/rules/workflow.md
§ HALT-gate rhythm`. Eval-specific: build against the eval, not gut feeling —
red-before-green here = a failing eval case / unit test first, then the change; a
milestone is reached only when its cases pass and the Schranken-Quote is 100%.
