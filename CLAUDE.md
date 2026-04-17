@AGENTS.md

# CLAUDE.md — SeaLAI Project Instructions for Claude Code
**Version:** 4.0
**Datum:** 2026-04-17
**Status:** Binding Claude Code project memory
**Purpose:** Claude-specific execution rules for working safely inside the SeaLAI repository

> This file extends `AGENTS.md` for Claude Code.
>
> If there is any conflict, precedence is:
> 1. `konzept/sealai_product_north_star.md` (product truths — what SeaLAI is for)
> 2. `konzept/sealai_ssot_architecture_plan.md` (base SSoT — architectural foundation)
> 3. `konzept/sealai_ssot_supplement_v1.md` (LangGraph role, consistency, schema layering, persistence)
> 4. `konzept/sealai_ssot_supplement_v2.md` (positioning, moat, MVP scope, terminology, capability, business logic)
> 5. `konzept/sealai_engineering_depth_ptfe_rwdr.md` (binding for all PTFE-RWDR engineering decisions)
> 6. `konzept/founder_decisions_phase_1a.md` (implementation-level decisions on 8 architectural questions + transition strategy)
> 7. `AGENTS.md`
> 8. this `CLAUDE.md`
>
> Product North Star is at the top because all technical decisions ultimately serve product purpose. If a technical decision seems to optimize correctly but feels wrong, check it against the North Star first.
> Where supplements conflict with the base SSoT on the same topic, the supplement wins (newer, addresses gaps identified during architectural review).
> Where the engineering depth guide conflicts with any SSoT document on PTFE-RWDR fields, the depth guide wins for PTFE-RWDR fields only.
> Founder Decisions are implementation-level reference: they translate SSoT into concrete commitments (schema changes, service boundaries, strategy choice). They do not override SSoT or North Star, but they fix the specific interpretation that has been chosen.

---

## 1. What Claude Code must do first

For any non-trivial task, Claude must begin with a read-only understanding phase.

Before changing code, Claude must:
- inspect the real implementation
- inspect the current wiring
- inspect the relevant tests
- inspect the relevant docs
- compare current code against the full authority set (Product North Star + SSoT + supplements + engineering depth + founder decisions)
- identify the smallest clean patch sequence

Do not jump directly into implementation for architectural work.

---

## 2. Required source-of-truth reading order

Before any architectural, backend, routing, state, cockpit, readiness, export, or domain task, Claude must read in this order:

1. `konzept/sealai_product_north_star.md` — product truths, user/manufacturer value, non-negotiables
2. `konzept/sealai_ssot_architecture_plan.md` — architectural foundation
3. `konzept/sealai_ssot_supplement_v1.md` — LangGraph role, consistency, schema layering, persistence
4. `konzept/sealai_ssot_supplement_v2.md` — positioning, moat, MVP scope, terminology, capability, business logic
5. `konzept/sealai_engineering_depth_ptfe_rwdr.md` — PTFE-RWDR engineering depth
6. `konzept/founder_decisions_phase_1a.md` — 8 implementation decisions + Selective Rewrite strategy
7. `AGENTS.md` (already imported here)
8. `konzept/SEALAI_KONZEPT_FINAL.md` — product/business narrative (subordinate)
9. `konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md` — communication target image (subordinate; may be stale, review separately)
10. `konzept/SEALAI_STACK_ARCHITEKTUR.md` — runtime/infrastructure reference only

