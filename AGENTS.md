# AGENTS.md

## Purpose

This repository builds **SeaLAI** as a conversation-first, governed engineering system for sealing technology.

SeaLAI is not a generic chatbot, not a supplier directory, not a product catalog, not a price-comparison marketplace, and not a final engineering approval engine.

SeaLAI is the technical qualification and decision-support layer between an unclear industrial sealing problem and a manufacturer-ready, evidence-backed RFQ.

The long-term target may include validated seal lifecycle management through a Seal Passport / Dichtstellenpass, post-RFQ validation, private reorder workflows, price-validity checks, human engineering review, and commercial partner models. These are not automatically MVP scope.

This file is the binding operating contract for coding agents working in this repository, especially Codex CLI, Claude Code, Gemini CLI, Antigravity, and similar autonomous coding agents.

Keep this file practical. Product and architecture depth belongs primarily in `konzept/konzept_sealing.md`. This file tells agents how to work safely in the repo.

---

## Required first read

Before any non-trivial task, read from the repository root:

1. `AGENTS.md`
2. `konzept/konzept_sealing.md`
3. Relevant implementation files and tests for the task

For UI, layout, cockpit, chat workspace, cards, rails, tabs, motion, styling, responsive behavior, or frontend interaction work, also read:

4. `frontend/DESIGN.md`

Do not work from memory when the current file exists in the repo. The current repository content is the evidence.

---

## Binding authority order

When documents, code, or prior notes disagree, use this order:

1. `konzept/konzept_sealing.md` — current binding SeaLAI product and architecture SSoT.
2. `frontend/DESIGN.md` — binding frontend design SSoT for UI, motion, spacing, tokens, cockpit, chat workspace, and responsive behavior.
3. `AGENTS.md` — binding coding-agent operating contract.
4. Current production code and tests — evidence of current contracts and seams, not automatic product truth.
5. Older concept files, supplements, prompts, chat notes, audit notes, or legacy implementation notes — historical context only.

Rules:

- `konzept/konzept_sealing.md` is the current SSoT. Older concept versions must not override it.
- Current code may be legacy, provisional, or misaligned. Do not assume it is correct.
- Fix misalignment through small, evidence-based patches, not broad rewrites.
- Do not add chat citations, `filecite` markers, or conversation artifacts to production docs.
- Do not turn `AGENTS.md` into a second concept document. Keep implementation guidance here; keep product depth in `konzept/konzept_sealing.md`.

---

## Product north star

Build SeaLAI as:

> **a technical qualification and decision-support system that turns unclear sealing situations into understandable, governed, manufacturer-ready RFQ preparation.**

SeaLAI must help users:

- understand their sealing situation
- see what is known, missing, ambiguous, stale, risky, or unconfirmed
- make better technical decisions before requesting a seal
- produce a structured, manufacturer-ready RFQ preview/export
- optionally, in later phases, request human engineering review, CAD/FEM plausibility support, or RFQ concierge support
- optionally, in later phases, preserve validated solutions in a Seal Passport / Dichtstellenpass for safe reorder workflows

SeaLAI must help manufacturers:

- receive better qualified RFQs
- see technical context, open points, evidence, and revision status
- avoid low-quality leads
- participate in problem-first matching without buying technical rank
- eventually maintain capability evidence, price validity, and reorder readiness for validated solutions

---

## Phase-1 MVP cut

`konzept/konzept_sealing.md` contains the target architecture and later-phase direction. Do not implement the full target image as one task.

### Phase 1 MVP scope

Unless explicitly instructed otherwise, implementation work should prioritize only:

1. Chat intake for technical sealing situations.
2. Pre-gate routing and runtime dispatch boundaries.
3. Governed Case-State.
4. `CaseField`, `FieldStatus`, `EngineeringValue`, provenance, and evidence-ready structures.
5. Governor hardening: schema validation, unit normalization, field status, conflict detection, event append, and revisioning.
6. Dependency/stale handling and deterministic calculation cascade for simple, well-defined values.
7. Readiness model.
8. Backend projection for cockpit status.
9. Decision Understanding MVP.
10. RFQ preview/export.
11. RFQ freeze revision and explicit consent.
12. Upload/document evidence basics, where uploaded values remain candidates until governed.

### Phase 1 domain focus

Phase 1 focuses on:

- rotating shafts
- agitators / Rührwerke
- pumps
- general rotary sealing positions
- PTFE-RWDR-near cases
- classical RWDR cases as prequalification
- mechanical-seal direction as shallow routing for pump / higher-pressure / demanding-media cases

