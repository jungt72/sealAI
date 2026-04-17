@AGENTS.md

# CLAUDE.md — SeaLAI Project Instructions for Claude Code
**Version:** 3.0
**Datum:** 2026-04-17
**Status:** Binding Claude Code project memory
**Purpose:** Claude-specific execution rules for working safely inside the SeaLAI repository

> This file extends `AGENTS.md` for Claude Code.
> If there is any conflict, precedence is:
> 1. `konzept/sealai_ssot_architecture_plan.md` (base SSoT)
> 2. `konzept/sealai_ssot_supplement_v1.md` (LangGraph role, consistency, schema layering, persistence)
> 3. `konzept/sealai_ssot_supplement_v2.md` (positioning, moat, MVP scope, terminology, capability, business logic)
> 4. `konzept/sealai_engineering_depth_ptfe_rwdr.md` (binding for all PTFE-RWDR engineering decisions)
> 5. `AGENTS.md`
> 6. this `CLAUDE.md`
>
> Where supplements conflict with the base SSoT on the same topic, the supplement wins because it is newer and addresses gaps identified during architectural review.
> Where the engineering depth guide conflicts with any SSoT document on PTFE-RWDR fields, the depth guide wins for PTFE-RWDR fields only.

---

## 1. What Claude Code must do first

For any non-trivial task, Claude must begin with a read-only understanding phase.

Before changing code, Claude must:
- inspect the real implementation
- inspect the current wiring
- inspect the relevant tests
- inspect the relevant docs
- compare current code against the SSoT and both supplements
- identify the smallest clean patch sequence

Do not jump directly into implementation for architectural work.

---

## 2. Required source-of-truth reading order

Before any architectural, backend, routing, state, cockpit, readiness, export, or domain task, Claude must read in this order:

1. `konzept/sealai_ssot_architecture_plan.md`
2. `konzept/sealai_ssot_supplement_v1.md`
3. `konzept/sealai_ssot_supplement_v2.md`
4. `konzept/sealai_engineering_depth_ptfe_rwdr.md`
5. `AGENTS.md` (already imported here)
6. `konzept/SEALAI_KONZEPT_FINAL.md`
7. `konzept/SEALAI_STACK_ARCHITEKTUR.md`

### Rule
- The base SSoT `sealai_ssot_architecture_plan.md` is the architectural foundation.
- Supplement v1 (chapters 33–36) adds LangGraph orchestration role, consistency model, four-layer schema separation, and persistence model.
- Supplement v2 (chapters 37–43) adds positioning, moat, MVP scope boundary, terminology mapping registry, manufacturer capability model, and business logic constraints.
- The engineering depth guide is binding for PTFE-RWDR engineering decisions (schema fields, risk thresholds, failure-mode taxonomy, check calculations).
- `SEALAI_KONZEPT_FINAL.md` is product/business context (subordinate to technical SSoT).
- `SEALAI_STACK_ARCHITEKTUR.md` is runtime/infrastructure reference only.
- If any older implementation detail conflicts with the current SSoT set, the SSoT set wins.

### Conflict handling
Where documents disagree on a specific rule:
- Newer supplement > older supplement > base SSoT (on the same topic)
- Engineering depth guide > any SSoT document (for PTFE-RWDR-specific fields only)
- Technical SSoT > product concept > runtime/infra reference (across categories)

Claude must NOT silently reinterpret. If a conflict is unclear, report it explicitly and ask before patching.

---

## 3. Claude execution mode

### 3.1 Default behavior
For multi-file or architecture-sensitive work, Claude must behave as if Plan Mode is required first.

That means:
- audit first
- explain current state against the full authority set
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
- terminology registry changes
- manufacturer capability model changes
- business-logic / monetization changes

### 3.3 Do not skip directly to edits when
- multiple layers are affected
- the task touches backend + frontend
- the task changes architecture or contracts
- the task changes canonical truth
- the task touches the moat layers defined in supplement v2 §37

---

## 4. SeaLAI-specific architectural guardrails

Claude must preserve these truths:

### 4.1 Product shape
- SeaLAI has two orthogonal dimensions: `request_type` and `engineering_path`
- **MVP depth is centered on PTFE-based radial shaft seals (`engineering_path = rwdr` + `sealing_material_family ∈ ptfe_*`)**, per supplement v2 §39
- Other paths and material families exist structurally in the schema, but must not be falsely presented as equally deep
- The MVP is narrow in depth and wide in structure: the data model accepts all RWDR variants as first-class, but full engineering fidelity is PTFE-RWDR-only in Phase 1

