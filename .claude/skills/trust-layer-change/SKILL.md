---
name: trust-layer-change
description: >-
  Change the sealingAI V2 four-layer trust spine safely — the L1 generator, the
  L3 verifier, the response contract / output guard, the trap catalog, or the
  Jinja2 prompts. Use when a task touches core/l1_generator.py,
  core/l3_verifier.py, core/response_contract.py, knowledge/traps.py, the
  prompts, or asks to adjust how assertively/cautiously the system answers.
  Encodes the never-weaken-a-guard line and the confident_wrong / destructive-hedge
  failure mode that has recurred twice.
---

# Change the four-layer trust spine (`backend/sealai_v2/core/`, `knowledge/`, `prompts/`)

Halluzination-resistance comes from four layers carrying **together**, not from
control-determinism. Read `AGENTS.md § Four-layer trust model` and
`.claude/rules/doctrine.md` alongside this. The **retired V1** files
`backend/app/agent/runtime/output_guard.py` / `.../v92/final_guard.py` are gone —
do not look for them. V2 has its **own live guard**, `core/output_guard.py`
(`evaluate_render` — claim-level, fail-closed; enforces the answer-contract that
`core/response_contract.py` builds), wired into `pipeline/pipeline.py` and
**active in prod** behind `SEALAI_V2_RESPONSE_CONTRACT_GENERAL_GUARD_ENABLED`.

## The pipeline (one directed chain, no routing mesh)

`verstehen → grounden → antworten (mit Konfidenz) → verifizieren → zitieren`

- **L1 · Generator** (`core/l1_generator.py`, `prompts/system_l1.jinja`) — strong
  LLM, the *why*. Must **not** invent precise numbers/norms or rubber-stamp a
  default. Honesty norms live in the prompt (ranges not false precision, no
  invented numbers, orientation ≠ release, mark "Allgemeinwissen — verifizieren").
- **L2 · Grounding** — RAG over Fachkarten + matrix + Qdrant, **with provenance**.
  Must not become control logic. (See the `knowledge-fachkarten` and
  `retrieval-rag` skills.)
- **L3 · Verifier** (`core/l3_verifier.py`, `prompts/verifier_l3.jinja`) — an
  independent critic vs. the **trap catalog** (`knowledge/traps.py`,
  `trap_catalog.json`) + matrix. A correction's replacement fact comes **only**
  from a `reviewed` entry; otherwise a deterministic **hedge**. L3 never invents
  its own source of truth and must not smooth over a correct answer.
- **L4 · Human/Manufacturer** — final validation stays outside the system.

## The hard line (never cross)

**Never weaken a guard, catalog, or eval test to make something pass.** If a test
only goes green by loosening what blocks → **HALT to human**, do not edit.
Changing what a `reviewed` catalog entry asserts is a doctrine change
(owner-grounded, never model-sourced).

## The recurring failure mode: destructive hedge / confident_wrong

This has bitten twice. Guard against both directions:

- **Over-hedge (L3 over-flags):** a correct, useful answer gets hijacked into a
  content-free warning. E.g. a PTFE Wissensfrage turned into a narrow trap
  warning; "welche material empfiehlst du mir" got a content-free hedge. The user
  must still get a **material** — the hedge is the rare marked edge, not the
  fallback.
- **Under-verify (confident_wrong):** L3 must be able to verify **norm- and
  equivalence-claims**, not only material recommendations. A confident-false claim
  is a hard-Schranke violation.

Provenance ≠ topical fit: a reviewed trap's `correct` is split into a
topic-agnostic `correct_general` (always injected) and a topic-scoped
`correct_recommendation` (injected only when the question matches the trap's
`applies_to`), so an off-topic trap firing never mis-directs with a wrong-topic
recommendation. Preserve that split.

## V2.1 calibration (how assertively to claim)

The calibration doctrine (confident-correct default, the never-gated SAFETY
clause, norms grounded-not-recited, equivalence as the sharpest edge) lives in
`.claude/rules/doctrine.md § V2.1 calibration` — read it there; do not re-derive
it. The one implication that bears directly on a code change here: **L3 must be
able to verify norm- and equivalence-claims, not only material recommendations**
(the uniform trust-spine).

## Discipline for any change here

1. **Audit first**, cite `file:line`. Root-cause from a **real LangSmith trace**
   where possible, not a guess (that is how the two hedge fixes were correctly
   found).
2. **Red-before-green** against the eval: a failing eval case / unit test first.
3. **Never invent numbers/norms** in code or prompts — the deterministic kernel is
   the only source of numbers; L2 grounding is the only source of specifics.
4. Prove the fix with a **real model call** producing the correct answer before
   claiming success (that is the standard the last confident_wrong fix met).
5. Offline suite green: `python -m pytest sealai_v2/ -q`; then a **targeted**
   REPLAY on the touched dimension (see the `eval-replay-adjudication` skill).

## Response contract + output guard

`core/response_contract.py` **builds** the answer contract; `core/output_guard.py`
(`evaluate_render`) **enforces** it — claim-level, fail-closed, regenerating on a
violation (see `pipeline/pipeline.py` ~L646 + the GOVERNANCE log line). It is
flag-gated (`SEALAI_V2_RESPONSE_CONTRACT_GENERAL_GUARD_ENABLED`) and live in prod
(activated 2026-07-03 after a targeted offline eval showed overblock_rate=0.0).
Touched response paths must preserve the contract / guard coverage (Definition of
Done); the eval harness exercises it via `eval/contract_eval.py`,
`eval/calibration.py`, `eval/general_guard_eval.py`. Jinja2 builds prompts +
renders artifacts; it **never decides domain content**.
