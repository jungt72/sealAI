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