### 4.2 Technical invariants
- Backend is the source of truth
- Frontend is a projection layer
- LLM normalizes, extracts, proposes, prioritizes, summarizes, renders — nothing else (base SSoT §8.1)
- Deterministic rules decide routing, mandatory fields, checks, readiness, and output class (base SSoT §8.3)
- No final manufacturer approval may be simulated
- No unconfirmed medium or web hint may be treated as confirmed engineering truth

### 4.3 Moat invariants (supplement v2 §37)
Every feature, contract, or UI decision must preserve:
- **Layer 1 — Structural neutrality**: no manufacturer influence on ranking outside declared sponsored zones; all sponsored content is explicitly labeled at every surface
- **Layer 2 — Technical translation**: matching operates on structured concepts and capability claims, never on marketing text or free-text similarity
- **Layer 3 — Request qualification**: cases reaching manufacturers are structured, parameterized inquiry packages with explicit open-points and assumptions

If a proposed change weakens any moat layer, it must justify the trade-off explicitly. If no justification is credible, the change is rejected.

---

## 5. Claude must not reintroduce old drift

### 5.1 Obsolete architectural patterns
Do not reintroduce:
- old "Phase F / G / H" implementation logic as binding truth (superseded by the current SSoT set)
- legacy naming such as `governed_recommendation`
- the ms_pump-centered MVP framing (superseded by PTFE-RWDR MVP in supplement v2)
- the binary `CONVERSATION / GOVERNED` gate without the intermediate EXPLORATION mode where it already exists
- output wording that sounds like final approval
- frontend-only engineering truth
- hidden assumptions when data is incomplete
- parallel orchestration stacks (`fast_brain` vs `agent/graph`) without explicit reconciliation per supplement v1 §33.10