Other sealing paths may be recognized and routed shallowly, but must not be deeply designed unless explicitly tasked.

### Out of Phase 1 unless explicitly tasked

Do not start with:

- automatic manufacturer matching
- public marketplace/shop
- payment flow
- merchant-of-record behavior
- automated provision logic
- full Seal Passport lifecycle
- private reorder checkout
- manufacturer dashboard
- ERP/CRM integration
- automatic FEM pipeline
- broad multi-country compliance engine
- broad self-service manufacturer portal

These may be later phases, but they must not distort the core governed runtime.

---

## Later-phase features

The following are target-direction features, not default MVP work:

- manual manufacturer capability registry
- manual matching pilot
- manufacturer feedback loop
- problem-first matching audit
- verified capability profiles
- human engineering review request objects
- RFQ concierge workflow
- CAD/FEM partner workflow
- post-RFQ validation lifecycle
- Seal Passport / Dichtstellenpass
- private reorder request
- price validity and manufacturer confirmation
- commercial governance and provision audit
- ERPNext / CRM export or integration

Only work on these if the user explicitly asks for that phase or file.

---

## Discovery-first rule

Architecture must not outrun market validation.

Before implementing Phase 2+ systems, prefer tasks that support or clarify:

- 8–12 user interviews
- 5–8 manufacturer interviews
- 5–10 real RFQ cases
- RFQ quality feedback
- falsifiable hypotheses around user value and manufacturer willingness to pay
- kill criteria for matching, reorder, FEM, and commercial models

Do not treat matching, reorder, FEM, or manufacturer dashboards as validated just because they exist in the long-term concept.

---

## Non-negotiable product boundaries

SeaLAI must not claim:

- guaranteed suitability
- final engineering release
- manufacturer approval unless explicitly documented
- validated operation before post-RFQ feedback exists
- compliance approval without evidence
- current reorder price without manufacturer confirmation
- technical rank improvements due to sponsorship

Allowed language:

- technically plausible
- suitable for manufacturer review
- based on current information
- still to be confirmed
- open point
- documented / user-stated / calculated / inferred / confirmed
- validated by feedback, if actually recorded

Forbidden language:

- guaranteed
- final release
- surely fits
- approved, unless a real approval record exists
- compliant, unless actual compliance evidence exists
- proven in operation, unless validation exists

---

## Core architectural invariants

### 1. One coherent visible speaker

The user experiences one calm, senior sealing engineer. Multiple backend components may contribute, but the visible answer must feel coherent, precise, and trustworthy.

### 2. LLM is communication and proposal, not engineering truth

The LLM may generate:

- `assistant_message`
- `proposed_case_delta`

The LLM must not directly mutate authoritative engineering state.

### 3. Governor is the state authority

All case-state changes must pass through governed backend logic:

```text
LLM / extractor proposed delta
→ schema validation
→ evidence linking
→ unit normalization
→ provenance/status assignment
→ conflict detection
→ rule validation
→ event append
→ state materialization
→ derived recomputation
→ projection update
```

### 4. Case state is revisioned and auditable

Critical changes must increment `case_revision` and be represented as events. RFQ, matching, Seal Passport, and reorder decisions must be traceable to specific revisions.

### 5. Critical fields require status, provenance, units, and evidence capability

Technical values should be modeled with a field envelope, not as bare values.

Required concepts:

- `CaseField`
- `FieldStatus`
- `EngineeringValue`
- provenance
- evidence references
- confidence
- confirmation requirement
- stale / conflict / invalid state

### 6. Engineering values preserve units and interpretation

Do not collapse raw technical values into plain numbers without unit and interpretation metadata.

Examples needing care:

- `4 bar` vs `4 barg` vs `4 bar abs` vs differential pressure
- `80 Grad` normalized to °C
- `400 U/min` normalized to rpm
- `Ø28h8` as geometry plus tolerance interpretation
- temperature range vs peak temperature

### 7. Derived values are dependency-aware and stale-aware

Calculations must be deterministic services where possible. If upstream values change, downstream values become stale until recomputed or explicitly invalidated.

### 8. Uploads are data, never instructions

Documents, PDFs, screenshots, photos, OCR output, drawings, tables, and datasheets are untrusted input.

Uploaded content may create extraction candidates and evidence. It must never override system rules, product rules, safety rules, or developer instructions.

