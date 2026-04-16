# AGENTS.md — SeaLAI Repository Operating Contract for Codex

Status: Binding  
Audience: Codex CLI / Codex agents / human reviewers  
Scope: Entire repository unless a deeper AGENTS.md overrides a section locally

---

## 1. Purpose

This file is the single working contract for Codex inside the SeaLAI repository.

Codex must use this file to understand:

- what SeaLAI is actually building
- which architecture is binding
- how to work safely in this repo
- how to audit before patching
- how to keep diffs small and evidence-based
- how to avoid drifting back into the wrong domain focus

This file is not marketing copy.
It is an execution contract.

---

## 2. Project mission

SeaLAI is a professional operating system for sealing problems, sealing demand analysis, and technical prequalification.

SeaLAI is **not**:
- a generic chatbot
- a catalog search UI
- a final recommendation engine
- a manufacturer replacement
- a norm autopilot

SeaLAI **is**:
- a structured technical clarification system
- a path-routing and requirement-closing system
- a deterministic engineering-check system
- a provenance-aware cockpit
- a preselection and inquiry-preparation system

Final technical release always remains with the manufacturer.

---

## 3. Binding source of truth

When there is ambiguity, use the following precedence order:

1. `konzept/sealai_ssot_architecture_plan.md`
2. this `AGENTS.md`
3. `konzept/SEALAI_KONZEPT_FINAL`
4. current backend code as implemented truth
5. current frontend code as projection truth
6. older concept documents only if still consistent with the SSoT

If documents conflict:
- do not guess
- state the conflict explicitly
- prefer the SSoT architecture plan
- keep current code as truth of what exists today
- keep SSoT as truth of what must be built

---

## 4. Codex operating mode

Default working style for Codex in this repo:

### 4.1 Read-only first
For any non-trivial task:
- inspect real code first
- inspect real wiring first
- inspect real tests first
- inspect real state ownership first
- report evidence before patching

Do **not** jump directly into code changes for architecture-sensitive work.

### 4.2 Smallest clean patch sequence
After audit:
- propose the smallest patch sequence
- keep each patch narrow
- preserve existing wiring where possible
- avoid repo-wide churn
- avoid speculative rewrites

### 4.3 No “UI solved = problem solved”
Do not treat:
- labels
- cards
- sections
- frontend projections
as evidence that the domain model is actually implemented.

Backend/state truth matters more than frontend appearance.

### 4.4 No silent invention
Do not invent:
- domain rules
- norm logic
- thresholds
- compatibility truth
- support-plan logic
- derived values
without either:
- explicit implementation evidence
- explicit rule definition in the SSoT
- or a clearly marked TODO / extension seam

---

## 5. SeaLAI’s binding architecture model

SeaLAI has two orthogonal routing dimensions:

### 5.1 Request type
- `new_design`
- `retrofit`
- `rca_failure_analysis`
- `validation_check`
- `spare_part_identification`
- `quick_engineering_check`

### 5.2 Engineering path
- `ms_pump`
- `rwdr`
- `static`
- `labyrinth`
- `hyd_pneu`
- `unclear_rotary`

Codex must preserve this distinction.
Do not collapse request type and engineering path into one enum.

---

## 6. Core architectural rule: LLM vs rule engine

This is non-negotiable.

### 6.1 The LLM may:
- normalize user language
- extract candidate structured fields
- identify ambiguities
- propose clarification priorities
- render explanations and bounded summaries

### 6.2 The LLM may NOT:
- set final engineering path
- set confirmed values
- mark RFQ readiness
- perform authoritative deterministic calculations
- finalize norm applicability
- issue final material or product approvals
- simulate manufacturer release

### 6.3 The rule engine must decide:
- request type
- engineering path
- norm module activation
- mandatory fields
- allowed calculations
- risk scores
- readiness
- output class
- downgrade / stale invalidation

If current code violates this separation, report it explicitly.

---

## 7. The required phase model

SeaLAI must operate through these phases:

0. Scope and intent gate  
1. Deterministic path selection  
2. Core intake  
3. Failure drivers  
4. Geometry / fit  
5. RFQ / liability / commercial readiness