### 5.2 Anti-patterns (supplement v2 §38)
Do not introduce or reintroduce:
- pay-for-ranking in matching
- artificial manufacturer supply (scraping without consent)
- hidden manufacturer priority (including for the founder's employer)
- manufacturer-specific advertising to users
- LLM-derived engineering authority (compatibility, risk thresholds, norm applicability)
- marketing-text matching or regex-on-description matching
- silent terminology fallthrough
- founder-employer matching bonus
- monetization tied to specific product categories

### 5.3 Legacy code
If current code still reflects historical patterns (RWDR-first implementation traces, `_legacy_v2`, `fast_brain` duplicates, Phase-F-era `interaction_policy.py`, etc.), report it explicitly and isolate it instead of expanding it.

Note: RWDR (specifically PTFE-RWDR) is now the MVP focus. This is NOT the old "RWDR-first domain bias" — the old bias was structural lopsidedness; the current setup is a deliberate narrow-depth/wide-structure MVP with explicit Phase 2+ expansion paths. Claude must distinguish between these.

---

## 6. Output discipline

Claude must preserve the bounded output model.

Allowed output classes are defined by the SSoT (base §24) and AGENTS.

Claude must not produce implementation or prompt changes that allow:
- "guaranteed"
- "definitely works"
- "fully approved"
- "norm compliant" without basis
- final approval claims
- hidden confidence inflation
- "objectively best match" / "unbiased recommendation" language when the matching basis is not documented and auditable

If in doubt, downgrade the output class instead of overclaiming.

---

## 7. State, stale invalidation, and regression

Claude must treat state invalidation as a first-class architectural concern (base SSoT §11, supplement v1 §34).

If a change affects:
- medium
- pressure
- temperature
- geometry reference
- motion type
- equipment type
- support-system context
- compliance context
- sealing_material_family
- ptfe_compound details (for PTFE-RWDR cases)
- shaft surface / finish / lead / hardness

then Claude must assume:
- dependent derived values can become stale
- readiness may need downgrade
- inquiry state may need invalidation
- recompute may be required
- affected risk scores must be recomputed per supplement v1 §34

Do not implement optimistic persistence of outdated derived values.

Mutation events are first-class (supplement v1 §34.3–34.4). Every case change flows through `case_service.apply_mutation()` with optimistic locking on `case_revision`. LangGraph nodes do NOT write directly to Postgres (supplement v1 §33.4).

---

## 8. Implementation style

Claude must prefer:
- smallest clean patch
- explicit contracts
- deterministic modules
- adapter seams over large rewrites
- versioned and testable logic
- evidence-based change reports
- services under `backend/app/services/` that are testable without LangGraph imports (supplement v1 §33.8)
- four-layer schema separation: domain / models / schemas / agent-state (supplement v1 §35)

Claude must avoid:
- repo-wide speculative rewrites
- mixing documentation cleanup with domain refactors in one patch
- changing architecture and UI semantics together without a clean contract
- duplicating rules that already live in the SSoT set or AGENTS
- business logic inside LangGraph nodes (supplement v1 §33.4)
- upward imports across the schema layers (supplement v1 §35.8)

---

## 9. Validation expectations

All commands must be run from:

`/home/thorsten/sealai`

Before concluding a task, Claude must:
- run the relevant tests for touched areas
- run build/type/lint checks where relevant
- verify no upward import violations (supplement v1 §35.8)
- verify services touched by the change don't import LangGraph (supplement v1 §33.8)
- verify moat invariants where applicable (supplement v2 §37.3)
- report what was actually executed
- clearly separate:
  - pre-existing failures
  - newly introduced failures
  - validated success paths

Claude must not claim "done" without explicit validation evidence.

---

## 10. Documentation discipline

Claude must not create competing truths.

Document responsibilities:
- **Base SSoT** (`sealai_ssot_architecture_plan.md`) = architectural foundation
- **Supplement v1** = technical implementation pillars (LangGraph role, consistency, schema layering, persistence)
- **Supplement v2** = positioning, moat, MVP scope, terminology, capability, business logic
- **Engineering depth guide (PTFE-RWDR)** = fact-dense engineering reference for MVP depth
- **AGENTS.md** = working contract for Codex and similar agents
- **CLAUDE.md** (this file) = Claude-specific execution rules
- **KONZEPT_FINAL** = product/business concept (narrative, subordinate)
- **STACK_ARCHITEKTUR** = infrastructure/runtime reference

If documentation changes are needed:
- update the smallest correct document
- do not duplicate architecture across files
- if a new engineering path reaches production depth, add a dedicated engineering depth guide (parallel to the PTFE-RWDR one)
- if a task reveals contradictions between authority documents, report them explicitly before patching

---

## 11. Preferred Claude workflow in this repo

Use this sequence:

1. Read the relevant authority documents (see §2) in the prescribed order
2. Inspect relevant code
3. Inspect tests and contracts
4. Produce delta report against the full authority set
5. Verify moat invariants for any user-facing or matching change
6. Propose smallest patch sequence
7. Implement one patch at a time
8. Validate
9. Report exact evidence

Do not combine architecture redesign, code migration, and broad cleanup in one uncontrolled step.

---

## 12. MVP scope awareness

Claude must actively maintain awareness of the MVP scope boundary (supplement v2 §39):

### 12.1 Deep (full engineering fidelity)
- `engineering_path = rwdr` with `sealing_material_family ∈ ptfe_*`

### 12.2 Shallow (structural support, flat depth)
- `engineering_path = rwdr` with `sealing_material_family ∈ elastomer_*` or `unknown`
- All other engineering paths (`ms_pump`, `static`, `hyd_pneu`, `labyrinth`, `unclear_rotary`)

### 12.3 Implications for Claude
- Features targeting deep scope may require full SSoT fidelity (all fields, all checks, all risk dimensions)
- Features targeting shallow scope should be structurally complete but may use simplified risk scoring and basic capability matching
- User-facing messages distinguishing depth levels use the verbatim strings in supplement v2 §39.7
- Golden cases must cover both deep and shallow examples per supplement v2 §39.8

---

## 13. Conflict-of-interest awareness

The founder is employed at a PTFE-RWDR manufacturer (supplement v2 §38.6). This creates binding constraints:

- The founder's employer, if listed as a manufacturer, receives exactly the same treatment as any other manufacturer — same onboarding, same fees, same matching algorithm
- No configuration flag, no dataset tuning, no algorithmic exception may introduce bonuses or demotions for the employer
- Data firewall: no employer-proprietary data enters SeaLAI code or datasets
- The COI relationship is publicly disclosed (founder bio, employer profile if listed)

Any code change that could plausibly introduce asymmetric treatment of the founder's employer must be flagged explicitly in the change report.

---

## 14. Final rule

When uncertain, Claude must choose:
- more explicit blockers
- more conservative readiness
- more traceability
- more deterministic structure
- less architectural drift
- less output overclaiming
- more moat-preserving defaults
- more transparent sponsorship labeling
- more honest depth-level acknowledgment ("shallow" instead of pretending deep)

Where uncertainty remains after consulting all authority documents, ask before patching. Silent reinterpretation of ambiguous rules is the most dangerous failure mode and must be avoided.

