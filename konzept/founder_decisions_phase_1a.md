# SeaLAI — Founder Decisions on Audit NEEDS_FOUNDER_INPUT

**Version:** 0.1 (in progress)
**Datum:** 2026-04-17
**Status:** Answers to the seven NEEDS_FOUNDER_INPUT entries from `audits/phase_1a_backend_core_transition_plan_2026-04-17.md`
**Purpose:** Decision record for Phase 1a transition planning. Read alongside the audit report. Feeds directly into the implementation plan.

---

## Decision #1 — Case state persistence pattern

**Audit question:** Should `case_state_snapshots` be kept (revision history per snapshot) and `mutation_events` be introduced in parallel, or should the Outbox/Mutation pattern replace the snapshot table?

**Founder decision:** **Option 1** — Introduce mutation_events and outbox as new tables; reassign `case_state_snapshots` to a projection-cache role.

**Rationale captured:**
- Supplement v1 §34 requires the mutation-event journal with outbox pattern; this is non-negotiable.
- Existing `case_state_snapshots` data is preserved and continues to be usable for direct revision reads.
- `apply_mutation()` becomes the single legitimate write path, producing both a mutation event and (transitionally) a snapshot — no breaking change for existing readers.
- Outbox integration arises naturally: every mutation produces an outbox entry, which drives downstream effects (risk-score recompute, notifications, external integrations).

**Implementation implications:**

1. **New tables (Alembic migration required):**
   - `mutation_events` — append-only journal per supplement v1 §34.3–34.4
   - `outbox` — pending side-effects per supplement v1 §34.5
   - Consider `risk_scores` as separate persisted risk layer per supplement v1 §36

2. **Schema changes to `cases` table:**
   - Add `case_revision` column (int, for optimistic locking)
   - Add all other columns required by supplement v1 §36.3 (tenant_id, payload JSONB, schema_version, ruleset_version, calc_library_version, risk_engine_version, phase, request_type, routing_path, rfq_ready, inquiry_admissible)
   - Tenant-id backfill strategy is deferred to Decision #6

3. **New service:**
   - `case_service` under `backend/app/services/case_service.py`
   - Single method `apply_mutation(case_id, mutation, expected_revision)` with optimistic locking
   - No LangGraph imports (supplement v1 §33.8)
   - Writes mutation event, updates case state, (transitionally) writes snapshot, creates outbox entry in one transaction

4. **LangGraph nodes change:**
   - All node write paths must go through `case_service.apply_mutation()`
   - No direct Postgres writes from nodes (supplement v1 §33.4)
   - This is a substantial refactor of the existing node code

5. **Transitional `case_state_snapshots` semantics:**
   - Phase 1: Both written (every mutation produces event + snapshot)
   - Phase 2: Snapshot becomes a derivable projection, rebuildable from events
   - Phase 3: Snapshot table becomes a pure performance cache

6. **Outbox worker:**
   - New `outbox_worker` service that processes pending outbox entries
   - Initial scope: trigger risk-score recompute, emit audit-log entries
   - Retry budget, idempotency, and dead-letter queue per supplement v1 §34.5

**Effort estimate:** XL (two to three weeks of focused work assuming single developer)
**Sequencing:** This is the foundation for all other persistence-related work. Must be done before Decisions #6 (tenant-id backfill) and #7 (norm module persistence) can be implemented cleanly.

---

## Decision #2 — Future of parallel orchestration stacks

**Audit question:** Will both parallel stacks be deprecated and the main `agent/` graph established as the canonical orchestration, or will one of them remain as an explicit "fast path" (with reconciliation tests)?

**Founder decision:** **Option A** — Consolidate to a single canonical stack: `backend/app/agent/`. Both `services/langgraph/` and `services/fast_brain/` are deprecated and removed. YAML rules from `services/langgraph/rules/*.yaml` are migrated to the new `risk_engine` and `checks_registry` services. The `fast_brain` routing concern is absorbed into the three-mode gate (CONVERSATION mode serves the fast-path role).

**Rationale captured:**
- A single-person project cannot sustain two parallel orchestration stacks — every feature change requires double work, every SSoT update must be replicated, every test must cover both.
- The three parallel stacks are the structural root cause of the 11 prior audit iterations that produced SSoT drift.
- Supplement v1 §33.10 does not strictly forbid parallel stacks, but it demands "explicit reconciliation" — which does not exist and would itself be substantial ongoing work.
- YAML rules in `services/langgraph/rules/` encode real domain knowledge that must not be lost. These are migrated, not deleted.
- `services/fast_brain/` has no unique value that cannot be served by the `agent/` stack with proper Fast-Path logic in the gate. Resurrecting a Fast-Path later is a deliberate decision, not a default.

**Implementation implications:**

