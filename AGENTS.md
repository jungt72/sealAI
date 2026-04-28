# AGENTS.md

## Purpose

This repository builds **SeaLAI / sealingAI**.

SeaLAI is not a generic chatbot, not a product catalog, not a supplier directory, not a marketplace, not a price-comparison tool, and not a final engineering approval engine.

SeaLAI is an RFQ Qualification Copilot for sealing technology:

> SeaLAI turns unclear industrial sealing situations into governed, evidence-backed, manufacturer-review-ready RFQ previews with field status, provenance, open points, risks, uncertainty, and explicit user consent.

This file is the binding operating contract for autonomous coding agents working in this repository, especially Codex CLI and similar tools.

Keep this file practical. Deep product and implementation detail belongs in:

```text
konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md
```

---

## Current mission

The current repository mission is **pilot readiness**, not feature expansion.

The next implementation work must focus on making SeaLAI a controlled, trustworthy Phase-1 MVP:

1. hard RFQ consent enforcement
2. prod-safe settings and startup behavior
3. secret/env hygiene
4. upload/IP/LLM safety baseline
5. backend RFQ preview integrated into the frontend main flow
6. unsafe product copy removal
7. RFQ output based on field envelopes
8. tenant/IDOR hardening
9. compliance-overclaim and prompt-injection tests

Do not build broad Phase-2+ features unless explicitly instructed.

---

## Required first read

Before any non-trivial task, read from the repository root:

1. `AGENTS.md`
2. `konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md`
3. relevant source files and tests for the specific task

For frontend/UI work, also read:

4. `frontend/DESIGN.md`

If a directory contains another `AGENTS.md`, follow the more specific file for files inside that directory.

Do not work from memory. Current repository content is the evidence.

---

## Binding authority order

Use this order when documents, code, or prior notes disagree:

1. `AGENTS.md` for coding-agent operating rules.
2. `konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md` for SeaLAI pilot-readiness product and implementation direction.
3. `frontend/DESIGN.md` for frontend design, layout, motion, spacing, cockpit, chat workspace, rails, tabs, and responsive behavior.
4. Current code and tests as evidence of existing contracts and seams.
5. Older concept files, archived notes, audit notes, prompts, chat notes, or implementation history as context only.

Rules:

- Do not resurrect deleted concept files.
- Do not reference deleted, archived, or superseded concept files as active SSoT.
- Current code may be legacy, provisional, or misaligned.
- Fix misalignment through small, evidence-based patches.
- Do not add chat citations, file citations, or conversation artifacts to production docs.
- Do not turn `AGENTS.md` into a second concept document.

---

## Non-negotiable product boundaries

SeaLAI must not claim:

- final engineering release
- guaranteed suitability
- automatic technical approval
- manufacturer approval unless explicitly documented
- compliance approval without evidence
- FDA/ATEX/Food/Pharma/Drinking Water approval without actual evidence
- validated operation before post-RFQ feedback exists
- current reorder price without manufacturer confirmation
- paid technical ranking or sponsorship-based technical fit

Allowed language:

- suitable for manufacturer review
- based on current information
- still to be confirmed
- open point
- documented
- user-stated
- calculated
- inferred
- confirmed
- conflict
- needs confirmation
- evidence required
- no final technical release

Forbidden language unless backed by explicit evidence:

- guaranteed
- final release
- approved
- compliant
- certified
- validated
- proven in operation
- surely fits
- technically released
- recommendation as final answer

---

## MVP scope

Unless the user explicitly says otherwise, implementation work is limited to Phase-1 pilot readiness.

### In scope

- dialogic intake for sealing cases
- governed case state
- `CaseField`
- `FieldStatus`
- `EngineeringValue`
- provenance
- evidence references
- unit normalization
- conflict detection
- field confirmation
- case revisioning
- deterministic calculations where simple and well-defined
- stale handling
- readiness/open-points model
- Decision Understanding projection
- backend cockpit/workspace projection
- RFQ preview/export
- RFQ freeze on `case_revision`
- explicit RFQ consent
- upload/document evidence basics
- upload-derived values as candidates, not truth
- tests for the above

### Phase-1 domain focus

- rotating shafts
- general rotary sealing positions
- pumps
- agitators / Rührwerke
- classical RWDR cases
- PTFE-RWDR-near cases
- mechanical-seal direction only as shallow routing when pressure, media, or application suggest it