### Rule
- The Product North Star is the compass: what SeaLAI is for, what it must never become, how it treats users and manufacturers. When in doubt, return here.
- The base SSoT is the architectural foundation.
- Supplement v1 (chapters 33–36) adds LangGraph orchestration role, consistency model, four-layer schema separation, and persistence model.
- Supplement v2 (chapters 37–43) adds positioning, moat, MVP scope boundary, terminology mapping registry, manufacturer capability model, and business logic constraints.
- The engineering depth guide is binding for PTFE-RWDR engineering decisions (schema fields, risk thresholds, failure-mode taxonomy, check calculations).
- Founder Decisions fix the specific interpretation of open architectural questions and the transition strategy (Selective Rewrite).
- `SEALAI_KONZEPT_FINAL.md` and `SEALAI_KOMMUNIKATION_ZIELBILD.md` are subordinate product/business context.
- `SEALAI_STACK_ARCHITEKTUR.md` is runtime/infrastructure reference only.
- If any older implementation detail conflicts with the current authority set, the current authority wins.

### Conflict handling
Where documents disagree on a specific rule:
- Product North Star > any technical document (for product-purpose questions)
- Newer supplement > older supplement > base SSoT (for the same technical topic)
- Engineering depth guide > any SSoT document (for PTFE-RWDR-specific fields only)
- Founder Decisions specify the chosen interpretation where SSoT left options open; they do not contradict SSoT
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
- knowledge base curation and knowledge service changes
- tenant model / authorization changes

### 3.3 Do not skip directly to edits when
- multiple layers are affected
- the task touches backend + frontend
- the task changes architecture or contracts
- the task changes canonical truth
- the task touches the moat layers defined in supplement v2 §37
- the task touches any of the 8 founder decisions

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

### 4.3 Product invariants (Product North Star)
- Users never feel stupid — SeaLAI guides without judging (North Star §2.1)
- Consultation is asynchronous by design — users return whenever they have time (North Star §2.2)
- SeaLAI understands before it advises — precise picture before solution (North Star §3.1)
- SeaLAI validates proactively — the user's current seal may not be optimal (North Star §3.2)
- SeaLAI teaches while qualifying — every question is also an explanation (North Star §3.3)
- Heterogeneous input is first-class — photos, article numbers, datasheets, free text all accepted (North Star §4)
- Small quantities are first-class — 1-10 pieces filtering as Manufacturer Capability Claim (North Star §5)
- Price context yes, price comparison no — not in MVP (North Star §6)

### 4.4 Moat invariants (supplement v2 §37)
Every feature, contract, or UI decision must preserve:
- **Layer 1 — Structural neutrality**: no manufacturer influence on ranking outside declared sponsored zones; all sponsored content is explicitly labeled at every surface
- **Layer 2 — Technical translation**: matching operates on structured concepts and capability claims, never on marketing text or free-text similarity
- **Layer 3 — Request qualification**: cases reaching manufacturers are structured, parameterized inquiry packages with explicit open-points and assumptions

If a proposed change weakens any moat layer, it must justify the trade-off explicitly. If no justification is credible, the change is rejected.

### 4.5 The five non-negotiables (Product North Star §7)
SeaLAI must never become:
- a catalog (displays products without understanding problems)
- a marketing funnel (sponsored content influences matching)
- a price aggregator (collapses technical fit into price competition)
- a tool that makes users feel stupid
- a tool that pretends to know what it doesn't (hallucinated engineering)

And SeaLAI must never bypass the manufacturer's final engineering authority.

---

## 5. Claude must not reintroduce old drift

### 5.1 Obsolete architectural patterns
Do not reintroduce:
- old "Phase F / G / H" implementation logic as binding truth (superseded by the current authority set)
- legacy naming such as `governed_recommendation`
- the ms_pump-centered MVP framing (superseded by PTFE-RWDR MVP in supplement v2)
- the binary `CONVERSATION / GOVERNED` gate without the intermediate EXPLORATION mode where it already exists
- output wording that sounds like final approval
- frontend-only engineering truth
- hidden assumptions when data is incomplete
- parallel orchestration stacks (`fast_brain` vs `services/langgraph/` vs `agent/graph`) — per Decision #2, these are consolidated into the single `agent/` stack
- `RoutingPath` and `ResultForm` as separate concepts — per Decision #5, `RoutingPath` is replaced by `PreGateClassification` (5 values) and `ResultForm` is removed (7 SSoT output classes are the single output classification)

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
If current code still reflects historical patterns (RWDR-first implementation traces from pre-SSoT era, `_legacy_v2`, `services/langgraph/` duplicates, `services/fast_brain/`, Phase-F-era `interaction_policy.py`, etc.), report it explicitly and isolate it instead of expanding it.