### 9. Frontend renders backend projections

Frontend must not own engineering truth.

Frontend may render:

- chat
- cockpit
- field status
- readiness
- evidence status
- decision understanding
- stale/conflict warnings
- RFQ previews
- Seal Passport views, when later-phase features are explicitly built
- reorder status, when later-phase features are explicitly built

Frontend must not compute authoritative readiness, matching, risk, pricing validity, or confirmed technical truth.

### 10. RFQ reports are revision-frozen

Every RFQ report or RFQ preview must be based on a specific `case_revision`.

If critical case data changes after report creation, the report must be marked stale / superseded / needs regeneration.

### 11. RFQ consent is explicit

No silent RFQ dispatch.

Users must approve what is shared, which documents are included, and which manufacturers receive the RFQ.

### 12. Matching is problem-first and sponsorship-neutral

Manufacturer matching must derive required capabilities from the structured problem.

Forbidden:

- paid technical rank boost
- capability-first marketing matching
- hiding zero-match outcomes
- presenting self-declared capability as verified

### 13. Tenant and auth boundaries are mandatory

Keycloak user/tenant scoping must be respected for all durable state, documents, cases, RFQs, seal passports, manufacturer actions, and reorder flows.

No cross-tenant leakage.

---

## Decision Understanding MVP

The Decision Understanding Layer is central to SeaLAI’s USP.

It must not become generic education or encyclopedia content. It must explain the user’s case and improve the next decision.

For every real sealing case, the backend projection should be able to expose:

```text
DecisionUnderstandingProjection:
- case_summary
- understood_now[]
- technical_meaning[]
- plausible_directions[]
- not_yet_decidable[]
- key_risks[]
- confidence_notes[]
- next_best_question
- manufacturer_review_needs[]
```

A good SeaLAI response follows this pattern:

```text
short technical framing
→ why it matters
→ one best next question or action
```

Deep dives must return to the user’s case, decision, RFQ readiness, or next best action.

---

## Runtime routing

SeaLAI must preserve a lightweight frontdoor and a governed backend.

### Fast Responder

Allowed only for:

- `GREETING`
- `META_QUESTION`
- `BLOCKED`

Rules:

- no case creation
- no durable engineering state write
- no full graph invocation
- fast response
- persona-consistent

If classification is ambiguous, fail safe toward the governed path.

### Knowledge Query

For general sealing knowledge, material comparisons, terminology, and learning before a real application exists.

Rules:

- no forced case creation
- may use knowledge service / retrieval
- may bridge to case if the user transitions into real application data
- must distinguish general explanation from case-specific assessment

### Governed Domain Inquiry

For real applications, operating data, RFQ intent, technical preselection, upload-derived case data, calculations, risk, readiness, RFQ, matching, Seal Passport, and reorder.

Rules:

- uses governed state
- may use LangGraph if appropriate
- must remain auditable and projection-driven

---

## State authority hierarchy

Preferred authority order:

1. Postgres durable case / RFQ / Seal Passport truth
2. Redis live/session/checkpoint state
3. LangGraph turn state
4. Frontend rendering state

Rules:

- frontend is never authoritative for engineering truth
- Redis-only truth must not become the only durable basis for RFQ, Seal Passport, or reorder
- LangGraph state is orchestration state, not final durable truth
- all projections should state what backend source they represent

---

## Required service seams

Prefer explicit services over route-heavy or prompt-only logic.

Phase-1 or near-term target seams include:

- `dispatch` / pre-gate routing authority
- `fast_responder_service`
- `knowledge_service`
- `bridge_to_case_service`
- `governor` / state mutation service
- `case_event_service`
- `engineering_value_service`
- `unit_normalization_service`
- `evidence_service`
- `field_promotion_policy`
- `conflict_detection_service`
- `dependency_graph_service`
- `calculation_registry`
- `calculation_cascade_service`
- `risk_evaluator`
- `readiness_evaluator`
- `medium_intelligence_service`
- `decision_understanding_projection`
- `cockpit_projection_service`
- `rfq_report_service`
- `rfq_freeze_service`
- `rfq_consent_service`
- `document_security_service`
- `document_extraction_service`

Later-phase seams may include:

- `manufacturer_capability_service`
- `problem_first_matching_service`
- `matching_audit_service`
- `human_engineering_review_service`
- `post_rfq_validation_service`
- `seal_passport_service`
- `reorder_service`
- `price_validity_service`
- `commercial_governance_service`

