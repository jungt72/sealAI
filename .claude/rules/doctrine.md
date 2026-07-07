# Doctrine (hard lines)

The product doctrine — what sealAI may and may not claim — lives in **`AGENTS.md`
§ Safety Boundaries** and the **sealingAI Leitbild V3** (also in `AGENTS.md`), with
`CLAUDE.md § Safety language` as the Claude-facing restatement. Those are the
source of truth. This file does **not** restate them; it records how they are
*enforced* in the V2 runtime and the lines that must never be crossed while
changing code.

## Source of truth
- Claim boundaries (no final release, no guaranteed suitability, no manufacturer
  approval without evidence, no compliance/certification without licensed rule,
  no product/compound claim from material-family evidence, no stale calc as
  proof): **AGENTS.md § Safety Boundaries**. Read it; do not paraphrase it here.
- Allowed wording stays scoped: screening, orientation, current evidence,
  calculated value, open point, review required, manufacturer review basis.

## The enforcement mechanism (V2 four-layer trust model)

The single production backend is `backend/sealai_v2/`. Halluzination-resistance
comes from four layers carrying **together**, not from control-determinism — the
concrete implementation of Leitsätze L1/L2. Full model: `AGENTS.md § Four-layer
trust model`.

1. **L1 honesty norms** in the system prompt (`prompts/system_l1.jinja`) —
   *primary*: ranges not false precision, no invented numbers/compound-numbers, no
   life-number, orientation ≠ release, mark "Allgemeinwissen — verifizieren".
2. **L2 grounding/provenance** — specifics (numbers, norms, compatibility) carried
   by curated Fachkarten + matrix + Qdrant retrieval, **with sources**. Never
   control logic.
3. **L3 verifier** (`core/l3_verifier.py`, `prompts/verifier_l3.jinja`) — critic
   pass vs. the **trap catalog** (`knowledge/traps.py`, `trap_catalog.json`) +
   matrix. A correction's replacement fact comes **only** from a `reviewed` entry,
   else a deterministic **hedge** — L3 never invents its own source of truth. The
   integrity rule guarantees **provenance** (reviewed-sourced), **not topical
   fit**: a reviewed trap's `correct` is split into a topic-agnostic
   `correct_general` (always injected) + a topic-scoped `correct_recommendation`
   (injected only when the question matches the trap's `applies_to`), so an
   off-topic trap firing never mis-directs with a wrong-topic recommendation. The
   general assertion always carries — the catch stays intact.
4. **L4 human/manufacturer** — final validation; and the **eval hard Schranken**
   measure it. The authoritative gated set is `ops/v2_deploy_gate.py`'s `GATED`
   columns — the seed-v0 trio (no entered trap, no confident-false, no invented
   precision) **plus** the memory, exfiltration, and parametric
   (multiturn/singleturn) Schranken-quotas — every gated column at
   `schranken_quota_final == 1.0`.

`core/response_contract.py` **builds** the answer contract; `core/output_guard.py`
(`evaluate_render`) **enforces** it — claim-level, fail-closed, regenerating on a
violation (wired in `pipeline/pipeline.py`). It is flag-gated
(`SEALAI_V2_RESPONSE_CONTRACT_GENERAL_GUARD_ENABLED`) and **live in prod**
(activated 2026-07-03). Touched response paths must preserve the contract / guard
coverage.

## Hard lines (never cross)
- **Never weaken a guard, catalog, or eval test to make something pass.** If a
  test only goes green by loosening what blocks → **HALT to human**, do not edit.
- Changing what a `reviewed` catalog/Fachkarte entry asserts is a **doctrine
  change** — owner-grounded, never model-sourced. `drafts` are model-proposed and
  flag-only; they surface, they never correct.
- **The human is the factual-correctness oracle** — the agent never
  self-adjudicates eval verdicts and never free-corrects a factual verdict.
- The deterministic kernel is the only source of numbers; the LLM never invents a
  value, norm, or compound fact.

## V2.1 calibration (forward — `docs/V2/sealingai_v2_1_*`)

Additive to the four-layer model above — not a replacement. Tunes *how assertively*
V2 claims, on the same "backend owns facts, LLM narrates" base. Canonical:
Produkt-Konzept §3 / §9.

- **Confident-correct is the default**, *as assertive as the grounding*; the hedge
  is the **rare marked edge**, never the fallback — the user always gets a
  material.
- **Safety-critical / unsure → "stop, confirm"** (the SAFETY clause is never gated
  away).
- **Norms grounded, never recited** — number/revision/value only from a reviewed
  source; honest where the current revision is unsure.
- **Equivalence is the sharpest edge** — "part X = part Y" only grounded, honest
  over the boundary (nominal size + material class, not compound); L4 carries real
  weight.
- **Neutrality is sacred — no pay-to-rank** (capability only).
- **Uniform Trust-Spine:** L3 must be able to verify norm- and equivalence-claims,
  not only material recommendations.

## Retired (historical only)

The former V1 `backend/app/` LangGraph runtime enforced doctrine with a two-layer
output guard (`backend/app/agent/runtime/output_guard.py` +
`backend/app/agent/v92/final_guard.py`). That runtime was **retired 2026-06-28**;
those layers are **not** live and are not the V2 mechanism. Do not look for them,
resurrect them, or build against them. The claim boundaries themselves
(AGENTS.md § Safety Boundaries) are unchanged and bind both the retired and current
worlds.