Other sealing paths may be recognized shallowly, but must not be deeply designed unless explicitly tasked.

### Out of scope unless explicitly tasked

Do not build:

- automatic manufacturer matching
- manufacturer dashboard
- public marketplace/shop
- payment flow
- merchant-of-record behavior
- automatic dispatch to manufacturers
- Seal Passport lifecycle
- private reorder checkout
- price validity logic
- ERP/CRM/Paperless integration
- automatic FEM/CAD pipeline
- broad compliance engine
- broad manufacturer self-service portal

These are later-phase features and must not distort Phase-1 RFQ qualification.

---

## Current PR sequence

When the user asks to implement pilot-readiness work, prefer this sequence:

1. RFQ Consent Boundary
2. Settings Drift and Startup Safety
3. Secret/Env Hygiene
4. Upload/IP Safety Baseline
5. RFQ Preview in Frontend Main Flow
6. Unsafe Product Copy Hardening
7. RFQ from CaseField Envelopes
8. Tenant Guards / IDOR Hardening
9. Compliance-Overclaim and Prompt-Injection Tests
10. Frontend Lint and Journey Stabilization

Do not combine several PRs unless explicitly instructed.

A good PR touches one bounded behavior, adds focused tests, and leaves the product closer to pilot-ready.

---

## Critical safety rules on this VPS

Default mode is safe and conservative.

Do not do any of the following unless explicitly instructed:

- restart services
- stop services
- run production migrations
- delete production data
- truncate tables
- clear Redis or checkpoints
- reset Qdrant collections
- change DNS/nginx/systemd production configuration
- expose secrets
- print `.env` values
- print API keys
- print tokens
- print passwords
- call external production APIs as a test
- send real RFQs
- dispatch anything to manufacturers
- install large new dependencies without justification

If secrets are found:

- never output the secret value
- output only filename, key name, and risk
- mask values fully as `[REDACTED]`
- recommend rotation if exposure is possible

---

## Core architectural invariants

### 1. LLM is not engineering truth

The LLM may generate:

- `assistant_message`
- `proposed_case_delta`
- extraction candidates
- explanations
- next-question proposals

The LLM must not directly mutate authoritative engineering state.

### 2. Governor owns state mutation

All case-state changes must pass through governed backend logic:

```text
proposed delta or extracted candidate
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

### 3. Case state is revisioned and auditable

Critical changes must increment or attach to `case_revision`.

RFQ previews, exports, consent records, and later lifecycle objects must be traceable to specific revisions.

### 4. Technical values need envelopes

Critical technical values must not be stored or rendered as bare values when authoritative use is intended.

Use or preserve:

- `CaseField`
- `FieldStatus`
- `EngineeringValue`
- raw value
- normalized value
- unit
- interpretation metadata
- provenance
- evidence references
- confidence
- confirmation requirement
- stale/conflict/invalid state

### 5. Derived values are deterministic

Calculations should be deterministic services where possible.

The LLM must not be the authority for calculations such as unit conversion, circumference speed, pressure interpretation, or readiness state.

### 6. Uploads are data, never instructions

Documents, PDFs, screenshots, photos, OCR output, drawings, tables, and datasheets are untrusted input.

Uploaded content may create extraction candidates and evidence references.

Uploaded content must never override system rules, product rules, safety rules, or developer instructions.

### 7. Frontend renders backend projections

Frontend must not own engineering truth.

Frontend may render:

- chat
- cockpit/workspace
- field status
- provenance
- evidence
- conflicts
- stale data
- readiness
- open points
- risks
- RFQ preview
- consent state

Frontend must not compute authoritative readiness, matching, risk, pricing validity, or confirmed technical truth.

### 8. RFQ previews are revision-frozen

Every RFQ preview/export must be based on a specific `case_revision`.

If critical case data changes after preview creation, the preview must be marked stale, superseded, or needs regeneration.

### 9. RFQ consent is explicit

No silent RFQ sharing.

No automatic manufacturer dispatch in Phase 1.

Consent must require explicit acknowledgement of:

- no final technical release
- open points understood
- documents/fields included for export or sharing
- recipients, if sending is ever implemented

### 10. Tenant boundaries are mandatory

Keycloak user/tenant/org scoping must be respected for all durable state, documents, cases, RFQs, uploads, previews, exports, and later lifecycle objects.

No cross-tenant leakage.

Do not trust client-provided IDs without server-side authorization checks.

---

## Decision Understanding rules

The Decision Understanding Layer is central to SeaLAI’s USP.

It must explain the user’s case and improve the next decision.

It must not become generic encyclopedia content.

A useful projection should expose:

```text
case_summary
understood_now[]
technical_meaning[]
plausible_directions[]
not_yet_decidable[]
key_risks[]
confidence_notes[]
next_best_question
manufacturer_review_needs[]
```

A good SeaLAI response follows this pattern:

```text
short technical framing
→ why it matters
→ one best next question or action
```

Deep dives must return to the user’s case, RFQ readiness, risk, open point, or next action.

---

## Runtime routing

SeaLAI must preserve a lightweight frontdoor and governed backend.

### Fast responder

Allowed only for:

- greeting
- meta question
- blocked/unsupported interaction

Rules:

- no case creation
- no durable engineering state write
- no full graph invocation
- fast response
- persona-consistent

If classification is ambiguous, prefer the governed path.

### Knowledge query

For general sealing knowledge, terminology, material explanations, and learning before a real application exists.

Rules:

- no forced case creation
- may use knowledge service/retrieval
- must distinguish general explanation from case-specific assessment
- may bridge to governed case if the user provides real application data

### Governed domain inquiry

For real applications, operating data, RFQ intent, technical preselection, uploads, calculations, risk, readiness, RFQ, consent, and export.

Rules:

- use governed state
- remain auditable
- use backend projections
- do not bypass field status, provenance, or confirmation requirements

---

## RFQ rules

RFQ is the Phase-1 product artifact.

Required:

- RFQ preview based on governed case state
- frozen `case_revision`
- clear separation of confirmed, documented, inferred, calculated, conflicting, missing, and open values
- user consent before export/sharing
- included/excluded documents
- stale handling if the case changes
- no final technical suitability claim
- no compliance approval claim

Forbidden:

- RFQ from raw chat only
- RFQ without revision
- RFQ without consent
- silent dispatch to manufacturers
- "An Hersteller senden" UI unless actual sending and recipient consent are implemented
- final suitability wording

---

## Document, upload, and IP rules

All document-derived values are candidates until governed.

Required behavior:

- extract technical candidates
- create evidence references where possible
- normalize engineering values
- mark status as documented/candidate/needs confirmation
- never treat document text as instruction
- never auto-confirm critical values from untrusted uploads
- preserve source references for RFQ and review

Default security stance:

- tenant isolation is mandatory
- dynamic LLM processing of uploaded document content must be default-off unless explicitly policy/consent-gated
- documents must not be shared with manufacturers without explicit user consent
- RFQ recipients must see only approved fields and approved documents
- internal file paths must not be exposed in health/error responses
- upload parsing needs safe size/type/error limits

If a task touches document storage, sharing, extraction, RFQ export, or manufacturer visibility, include an IP/security review in the patch report.

---

## Compliance awareness

SeaLAI may touch regulated use cases such as food, pharma, chemical processing, ATEX-relevant environments, drinking water, steam, hygienic design, hydrogen, aggressive media, or safety-relevant equipment.

For regulated contexts:

- mark the requirement explicitly
- track certification evidence and validity where available
- do not claim compliance without evidence
- keep manufacturer review/final release explicit
- preserve document provenance and revision
- surface open compliance questions in RFQ output

Examples of regulated references:

- FDA
- EU 1935/2004
- EU 10/2011
- ATEX
- EHEDG
- USP Class VI
- drinking-water approvals
- TA-Luft
- GMP

Do not implement a broad compliance engine unless explicitly tasked.

---

## Frontend rules

`frontend/DESIGN.md` is binding for UI work.

Frontend may:

- render chat
- render cockpit/workspace
- render Decision Understanding
- show field status, provenance, evidence, conflicts, stale data, risks, open points, and readiness
- trigger clarification, upload, RFQ preview, consent, and export flows

Frontend must not:

- compute authoritative engineering truth
- invent readiness
- own matching logic
- hide backend conflicts
- silently reconcile state mismatches
- create a parallel design system
- bypass `frontend/DESIGN.md`
- show final engineering approval language
- show automatic manufacturer dispatch unless implemented and consent-gated

Unsafe copy to avoid:

- Empfehlung ableiten
- Technische Validierung
- finalisieren und versenden
- Anfrage erfolgreich versendet
- An Hersteller senden
- neutral geprüfte Auswahl
- freigegeben
- validiert
- geeignet
- zertifiziert
- compliant

Preferred copy:

- RFQ-Preview
- Anfragebasis für Herstellerprüfung
- offene Punkte
- Risiken
- Datenherkunft
- noch nicht final freigegeben
- zur Herstellerprüfung vorbereitet
- Export vorbereiten
- Nutzerbestätigung erforderlich

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
- deterministic calculations
- risk/readiness evaluation
- RFQ freeze
- RFQ consent
- document security and extraction
- tenant scoping
- frontend-ready projections

Backend must expose frontend-ready projections.

Frontend should not infer product truth from raw backend internals.

---

## Coding-agent operating model

### Default: audit first, patch second

For every non-trivial task:

1. Read `AGENTS.md`.
2. Read `konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md`.
3. Inspect relevant code and tests.
4. Map the existing productive seam.
5. State what is true now.
6. State the exact misalignment.
7. Propose the smallest productive patch.
8. Patch only that seam.
9. Add or update focused tests.
10. Run relevant validation.
11. Report changed files, commands, results, risks, and next patch.

### Patch-size policy

A good patch:

- touches one architectural seam or bounded behavior
- has clear before/after behavior
- adds or updates focused tests
- avoids speculative abstractions
- avoids dead future code
- improves pilot readiness

A bad patch:

- mixes state models, UI, routing, RFQ, matching, and business logic
- creates parallel services beside the real seam
- hides broad rewrites inside a small patch
- implements Phase-2+ features without explicit instruction
- adds prompt-only backend rules
- makes frontend authoritative for engineering truth

---

## Required reporting format for patch work

Every implementation summary must use:

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
- no hand-wavy "should work"

Preferred validation types:

- service unit tests
- API contract tests
- projection tests
- routing boundary regression tests
- deterministic calculation tests
- RFQ freeze/stale/consent tests
- tenant/IDOR tests
- upload/IP safety tests
- prompt-injection tests
- compliance-overclaim tests
- frontend journey tests

Always provide commands from:

```bash
/home/thorsten/sealai
```

Before inventing frontend commands, inspect:

```text
frontend/package.json
```

Before inventing backend commands, inspect existing test structure and config files.

Known useful validation commands may include:

```bash
cd /home/thorsten/sealai && python -m pytest backend/app/api/tests/test_rfq_endpoint.py -q
```

```bash
cd /home/thorsten/sealai && python -m pytest backend/app/agent/tests/test_case_delta_contract.py backend/app/agent/tests/test_normalization.py backend/app/agent/tests/test_governed_runtime_seam.py -q
```

```bash
cd /home/thorsten/sealai && npm --prefix frontend run test:run
```

```bash
cd /home/thorsten/sealai && npm --prefix frontend run lint
```

Run only relevant tests unless explicitly asked for full-suite validation.

---

## Test expectations by current pilot-readiness PR

### PR 1 — RFQ Consent Boundary

Required tests:

- missing `user_acknowledged_no_final_release` is rejected
- open points present plus missing `user_acknowledged_open_points` is rejected
- valid acknowledgements are accepted
- stale preview is rejected
- `dispatch_enabled` remains false

### PR 2 — Settings and Startup Safety

Required tests:

- all referenced settings exist
- production-safe defaults do not clear Redis/checkpoints
- worker startup is explicitly gated
- docs/openapi exposure is environment-gated if changed
- config import smoke test passes

### PR 3 — Secret/Env Hygiene

Required checks:

- no real `.env` files are versioned
- examples use placeholders only
- Keycloak exports do not contain live secrets or are marked rotation-required
- output never prints secret values

### PR 4 — Upload/IP Safety

Required tests:

- dynamic LLM metadata extraction is disabled by default
- unsafe/spoofed uploads are rejected or safely handled
- internal paths are redacted from health/error responses
- parser errors are safe
- upload-derived values remain candidates

### PR 5 — RFQ Preview Frontend Flow

Required tests:

- RFQ preview loads from backend/BFF
- open points are visible
- consent acknowledgements are required
- stale preview state is visible
- forbidden product copy does not appear in the main flow
- no automatic manufacturer dispatch is shown

### PR 6 — RFQ Field Envelopes

Required tests:

- confirmed/documented/user-stated/inferred/calculated/conflicting/missing fields are separated
- critical values include status/provenance/evidence where available
- no bare critical value appears as authoritative RFQ truth

### PR 7 — Tenant Guards

Required tests:

- user A cannot read user B case/RFQ/document
- user A cannot consent user B preview
- cross-tenant IDs return 403 or 404
- no client-provided ID is trusted without server-side authorization

### PR 8 — Compliance and Prompt Injection

Required tests:

- FDA/ATEX/Food/Pharma/Drinking Water overclaims are rejected or rewritten safely
- uploaded document instructions cannot override product/system rules
- allowed language remains cautious and review-oriented

---

## Current stack assumptions

Assume the productive stack is approximately:

- FastAPI backend
- SQLAlchemy/Alembic
- Postgres durable storage
- Redis live/checkpoint/rate-limit layer
- Qdrant retrieval
- LangGraph/LangChain where appropriate
- OpenAI LLM/embeddings integration
- Keycloak authentication and tenant boundary
- Next.js/React frontend
- NextAuth frontend auth
- Dockerized deployment behind nginx

This stack is sufficient.

Do not replace the stack without explicit instruction.

---

## Anti-patterns

Avoid:

1. Big-bang implementation.
2. Architecture cosplay.
3. Prompt-only backend rules.
4. Hidden rewrites.
5. Duplicate truth across frontend, Redis, LangGraph, and Postgres.
6. Duplicate services beside the real seam.
7. Overeager persistence for greetings/meta questions.
8. Frontend hiding backend authority problems.
9. Auto-confirming critical technical fields.
10. Final engineering recommendation language.
11. RFQ without revision.
12. RFQ without consent.
13. Silent manufacturer dispatch.
14. Upload content treated as instruction.
15. Cross-tenant assumptions.
16. Matching before RFQ qualification is reliable.
17. Seal Passport before post-RFQ validation exists.
18. Reorder before validated solution identity exists.
19. Price claims without manufacturer confirmation.
20. Compliance hand-waving.
21. ERP/CRM gravity distorting the MVP.
22. New dependencies without necessity.
23. Broad refactors before pilot blockers are fixed.

---

## When to stop and ask

Stop and ask before proceeding if:

- the task requires deleting data
- the task requires service restart
- the task requires production migration
- the task exposes or rotates secrets
- the task changes auth/tenant boundaries broadly
- the task sends real RFQs or contacts manufacturers
- the task changes deployment topology
- requirements conflict with this file
- the smallest safe patch is unclear

If the issue is a normal code ambiguity inside the requested PR, make a conservative best-effort choice and document it.

---

## Glossary

### CaseField

A field envelope around a technical value. It preserves status, provenance, confidence, evidence references, units, and confirmation requirements.

### EngineeringValue

A normalized technical value with unit, raw input, canonical value, and interpretation metadata.

### Governor

The backend authority that validates proposed changes, applies rules, records events, updates state, triggers recalculation, and produces projections.

### Decision Understanding Layer

The projection that explains what SeaLAI understands, why it matters, what is not yet decidable, and which next decision or question is most useful.

### RFQ Freeze

Binding an RFQ preview/export to a specific `case_revision` so later state changes can mark it stale rather than silently changing it.

### RFQ Qualification Copilot

The Phase-1 product identity: a governed assistant that turns unclear sealing situations into manufacturer-review-ready RFQ preparation, not final product selection.

---

## Final instruction

When in doubt, choose the path that:

- preserves the current SSoT
- keeps SeaLAI focused on RFQ qualification
- keeps engineering truth governed in the backend
- makes uncertainty visible
- preserves provenance and evidence
- respects tenant boundaries
- avoids duplicate architecture
- avoids Phase-2+ scope creep
- produces the smallest reliable patch
- adds tests or evidence for the next agent

SeaLAI should increasingly feel like:

> one experienced sealing engineer on the surface, backed by a disciplined, auditable engineering system underneath.