If a productive seam already exists under another name, tighten or refactor that seam. Do not create a parallel architecture.

---

## Coding-agent operating model

### Default: audit first, patch second

For any non-trivial task:

1. Read current SSoT and relevant code/tests.
2. Map the existing productive seam.
3. State what is true now.
4. State the specific misalignment.
5. Propose the smallest productive patch.
6. Patch only that seam.
7. Add or update focused tests.
8. Run relevant validation.
9. Report exact files changed, commands, risks, and next patch.

### For architecture-heavy tasks

Start with a read-only audit unless explicitly asked to patch.

Do not implement the target architecture as a big-bang task. The concept is the product and architecture direction; implementation must be phased, minimal, and testable.

### Patch-size policy

A good patch:

- touches one architectural seam or bounded behavior
- has clear before/after behavior
- adds or updates focused tests
- leaves the system more aligned with SSoT
- avoids speculative abstractions

A bad patch:

- mixes state models, UI, routing, RFQ, matching, and business logic
- creates many new files without proving the seam
- hides broad rewrites inside a “small patch”
- adds dead future code
- duplicates a messy existing service instead of improving the real seam

---

## Required reporting format for patch work

Every implementation summary should use:

### 1. Short diagnosis

What is true now? What is the exact gap?

### 2. Exact files changed

List only changed files.

### 3. Why these files

Explain the productive seam.

### 4. Behavioral delta

What changed at runtime?

### 5. Validation

Commands run from `/home/thorsten/sealai` and results.

### 6. Risks / limitations

What remains unresolved by design?

### 7. Next productive patch

The smallest sensible next move.

---

## Validation policy

Every meaningful patch must include validation.

Minimum:

- focused unit or contract tests where possible
- exact validation commands
- expected behavior
- no hand-wavy “should work”

Preferred validation types:

- unit tests for services
- API contract tests for envelopes
- projection tests for cockpit and decision understanding
- routing boundary regression tests
- deterministic calculation tests
- RFQ freeze / consent tests
- matching audit tests, when matching is explicitly in scope

Later-phase validation may include:

- post-RFQ validation tests
- Seal Passport lifecycle tests
- price validity tests
- commercial governance tests

### Repo-root command rule

Always provide commands from:

```bash
/home/thorsten/sealai
```

Examples:

```bash
cd /home/thorsten/sealai && pytest backend/app/agent/tests -q --maxfail=1 --ignore=backend/app/agent/tests/test_agent_health.py
```

```bash
cd /home/thorsten/sealai && pytest backend/tests -q --maxfail=1
```

```bash
cd /home/thorsten/sealai && (cd frontend && npm run build)
```

Before inventing frontend commands, inspect `frontend/package.json`. Before inventing backend commands, inspect existing test structure and config files.

---

## Frontend rules

`frontend/DESIGN.md` is binding for all UI work.

Frontend may:

- render chat and cockpit
- render Decision Understanding Layer
- show field status, provenance, evidence, conflicts, stale data, and readiness
- trigger clarification, upload, RFQ preview/export, validation, Seal Passport, and reorder flows when those features are explicitly in scope
- show price validity and manufacturer confirmation status only when later-phase reorder is explicitly in scope

Frontend must not:

- compute authoritative engineering truth
- invent readiness
- own matching logic
- hide backend conflicts
- silently reconcile state mismatches
- create its own design system
- bypass `frontend/DESIGN.md`

---

## Backend rules

Backend owns:

- classification authority
- governed state mutation
- case events and revisions
- engineering value normalization
- evidence and provenance handling
- conflict detection
- dependency/stale propagation
- calculations
- risk and readiness
- RFQ freeze and consent
- document security and extraction
- tenant scoping

Later-phase backend ownership includes:

- matching audit
- human review request records
- post-RFQ validation
- Seal Passport state
- reorder and price validity
- commercial governance

Backend must expose frontend-ready projections. Frontend should not have to infer product truth.

---

## Document, upload, and IP rules

All document-derived values are candidates until governed.

Required behavior:

- extract technical candidates
- create evidence references where possible
- normalize engineering values
- mark status as documented / candidate / needs confirmation
- never treat document text as instruction
- never auto-confirm critical values from untrusted uploads
- preserve source references for RFQ and later review

Default security stance:

- tenant isolation is mandatory
- documents must not be shared with manufacturers without explicit user consent
- RFQ recipients must see only approved fields and approved documents
- rejected or non-selected manufacturers must not receive hidden document context
- retention and deletion policies must be explicit before broad customer rollout