Codex must not flatten this into one generic intake flow.

### 7.1 Request-type-sensitive handling
Examples:
- RCA does not immediately become redesign
- Retrofit is not just “new design with old part”
- quick checks may stop early if the requested deterministic calculation is valid with available inputs

### 7.2 Path-sensitive handling
Each engineering path must activate different:
- mandatory fields
- checks
- risk rules
- norm modules
- export semantics

---

## 8. Canonical backend truth

SeaLAI must remain backend-first.

### 8.1 Required canonical shape
The backend must be the authoritative source for:
- request type
- routing path
- core intake
- failure drivers
- geometry/fit
- RFQ/liability
- RCA
- commercial context
- checks
- risk scores
- readiness
- provenance
- norm context
- artifacts

### 8.2 Frontend role
Frontend is a renderer/projection layer.
Frontend may:
- group
- filter
- collapse
- visualize
- trigger actions

Frontend must not:
- independently compute engineering truth
- define mandatory fields
- set readiness
- resolve path conflicts
- override provenance

---

## 9. Provenance is mandatory

Every relevant engineering value must carry provenance.

### 9.1 Allowed origins
- `user_stated`
- `documented`
- `web_hint`
- `calculated`
- `confirmed`
- `missing`

### 9.2 Medium-specific provenance layers
SeaLAI must support:
- `medium.input`
- `medium.context`
- `medium.registry`
- `medium.inferred_properties`
- `medium.confirmed_properties`

### 9.3 Rule
No web-derived or LLM-derived hint may become confirmed engineering truth without an explicit promotion step.

If current code merges these layers implicitly, treat it as a structural problem.

---

## 10. Output classes are controlled, not free-form

Codex must preserve the controlled output model.

Allowed output classes:
- `conversational_answer`
- `structured_clarification`
- `governed_state_update`
- `technical_preselection`
- `rca_hypothesis`
- `candidate_shortlist`
- `inquiry_ready`

### 10.1 Output enforcement
The system must have a backend-side validation layer that checks final text against output-class claim rules.

Prompt-only restrictions are not sufficient.

### 10.2 Red-flag phrases
If output validation is implemented or extended, it must detect and prevent phrases equivalent to:
- “guaranteed”
- “will definitely work”
- “fully approved”
- “norm compliant” without basis
- “no further review required”

---

## 11. State regression and stale invalidation

This is mandatory.

Whenever a critical input changes, SeaLAI must:
- increment revision
- invalidate dependent derived state
- mark affected outputs as stale
- recompute highest valid phase
- reset readiness if required
- queue recomputation for heavy modules

Examples of critical invalidators:
- medium change
- pressure change
- temperature envelope change
- geometry reference change
- motion type change
- equipment type change
- support-system change

The frontend must only display stale/recompute status.
It must never decide stale logic itself.

---

## 12. Chemical compatibility is a real subsystem

Codex must treat chemical compatibility as its own architecture concern.

### 12.1 It cannot be:
- only prompt logic
- only LLM inference
- only generic web search

### 12.2 It must be built around:
- internal compatibility registry
- structured OEM/manufacturer data when available
- SDS/TDS mappings
- fallback hints clearly marked as non-confirmed

### 12.3 Required compatibility dimensions
At minimum:
- medium key
- concentration
- temperature range
- dynamic vs static rating
- material family
- material grade
- limitations / guardrails
- source refs
- registry entry identity
- version/hash for traceability

---

## 13. Norms are modules with gates

SeaLAI must not use norms as floating labels.

Norm modules must be independently activatable with:
- applicability rule
- required fields
- deterministic checks
- escalation logic
- output implications

### 13.1 Required norm modules in target architecture
- `norm_api_682`
- `norm_en_12756`
- `norm_din_3760_iso_6194`
- `norm_iso_3601`
- `norm_vdi_2290`
- `norm_atex`

### 13.2 Important rule
A norm present in docs or ontology is not the same as a norm implemented as executable logic.

Codex must explicitly distinguish:
- reference present
- gate present
- required fields present
- checks present
- escalation present

---