1. **Pre-migration YAML review (required before deletion):**
   - Review `services/langgraph/rules/common.yaml` — per-rule classification: migrate-to-risk-engine / migrate-to-checks-registry / obsolete-delete
   - Review `services/langgraph/rules/rwdr.yaml` — same classification
   - Produce a migration table as a short document in `audits/yaml_rule_migration_<date>.md` before any deletion

2. **Sequencing with Decision #1:**
   - Decision #1 (persistence + case_service + mutation/outbox) comes first
   - Then agent/ node consolidation (break oversized nodes into Node + Service pairs per supplement v1 §33.4)
   - Then YAML rule review and migration to risk_engine / checks_registry
   - Then deprecate and delete services/langgraph/
   - Then deprecate endpoint `langgraph_v2.py`, remove services/fast_brain/, deprecate endpoint `fast_brain_runtime.py`

3. **Endpoint cleanup:**
   - `backend/app/api/v1/endpoints/langgraph_v2.py` → deprecated, redirect period to SSoT endpoints, then deleted
   - `backend/app/api/v1/endpoints/fast_brain_runtime.py` → deprecated, delete
   - `backend/app/api/v1/endpoints/sse_runtime.py` → review whether still needed; likely repurpose to serve SSoT `/v1/case/{id}/stream` or similar
   - Feature flag `ENABLE_LEGACY_V2_ENDPOINT` in `core/config.py` → removed once deprecation complete

4. **CONVERSATION mode absorbs Fast-Path responsibility:**
   - `agent/runtime/gate.py` with existing three-mode gate is the replacement
   - No new code required for this transition per se; Fast-Path logic simply stops existing as a separate module