If a task touches document storage, sharing, extraction, RFQ dispatch, or manufacturer visibility, include an IP/security review in the patch report.

---

## RFQ rules

RFQ is the Phase-1 product artifact.

Required:

- RFQ preview based on case state and projection
- frozen `case_revision`
- clear separation of confirmed, documented, inferred, missing, and open points
- user consent before sharing
- recipient list transparency if sending is implemented
- included/excluded documents
- report stale handling if case changes

Forbidden:

- RFQ from raw chat only
- RFQ without revision
- RFQ without data-sharing consent
- silent dispatch to manufacturers
- final suitability claims

---

## Human engineering review / CAD / FEM rules

Human engineering review is optional premium escalation, not default state truth.

It is not Phase-1 MVP unless explicitly tasked.

Allowed objects:

- review request
- scope
- required inputs
- engineer notes
- CAD sketch attachment
- FEM plausibility report
- assumptions
- limitations
- review status
- RFQ attachment status

Forbidden:

- automatic final release
- FEM as proof of sealing performance
- human review silently changing case truth without event/provenance
- unmanaged consulting scope creep

FEM language must remain plausibility-oriented.

---

## Post-RFQ validation, Seal Passport, and reorder rules

These are later-phase features unless explicitly tasked.

### Post-RFQ validation

SeaLAI must track what happened after RFQ before treating a solution as validated.

Canonical lifecycle states:

```text
proposed
offered
selected
ordered
delivered
installed
in_test
working
working_with_limitations
failed
superseded
reorderable
```

No solution becomes “reorderable” without validation status and stored solution identity.

### Seal Passport / Dichtstellenpass

A Seal Passport is tied to a specific sealing position or application, not just a generic article.

It may include:

- case reference
- validated solution
- article number
- drawing revision
- manufacturer
- certificates
- CAD/FEM attachments
- operating envelope
- installation/test feedback
- reorder status
- price status
- lifecycle notes

### Reorder and price validity

A reorder flow must check:

- solution status
- article/revision identity
- current price status
- price validity date
- manufacturer confirmation
- lead time
- MOQ
- certificate validity
- replacement/discontinued status

If price is expired or not confirmed, show request flow, not hard checkout.

Default later-phase rule:

- standard price validity: 90 days
- manufacturer reminder: 14 days before expiry
- expired price becomes `price_on_request`
- user can submit reorder request with existing Seal Passport context

Do not build a public marketplace shop before private Seal-Passport-based reorder is stable.

---

## Commercial governance rules

Commercial models may include, in later phases:

- partner subscription
- verified capability profile
- accepted RFQ fee
- engineering review fee
- RFQ concierge fee
- reorder service fee
- success fee / provision where contractually clear

Commercial models must not:

- influence technical matching score
- hide paid relationships
- create pay-to-play technical ranking
- make SeaLAI appear neutral if it is acting as paid sales agent in a specific flow

Use transparent labels and audit trails.

Commercial governance is not Phase-1 MVP unless explicitly tasked.

---

## Matching rules

Matching is Phase 2+ unless explicitly tasked.

Required matching flow:

1. derive structured problem signature
2. derive required capabilities
3. hard-filter must-have criteria where appropriate
4. score technical fit
5. show rationale, uncertainty, missing evidence, and exclusions
6. keep sponsorship out of technical score

Capability evidence matters:

- self_declared
- documented
- platform_curated
- verified

Do not treat all capability claims equally.

Cold-start rule:

- bootstrap manufacturer capabilities manually where needed
- keep evidence levels explicit
- do not pretend unverified capability data is verified
- do not make matching the first MVP dependency if RFQ qualification is not yet reliable

---

## Knowledge and medium intelligence rules

SeaLAI may combine:

- registry-grounded knowledge
- curated tables
- user-provided facts
- document-derived facts
- LLM synthesis

But must distinguish them.

Never present plausible LLM synthesis as validated engineering truth.

Case-specific knowledge should return to:

- decision understanding
- next best question
- risk/readiness
- RFQ quality

---

## Compliance awareness

SeaLAI may touch regulated use cases such as food, pharma, chemical processing, ATEX-relevant environments, drinking water, steam, hygienic design, hydrogen, or aggressive media.

Do not treat certificates and standards as simple labels.

For regulated contexts:

- mark the requirement explicitly
- track certification evidence and validity where available
- do not claim compliance without evidence
- keep manufacturer review/final release explicit
- preserve document provenance and revision
- surface open compliance questions in RFQ output

Examples of possible regulated references include FDA, EU 1935/2004, EU 10/2011, ATEX, EHEDG, USP Class VI, drinking-water approvals, TA-Luft, and GMP.

Do not implement a full compliance engine unless explicitly tasked.

---

## Journey-level tests

Layer tests are not enough.

When implementing user-visible lifecycle behavior, add or preserve journey tests where feasible, for example:

```text
unclear problem
→ governed case
→ Decision Understanding projection
→ RFQ preview
→ RFQ freeze
→ user consent
→ manufacturer-ready export
```

Later-phase example:

```text
RFQ
→ manufacturer solution selected
→ installed/tested feedback
→ validated Seal Passport
→ reorder request with price validity check
```

Do not create broad E2E tests that require unavailable external services unless the repo already provides suitable fakes/mocks.

---

## Anti-patterns

Avoid:

1. Architecture cosplay — fancy abstractions without production value.
2. Hidden rewrites — broad changes disguised as small patches.
3. Prompt as backend — durable engineering rules only in prompts.
4. UI concealment — frontend hiding backend authority problems.
5. Duplicate truth — competing Redis/Postgres/frontend/LangGraph authorities.
6. Duplicate seam — new service beside the real messy seam.
7. Overeager persistence — cases for greetings or simple meta questions.
8. Overblocking — pushing light interactions into heavy governed flows.
9. False empathy — gushy, dramatic, or emoji-heavy voice.
10. Silent assumption loading — auto-confirming critical fields.
11. Pay-to-play matching — sponsorship influences technical fit.
12. RFQ without revision.
13. Reorder without validation.
14. Price without validity.
15. ERP gravity — ERP/CRM concerns distorting core runtime too early.
16. Big-bang target architecture — trying to implement the full target image in one patch.
17. Discovery bypass — building Phase 2+ systems without user/manufacturer validation.
18. Compliance hand-waving — treating regulated contexts as simple boolean flags.

---

## Prompting contract for coding agents

Good task prompts should include:

- Task Summary
- Architectural intent
- Current suspected seam
- Files to inspect first
- Constraints / invariants
- Expected artifacts
- Tests required
- Validation commands
- Explicit forbidden moves

For complex tasks, produce a plan or read-only audit before patching.

---

## Current stack assumptions

Assume the productive stack is approximately:

- FastAPI backend
- LangGraph-governed orchestration where appropriate
- Redis live/checkpoint layer
- Postgres durable storage
- Qdrant retrieval
- Keycloak authentication / tenant boundary
- Next.js frontend
- Dockerized deployment behind nginx
- ERPNext downstream integration, not core runtime authority

This stack is sufficient. Shape it correctly; do not replace it without explicit instruction.

---

## Glossary

### CaseField

A field envelope around a technical value. It should preserve status, provenance, confidence, evidence references, and confirmation requirements.

### EngineeringValue

A normalized technical value with unit, raw input, canonical value, and interpretation metadata.

### Governor

The backend authority that validates proposed changes, applies rules, records events, updates state, triggers recalculation, and produces projections.

### Decision Understanding Layer

The projection that explains what SeaLAI understands, why it matters, what is not yet decidable, and which next decision or question is most useful.

### RFQ Freeze

The act of binding an RFQ report or RFQ preview to a specific `case_revision` so later state changes can mark the report stale rather than silently changing it.

### Seal Passport / Dichtstellenpass

A later-phase lifecycle record for a specific sealing position, including validated solution, documents, revision, test feedback, and reorder status.

### Reorderable

A solution is reorderable only when its identity, validation status, and commercial/price status are sufficiently documented.

### Problem-first matching

Matching that begins with the user’s structured technical problem and derives required capabilities before scoring manufacturers.

---

## Final instruction

When in doubt, choose the path that:

- preserves the current SSoT
- keeps SeaLAI conversation-first for the user
- keeps engineering truth governed in the backend
- makes uncertainty visible
- preserves neutrality
- avoids duplicate architecture
- respects the Phase-1 MVP cut
- does not build Phase 2+ without explicit instruction
- produces the smallest reliable patch
- adds evidence for the next agent

SeaLAI should increasingly feel like:

> **one experienced sealing engineer on the surface, backed by a disciplined, auditable engineering system underneath.**