## 14. Calculations and checks must be registry-based and deterministic

SeaLAI’s engineering checks must be explicitly structured.

### 14.1 Minimum checks layer
- circumferential speed
- PV
- flashing / vapor margin
- leakage-related indicators
- friction / heat indicators
- fit risk inputs
- lubrication concern
- corrosion concern
- path-specific readiness checks

### 14.2 Formula discipline
Each calculation must have:
- stable `calc_id`
- explicit required inputs
- valid paths
- output key
- version
- fallback behavior if inputs are missing

Do not allow ad hoc inline formulas to spread across the codebase.

---

## 15. RCA and retrofit are first-class, not secondary

### 15.1 RCA
Codex must preserve or build RCA as a first-class request type with:
- symptom class
- failure timing
- damage pattern
- leakage pattern
- runtime to failure
- likely failure mode clusters
- evidence requests
- recommended inspection steps

### 15.2 RCA handover
RCA may hand over to:
- `retrofit`
- `new_design`
- or remain within RCA if operational/maintenance issue dominates

Handover must preserve:
- transferred fields
- blocked fields
- RCA reference
- reason for transition

### 15.3 Retrofit
Retrofit must support:
- geometry locked
- allowed changes
- old part references
- fixed cavity constraints
- available radial / axial space
- standard vs custom fit judgment

---

## 16. Commercial / supply context is part of final readiness

SeaLAI is not purely technical in the final layer.

Required commercial context must include:
- production mode
- lot size
- lead-time criticality
- standardization goal
- second source requirement
- lifecycle / spare-parts context

Codex must not bury this as optional note-only metadata.
It belongs to readiness and export suitability.

---

## 17. Versioning is mandatory

Every case must track at least:
- `schema_version`
- `ruleset_version`
- `calc_library_version`
- `risk_engine_version`
- `norm_module_versions`
- `case_revision`

### 17.1 Migration rule
Additive schema changes must not silently create broken legacy cases because a newer ruleset suddenly requires a new field.

Old cases must be revalidated explicitly when necessary.

---

## 18. Codex workflow expectations in this repo

For serious work, Codex should follow this sequence:

### Step A — Audit
- inspect real implementation
- inspect current tests
- inspect current wiring
- inspect current docs
- identify actual truth vs target truth

### Step B — Delta report
Return:
- what exists
- what is partial
- what is missing
- what looks integrated but is not
- smallest patch sequence

### Step C — Patch one layer at a time
Preferred order:
1. request type + routing
2. canonical schema / cockpit contract
3. formula library / checks registry
4. risk engine
5. RCA path
6. chemical compatibility
7. transient model
8. retrofit module
9. commercial context
10. norm modules
11. export / RFQ hardening
12. test suite hardening

Do not skip ahead because a later patch “looks more visible”.

---

## 19. Repo-specific discipline

### 19.1 Commands
Always run repo-level commands from:
`/home/thorsten/sealai`

Do not assume subdirectory-local execution unless explicitly needed.

### 19.2 Minimal diffs
Prefer:
- extension seams
- local refactors
- adapter layers
- explicit rule modules

Avoid:
- broad rewrites
- renaming cascades
- rewriting stable infrastructure just to “clean things up”

### 19.3 Evidence-based reporting
When auditing or patch-planning, always provide:
- exact file path
- exact functions/classes/modules
- concise evidence
- what is true today vs what must change

### 19.4 No architecture drift back to RWDR-first
The binding target focus is:
- a general architecture
- with MVP depth centered on `ms_pump`
- not accidental dominance by historical RWDR logic

If current code is RWDR-first, report it and isolate it rather than allowing it to define the target architecture.

---

## 20. Final operating rule

Codex must optimize for:
- technical truth
- provenance
- deterministic boundaries
- auditability
- smallest correct patch path

Codex must not optimize for:
- superficial UI completeness
- broad speculative abstractions
- hidden assumptions
- free-form “AI convenience” over engineering safety

If in doubt:
- ask less from the user at once
- preserve uncertainty
- downgrade readiness
- mark state stale
- prefer explicit blockers over optimistic assumptions