**Effort estimate:** L (above and beyond Decision #1). Spread across the overall transition, not a single-shot task.
**Sequencing:** After Decision #1. The consolidation cannot happen before `case_service.apply_mutation()` exists, because all node write paths must route through it.

**Dependencies to other decisions:**
- Depends on Decision #1 (persistence foundation)
- Sets direction for Decision #5 (RoutingPath/ResultForm) — if we consolidate stacks, the Interaction-Sublayer question is simpler

## Decision #3 — COI data firewall

**Audit question:** Is there documented evidence that no founder-employer-proprietary data has entered the SeaLAI corpus (Qdrant, KB-JSON, YAML rules, prompts)?

**Founder decision:** **Status clean.** Explicit self-assurance that all four firewall-relevant categories are compliant:
- No direct employer-proprietary data (compound recipes, internal test results, customer lists, non-public datasheets, internal calculation tables) in any SeaLAI dataset
- KB-JSONs for PTFE-RWDR contain only values from public sources (standards DIN/ISO/API, publicly available manufacturer datasheets, professional literature) and the founder's general engineering domain knowledge, not employer-proprietary knowledge
- Golden Cases and test fixtures are based on generic, constructed, or public examples — not on actual customer inquiries at the employer
- Qdrant documents do not originate from internal employer sources

**Rationale captured:**
- Supplement v2 §38.6 and §43 require a strict COI data firewall between founder's employer and SeaLAI
- This firewall is organizational/procedural, not technical — cannot be auto-verified, depends on founder's conscientious declaration
- Legal context (Germany): §17 UWG (trade secret protection), §§ 823/826 BGB (damages) make this non-negotiable regardless of employer's informal support
- Strategic context: Moat layer 1 (structural neutrality) depends on verifiable absence of employer-specific content; a future discovery of employer-origin material would immediately falsify the neutrality claim

**Implementation implications:**

1. **New repo artifact required:**
   - `konzept/coi_firewall_log.md` — written declaration with founder signature line, date, and explicit scope
   - Document is part of the final Phase 1a baseline commit
   - Content structure:
     - Purpose (why the log exists)
     - Covered SeaLAI artifacts (KB-JSONs, YAML rules, prompts, Qdrant documents, golden cases, test fixtures)
     - Founder declaration (the four-point clean statement)
     - Review trigger events (when the log must be revisited)
     - Date and signature line

2. **Review trigger events (documented in the log itself):**
   - Quarterly review (default)
   - On adding any new manufacturer-specific content to the corpus
   - On change of employer or substantial change in employer's ownership
   - On the first external manufacturer pilot onboarding (pre-launch check)
   - On any legal inquiry touching this area

3. **No immediate code action required.**
   - The clean declaration does not require data cleanup
   - It does require future discipline: when new content is added to the corpus, its source must be identifiable and documentable as public or general-domain

4. **Interaction with Annex A (employer agreement):**
   - The employer agreement template in supplement v2 Annex A explicitly references SeaLAI's data firewall as a binding condition
   - Before the first external pilot, the agreement must be signed AND the firewall log must be in place

**Effort estimate:** XS (write the log, commit it)
**Sequencing:** Part of the Phase 1a baseline. Not blocking implementation, but must be committed alongside the transition-plan kickoff.

**Dependencies to other decisions:** None directly. The firewall is an ongoing organizational commitment, independent of technical decisions.

## Decision #4 — rca_hypothesis priority

**Audit question:** When must `rca_hypothesis` be in production? RCA is defined as a first-class Request-Type in AGENTS §5.1 and §15 but is currently unimplemented. Should RCA be pulled into the MVP scope (PTFE-RWDR-centered) or explicitly deferred to Phase 2+?

**Founder decision:** **Option B** — RCA deferred to Phase 2. The MVP launches with six of seven SSoT output classes (all except `rca_hypothesis`). RCA requests during MVP phase degrade gracefully with an explicit user-facing message plus optional early-access signup.

**Rationale captured:**
- MVP viability stands or falls with the first paying pilot manufacturer (founder's employer as design partner). The core use-cases "new design selection" and "spare part identification" are sufficient to demonstrate value at pilot stage.
- RCA has a higher quality bar than other output classes: a bad RCA hypothesis is worse than no hypothesis (sends the user in the wrong direction). Robust failure-mode matching requires real failure case data, which only exists after the platform is operational.
- The moat layer 3 value proposition (request qualification) is most visible for new-design and replacement cases, where "short inquiry in → qualified spec out" is immediately demonstrable. RCA's value is subtler (hypothesis vs. answer).
- Phase 2 RCA development can happen in co-development with an external pilot manufacturer using real failure cases from their daily operations — a better development context than isolation.
- Engineering domain basis for RCA is already complete: `sealai_engineering_depth_ptfe_rwdr.md` §7 contains the 15-entry failure-mode taxonomy (including spiral_failure, lead_induced_pumping_leakage, creep_induced_contact_loss, chemical_attack_filler, hang_up). Implementation is pipeline work, not domain research.

**Implementation implications:**

1. **MVP output class count: 6 of 7.**
   - Implemented: `conversational_answer`, `structured_clarification`, `governed_state_update`, `technical_preselection`, `candidate_shortlist`, `inquiry_ready`
   - Deferred: `rca_hypothesis`

2. **RCA-recognition in the gate (minimal, MVP-compatible):**
   - `agent/runtime/gate.py` must recognize RCA-indicative user input (keywords: "ausgefallen", "kaputt", "Leckage nach", "Lebensdauer", "warum versagt", "failure", "troubleshoot")
   - On recognition, route to a dedicated "out-of-scope graceful degrade" path
   - Do NOT degrade silently to `structured_clarification` — the user must understand that RCA-specific analysis is not available

3. **RCA-degrade message (verbatim for MVP):**

   ```
   "Sie fragen nach einer Ausfall-Analyse einer bestehenden Dichtung.
   SeaLAI unterstützt aktuell die Neuauslegung und
   Ersatzteil-Identifikation von PTFE-Radialwellendichtungen mit voller
   engineering depth. Die Ausfall-Analyse (RCA) ist in Vorbereitung für
   eine kommende Version.

   Sie können uns Ihre Ausfall-Fallbeschreibung zusenden, und wir nehmen
   Sie in die Early-Access-Liste für RCA auf — oder wir bearbeiten Ihre
   Anfrage als Ersatzteil-Anfrage, wenn Sie primär eine
   Nachfolge-Dichtung suchen."
   ```

   This message is stored in the prompt library and rendered verbatim. English translation to be provided for English-language users with equivalent content.

4. **Early-access data collection (Phase 2 preparation):**
   - RCA inquiries during MVP phase may optionally store the user's failure-case description as an Early-Access entry
   - Storage format: simple append-only record with user-provided text, timestamp, optional contact info, anonymized operating-envelope if derivable
   - No LLM processing during MVP; this is raw collection for Phase 2 training data
   - Storage location: new `rca_early_access` table, not the main cases table
   - Explicit user consent required before storing personally identifiable information

5. **Phase 2 RCA scope (out of this Phase 1a audit):**
   - Full RCA intake pipeline (symptoms, failure timing, damage pattern evidence, photo uploads)
   - Damage-pattern matching against the 15-entry failure-mode taxonomy
   - Hypothesis output class with confidence levels and remediation suggestions
   - Co-development with one pilot manufacturer using their real failure-case archive

**Effort estimate for MVP phase:** XS (gate keyword detection + degrade message + minimal early-access table)
**Effort estimate for Phase 2 RCA implementation:** L (deferred)
**Sequencing:** The MVP-phase RCA-degrade logic is lightweight and can be implemented anywhere in the transition plan; not a blocker.

**Dependencies to other decisions:**
- Indirectly depends on Decision #2 (single canonical stack) — the gate keyword detection lives in the consolidated `agent/` stack
- Sets context for Decision #5 (RoutingPath/ResultForm consolidation) — the RCA degrade path must integrate cleanly with whichever routing model is chosen

## Decision #5 — RoutingPath / ResultForm consolidation

**Audit question:** Are `RoutingPath` and `ResultForm` retained as Interaction/Runtime sublayer of a two-stage model (Interaction-Routing → Engineering-Routing), or should they be fully replaced by SSoT enums (engineering_path, request_type, 7 output classes)?

**Founder decision:** **Option B** — `RoutingPath` is restructured as a Pre-Gate Classifier with reduced, semantically clean values. `ResultForm` is removed entirely. The seven SSoT output classes are the single output classification.

**Rationale captured:**
- The three-mode gate (CONVERSATION/EXPLORATION/GOVERNED) is productive and positively cited in the audit. It must not be thrown away.
- `ResultForm` (DIRECT_ANSWER, GUIDED_RECOMMENDATION, DETERMINISTIC_RESULT, QUALIFIED_CASE) is a precursor/subset of the seven SSoT output classes. Consolidating to the seven output classes is cleaner architecture at no semantic loss.
- `RoutingPath` contains legitimate distinctions (GREETING, META, BLOCKED) that the three-mode gate does not cover. Removing `RoutingPath` entirely would be a regression.
- The resolution: reduce `RoutingPath` to a Pre-Gate Classifier with only the values that complement (not duplicate) the three-mode gate.

**New classification architecture:**

```
Pre-Gate Classifier (replaces RoutingPath)
  ∈ {GREETING, META_QUESTION, BLOCKED, DOMAIN_INQUIRY}
         │
         │ if DOMAIN_INQUIRY:
         ▼
Three-Mode Gate (existing, retained as-is)
  ∈ {CONVERSATION, EXPLORATION, GOVERNED}
         │
         ▼
Domain Classification (SSoT enums, mandatory for Case records)
  engineering_path ∈ {ms_pump, rwdr, static, labyrinth, hyd_pneu, unclear_rotary}
  request_type     ∈ {new_design, retrofit, rca_failure_analysis, validation_check,
                       spare_part_identification, quick_engineering_check}
  sealing_material_family ∈ {ptfe_virgin, ptfe_glass_filled, ... , elastomer_nbr, ...}
         │
         ▼
Output Classification (SSoT, deterministic derivation)
  ∈ {conversational_answer, structured_clarification, governed_state_update,
     technical_preselection, rca_hypothesis, candidate_shortlist, inquiry_ready}
```

**Implementation implications:**

1. **Changes to `agent/runtime/policy.py`:**
   - Replace `RoutingPath` enum with new `PreGateClassification` enum (4 values instead of 5)
   - Remove `ResultForm` enum entirely
   - Keep `ThreeModeGate` / `GateMode` enum unchanged
   - Migrate all consumers

2. **Pre-Gate Classifier as a dedicated service:**
   - New `backend/app/services/pre_gate_classifier.py`
   - Inputs: user input text, conversation context
   - Outputs: `PreGateClassification` with confidence
   - Testable without LangGraph imports (supplement v1 §33.8)
   - Classification is deterministic-first (keyword/pattern based), LLM-assisted only for ambiguous cases (and marked as such in provenance)

3. **Greeting / Meta / Blocked handling (deterministic, no Case creation):**
   - `GREETING` → short friendly response, no Case, no Postgres write
   - `META_QUESTION` → short info response with links to documentation, no Case
   - `BLOCKED` → polite decline with clear reason, no Case
   - Only `DOMAIN_INQUIRY` proceeds to Case creation and the three-mode gate

4. **Output class derivation as a service:**
   - Current implementation: inline in `output_contract_node.py` (1335 lines, violates supplement v1 §33.4)
   - Target: new `backend/app/services/output_classifier.py`
   - Inputs: governance state, readiness, matching context, request type
   - Output: deterministic mapping to one of the seven output classes
   - The node becomes a thin orchestrator per supplement v1 §33.4

5. **Mapping table (documentation):**
   - A small reference table in the code comments (or a separate markdown document) documents which combinations of (PreGateClassification, GateMode, engineering_path, request_type, readiness) map to which output class
   - This mapping is the contract; any change requires explicit review

**Effort estimate:** M (medium). Requires:
- Enum replacement and consumer migration
- Extraction of `output_classifier` service from the oversized node
- New `pre_gate_classifier` service implementation
- Tests for all 4×3=12 combinations of pre-gate × gate-mode

**Sequencing:**
- Happens in parallel with Decision #1 and Decision #2
- Cannot start before Decision #1 (need `case_service.apply_mutation()` for Domain Classification to persist)
- Can happen before full stack consolidation (Decision #2) since it's internal to `agent/`

**Dependencies to other decisions:**
- Depends on Decision #1 (persistence layer for domain classification storage)
- Supports Decision #2 (single canonical stack — no duplicate classification logic)
- Integrates with Decision #4 (RCA degrade path uses Pre-Gate Classifier's BLOCKED or a special "out_of_scope_rca" sub-state)

## Decision #6 — Tenant-id interpretation and backfill strategy

**Audit question:** When introducing `tenant_id NOT NULL` on `cases`: What default does existing cases in the live system receive? Dummy tenant, "legacy" tenant, hand-migration?

**Founder decision:** **The user owns the Case. Existing cases are test chats and will be deleted.**

Tenant model:
- **`tenant_id` represents the User** — the person initiating the case (design engineer, maintenance engineer, purchaser). The case, its conversation history, its evidence, its derived parameters belong to the user.
- **Manufacturers receive only the qualified inquiry extract**, not the full case. The manufacturer-facing view is a structured, technical, de-contextualized package sufficient for quote generation — not the raw interaction history.
- **SeaLAI has analytics access** for product improvement, golden case collection, and matching-quality optimization. This access is anonymized and aggregated, governed by explicit policy.

Backfill strategy: **Option 3 — delete.** Existing cases are all test/development chats with no production value. Clean baseline.

**Rationale captured:**
- User-owned case model is the correct DSGVO/GDPR-compliant architecture for a B2B platform with individual end-users. It aligns with data-protection norms and with the North Star principle that SeaLAI serves the user, not the manufacturer.
- Three-role data access model: User (owns), Manufacturer (receives extract), SeaLAI (analytics only) — mutually non-overlapping, legally clean, ethically consistent.
- Golden Case concept: successful anonymized cases become regression-test and training material. This is a product-quality asset distinct from user data.
- Deleting existing test cases is safe because no production data is at risk.

**Implementation implications:**

1. **Schema changes on `cases`:**
   - Add `tenant_id` as NOT NULL column
   - Add foreign key to a new `users` or `tenants` table (implementation detail: likely existing Keycloak user ID, or a dedicated internal user table synced with Keycloak)
   - Add `created_by` (user-id), `last_modified_by` columns
   - Add `case_ownership_type` enum: `user_owned` (default), `shared_with_manufacturer` (after inquiry dispatch), `internal_analytics_only` (for anonymized golden cases)

2. **New table `inquiry_extracts`:**
   - Separate table representing what a manufacturer sees
   - Structured, technical, anonymized by design (no user PII)
   - Fields: case_id (internal reference only), engineering_path, request_type, sealing_material_family, operating_envelope JSONB, geometry JSONB, quantity, delivery_urgency, created_at, dispatched_to_manufacturer_id
   - Explicit opt-in: a case only produces an inquiry_extract when the user confirms "dispatch to manufacturer"

3. **New table `golden_cases`:**
   - Stores anonymized cases for training / testing / regression
   - Fields: derived engineering parameters, final outcome, user-satisfaction signal, manufacturer-match quality signal, PTFE-RWDR classification, lessons learned
   - Creation trigger: successful case + user opt-in for anonymized retention
   - Anonymization process: PII removal (names, companies, emails, project codes, photo EXIF metadata), replace with generic placeholders

4. **New service `inquiry_extract_service`:**
   - Under `backend/app/services/inquiry_extract_service.py`
   - Pure function: Case → InquiryExtract
   - Enforces manufacturer-view boundaries: no user identity, no conversation history, no non-technical fields
   - Testable without LangGraph imports (supplement v1 §33.8)

5. **New service `anonymization_service`:**
   - Under `backend/app/services/anonymization_service.py`
   - Removes PII from case content for golden case generation and analytics
   - Handles text (names/companies), metadata (photos), article numbers (keep technical part, remove customer codes)
   - Has explicit PII dictionary and detection rules, extendable

6. **Migration steps:**
   - Alembic migration: add `tenant_id` + related columns as NULLABLE initially
   - Delete all existing cases (test data, no backfill needed)
   - Second migration: set `tenant_id` NOT NULL
   - New cases all have tenant_id from the start

7. **Keycloak integration:**
   - SeaLAI uses existing Keycloak deployment (stack doc)
   - User-tenant-id is derived from Keycloak subject ID
   - Anonymous users (no auth) can start a session but cannot save/reload — require registration to own a case
   - This is a UX decision: should anonymous sessions be allowed at all? See open question below.

8. **Role-based access:**
   - User sees own cases only (tenant_id filter on every query)
   - Manufacturer sees inquiry_extracts dispatched to them, not other cases
   - SeaLAI internal analytics user has read-only access to anonymized views

**Effort estimate:** L (medium-large). Includes schema changes, new services, Keycloak integration verification, tenant-filter middleware, authorization policy.

**Sequencing:** After Decision #1 (persistence foundation) and Decision #2 (stack consolidation). The tenant_id column goes in the cases table migration; inquiry_extracts and golden_cases are separate migrations that can happen in parallel once the foundation is in place.

**Dependencies to other decisions:**
- Depends on Decision #1 (case schema changes go in the same migration wave)
- Shapes Decision #5 (output classification must respect user-owned vs. manufacturer-view)
- Enables future Phase 2 work (Golden Case training, RCA Phase 2, manufacturer onboarding)

**Open sub-question for later implementation phase:**
- *Should anonymous users (not registered) be allowed to start a session?* Pros: lower barrier to entry, user can try before registering. Cons: case can't be saved, can't be reloaded, might feel confusing. Suggested approach: anonymous session allowed for initial exploration, but any step toward "dispatch to manufacturer" or "save for later" triggers a registration prompt. This is a UX decision, not a core architectural one — deferrable to implementation.

## Decision #7 — Norm module priority

**Audit question:** Which norm modules are implemented as binding code gates in Phase 1a? All (API 682, EN 12756, DIN 3760/ISO 6194, ISO 3601, VDI 2290, ATEX) or only the PTFE-RWDR-relevant subset?

**Founder decision:** **Option B** — MVP subset: DIN 3760 / ISO 6194 as full code gates, Food-Grade compliance (EU 10/2011, FDA 21 CFR 177.1550) as full code gates, ATEX as a capability-claim flag. Other norms deferred to later phases. **Condition:** The norm module framework must be extensible without requiring architectural rework — SeaLAI's long-term goal is to cover the full sealing industry.

**Rationale captured:**
- Food-grade inquiries are frequent in founder's practice — not a niche concern. Examples include chocolate, milk, and food processing applications. Missing FDA/EU food-grade compliance would be a real product failure.
- ATEX is less frequent but important; modeling it as a capability-flag on manufacturers (ATEX-certified yes/no) and on cases (ATEX-required yes/no) is sufficient for MVP without dedicated check logic.
- DIN 3760 / ISO 6194 are unavoidable for PTFE-RWDR scope — they define the dimensional and type conventions every matching decision rests on.
- API 682, EN 12756 are ms_pump-specific and come naturally with Phase 2 scope expansion.
- ISO 3601 (O-rings) and VDI 2290 (static leakage) are static-path-specific and come with Phase 3+ static expansion.
- **The architecture must support adding any of the deferred norms as a pure capability extension**, without schema migrations or service rewrites. This is a first-class non-functional requirement.

**Implementation implications:**

1. **Norm module framework (base scaffolding, required for MVP):**
   - Abstract `NormModule` interface under `backend/app/services/norm_modules/`
   - Each norm module provides:
     - `applies_to(case: Case) -> bool` — applicability check
     - `required_fields(case: Case) -> list[FieldName]` — data required for the check
     - `check(case: Case) -> NormCheckResult` — the actual validation
     - `escalation_policy() -> EscalationPolicy` — what to do on violation
     - `version: str` — semantic versioning per base SSoT §17
   - Module registration via a registry pattern, allowing new norms to be added as isolated files

2. **MVP norm modules (Phase 1a):**
   - `din_3760_iso_6194.py` — dimensional and type conventions for RWDR. Applies when engineering_path = rwdr. Required fields: shaft diameter, housing ID, seal width. Checks: dimension table conformance, type designation validity.
   - `eu_food_contact.py` — EU Regulation 10/2011 on plastics in contact with food. Applies when medium is food-adjacent. Required fields: medium identification, temperature profile, cleaning regime. Checks: compound food-grade certification, migration limits documented.
   - `fda_food_contact.py` — FDA 21 CFR 177.1550 (PTFE) and related. Parallel structure to EU variant. May share certification data sources with EU module.
   - ATEX is not a module; it is a capability flag on manufacturer profiles and a requirement flag on cases. Matching filters out non-ATEX-certified manufacturers when case requires ATEX.

3. **Extensibility architecture (MUST be proven with MVP modules):**
   - Adding a new norm (e.g., API 682 in Phase 2) MUST be possible by:
     - Creating one new file under `services/norm_modules/`
     - Adding capability-claim fields to ManufacturerCapabilityClaim (if norm implies manufacturer certification)
     - Registering the new module in the norm registry
     - No changes to core case processing, matching, or output logic
   - A regression test verifies that the MVP norm modules can coexist and that a "fake new norm" can be plugged in without touching existing modules.

4. **Integration with output contract:**
   - When a norm module raises a violation, the case cannot reach `inquiry_ready` output class
   - Violations produce `structured_clarification` output with the norm's escalation message
   - Violation resolution paths are explicit (e.g., "Your case requires FDA food-grade compliance. Select a FDA-certified compound.")

5. **Capability-claim extensions for norm certifications:**
   - `ManufacturerCapabilityClaim.certifications[]` already exists per supplement v2 §41
   - MVP adds structured entries for: `DIN_3760_certified`, `ISO_6194_certified`, `FDA_21_CFR_177_1550`, `EU_10_2011`, `ATEX_certified` with validity periods and certificate references

**Effort estimate:** M (medium). Three modules to implement, registry scaffolding, integration with output contract, capability-claim extensions.

**Sequencing:** After Decision #1 (case persistence foundation). Norm modules can be developed in parallel with Decision #6 (tenant-id) since they operate on already-structured case data.

**Dependencies to other decisions:**
- Depends on Decision #1 (case data model)
- Integrates with Decision #5 (norm violations produce structured_clarification output)
- Enables future phase expansion (adding API 682 etc. requires only new module files)

---

## Decision #8 (additional) — Knowledge queries as a first-class interaction mode

**This decision was not in the original audit's seven NEEDS_FOUNDER_INPUT entries. It emerged during the decision-sequence when the founder articulated that SeaLAI must support knowledge-oriented questions alongside case-oriented ones.**

**Founder statement:**

> *"Was allerdings noch in SeaLAI möglich sein sollte ist klassisches Fachwissen. Ich denke das kann aber das LLM mit RAG liefern. Also zb ein klassischer Vergleich zwischen FKM und PTFE oder so. Oder was genau ein RWDR ist und wie er funktioniert. Das sind ja auch Themen die ein User interessieren wird."*

**Founder decision:** **Knowledge queries are a first-class interaction mode in MVP.** Implemented as a dedicated Pre-Gate Classification `KNOWLEDGE_QUERY` with a curated, versioned knowledge base and deterministic provenance attribution. Not implemented as generic LLM+RAG (that would collapse SeaLAI into a "ChatGPT-for-seals" wrapper, which is a USP failure mode).

**Rationale captured:**
- Real users have legitimate knowledge questions (FKM vs PTFE comparison, RWDR function explanation, norm interpretation)
- These questions are not case-creation interactions — no Case is created, no manufacturer matching happens
- The Product North Star §3.3 ("Teach while qualifying") makes consultative knowledge delivery a core product value
- Generic LLM+RAG would work technically but would erode the Moat Layer 2 (technical translation via SeaLAI's own terminology registry) and the engineering-precision reputation

**Implementation implications:**

1. **Extend Pre-Gate Classifier (revising Decision #5):**

   ```
   PreGateClassification ∈ {
     GREETING,
     META_QUESTION,      // about SeaLAI itself
     KNOWLEDGE_QUERY,    // NEW: about sealing technology
     BLOCKED,
     DOMAIN_INQUIRY      // case-creating
   }
   ```

2. **Knowledge Base — curated, versioned, attribution-enabled:**
   - Location: `backend/app/data/knowledge_base/` + Qdrant collection for retrieval
   - MVP scope: 50–100 curated entries focused on PTFE-RWDR and general RWDR context
   - Entry types:
     - Material comparisons (NBR vs FKM vs PTFE vs EPDM vs FFKM)
     - Seal type functions (what is an RWDR, Cassette seal, V-ring)
     - Construction fundamentals (lip geometry, shaft requirements, installation)
     - Norm explanations (DIN 3760, ISO 6194, EU 10/2011, FDA 21 CFR)
     - Application patterns (food-grade processing, chemical process, gearbox, hydraulic)
   - Each entry: text content, source references (DIN standards, datasheets, textbooks), version, last_reviewed_at
   - Extensible: golden cases (Decision #6) feed lessons-learned back as new entries

3. **Knowledge Service:**
   - Under `backend/app/services/knowledge_service.py`
   - Interface: `query(user_text: str, context: Optional[CaseContext]) -> KnowledgeResponse`
   - Uses Qdrant for retrieval over the curated knowledge base
   - Uses LLM for response synthesis BUT with hard constraint: every factual claim traces to a source entry with explicit citation
   - Does NOT invent facts; when no relevant entry exists, responds "I don't have detailed information on this specific question"

4. **Attribution and provenance — the differentiator from generic RAG:**
   - Every knowledge response cites sources: norm references (DIN 3760 §4.1), terminology registry entries (Simmerring → Freudenberg trademark for RWDR Type A), technical literature
   - This visually differentiates SeaLAI responses from ChatGPT-style answers
   - Users see that SeaLAI's knowledge is grounded, not fabricated

5. **Bridge from knowledge to case:**
   - User starts in KNOWLEDGE_QUERY mode with a general question
   - As the conversation becomes concrete ("I have a pump with kerosene..."), the Pre-Gate Classifier detects the transition
   - User is offered: "You're describing a specific application. Shall I start structured qualification (create a case)?"
   - Seamless transition preserves all context entered so far

6. **Output class:**
   - Knowledge queries produce `conversational_answer` output (existing base SSoT §10 class)
   - But with enriched metadata: source citations, related concepts, suggestion to deepen into a case

7. **No persistence without consent:**
   - Anonymous knowledge sessions allowed (lowest barrier to entry — supports North Star §2.2 asynchronous respect)
   - Saving the session or dispatching any inquiry requires registration (consistent with Decision #6 tenant model)

**Effort estimate:** M (medium). Knowledge base curation + knowledge service + Pre-Gate Classifier extension + bridge logic.

**Sequencing:** Can be developed in parallel with other services once Decision #1 foundation is in place. The knowledge base content curation is itself substantial (50-100 entries) but can start immediately using existing Authority documents and technical literature.

**Dependencies to other decisions:**
- Extends Decision #5 (fifth Pre-Gate value)
- Uses Decision #1 infrastructure (services under `backend/app/services/`)
- Feeds into Decision #6 golden case pipeline (successful knowledge-to-case bridges can become training data)
- Integrates with Decision #7 (norm modules expose their content to the knowledge base for user education)

**Strategic significance:**
Knowledge queries are what elevate SeaLAI from a matchmaking tool to a consultative platform. The North Star §3.3 principle ("Teach while qualifying") only works if users can actually come with questions, not just with cases. Making this a first-class mode — with curated content and attribution — is what prevents SeaLAI from becoming a commodity LLM wrapper.

---

## Meta-decision — Transition strategy

**Founder decision:** **Selective Rewrite.** Core services are built greenfield; valuable existing structures are retained (strangler pattern); obsolete artifacts are removed.

**Rationale captured:**
- Audit identified two XL-REPLACE blocks (persistence layer, services layer) that cannot be incrementally improved because critical components do not exist yet
- Audit simultaneously identified valuable KEEP substance (topology.py, three-mode gate, output contract logic, observability, audit logger) that would be wasteful to discard
- Pure Greenfield would discard working product substance
- Pure Strangler would self-deceive because fundamental layers don't exist to be "gradually improved"
- Selective Rewrite combines both: Greenfield for missing foundations, Strangler for existing value

**Strategy breakdown:**

### Greenfield (build new, no legacy code)
- Persistence layer extensions: `mutation_events`, `outbox`, `risk_scores`, extended `cases` schema with tenant_id
- Service layer (new files under `backend/app/services/`):
  - `case_service` with `apply_mutation()`
  - `phase_gate_service`
  - `pre_gate_classifier`
  - `output_classifier` (extracted from oversized node)
  - `inquiry_extract_service`
  - `anonymization_service`
  - `knowledge_service`
  - `terminology_service`
  - `risk_engine` with PTFE-specific dimensions
  - `compatibility_service`
  - `outbox_worker`
  - `norm_modules/` (DIN 3760, ISO 6194, EU food contact, FDA food contact)
  - `output_validator`
  - `formula_library`
  - `projection_service`
- Schema layer: `backend/app/domain/` as top-level, with proper four-layer separation per supplement v1 §35
- New tables: `manufacturer_profiles`, `manufacturer_capability_claims`, `generic_concepts`, `product_terms`, `term_mappings`, `inquiry_extracts`, `golden_cases`, `rca_early_access`

### Strangler (preserve, refactor in place)
- `agent/graph/topology.py` — structure preserved, nodes shrink as logic moves to services
- Three-mode gate — preserved as-is, only augmented by Pre-Gate Classifier
- Oversized nodes (intake_observe, matching, output_contract, rfq_handover) — business logic extracted to services, nodes become thin orchestrators
- Observability, audit logger — preserved and extended

### Remove (archive or delete)
- `services/langgraph/` — after YAML rule migration to risk_engine/checks_registry
- `services/fast_brain/` — absorbed by three-mode gate's CONVERSATION mode
- `_legacy_v2/` and `_trash/` directories
- Legacy feature flags (`SEALAI_ENABLE_BINARY_GATE`, `SEALAI_ENABLE_CONVERSATION_RUNTIME`, `ENABLE_LEGACY_V2_ENDPOINT`)
- `interaction_policy.py` shim
- `ResultForm` enum (replaced by seven SSoT output classes)
- Old endpoints (`langgraph_v2.py`, `fast_brain_runtime.py`) after deprecation period

**Sequencing principles:**
1. Persistence foundation first (case_service + mutation_events + outbox + extended cases schema)
2. Authority-driven services next (pre_gate_classifier, output_classifier, terminology_service, capability_claim tables)
3. Node refactoring in parallel (shrink oversized nodes as services become available)
4. Knowledge service and norm modules as the last MVP feature wave
5. Legacy cleanup as each replacement lands, not at the end

**Effort estimate:** Total XL. Realistic horizon: 6-12 weeks of focused work for a single developer working part-time, 3-6 weeks full-time. This is not a weekend sprint.

**Success criteria:**
- All acceptance criteria for each of the eight decisions met
- Test suite passes for core paths (case creation, mutation, inquiry dispatch, knowledge query)
- No upward imports across schema layers
- No LangGraph imports in services
- Moat invariants verifiable via automated checks
- Golden case pipeline operational
- One successful end-to-end PTFE-RWDR case from user input to manufacturer dispatch

---

**Document end.** Total decisions captured: 8 (7 audit-originated + 1 emergent) + 1 meta-decision on transition strategy. This document is the authoritative input for Phase 1a implementation planning.