Per Decision #2 (Selective Rewrite strategy):
- `services/langgraph/` and `services/fast_brain/` are scheduled for removal after YAML rule migration to risk_engine / checks_registry
- Their removal is not optional; it is a planned transition step

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

Knowledge query responses (Decision #8) must cite sources with explicit attribution. "SeaLAI says" is never sufficient; source reference (norm §, datasheet, terminology registry entry) is required for factual claims.

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
- tenant_id (rare, but changes downstream visibility)

then Claude must assume:
- dependent derived values can become stale
- readiness may need downgrade
- inquiry state may need invalidation
- recompute may be required
- affected risk scores must be recomputed per supplement v1 §34

Do not implement optimistic persistence of outdated derived values.

Mutation events are first-class (supplement v1 §34.3–34.4; Decision #1). Every case change flows through `case_service.apply_mutation()` with optimistic locking on `case_revision`. LangGraph nodes do NOT write directly to Postgres (supplement v1 §33.4).

---

## 8. Implementation style

Claude must prefer:
- smallest clean patch
- explicit contracts
- deterministic modules
- adapter seams over large rewrites (where Strangler is applicable)
- greenfield construction for missing foundations (where Selective Rewrite is applicable)
- versioned and testable logic
- evidence-based change reports
- services under `backend/app/services/` that are testable without LangGraph imports (supplement v1 §33.8)
- four-layer schema separation: domain / models / schemas / agent-state (supplement v1 §35)

Claude must avoid:
- repo-wide speculative rewrites
- mixing documentation cleanup with domain refactors in one patch
- changing architecture and UI semantics together without a clean contract
- duplicating rules that already live in the authority set or AGENTS
- business logic inside LangGraph nodes (supplement v1 §33.4)
- upward imports across the schema layers (supplement v1 §35.8)

### 8.1 Selective Rewrite awareness (Founder Decisions meta-decision)
The transition strategy is Selective Rewrite:
- **Greenfield**: persistence extensions, new services (case_service, output_classifier, pre_gate_classifier, inquiry_extract_service, anonymization_service, knowledge_service, terminology_service, risk_engine, compatibility_service, outbox_worker, norm_modules, output_validator, formula_library, projection_service), new tables for capability/terminology/knowledge/extracts
- **Strangler**: preserve topology.py, three-mode gate, observability, audit logger; shrink oversized nodes by extracting logic to services
- **Remove**: services/langgraph/, services/fast_brain/, _legacy_v2/, ResultForm enum, legacy feature flags, interaction_policy.py shim after consumer migration

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
- verify tenant isolation where applicable (Decision #6)
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
- **Product North Star** (`sealai_product_north_star.md`) = product compass, user/manufacturer value, non-negotiables
- **Base SSoT** (`sealai_ssot_architecture_plan.md`) = architectural foundation
- **Supplement v1** = technical implementation pillars (LangGraph role, consistency, schema layering, persistence)
- **Supplement v2** = positioning, moat, MVP scope, terminology, capability, business logic
- **Engineering depth guide (PTFE-RWDR)** = fact-dense engineering reference for MVP depth
- **Founder Decisions** = implementation-level choices on the 8 open architectural questions + transition strategy
- **AGENTS.md** = working contract for Codex and similar agents
- **CLAUDE.md** (this file) = Claude-specific execution rules
- **KONZEPT_FINAL** = product/business concept narrative (subordinate)
- **KOMMUNIKATION_ZIELBILD** = communication target (subordinate, may be stale; review separately)
- **STACK_ARCHITEKTUR** = infrastructure/runtime reference

If documentation changes are needed:
- update the smallest correct document
- do not duplicate architecture across files
- if a new engineering path reaches production depth, add a dedicated engineering depth guide (parallel to the PTFE-RWDR one)
- if a task reveals contradictions between authority documents, report them explicitly before patching
- if a Founder Decision needs revision, mark the change explicitly and request founder confirmation; do not silently rewrite decisions

---

## 11. Preferred Claude workflow in this repo

Use this sequence:

1. Read the relevant authority documents (see §2) in the prescribed order
2. Inspect relevant code
3. Inspect tests and contracts
4. Produce delta report against the full authority set
5. Verify moat invariants for any user-facing or matching change
6. Verify Product North Star alignment for any user-interaction or user-experience change
7. Propose smallest patch sequence
8. Implement one patch at a time
9. Validate
10. Report exact evidence

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
- Knowledge queries (Decision #8) in MVP are PTFE-RWDR-focused with 50-100 curated entries; broader topics return "I don't have detailed information on this specific question"
- Norm modules (Decision #7) in MVP: DIN 3760/ISO 6194 + EU 10/2011 + FDA 21 CFR 177.1550 full gates; ATEX as capability flag

---

## 13. Conflict-of-interest awareness

The founder is employed at a PTFE-RWDR manufacturer (supplement v2 §38.6; Decision #3). This creates binding constraints:

- The founder's employer, if listed as a manufacturer, receives exactly the same treatment as any other manufacturer — same onboarding, same fees, same matching algorithm
- No configuration flag, no dataset tuning, no algorithmic exception may introduce bonuses or demotions for the employer
- Data firewall: no employer-proprietary data enters SeaLAI code or datasets (confirmed clean per Decision #3)
- The COI relationship is publicly disclosed (founder bio, employer profile if listed)

Any code change that could plausibly introduce asymmetric treatment of the founder's employer must be flagged explicitly in the change report.

---

## 14. Tenant and ownership model (Decision #6)

Claude must respect the three-role data access model:

### 14.1 User owns the case
- Every case has a `tenant_id` referring to the user (design engineer, maintenance engineer, purchaser)
- Users see only their own cases
- Case conversation history, evidence (photos, notes), derived parameters belong to the user

### 14.2 Manufacturer receives inquiry extract, not the case
- Manufacturers see `inquiry_extracts`, not full case objects
- Inquiry extracts are structured, technical, anonymized
- No user PII, no conversation history, no non-technical fields
- Dispatch requires explicit user consent

### 14.3 SeaLAI has analytics-only access
- Anonymized aggregates for product improvement
- Golden cases (anonymized successful cases) for training/testing/regression
- PII removal is automated and enforced by `anonymization_service`

Any query or code path that returns case data must filter by role and tenant. No cross-tenant leaks are tolerated.

---

## 15. Knowledge query mode (Decision #8)

Claude must recognize knowledge queries as a first-class interaction mode, not as generic LLM fallback:

- Pre-Gate Classification has 5 values: `GREETING`, `META_QUESTION`, `KNOWLEDGE_QUERY`, `BLOCKED`, `DOMAIN_INQUIRY`
- `KNOWLEDGE_QUERY` uses a curated, versioned knowledge base (50-100 PTFE-RWDR-focused entries in MVP)
- Every factual claim in a knowledge response cites a source (norm §, datasheet, terminology registry entry)
- No invented facts; when no relevant entry exists, respond honestly that information is not available
- Seamless bridge from knowledge to case when the user moves from general question to specific application
- Anonymous knowledge sessions allowed; persistence requires registration

---

## 16. Final rule

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
- more user dignity (never makes the user feel stupid — North Star §2.1)
- more source attribution in knowledge responses

Where uncertainty remains after consulting all authority documents, ask before patching. Silent reinterpretation of ambiguous rules is the most dangerous failure mode and must be avoided.

The Product North Star is the ultimate tiebreaker: when technical purity and product purpose conflict, product purpose wins.

