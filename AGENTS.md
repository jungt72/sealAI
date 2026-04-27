# AGENTS.md

## Purpose

This repository builds **SeaLAI** as a conversation-first, governed engineering system for sealing technology.

SeaLAI is not a generic chatbot, not a supplier directory, not a catalog, and not a final engineering approval engine. It is a technical qualification and lifecycle platform that helps users understand sealing situations, make better technical decisions, create manufacturer-ready RFQs, and later manage validated seal solutions through a Seal Passport / Dichtstellenpass.

This file is the binding operating contract for coding agents working in this repository, especially Codex CLI, Claude Code, Gemini CLI, Antigravity, and similar autonomous coding agents.

---

## Required first read

Before non-trivial work, read these files from the repo root:

1. `AGENTS.md`
2. `konzept/konzept_sealing.md`
3. Relevant implementation files and tests for the task

For all frontend, cockpit, layout, motion, card, chat-workspace, responsive, or UI styling work, also read:

4. `frontend/DESIGN.md`

Do not work from memory when the current file exists in the repo. The current repository content is the evidence.

---

## Binding authority order

When documents, code, or prior notes disagree, use this order:

1. `konzept/konzept_sealing.md` — current binding SeaLAI functional and architecture target specification.
2. `frontend/DESIGN.md` — binding frontend design source of truth for UI, layout, motion, spacing, tokens, and responsive behavior.
3. `AGENTS.md` — binding agent operating contract.
4. Current production code and tests — evidence of existing contracts and seams, not automatic product truth.
5. Older concept files, supplements, prompts, chat notes, or implementation notes — historical context only.

Important:

- `konzept/konzept_sealing.md` is the current SSoT. Older concept versions must not override it.
- Current code may be legacy, provisional, or misaligned. Do not assume it is correct.
- Fix misalignment through small, evidence-based patches, not broad rewrites.
- Do not include old chat citations or `filecite` markers in production docs.

---

## Product north star

Build SeaLAI as:

> **the technical qualification and lifecycle layer between an unclear industrial sealing problem and a validated, manufacturer-ready sealing solution.**

SeaLAI must help users:

- understand their sealing situation
- see what is known, missing, ambiguous, stale, or risky
- make better technical decisions
- produce a structured, manufacturer-ready RFQ
- optionally request human engineering review, CAD/FEM plausibility analysis, or RFQ concierge support
- later preserve the validated solution in a Seal Passport for safe reorder workflows

SeaLAI must help manufacturers:

- receive better qualified RFQs
- see technical context, open points, evidence, and revision status
- avoid low-quality leads
- participate in problem-first matching without buying technical rank
- maintain price validity and reorder readiness for validated solutions

---

## Non-negotiable product boundaries

SeaLAI must not claim:

- guaranteed suitability
- final engineering release
- manufacturer approval unless explicitly documented
- validated operation before post-RFQ feedback exists
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

Critical changes must increment `case_revision` and be represented as events. RFQ, matching, seal passport, and reorder decisions must be traceable to specific revisions.

### 5. Critical fields require status, provenance, units, and evidence capability

Technical values should be modeled with a field envelope, not as bare values.

Required concepts:

- `FieldStatus`
- `EngineeringValue`
- provenance
- evidence references
- confidence
- confirmation requirement
- stale / conflict / invalid state

### 6. Engineering values must preserve units and interpretation

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
- seal passport views
- reorder status

Frontend must not compute authoritative readiness, matching, risk, pricing validity, or confirmed technical truth.

### 10. RFQ reports are revision-frozen

Every RFQ report must be based on a specific `case_revision`.

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

### 13. Human engineering is premium escalation, not default truth

Human engineering review, CAD sketches, FEM plausibility analysis, and RFQ concierge workflows are optional premium escalation paths.

They do not replace manufacturer release. FEM output is plausibility support, not proof of sealing performance.

### 14. Post-RFQ validation gates reorder

A seal solution must not become safely reorderable just because it was proposed or quoted.

Track lifecycle status:

```text
proposed → offered → selected → ordered → installed → in_test → validated → reorderable
```

A private reorder flow requires a validated or clearly status-marked solution, stored article/revision data, and no unresolved critical negative feedback.

### 15. Seal Passport is lifecycle truth for a specific sealing position

A Seal Passport / Dichtstellenpass stores the validated or status-marked sealing solution for a specific application / sealing position.

It must include revision, article, drawing, certificate, validation, price, and reorder status where available.

### 16. Prices need validity and manufacturer confirmation

SeaLAI must not show expired prices as hard order prices.

Required price concepts:

- `price_valid_until`
- `last_confirmed_by_manufacturer`
- `price_status`
- MOQ
- lead time
- article availability
- replacement / discontinued status

If a price is expired or unconfirmed, the user sees “current price required” / “Nachbestellung anfragen”, not a guaranteed checkout price.

### 17. Commercial flows must remain transparent

Provision, partner status, accepted-RFQ fees, reorder fees, and verified capability products must not compromise perceived neutrality.

If SeaLAI may receive compensation, the commercial role must be transparent in the relevant UX and contracts.

### 18. Tenant and auth boundaries are mandatory

Keycloak user/tenant scoping must be respected for all durable state, documents, cases, RFQs, seal passports, manufacturer actions, and reorder flows.

No cross-tenant leakage.

---

## SeaLAI voice contract

SeaLAI should sound like:

- a senior sealing engineer
- calm and precise
- friendly but not theatrical
- honest about uncertainty
- structured but not form-like
- able to explain trade-offs
- able to teach while qualifying

