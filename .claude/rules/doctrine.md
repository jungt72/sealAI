# Doctrine (hard lines)

The product doctrine — what SealAI may and may not claim — lives in **`AGENTS.md`
§ Safety Boundaries** and **`CLAUDE.md` § Safety language**. Those are the source
of truth. This file does **not** restate them; it records how they are *enforced*
and the lines that must never be crossed while changing code.

## Source of truth
- Claim boundaries (no final release, no guaranteed suitability, no manufacturer
  approval without evidence, no compliance/certification without licensed rule,
  no product/compound claim from material-family evidence, no stale calc as
  proof): **AGENTS.md § Safety Boundaries**. Read it; do not paraphrase it here.
- Allowed wording stays scoped: screening, orientation, current evidence,
  calculated value, open point, review required, manufacturer review basis.

## Two-layer output enforcement (the mechanism)
- **L1** `backend/app/agent/runtime/output_guard.py::check_fast_path_output` — the
  live streaming enforcer. Categories: manufacturer, recommendation, suitability,
  comparative-ranking, compliance-overclaim, form-dump.
- **L2** `backend/app/agent/v92/final_guard.py::validate_final_output` — the
  knowledge-turn / non-technical backstop. Shares the comparative-ranking denylist
  with L1 via `comparative_ranking_patterns()` (single source of truth).
- Both layers now **enforce** (substitute the safe fallback on block) on the
  streamed (F1) and non-technical (F2) knowledge paths. See
  `docs/runtime-audit-fixmap.md`.

## Hard lines (never cross)
- **Never weaken a guard, lexicon, or doctrine test to make something pass.** If a
  test only goes green by loosening what blocks → **HALT to human**, do not edit.
- Changing *what* blocks (L1/L2 lexicon, denylist) is a doctrine change → plan +
  zero-FP proof against the `material_comparison.py` corpus + existing negatives +
  golden, and surface it. Changing only *that a block is enforced* is mechanics.
- The four original comparative-ranking repros must always block at L1:
  "EPDM könnte optimal sein", "PTFE ist NBR überlegen", "PTFE übertrifft NBR",
  "EPDM ist optimal für diese Anwendung". A change that lets any of them through
  is a regression, not a feature.
- AC8: legitimate, thorough knowledge answers + property statements + the
  deterministic comparison render must keep streaming (no over-block).
- AC9: knowledge-without-concrete-facts must not create or mutate `CaseState`.
- The comparative-ranking denylist is a *leaky backstop*; the prompt (#1) and the
  deterministic passthrough (#4) stay primary. Do not treat the denylist as the
  whole defense.

## V2 doctrine mechanism (`backend/sealai_v2/` — green-field, not cut over)

> Applies to the V2 tree only. The V1 L1/L2 enforcement above (`output_guard.py` /
> `final_guard.py`) is unchanged and stays the live V1 mechanism. The claim
> boundaries themselves (AGENTS.md § Safety Boundaries) are the same source of truth
> for both worlds. Full V2 doctrine: `AGENTS.md § "V2.0 green-field track"`.

- **V2 does NOT use the V1 `output_guard.py` / `final_guard.py` layers.** Its
  honesty/grounding/verification spine is the **four-layer trust model**:
  1. **L1 honesty norms** in the system prompt (`prompts/system_l1.jinja`) — *primary*:
     ranges not false precision, no invented numbers/compound-numbers, no life-number,
     orientation ≠ release, mark "Allgemeinwissen — verifizieren".
  2. **L2 grounding/provenance** — specifics carried by curated facts with sources.
  3. **L3 verifier** (`core/l3_verifier.py`) — critic pass vs. the **trap catalog**;
     a correction's replacement fact comes **only** from a `reviewed` entry, else a
     deterministic **hedge** — L3 never invents its own source of truth. The integrity rule
     guarantees **provenance** (reviewed-sourced), **not topical fit**: a reviewed trap's `correct`
     is split into a topic-agnostic `correct_general` (always injected) + a topic-scoped
     `correct_recommendation` (injected only when the question matches the trap's `applies_to`), so an
     off-topic trap firing never mis-directs with a wrong-topic material recommendation
     (OPTIMIZE_BACKLOG #5). The general assertion always carries — the catch stays intact.
  4. **L4 human/manufacturer** — final validation; and the **eval hard Schranken**
     (no entered trap, no confident-false, no invented precision → **100 %**) measure it.
- **The hard lines extend to V2.** Never weaken a guard, catalog, or eval test to make
  something pass → **HALT to human**. Changing what `reviewed` catalog entries assert is
  a doctrine change (owner-grounded, never model-sourced). **The human is the
  factual-correctness oracle** — the agent never self-adjudicates eval verdicts.

## V2.1 calibration (forward — `docs/V2/sealingai_v2_1_*`)

> Additive to the four-layer model above — not a replacement. Tunes *how assertively* V2 claims,
> on the same "backend owns facts, LLM narrates" base. Canonical: Produkt-Konzept §3 / §9.

- **Confident-correct is the default**, *as assertive as the grounding*; the hedge is the **rare
  marked edge**, never the fallback — the user always gets a material.
- **Safety-critical / unsure → "stop, confirm"** (the SAFETY clause is never gated away).
- **Norms grounded, never recited** — number/revision/value only from a reviewed source; honest
  where the current revision is unsure.
- **Equivalence is the sharpest edge** — "part X = part Y" only grounded, honest over the boundary
  (nominal size + material class, not compound); L4 carries real weight.
- **Neutrality is sacred — no pay-to-rank** (capability only).
- **Uniform Trust-Spine:** L3 must be able to verify norm- and equivalence-claims, not only
  material recommendations.
