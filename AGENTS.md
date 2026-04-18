# AGENTS.md — SeaLAI Repository Operating Contract for Codex

**Version:** 3.0
**Datum:** 2026-04-18
**Status:** Binding
**Audience:** Codex CLI / Codex agents / human reviewers
**Scope:** Entire repository unless a deeper AGENTS.md overrides a section locally

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

This file is not marketing copy. It is an execution contract.

---

## 2. Project mission

SeaLAI is a neutral technical translation and qualification platform for the sealing technology industry. It connects users with the sealing problem and manufacturers with the technical capability, without acting as a catalog, marketing funnel, or price aggregator.

SeaLAI is **not**:
- a generic chatbot
- a catalog search UI
- a final recommendation engine
- a manufacturer replacement
- a norm autopilot
- a price comparison platform (in MVP; future evolution is out of scope for current sprints)

SeaLAI **is**:
- a structured technical clarification system that understands before it advises
- a path-routing and requirement-closing system with explicit Pre-Gate classification
- a deterministic engineering-check system with cascading calculations
- a provenance-aware cockpit for users, manufacturers, and SeaLAI analytics
- a preselection and inquiry-preparation system that produces structured inquiry packages
- a consultative platform that teaches while qualifying (Product North Star §3.3)

Final technical release always remains with the manufacturer.

---

## 3. Binding source of truth

**Precedence order (highest to lowest):**

1. `konzept/sealai_product_north_star.md` — product truths, user/manufacturer value, non-negotiables
2. `konzept/sealai_ssot_architecture_plan.md` — architectural foundation (base SSoT)
3. `konzept/sealai_ssot_supplement_v1.md` — LangGraph role, consistency, schema layering, persistence (Ch. 33-36)
4. `konzept/sealai_ssot_supplement_v2.md` — positioning, moat, MVP scope, terminology, capability, business logic (Ch. 37-43)
5. `konzept/sealai_ssot_supplement_v3.md` — Product North Star operationalization: Fast Responder, Problem-First Matching, Application Patterns, Small-Quantity, Advisory, Cascading Calculations, Medium Intelligence, Educational Contract, Multimodal Input, Knowledge Bridge (Ch. 44-53)
6. `konzept/sealai_engineering_depth_ptfe_rwdr.md` — PTFE-RWDR engineering depth (binding for MVP depth fields)
7. `konzept/founder_decisions_phase_1a.md` — 8 implementation decisions + Selective Rewrite transition strategy
8. `audits/phase_1a_implementation_plan_2026-04-18.md` — binding sprint-level execution contract
9. this `AGENTS.md`
10. `konzept/SEALAI_KONZEPT_FINAL.md` — product/business narrative (subordinate)
11. `konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md` — communication target image (subordinate, may be stale)
12. `konzept/SEALAI_STACK_ARCHITEKTUR.md` — runtime/infrastructure reference only
13. current backend code as implemented truth
14. current frontend code as projection truth

**Conflict handling:**
- Product North Star > any technical document (for product-purpose questions)
- Newer supplement > older supplement > base SSoT (on the same topic)
- Supplement v3 is binding technical operationalization of the Product North Star
- Engineering depth guide > any SSoT document on PTFE-RWDR-specific fields
- Implementation Plan specifies which patches run in which sprint; it must not be deviated from silently
- If documents conflict, state the conflict explicitly and ask — do not guess

**Current code vs. target:** Keep current code as truth of what exists today. Keep Authority set as truth of what must be built. The delta between them is what Phase 1a sprints address.

---

## 4. Codex operating mode

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
- preserve existing wiring where possible in strangler zones
- construct new foundations greenfield where the Implementation Plan requires
- avoid repo-wide churn
- avoid speculative rewrites beyond the current sprint's scope

### 4.3 Sprint boundary respect
Codex MUST NOT work ahead into future sprints. If a current-sprint patch tempts a fix that would properly belong to a later sprint (e.g., "while I'm here, let me also refactor X"), that temptation is refused. The Implementation Plan's sprint boundaries are binding.

### 4.4 No "UI solved = problem solved"
Do not treat labels, cards, sections, or frontend projections as evidence that the domain model is actually implemented. Backend/state truth matters more than frontend appearance.

