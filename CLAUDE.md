@AGENTS.md

# CLAUDE.md — SeaLAI Project Instructions for Claude Code
**Version:** 2.0  
**Datum:** 2026-04-16  
**Status:** Binding Claude Code project memory  
**Purpose:** Claude-specific execution rules for working safely inside the SeaLAI repository

> This file extends `AGENTS.md` for Claude Code.
> If there is any conflict:
> 1. `konzept/sealai_ssot_architecture_plan.md`
> 2. `AGENTS.md`
> 3. this `CLAUDE.md`

---

## 1. What Claude Code must do first

For any non-trivial task, Claude must begin with a read-only understanding phase.

Before changing code, Claude must:
- inspect the real implementation
- inspect the current wiring
- inspect the relevant tests
- inspect the relevant docs
- compare current code against the SSoT
- identify the smallest clean patch sequence

Do not jump directly into implementation for architectural work.

---

## 2. Required source-of-truth reading order

Before any architectural, backend, routing, state, cockpit, readiness, export, or domain task, Claude must read in this order:

1. `konzept/sealai_ssot_architecture_plan.md`
2. `AGENTS.md` (already imported here)
3. `konzept/SEALAI_KONZEPT_FINAL.md`
4. `konzept/SEALAI_STACK_ARCHITEKTUR.md`

### Rule
- `sealai_ssot_architecture_plan.md` is the only binding architecture SSoT.
- `SEALAI_KONZEPT_FINAL.md` is product/business context.
- `SEALAI_STACK_ARCHITEKTUR.md` is runtime/infrastructure reference only.
- If any older implementation detail conflicts with the SSoT, the SSoT wins.

---

## 3. Claude execution mode

### 3.1 Default behavior
For multi-file or architecture-sensitive work, Claude must behave as if Plan Mode is required first.

That means:
- audit first
- explain current state
- propose patch sequence
- only then implement

### 3.2 Use Plan Mode for
- routing changes
- request type changes
- engineering path changes
- state model changes
- readiness / output-class / risk-engine work
- medium / compatibility / RCA / retrofit work
- API contract changes
- cockpit projection changes
- export / inquiry / PDF pipeline changes

### 3.3 Do not skip directly to edits when
- multiple layers are affected
- the task touches backend + frontend
- the task changes architecture or contracts
- the task changes canonical truth

---

## 4. SeaLAI-specific architectural guardrails

Claude must preserve these truths:

- SeaLAI has two orthogonal dimensions:
  - `request_type`
  - `engineering_path`
- MVP depth is centered on `ms_pump`
- other paths may exist structurally, but must not be falsely presented as equally deep
- backend is the source of truth
- frontend is a projection layer
- LLM helps parse, clarify, and render
- deterministic rules decide routing, mandatory fields, checks, readiness, and output class
- no final manufacturer approval may be simulated
- no unconfirmed medium or web hint may be treated as confirmed engineering truth

---

## 5. Claude must not reintroduce old drift

Do not reintroduce:
- RWDR-first domain bias as the default architecture
- old “Phase F / G / H” implementation logic as binding truth
- legacy naming such as `governed_recommendation`
- output wording that sounds like final approval
- frontend-only engineering truth
- hidden assumptions when data is incomplete

If current code still reflects historical RWDR-first implementation, report it explicitly and isolate it instead of expanding it.

---

## 6. Output discipline

Claude must preserve the bounded output model.

Allowed output classes are defined by the SSoT and AGENTS.
Claude must not produce implementation or prompt changes that allow:
- “guaranteed”
- “definitely works”
- “fully approved”
- “norm compliant” without basis
- final approval claims
- hidden confidence inflation

If in doubt, downgrade the output class instead of overclaiming.

---

## 7. State, stale invalidation, and regression

Claude must treat state invalidation as a first-class architectural concern.

If a change affects:
- medium
- pressure
- temperature
- geometry reference
- motion type
- equipment type
- support-system context
- compliance context

then Claude must assume:
- dependent derived values can become stale
- readiness may need downgrade
- inquiry state may need invalidation
- recompute may be required

Do not implement optimistic persistence of outdated derived values.

---

## 8. Implementation style

Claude must prefer:
- smallest clean patch
- explicit contracts
- deterministic modules
- adapter seams over large rewrites
- versioned and testable logic
- evidence-based change reports

Claude must avoid:
- repo-wide speculative rewrites
- mixing documentation cleanup with domain refactors in one patch
- changing architecture and UI semantics together without a clean contract
- duplicating rules that already live in SSoT or AGENTS

---

## 9. Validation expectations

All commands must be run from:

`/home/thorsten/sealai`

Before concluding a task, Claude must:
- run the relevant tests for touched areas
- run build/type/lint checks where relevant
- report what was actually executed
- clearly separate:
  - pre-existing failures
  - newly introduced failures
  - validated success paths

Claude must not claim “done” without explicit validation evidence.

---

## 10. Documentation discipline

Claude must not create competing truths.

If documentation changes are needed:
- update the smallest correct document
- do not duplicate architecture into multiple files
- keep:
  - SSoT = architecture truth
  - AGENTS = working contract
  - CLAUDE = Claude-specific execution rules
  - KONZEPT_FINAL = product/business concept
  - STACK_ARCHITEKTUR = infra/runtime reference

If a task reveals contradictions, report them explicitly before patching.

---

## 11. Preferred Claude workflow in this repo

Use this sequence:

1. Read relevant docs
2. Inspect relevant code
3. Inspect tests and contracts
4. Produce delta report
5. Propose smallest patch sequence
6. Implement one patch at a time
7. Validate
8. Report exact evidence

Do not combine architecture redesign, code migration, and broad cleanup in one uncontrolled step.

---

## 12. Final rule

When uncertain, Claude must choose:
- more explicit blockers
- more conservative readiness
- more traceability
- more deterministic structure
- less architectural drift
- less output overclaiming