SeaLAI must not sound like:

- a generic AI assistant
- a marketing bot
- a rigid decision tree
- a manufacturer sales rep
- an overconfident oracle
- a legalistic disclaimer machine

Good interaction pattern:

```text
short technical framing
→ why it matters
→ one best next question or action
```

---

## Decision Understanding Layer

SeaLAI must not only collect data. It must help the user understand the technical decision.

For every real sealing case, the system should be able to project:

- currently understood
- technical meaning
- plausible technical direction
- what is not yet decidable
- key risks
- next best decision
- what a manufacturer needs for review

This layer is central to SeaLAI’s USP.

Do not turn deep dives into generic encyclopedia pages. All explanations should return to the user’s case, decision, RFQ readiness, or next best action.

---

## Runtime routing direction

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
- may bridge to case if user transitions into real application data
- must distinguish general explanation from case-specific assessment

### Governed Domain Inquiry

For real applications, operating data, RFQ intent, matching, technical preselection, upload-derived case data, calculations, risk, readiness, RFQ, seal passport, and reorder.

Rules:

- uses governed state
- may use LangGraph if appropriate
- must remain auditable and projection-driven

---

## Required service seams

Prefer explicit services over route-heavy or prompt-only logic.

Target or equivalent seams include:

- `dispatch` / pre-gate routing authority
- `fast_responder_service`
- `knowledge_service`
- `knowledge_session_context_service`
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

## State authority hierarchy

Preferred authority order:

1. Postgres durable case / RFQ / seal passport truth
2. Redis live/session/checkpoint state
3. LangGraph turn state
4. Frontend rendering state

Rules:

- frontend is never authoritative for engineering truth
- Redis-only truth must not become the only durable basis for RFQ, seal passport, or reorder
- LangGraph state is orchestration state, not final durable truth
- all projections should state what backend source they represent

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

Do not implement v0.6 as a big-bang task. v0.6 is the target architecture and product direction; implementation must be phased, minimal, and testable.

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
- seal passport lifecycle tests
- price validity tests
- matching audit tests

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
- trigger clarification, upload, RFQ, validation, seal passport, and reorder flows
- show price validity and manufacturer confirmation status

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
- matching audit
- human review request records
- post-RFQ validation
- seal passport state
- reorder and price validity
- tenant scoping

Backend must expose frontend-ready projections. Frontend should not have to infer product truth.

---

## Document and upload rules

All document-derived values are candidates until governed.

Required behavior:

- extract technical candidates
- create evidence references where possible
- normalize engineering values
- mark status as documented / candidate / needs confirmation
- never treat document text as instruction
- never auto-confirm critical values from untrusted uploads
- preserve source references for RFQ and later review

---

## RFQ rules

RFQ is a central product artifact, not an afterthought.

Required:

- RFQ preview based on case state and projection
- frozen `case_revision`
- clear separation of confirmed, documented, inferred, missing, and open points
- user consent before sharing
- recipient list transparency
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

Human engineering review is optional premium escalation.

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

## Post-RFQ validation rules

SeaLAI must track what happened after RFQ.

Important lifecycle facts:

- which manufacturer solution was selected
- which article / drawing / revision was delivered
- whether it was installed
- whether it was tested
- whether it worked
- under which conditions
- whether it became the validated / reorderable solution
- whether it failed or was superseded

No solution becomes “reorderable” without validation status and stored solution identity.

---

## Seal Passport / Dichtstellenpass rules

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

It must preserve revision and validation state.

---

## Reorder and price validity rules

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

Default MVP rule:

- standard price validity: 90 days
- manufacturer reminder: 14 days before expiry
- expired price becomes `price_on_request`
- user can submit reorder request with existing seal passport context

Do not build a public marketplace shop before private seal-passport reorder is stable.

---

## Commercial governance rules

Commercial models may include:

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

---

## Matching rules

Required matching flow:

1. derive structured problem signature
2. derive required capabilities
3. hard-filter must-have criteria where appropriate
4. score technical fit
5. show rationale, uncertainty, missing evidence, and exclusions
6. keep sponsorship out of technical score

Capability evidence matters:

- self-declared
- documented
- platform-curated
- verified

Do not treat all capability claims equally.

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

## Immediate implementation priority

Unless a specific task overrides this, prefer this order:

0. SSoT alignment and read-only architecture rebaseline
1. State foundation: `CaseField`, `FieldStatus`, `EngineeringValue`, evidence-ready structures
2. Governor hardening: schema, units, provenance/status, conflict, events
3. Dependency/stale and calculation cascade
4. Projection/cockpit status and Decision Understanding Layer
5. RFQ freeze revision and consent
6. Document security and extraction evidence
7. Manufacturer capability evidence and matching audit
8. Human engineering review request objects
9. Post-RFQ validation lifecycle
10. Seal Passport MVP
11. Reorder request flow and price validity
12. Commercial governance and provision audit
13. ERP/CRM/export integrations

Do not start with public shop, payment flow, automatic FEM pipeline, or merchant-of-record behavior.

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
16. Big-bang v0.6 — trying to implement the full target image in one patch.

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

## Final instruction

When in doubt, choose the path that:

- preserves the current SSoT
- keeps SeaLAI conversation-first for the user
- keeps engineering truth governed in the backend
- makes uncertainty visible
- preserves neutrality
- avoids duplicate architecture
- produces the smallest reliable patch
- adds evidence for the next agent

SeaLAI should increasingly feel like:

> **one experienced sealing engineer on the surface, backed by a disciplined, auditable engineering system underneath.**