### 4.5 No silent invention
Do not invent domain rules, norm logic, thresholds, compatibility truth, support-plan logic, or derived values without either:
- explicit implementation evidence
- explicit rule definition in the Authority set
- or a clearly marked TODO / extension seam

### 4.6 Tests green before merge — always
No patch merges with failing tests. If a patch causes a test failure, the test must be fixed (if the test was wrong) or the patch must be fixed (if the code was wrong) before merge. "Fix later" is not an option.

---

## 5. SeaLAI's binding architecture model

SeaLAI has two orthogonal domain dimensions plus a runtime classification layer.

### 5.1 Domain dimensions

**Request type** (per AGENTS §5.1 in Base SSoT):
- `new_design`
- `retrofit`
- `rca_failure_analysis` (MVP: recognized but degraded per Founder Decision #4)
- `validation_check`
- `spare_part_identification`
- `quick_engineering_check`

**Engineering path** (per AGENTS §5.1 in Base SSoT):
- `ms_pump`
- `rwdr`
- `static`
- `labyrinth`
- `hyd_pneu`
- `unclear_rotary`

### 5.2 Sealing material family (per Supplement v2 §39)

Each case carries `sealing_material_family`:
- `ptfe_virgin`, `ptfe_glass_filled`, `ptfe_carbon_filled`, `ptfe_bronze_filled`, `ptfe_mos2_filled`, `ptfe_graphite_filled`, `ptfe_peek_filled`, `ptfe_mixed_filled`
- `elastomer_nbr`, `elastomer_fkm`, `elastomer_epdm`, `elastomer_hnbr`, `elastomer_ffkm`, `elastomer_silicone`
- `unknown`

### 5.3 Runtime classification (per Supplement v3 §44, Founder Decision #5)

**Pre-Gate Classification** (5 values — replaces legacy `RoutingPath`):
- `GREETING` — Fast Responder path
- `META_QUESTION` — Fast Responder path
- `KNOWLEDGE_QUERY` — Knowledge Service path (no case creation)
- `BLOCKED` — Fast Responder path
- `DOMAIN_INQUIRY` — Full graph pipeline, case creation

**Three-Mode Gate** (within DOMAIN_INQUIRY, preserved as-is):
- `CONVERSATION`
- `EXPLORATION`
- `GOVERNED`

Codex MUST preserve this layered classification. Do NOT collapse Pre-Gate and Gate Mode. Do NOT reintroduce `RoutingPath` or `ResultForm` (both removed per Founder Decision #5).

### 5.4 MVP depth boundary

**Deep (full engineering fidelity):**
- `engineering_path = rwdr` with `sealing_material_family ∈ ptfe_*`

**Shallow (structural support, flat depth):**
- `engineering_path = rwdr` with non-PTFE sealing_material_family
- All other engineering paths

The MVP is narrow in depth and wide in structure. PTFE-RWDR is the exclusive Phase 1a deep-fidelity domain.

---

## 6. Core architectural rule: LLM vs rule engine

This is non-negotiable.

### 6.1 The LLM may:
- normalize user language
- extract candidate structured fields
- identify ambiguities
- propose clarification priorities
- render explanations and bounded summaries
- synthesize Medium Intelligence with three-tier provenance (Supplement v3 §50)
- generate knowledge-query responses with mandatory source citation (Founder Decision #8)

### 6.2 The LLM may NOT:
- set final engineering path
- set confirmed values
- mark RFQ readiness
- perform authoritative deterministic calculations
- finalize norm applicability
- issue final material or product approvals
- simulate manufacturer release
- produce factual claims without provenance (per Supplement v3 §50.2 three-tier rule)

### 6.3 The rule engine must decide:
- request type
- engineering path
- pre-gate classification (deterministic-first, LLM-assist only for ambiguity)
- gate mode
- norm module activation
- mandatory fields
- allowed calculations
- cascading calculation execution (Supplement v3 §49)
- risk scores
- readiness
- output class
- downgrade / stale invalidation

If current code violates this separation, report it explicitly.

---

## 7. Product invariants (Product North Star)

Codex MUST respect these invariants in every user-facing decision:

1. **Dignity** — users never feel stupid (North Star §2.1). No form-gates, no jargon without explanation, no silent rejection.
2. **Async respect** — users return whenever they have time (North Star §2.2). No session timeouts that lose context.
3. **Understand before advise** — precise picture before solution (North Star §3.1).
4. **Proactive validation** — the user's current seal may not be optimal (North Star §3.2).
5. **Teach while qualifying** — every question is also an explanation (North Star §3.3).
6. **Heterogeneous input is first-class** — photos, article numbers, datasheets, free text all accepted (North Star §4).
7. **Small quantities are first-class** — 1-10 pieces filtering as Manufacturer Capability Claim (North Star §5).
8. **Price context yes, price comparison no** — not in MVP (North Star §6).

### 7.1 The five non-negotiables (North Star §7)
SeaLAI must never become: a catalog, a marketing funnel, a price aggregator, a tool that makes users feel stupid, a tool that pretends to know what it doesn't. And must never bypass the manufacturer's final engineering authority.

---

## 8. Moat invariants (Supplement v2 §37)

Every feature, contract, or UI decision must preserve:

- **Layer 1 — Structural neutrality**: no manufacturer influence on ranking outside declared sponsored zones; all sponsored content labeled at every surface
- **Layer 2 — Technical translation**: matching operates on structured concepts and capability claims, never on marketing text or free-text similarity. Problem-First Matching (Supplement v3 §45) is the algorithmic enforcement.
- **Layer 3 — Request qualification**: cases reaching manufacturers are structured, parameterized inquiry packages with explicit open-points and assumptions

If a proposed change weakens any moat layer, it must justify the trade-off explicitly. If no justification is credible, the change is rejected.

---

## 9. Canonical backend truth

SeaLAI must remain backend-first.

### 9.1 Required canonical shape
The backend is the authoritative source for:
- request type, engineering path, sealing material family
- pre-gate classification, gate mode
- core intake (fields per phase)
- failure drivers, geometry/fit, RFQ/liability, RCA, commercial context
- checks, cascading calculations, risk scores
- readiness, provenance, norm context, artifacts
- application pattern assignment (Supplement v3 §46)
- medium intelligence output (Supplement v3 §50)
- advisory notes (Supplement v3 §48)
- tenant ownership (Founder Decision #6)

### 9.2 Frontend role
Frontend is a renderer/projection layer. Frontend may group, filter, collapse, visualize, trigger actions. Frontend must not independently compute engineering truth, define mandatory fields, set readiness, resolve path conflicts, or override provenance.

---

## 10. Provenance is mandatory

Every relevant engineering value must carry provenance.

### 10.1 Allowed origins (base SSoT §9)
- `user_stated`
- `documented`
- `web_hint`
- `calculated`
- `confirmed`
- `missing`

### 10.2 Medium-specific provenance layers (Supplement v3 §50)
Three-tier model for Medium Intelligence:
- **Tier 1 — Registry-grounded**: from curated medium registry, high confidence
- **Tier 2 — LLM-synthesis**: from LLM general knowledge, explicitly labeled with "Plausibilitäts-Schätzung, bitte im konkreten Fall prüfen"
- **Tier 3 — User-provided**: treated as given

Plus generic medium-related provenance: `medium.input`, `medium.context`, `medium.registry`, `medium.inferred_properties`, `medium.confirmed_properties`.

### 10.3 Rule
No web-derived or LLM-derived hint may become confirmed engineering truth without an explicit promotion step. Every knowledge-query factual claim must cite a source.

---

## 11. Output classes are controlled

Codex must preserve the controlled output model.

**Seven allowed output classes** (Base SSoT §10):
- `conversational_answer`
- `structured_clarification`
- `governed_state_update`
- `technical_preselection`
- `rca_hypothesis` (Phase 2+ per Founder Decision #4; MVP degrades to structured_clarification)
- `candidate_shortlist`
- `inquiry_ready`

**Removed (do NOT reintroduce):** `ResultForm` enum (Founder Decision #5).

### 11.1 Output enforcement
The system must have a backend-side validation layer that checks final text against output-class claim rules. Prompt-only restrictions are not sufficient.

### 11.2 Red-flag phrases
Output validation must detect and prevent phrases equivalent to: "guaranteed", "will definitely work", "fully approved", "norm compliant" without basis, "no further review required", "objectively best match".

### 11.3 Advisory Notes (Supplement v3 §48)
Advisory Notes are a cross-cutting output element — co-exist with any output class. Every advisory carries the disclaimer: "Nicht alle Umstände dieses konkreten Falls konnten berücksichtigt werden."

---

## 12. Fast Responder boundary (Supplement v3 §44)

Fast Responder is the pre-graph layer for non-case-creating interactions.

### 12.1 Fast Responder handles ONLY
- `GREETING`, `META_QUESTION`, `BLOCKED` classifications
- No case creation, no persistence, no graph invocation
- Latency target: 500ms–1s

### 12.2 Fast Responder MUST NOT handle
- `KNOWLEDGE_QUERY` (goes to Knowledge Service)
- `DOMAIN_INQUIRY` (goes to full graph)
- Any classification added later, without an explicit supplement amendment

### 12.3 Classification ambiguity defaults to graph
If Pre-Gate Classifier returns uncertain/ambiguous classification, fail-safe is the Full Graph Pipeline. Never fail-safe into Fast Responder.

---

## 13. State regression and stale invalidation

Whenever a critical input changes, SeaLAI must increment revision, invalidate dependent derived state, mark affected outputs as stale, recompute highest valid phase, reset readiness if required, queue recomputation.

**Critical invalidators:**
- medium change
- pressure change
- temperature envelope change
- geometry reference change
- motion type change
- equipment type change
- support-system change
- `sealing_material_family` change
- `ptfe_compound` detail change (for PTFE-RWDR)
- shaft surface / finish / lead / hardness change
- application pattern assignment change (Supplement v3 §46)
- any input to a cascading calculation (Supplement v3 §49)

**Mutation discipline (Supplement v1 §34, Founder Decision #1):**
- Every case change flows through `case_service.apply_mutation()`
- Optimistic locking on `case_revision`
- LangGraph nodes MUST NOT write directly to Postgres
- Every mutation produces a `mutation_events` entry AND an `outbox` entry
- `case_state_snapshots` is a projection cache, not primary source of truth

**Cascading calculations (Supplement v3 §49):**
- Execute synchronously to fixpoint when inputs are satisfied
- Every derived value carries `provenance = "calculated"` with calc_id, version, inputs used
- Stale invalidation propagates through the calculation graph

The frontend must only display stale/recompute status. It must never decide stale logic itself.

---

## 14. Tenant ownership model (Founder Decision #6)

Three-role data access:

### 14.1 User owns the case
- Every case has a `tenant_id` referring to the user
- `tenant_id` is NOT NULL (enforced at schema and API layer)
- Users see only their own cases
- Conversation history, evidence, derived parameters belong to the user

### 14.2 Manufacturer receives inquiry extract, not the case
- Manufacturers see `inquiry_extracts` (separate table), not full case objects
- Structured, technical, anonymized (no user PII, no conversation history)
- Dispatch requires explicit user consent
- Produced by `inquiry_extract_service`

### 14.3 SeaLAI has analytics-only access
- Anonymized aggregates for product improvement
- Golden cases (anonymized successful cases) for training/testing/regression
- PII removal is automated via `anonymization_service`

Any query or code path that returns case data must filter by role and tenant. No cross-tenant leaks.

---

## 15. Chemical compatibility is a real subsystem

Treat chemical compatibility as its own architecture concern.

### 15.1 It cannot be:
- only prompt logic
- only LLM inference
- only generic web search

### 15.2 It must be built around:
- internal compatibility registry
- structured OEM/manufacturer data when available
- SDS/TDS mappings
- Medium Intelligence Service (Supplement v3 §50) with three-tier provenance
- fallback hints clearly marked as non-confirmed

### 15.3 Required compatibility dimensions
At minimum: medium key, concentration, temperature range, dynamic vs static rating, material family, material grade, limitations/guardrails, source refs, registry entry identity, version/hash for traceability.

---

## 16. Norms are modules with gates

Norm modules must be independently activatable with: applicability rule, required fields, deterministic checks, escalation logic, output implications.

### 16.1 MVP norm modules (Founder Decision #7)
- `norm_din_3760_iso_6194` — full code gate (PTFE-RWDR dimensional and type conventions)
- `norm_eu_food_contact` — full code gate (EU 10/2011)
- `norm_fda_food_contact` — full code gate (FDA 21 CFR 177.1550)
- `norm_atex` — capability flag, not full module

### 16.2 Deferred norm modules (Phase 2+)
- `norm_api_682` — ms_pump / mechanical seal domain
- `norm_en_12756` — mechanical seal dimensions
- `norm_iso_3601` — O-ring static
- `norm_vdi_2290` — static leakage classes

### 16.3 Extensibility rule
The norm module framework MUST allow adding a new norm as a pure capability extension: one new file, capability-claim additions, registry entry. No schema migration or service rewrite. Regression test verifies extensibility.

### 16.4 Distinction rule
Codex must explicitly distinguish: reference present vs. gate present vs. required fields present vs. checks present vs. escalation present. A norm mentioned in docs is not a norm implemented.

---

## 17. Calculations and checks: registry-based, deterministic, cascading

### 17.1 Minimum checks layer
- circumferential speed
- PV loading
- flashing / vapor margin
- leakage-related indicators
- friction / heat indicators
- creep-gap estimate (PTFE-specific)
- extrusion gap check
- compound temperature headroom
- fit risk inputs
- lubrication concern
- corrosion concern
- path-specific readiness checks

### 17.2 Formula discipline (Supplement v3 §49)
Each calculation must have:
- stable `calc_id`
- explicit required inputs (`FieldPath[]`)
- optional inputs (improves precision)
- output fields
- `applicable_when` predicate
- formula function
- fallback behavior on missing inputs
- version (semantic)
- provenance metadata

### 17.3 Cascading execution
The Cascading Calculation Engine executes all applicable formulas to fixpoint when inputs become available, synchronously within the same request. Maximum iterations guard against cycles.

No ad hoc inline formulas. No manual calculation chains. The engineer should never have to trigger a follow-on calculation by hand.

---

## 18. Application Patterns (Supplement v3 §46)

Pattern Library is a first-class data source, not prose.

### 18.1 Pattern entity
Each pattern: canonical_name, display_name (localized), triggering_contexts, engineering_path, typical_sealing_material_families, auto_populated_fields (with confidence), required_clarification_fields, typical_operating_envelope, relevant_norm_modules, candidate_compound_families, typical_failure_modes, quantity_profile, educational_note, provenance, version.

### 18.2 MVP seed
14 patterns covering PTFE-RWDR-relevant applications (chemical_process_pump, hydraulic_gearbox, food_processing_chocolate, food_processing_dairy, pharmaceutical_mixing, water_treatment, automotive_gearbox, rotating_drum_mixer, compressor_sealing, cryogenic, high_speed_spindle, pump_dry_run_risk, rebuild_replacement_individual, generic_industrial_unclear).

### 18.3 Matching is explicit, not silent
Pattern selection is presented to the user for confirmation. Auto-populated fields are flagged as `pattern_derived` with user override option.

### 18.4 Extensibility
Adding a new pattern = new data record + regression test. No code change.

---

## 19. Small-quantity first-class (Supplement v3 §47)

### 19.1 User input
`quantity_requested` is a first-class Case field: `pieces` (int or range), `urgency`, `context`, `flexibility`.

### 19.2 Manufacturer capability extension
ManufacturerCapabilityClaim extends `lot_size_capability`:
- `minimum_order_pieces`, `typical_minimum_pieces`, `maximum_order_pieces`
- `accepts_single_pieces` boolean
- `tooling_cost_range_eur`, `tooling_amortization_strategy`
- `price_structure_example` with staffelpreise (1, 4, 10, 100)
- `rapid_manufacturing_available`, surcharge percent, leadtime hours

### 19.3 Matching behavior
- Quantity ≤ 10: HARD filter on `accepts_single_pieces = true`
- Quantity > 10: soft signal via `preferred_batch_size_range`

### 19.4 User expectation management
Pre-dispatch, show expected price range as context (Supplement v3 §47.7). Range indication only, never price comparison.

---

## 20. Knowledge queries first-class (Founder Decision #8, Supplement v3 §53)

### 20.1 Knowledge Service
Dedicated service for `KNOWLEDGE_QUERY` classification. Uses curated, versioned knowledge base (50-100 PTFE-RWDR-focused entries in MVP).

### 20.2 Attribution mandatory
Every factual claim cites a source (norm §, datasheet, terminology registry entry, literature reference). No invented facts. When no relevant entry exists, respond honestly.

### 20.3 Bridge to case
Transition signals detected per turn. Context accumulated in session is transferred to new case on bridge acceptance. Registration prompt at bridge point.

### 20.4 Knowledge is not generic LLM
Knowledge Service MUST NOT be a ChatGPT-wrapper. Every response grounded in the curated knowledge base; LLM synthesizes but does not invent.

---

## 21. Multimodal input (Supplement v3 §52)

### 21.1 MVP input types
Photo, article number/part designation, datasheet fragment, dimensional sketch, free-text description.

### 21.2 Extraction is proposal, not ground truth
All extracted parameters are flagged as proposals requiring user verification. Never silent adoption.

### 21.3 Conflict handling
If inputs disagree (e.g., photo shows cassette, article number decodes as single-lip), present conflict to user explicitly. Never silently resolve.

### 21.4 Privacy
User-uploaded photos: retained only on user's case, stripped from manufacturer extracts and golden cases. EXIF metadata removed.

---

## 22. RCA and retrofit (Founder Decision #4 for RCA, unchanged for retrofit)

### 22.1 RCA in MVP — degraded
RCA requests are recognized by Pre-Gate (keywords: "ausgefallen", "Leckage nach", "Lebensdauer"). Degraded with explicit verbatim message (Founder Decision #4 implementation spec) + optional Early-Access signup (`rca_early_access` table).

### 22.2 RCA full pipeline in Phase 2+
Full RCA intake pipeline, damage-pattern matching, `rca_hypothesis` output class — all deferred.

### 22.3 Retrofit (MVP scope)
Retrofit must support: geometry locked, allowed changes, old part references, fixed cavity constraints, available radial/axial space, standard vs custom fit judgment.

### 22.4 Handover preservation
Retrofit / new_design / RCA handover must preserve: transferred fields, blocked fields, original-request reference, reason for transition.

---

## 23. Commercial / supply context

Required commercial context part of final readiness:
- production mode
- lot size (per quantity_requested and Supplement v3 §47)
- lead-time criticality
- standardization goal
- second source requirement
- lifecycle / spare-parts context
- ATEX / food-grade requirement flags

Must not be buried as optional note-only metadata.

---

## 24. Versioning is mandatory

Every case tracks (Supplement v1 §36):
- `schema_version`
- `ruleset_version`
- `calc_library_version`
- `risk_engine_version`
- `norm_module_versions`
- `case_revision` (optimistic locking — Founder Decision #1)

### 24.1 Migration rule
Additive schema changes must not silently create broken legacy cases. Old cases must be revalidated explicitly when necessary.

---

## 25. Selective Rewrite transition strategy (Founder Decisions meta)

Phase 1a transition is **Selective Rewrite**:

### 25.1 Greenfield (build new)
Persistence extensions (`mutation_events`, `outbox`, extended `cases` schema).
New services: `case_service`, `output_classifier`, `pre_gate_classifier`, `inquiry_extract_service`, `anonymization_service`, `knowledge_service`, `terminology_service`, `risk_engine`, `compatibility_service`, `outbox_worker`, `norm_modules/`, `output_validator`, `formula_library`, `projection_service`, `fast_responder_service`, `application_pattern_service`, `medium_intelligence_service`, `advisory_engine`, `photo_analysis_service`, `article_number_decoder_service`, `datasheet_extraction_service`.
New tables for capability, terminology, knowledge, extracts, patterns, media, advisories.

### 25.2 Strangler (preserve, refactor in place)
`agent/graph/topology.py`, three-mode gate, observability, audit logger. Oversized nodes (intake_observe, matching, output_contract, rfq_handover) shrink as business logic extracts to services.

### 25.3 Remove
`services/langgraph/` (after YAML rule migration), `services/fast_brain/` (absorbed by three-mode gate CONVERSATION), `_legacy_v2/`, `ResultForm` enum, legacy feature flags (`SEALAI_ENABLE_BINARY_GATE`, `SEALAI_ENABLE_CONVERSATION_RUNTIME`, `ENABLE_LEGACY_V2_ENDPOINT`), `interaction_policy.py` shim, old endpoints (`langgraph_v2.py`, `fast_brain_runtime.py`).

---

## 26. Codex workflow expectations

### Step A — Audit
- inspect real implementation
- inspect current tests
- inspect current wiring
- inspect current docs
- identify actual truth vs target truth (per Implementation Plan)

### Step B — Delta report
Return: what exists, what is partial, what is missing, what looks integrated but is not, smallest patch sequence within current sprint scope.

### Step C — Patch one layer at a time
Follow the Implementation Plan sprint order. Do NOT skip ahead because a later patch "looks more visible". Do NOT combine patches across sprint boundaries.

### Step D — Validate
Run tests for touched area. Run import-graph check. Run moat-invariant check where applicable. Run tenant-isolation check where applicable. Green before merge.

### Step E — Report
Exact file paths. Exact functions/classes/modules. Concise evidence. What changed. What tests confirm the change.

---

## 27. Repo-specific discipline

### 27.1 Commands
Always run repo-level commands from `/home/thorsten/sealai`.

### 27.2 Minimal diffs
Prefer: extension seams, local refactors, adapter layers, explicit rule modules. Avoid: broad rewrites, renaming cascades, rewriting stable infrastructure "to clean up".

### 27.3 Evidence-based reporting
When auditing or patch-planning: exact file path, exact functions/classes/modules, concise evidence, today vs. target state.

### 27.4 MVP scope respect
The MVP depth boundary is PTFE-RWDR. If current code has lingering RWDR-first artifacts from the pre-SSoT era, report and isolate — do NOT expand them. The new PTFE-RWDR focus is deliberate narrow-depth/wide-structure per Supplement v2 §39.

### 27.5 Layer isolation (Supplement v1 §35)
- `backend/app/domain/` — no upward imports
- `backend/app/models/` — imports only from `domain/`
- `backend/app/schemas/` — imports only from `domain/`
- `backend/app/services/` — must NOT import from `backend/app/agent/`
- LangGraph nodes MUST NOT import from `services/` except through defined service interfaces

Verify with `grep` commands before merging.

---

## 28. Test discipline

### 28.1 Green before merge
No patch merges with failing tests. Ever.

### 28.2 Test-first for critical services
For services governing core invariants (`case_service`, `pre_gate_classifier`, `output_classifier`, `anonymization_service`, `norm_modules`), tests are written alongside or before implementation, not after.

### 28.3 Coverage expectations
- Unit tests for every public service method
- Integration tests for authority invariants (moat, provenance, tenant isolation, fast responder boundary, cascade convergence)
- Regression tests for every bug fix

### 28.4 Test hygiene
Tests must be: deterministic, isolated, self-explanatory. Flaky tests get fixed, not retried.

---

## 29. Audit gates (Implementation Plan Part C)

Between every sprint, Claude Code runs a read-only audit gate. Codex CLI does not pass its own audits. The audit gate produces a pass/fail verdict with evidence.

Codex CLI must not proceed into the next sprint until the current sprint's gate is passed and the founder has explicitly approved transition.

If an audit gate reveals issues, Codex CLI produces remediation patches within the current sprint — not the next one.

---

## 30. Final operating rule

Codex must optimize for:
- technical truth
- provenance
- deterministic boundaries
- auditability
- smallest correct patch path
- Product North Star alignment (user dignity, async respect, teach while qualifying)
- moat preservation

Codex must NOT optimize for:
- superficial UI completeness
- broad speculative abstractions
- hidden assumptions
- free-form "AI convenience" over engineering safety
- cross-sprint "while we're here" fixes
- backward compatibility with deprecated patterns (ResultForm, RoutingPath, services/langgraph/, services/fast_brain/, etc.)

If in doubt:
- ask less from the user at once
- preserve uncertainty
- downgrade readiness
- mark state stale
- prefer explicit blockers over optimistic assumptions
- escalate to founder via Claude Code audit rather than silently reinterpret
