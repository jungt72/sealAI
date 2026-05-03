# AGENTS.md

## Purpose

This repository builds **SeaLAI / sealingAI**.

SeaLAI is not a generic chatbot, not a generic product catalog, not an ungoverned supplier directory, not a hidden advertising portal, not a price-comparison tool, and not a final engineering approval engine.

SeaLAI is a **multi-scenario technical clarification system for sealing technology**:

> SeaLAI helps users understand sealing situations, qualify technical cases, prepare manufacturer-review-ready RFQ artifacts, match cases to suitable paid partner manufacturers transparently, and support technical inquiries, compatibility questions, complaints, and failure-intake workflows with governed evidence, uncertainty, and consent.

This file is the binding operating contract for autonomous coding agents working in this repository, especially Codex App, Codex CLI, and similar coding agents.

Keep this file practical. Product depth belongs in the concept files. Do not turn `AGENTS.md` into a second product specification.

---

## Active mission

The active implementation mission is **SeaLAI v0.8.3 on the current stack**, implemented safely and incrementally.

The active product direction is:

```text
Understand → Qualify → Match → Support → Document
```

SeaLAI must increasingly feel like:

> one experienced sealing engineer on the surface, backed by a disciplined, auditable engineering system underneath.

The current work must move the existing app toward v0.8.3 without big-bang rewrites, without destructive production actions, and without replacing the current stack.

---

## Required first read

Before any non-trivial task, read from the repository root:

1. `AGENTS.md`
2. `docs/implementation/SEALAI_COMMUNICATION_ARCHITECTURE_V5_IMPLEMENTATION_CONCEPT.md`
3. `docs/implementation/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md`
4. `docs/implementation/SEALAI_V08_2_STACK_AUDIT_IST.md`
5. `docs/implementation/SEALAI_V08_3_IMPLEMENTATION_ROADMAP_FROM_AUDIT.md`
6. `docs/implementation/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md`
7. relevant source files and tests for the specific task

For frontend/UI work, also read:

8. `frontend/DESIGN.md`

If a directory contains another `AGENTS.md`, follow the more specific file for files inside that directory.

Do not work from memory. Current repository content is the evidence.

---

## Binding authority order

Use this order when documents, code, or prior notes disagree:

1. `AGENTS.md` for coding-agent operating rules and safety boundaries.
2. `docs/implementation/SEALAI_COMMUNICATION_ARCHITECTURE_V5_IMPLEMENTATION_CONCEPT.md` for the active communication architecture, FinalAnswerLayer target, answer-mode policy, composer tiers, traces, eval gates, and rollout sequence.
3. `docs/implementation/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md` for active SeaLAI v0.8.3 product and implementation direction.
4. `docs/implementation/SEALAI_V08_2_STACK_AUDIT_IST.md` for current-stack evidence and implementation gaps.
5. `docs/implementation/SEALAI_V08_3_IMPLEMENTATION_ROADMAP_FROM_AUDIT.md` for active PR order and implementation sequencing.
6. `docs/implementation/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md` for pilot-readiness guardrails, RFQ governance, consent, IP/upload safety, and earlier implementation constraints.
7. `frontend/DESIGN.md` for frontend design, layout, motion, spacing, cockpit, chat workspace, rails, tabs, and responsive behavior.
8. Current code and tests as evidence of existing contracts and productive seams.
9. Older concept files, archived notes, audit notes, prompts, chat notes, or implementation history as context only.

Rules:

- Do not resurrect deleted concept files.
- Do not reference deleted, archived, or superseded concept files as active SSoT.
- Current code may be legacy, provisional, or misaligned.
- Fix misalignment through small, evidence-based patches.
- Do not add chat citations, file citations, or conversation artifacts to production docs.
- Do not add speculative documentation that is not wired to code or an explicit concept requirement.

---

## Non-negotiable product boundaries

SeaLAI must not claim:

- final engineering release
- guaranteed suitability
- automatic technical approval
- manufacturer approval unless explicitly documented by the manufacturer
- compliance approval without evidence
- FDA/ATEX/Food/Pharma/Drinking Water approval without actual evidence
- validated operation before post-RFQ or manufacturer feedback exists
- current reorder price without manufacturer confirmation
- paid technical ranking
- sponsorship-based technical fit
- full-market manufacturer neutrality when only SeaLAI partners are considered

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
- partner-network match
- technical fit within the SeaLAI partner network
- LLM-research fallback, not validated
- general technical orientation, not a final assessment

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
- neutral full-market ranking
- best manufacturer in the market
- final material recommendation
- final compatibility confirmation
- final root cause

## Active Communication Architecture V5

`docs/implementation/SEALAI_COMMUNICATION_ARCHITECTURE_V5_IMPLEMENTATION_CONCEPT.md` is the active implementation concept for chat, knowledge, governed intake, active-case side questions, and visible answer orchestration.

Coding agents must implement V5 as an architecture, not as example-specific fixes:

- Every user-visible answer must be assembled through one final decision boundary: the `FinalAnswerLayer`.
- Upstream components may produce deterministic fallback text, evidence, state deltas, contexts, and answer plans, but they are not independent final voices.
- The target public contract remains `reply` as deterministic fallback and `answer_markdown` as the final visible answer.
- `answer_trace` must explain the route, answer mode, composer tier, source, fallback reason, and safety result without exposing secrets, raw prompts, raw evidence chunks, or internal graph state.
- Tier A / Micro Composer is for smalltalk, meta, short confirmations, and transitions.
- Tier B / Standard Composer is for knowledge, material comparison, PFAS orientation, needs analysis, governed intake, and active-case side questions.
- No Tier C exists in V5. Larger deep-dive models require a later concept/eval decision.
- Material comparison must be generic over supported material pairs, not hardcoded to examples such as NBR/PTFE or FKM/EPDM.
- Active-case side questions such as material comparisons must not be forced through governed intake or legacy exploration just because a case exists.
- Fallback is safe degradation only; it is not the target UX when a composer is allowed, available, and passes guards.
- Roll out V5 in the implementation sequence defined in the concept: inventory voices, add envelope/adapter, introduce FinalAnswerLayer, migrate smalltalk, migrate knowledge/material comparison, migrate governed intake, migrate active-case side questions, then enforce legacy-voice removal.
- Every V5 patch needs deterministic tests for route, answer mode, fallback, trace metadata, safety guards, and no unintended case mutation.

## SeaLAI LLM Safety Rules

- Backend state, deterministic services, calculations, rules, and evidence are the source of truth.
- LLMs may explain, summarize, ask targeted questions, and make the experience more human, but must not create engineering truth.
- Case-bound engineering statements must be grounded in explicit `allowed_claims`.
- Evidence-based statements must cite explicit evidence refs supplied by the backend; never invent sources, standards, datasheets, or manufacturer statements.
- LLMs must never directly confirm fields, compute readiness, approve materials, select final sealing solutions, assert manufacturer acceptance, or override deterministic services.
- Field extraction from chat creates proposals only; the communication LLM may only echo extracted proposals and must not introduce new engineering fields.
- Tests for LLM-facing features must use deterministic mocks and cover prompt injection, unsupported claims, fabricated IDs/evidence, and final-release language.

---

## Current scope

v0.8.2 extends the earlier RFQ-only MVP into a multi-scenario case system.

### In scope

- empathic and precise conversation frontdoor
- small talk and general sealing questions without forced case creation
- needs analysis and current-state analysis
- next-best-question logic
- governed sealing case state
- `CaseType`
- `SealFamily` / `SealType`
- `CaseField`
- `FieldStatus`
- `EngineeringValue`
- provenance
- evidence references
- source and validation status
- RAG-first knowledge lookup
- LLM-research fallback when RAG is insufficient
- explicit labeling of non-validated fallback information
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
- manufacturer matching inside the paid SeaLAI partner network
- transparent partner-network disclosure
- technical fit score not influenced by payment beyond network eligibility
- support and complaint qualification
- compatibility inquiry handling
- failure-analysis intake
- replacement/reorder/legacy-part intake
- compliance/certificate request handling
- tests for the above

### In scope as shallow recognition first

These may be classified, routed, and minimally supported before deeper workflows exist:

- drawing review
- quote comparison
- material substitution
- emergency MRO
- manufacturer support intake
- distributor intake
- audit/document bundle
- Seal Passport update

### Out of scope unless explicitly tasked

Do not build:

- public marketplace/shop
- payment flow
- merchant-of-record behavior
- automatic dispatch to manufacturers
- manufacturer self-service portal
- broad manufacturer dashboard
- automatic ERP/CRM/Paperless integration
- automatic FEM/CAD pipeline
- full compliance engine
- final material approval engine
- final failure-root-cause engine
- full Seal Passport lifecycle
- private reorder checkout
- price validity logic
- ranking based on sponsorship or payment tier
- untransparent lead selling

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
- change deployment topology
- modify Keycloak realm settings in production

If secrets are found:

- never output the secret value
- output only filename, key name, and risk
- mask values fully as `[REDACTED]`
- recommend rotation if exposure is possible

If a requested task appears to require a destructive or production-affecting action, stop and ask before doing it.

---

## Core architectural invariants

### 1. LLM is not engineering truth

The LLM may generate:

- `assistant_message`
- `proposed_case_delta`
- extraction candidates
- explanations
- next-question proposals
- general technical orientation
- LLM-research fallback output if RAG is insufficient

The LLM must not directly mutate authoritative engineering state.

The LLM must not be the authority for:

- final material suitability
- final compatibility
- final compliance
- manufacturer approval
- final root cause
- technical ranking beyond governed matching logic
- deterministic calculations
- RFQ consent
- tenant authorization

### 2. Governor owns state mutation

All case-state changes must pass through governed backend logic:

```text
proposed delta or extracted candidate
→ schema validation
→ evidence linking
→ unit normalization
→ provenance/status assignment
→ source validation status assignment
→ conflict detection
→ rule validation
→ event append
→ state materialization
→ derived recomputation
→ projection update
```

Do not bypass the governor with direct frontend state writes or raw LLM writes.

### 3. Case state is revisioned and auditable

Critical changes must increment or attach to `case_revision`.

RFQ previews, exports, consent records, matching matrices, support artifacts, complaint artifacts, and later lifecycle objects must be traceable to specific revisions.

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
- source type
- evidence references
- confidence
- validation status
- confirmation requirement
- stale/conflict/invalid state

### 5. Derived values are deterministic

Calculations should be deterministic services where possible.

The LLM must not be the authority for calculations such as unit conversion, circumference speed, pressure interpretation, readiness state, fit-score calculation, or stale-state propagation.

### 6. Uploads are data, never instructions

Documents, PDFs, screenshots, photos, OCR output, drawings, tables, datasheets, oil reports, certificates, and customer e-mails are untrusted input.

Uploaded content may create extraction candidates and evidence references.

Uploaded content must never override system rules, product rules, safety rules, developer instructions, or this file.

### 7. Frontend renders backend projections

Frontend must not own engineering truth.

Frontend may render:

- chat
- cockpit/workspace
- Decision Understanding
- field status
- provenance
- evidence
- conflicts
- stale data
- readiness
- open points
- risks
- RFQ preview
- manufacturer fit matrix
- support artifacts
- complaint artifacts
- consent state

Frontend must not compute authoritative readiness, matching, risk, pricing validity, or confirmed technical truth.

### 8. RFQ previews are revision-frozen

Every RFQ preview/export must be based on a specific `case_revision`.

If critical case data changes after preview creation, the preview must be marked stale, superseded, or needs regeneration.

### 9. Consent is explicit

No silent RFQ sharing.

No automatic manufacturer dispatch unless explicitly implemented, consent-gated, recipient-specific, and authorized.

Consent must require explicit acknowledgement of:

- no final technical release
- open points understood
- documents/fields included for export or sharing
- partner-network disclosure when matching is used
- recipients, if sending is ever implemented

### 10. Tenant boundaries are mandatory

Keycloak user/tenant/org scoping must be respected for all durable state, documents, cases, RFQs, uploads, previews, exports, matching artifacts, partner visibility, and later lifecycle objects.

No cross-tenant leakage.

Do not trust client-provided IDs without server-side authorization checks.

---

## Conversation Intelligence Layer

SeaLAI must not behave like a cold form or a generic chat toy.

The first job is to understand the user's intent, emotional state, technical situation, and current information quality.

### ConversationIntent

The system should distinguish at least:

```text
small_talk
meta_question
general_sealing_question
needs_analysis
current_state_analysis
new_rfq
manufacturer_matching
compatibility_inquiry
complaint_case
failure_analysis
replacement_reorder
unknown_legacy_part
drawing_review
quote_comparison
compliance_certificate_request
material_substitution
emergency_mro
manufacturer_support_intake
off_topic
unsupported
```

### ResponseMode

Use the right response mode:

```text
fast_responder
knowledge_answer
empathic_triage
governed_case_intake
artifact_generation
matching_flow
support_flow
complaint_flow
consent_flow
refusal_or_boundary
```

### Small talk and simple messages

For greetings, thanks, or meta questions:

- do not create a case
- do not persist engineering state
- respond warmly and briefly
- offer useful entry paths

Example behavior:

```text
User: Hallo
SeaLAI: Ich kann bei Dichtungsfragen, RFQ-Vorbereitung, Hersteller-Fit und Reklamationen helfen. Geht es um eine neue Dichtung, ein Ersatzteil, einen Ausfall oder eine allgemeine Frage?
```

### General sealing questions

For general knowledge questions:

- do not force case creation
- answer generally
- distinguish general orientation from case-specific assessment
- use RAG first
- if RAG is insufficient, use LLM-research fallback if implemented and allowed
- label fallback content as non-validated
- offer to turn it into a case when the user provides application data

### Frustrated or chaotic user input

Users may be stressed, angry, vague, or technically imprecise.

SeaLAI should:

- acknowledge the situation without imitating profanity
- reduce complexity
- ask the most useful next question
- avoid overwhelming lists
- move toward structured intake

Example behavior:

```text
User: Diese Dichtung leckt schon wieder.
SeaLAI: Das klingt nach einem wiederkehrenden Ausfall. Ich helfe, das sauber einzugrenzen. Die wichtigste erste Frage: Um welchen Dichtungstyp geht es — z. B. Wellendichtring, O-Ring, Flachdichtung oder Hydraulikdichtung?
```

### Needs analysis vs current-state analysis

Separate:

```text
Needs analysis = what the user wants to achieve.
Current-state analysis = what is already known about the sealing situation.
```

Needs may include:

- understand a sealing problem
- prepare RFQ
- find suitable partner manufacturer
- replace an unknown part
- compare offers
- answer a customer inquiry
- evaluate compatibility
- handle a complaint
- investigate failure
- request certificates
- handle emergency downtime

Current-state may include:

- seal type
- dimensions
- material
- medium
- temperature
- pressure
- motion
- installation situation
- damage pattern
- documents
- analysis report
- existing manufacturer
- urgency
- compliance requirements

### Next Best Question Engine

SeaLAI should not ask ten questions at once.

Rules:

- ask 1-3 targeted next questions
- in emergencies ask only the single most important next question
- do not repeat already answered questions
- prioritize scenario and seal type early
- every question should have a short technical reason
- prefer questions that unlock the next useful artifact
- preserve a `CompletenessScore` or equivalent readiness signal

---

## Scenario architecture

Scenario and seal type are two different axes.

A scenario describes the process context:

```text
What is happening?
```

A seal type describes the technical object:

```text
What kind of sealing system is involved?
```

Do not conflate them.

### CaseType

Use or add a stable enum/model equivalent:

```text
new_rfq
manufacturer_matching
compatibility_inquiry
complaint_case
failure_analysis
replacement_reorder
unknown_legacy_part
drawing_review
quote_comparison
compliance_certificate_request
material_substitution
emergency_mro
manufacturer_support_intake
general_knowledge
```

### ArtifactType

Use or add a stable enum/model equivalent:

```text
rfq_preview
manufacturer_fit_matrix
technical_inquiry_summary
compatibility_matrix
complaint_intake
failure_analysis_intake
replacement_sheet
legacy_part_intake
drawing_review
quote_comparison
compliance_checklist
material_substitution_brief
emergency_triage
customer_reply_draft
internal_engineering_note
```

Each artifact must be tied to:

- `case_id`
- `case_revision`
- `artifact_type`
- content
- status
- evidence/provenance where applicable
- exportability
- consent requirement

---

## Seal type architecture

SeaLAI must understand that different seal types require different questions, risks, artifacts, and partner capabilities.

### SealFamily examples

```text
static_elastomer
flat_gasket
rotary_shaft
mechanical_face
hydraulic
pneumatic
packing
metal_seal
custom_profile
unknown
```

### SealType examples

Support normalization for at least:

```text
o_ring
x_ring
backup_ring
flat_gasket
flange_gasket
profile_gasket
bonded_seal
clamp_gasket
radial_shaft_seal
cassette_seal
v_ring
rotary_lip_seal
rotary_swivel_seal
mechanical_seal
hydraulic_rod_seal
hydraulic_piston_seal
hydraulic_wiper
hydraulic_guide_ring
hydraulic_buffer_seal
pneumatic_rod_seal
pneumatic_piston_seal
u_cup
chevron_packing
gland_packing
valve_stem_seal
expansion_joint_seal
spring_energized_seal
metal_seal
custom_profile
molded_seal
fabric_reinforced_seal
unknown_seal
```

### Alias normalization

Normalize common aliases, including German and English terms.

Examples:

```text
Wellendichtring / Radialwellendichtring / RWDR / WDR / Simmerring / oil seal / rotary lip seal
→ radial_shaft_seal

Flachdichtung / Flanschdichtung / gasket / flange gasket / cut gasket
→ flat_gasket or flange_gasket

Stangendichtung / rod seal
→ hydraulic_rod_seal or pneumatic_rod_seal depending on context

Kolbendichtung / piston seal
→ hydraulic_piston_seal or pneumatic_piston_seal depending on context

Gleitringdichtung / mechanical seal / face seal
→ mechanical_seal

Stopfbuchspackung / gland packing / compression packing
→ gland_packing
```

### SealApplicationProfile

Each real case should have or derive a profile such as:

```text
case_type
seal_family
seal_type
seal_type_confidence
application_domain
motion_type
medium
temperature
pressure
dimensions
standard_refs
critical_missing_fields
type_specific_risk_flags
partner_capability_requirements
```

### Type-specific intake

Do not use the same question list for every seal.

Radial shaft seal questions differ from flat gasket questions, hydraulic seal questions, and mechanical seal questions.

When adding intake logic, keep type-specific question profiles small, focused, and testable.

---

## RAG, knowledge, and LLM-research fallback

SeaLAI must prefer validated internal/retrieved knowledge over free LLM guessing.

### Required knowledge flow

For technical knowledge or explanations:

```text
1. Try RAG / curated knowledge / verified partner/manufacturer data.
2. If sufficient: answer with validated or sourced status.
3. If insufficient: run LLM-research fallback only if implemented, configured, and allowed.
4. Clearly label fallback information as not validated.
5. Do not persist fallback information as authoritative engineering truth.
6. Do not use fallback information as final approval, compliance proof, or manufacturer validation.
```

### Source and validation model

Use or add equivalent metadata:

```text
source_type:
  rag_verified
  partner_verified
  manufacturer_documented
  uploaded_evidence
  user_stated
  deterministic_calculation
  llm_research_fallback
  unknown

validation_status:
  validated
  documented
  self_declared
  user_stated
  candidate
  unvalidated
  conflicting
  rejected
```

### Required labeling for fallback

Any LLM-research fallback must be visibly labeled in UI and artifacts:

```text
Information source: LLM research fallback
Validation status: Not validated
Use: General orientation only
Not a manufacturer approval or final technical release
```

### Persistence rule

LLM-research fallback may be stored as a traceable note or candidate if needed, but must not be treated as:

- confirmed case field
- validated RAG content
- manufacturer-verified information
- compliance evidence
- final compatibility proof
- final RFQ truth

### RAG-miss behavior

If no useful RAG information exists and fallback is unavailable or disabled, SeaLAI must say so clearly and continue with questions or a manufacturer-review path.

Do not hallucinate certainty to hide knowledge gaps.

---

## Manufacturer matching rules

Manufacturer matching is part of v0.8.2, but it must be trust-preserving.

### Network eligibility

Only active paid SeaLAI partner manufacturers may appear in the recommendation/matching matrix.

Non-participating manufacturers are not included.

This must be transparent in the UI and artifacts.

Required disclosure:

```text
Only active SeaLAI partner manufacturers are included in this matrix. The ranking shows technical fit within the SeaLAI partner network, not a full-market comparison.
```

### Fit score

Payment may determine eligibility for inclusion in the network.

Payment must not influence technical fit score.

Technical fit should be based on:

- seal type capability
- material capability
- medium/application experience
- industry capability
- certification/documentation capability
- custom vs standard capability
- MRO/emergency capability
- region/language/support availability
- manufacturer support capability
- known gaps and missing information

### No suitable partner

The matching system must support:

```text
No suitable SeaLAI partner found for the currently known requirements.
```

Do not force a partner match if the technical fit is insufficient.

### Transparency

Each partner result must include:

- fit score or fit band
- fit reasons
- gaps
- missing requirements
- verification level
- whether capabilities are self-declared or verified
- required manufacturer review

### Forbidden

Do not implement:

- hidden sponsored ranking
- "best manufacturer on the market" wording
- full-market neutrality claim
- ranking boost by payment tier
- automatic RFQ dispatch
- manufacturer contact without explicit user consent

---

## RFQ rules

RFQ remains a central product artifact.

Required:

- RFQ preview based on governed case state
- frozen `case_revision`
- clear separation of confirmed, documented, user-stated, inferred, calculated, conflicting, missing, and open values
- user consent before export/sharing
- included/excluded documents
- stale handling if the case changes
- no final technical suitability claim
- no compliance approval claim
- manufacturer-review framing
- partner-network disclosure when a partner is included

Forbidden:

- RFQ from raw chat only
- RFQ without revision
- RFQ without consent
- silent dispatch to manufacturers
- "An Hersteller senden" UI unless actual sending and recipient consent are implemented
- final suitability wording

---

## Support, compatibility, complaint, and failure-analysis rules

SeaLAI must handle more than new RFQs.

### Compatibility inquiries

Examples:

- "Is FKM suitable for these oil analysis values?"
- "Are water, sodium, potassium critical for this seal?"
- "Is this medium compatible with this material?"

Rules:

- distinguish general orientation from compound-specific validation
- extract values, units, method, context, and evidence
- ask for missing data
- do not claim final compatibility without manufacturer/compound evidence
- generate `compatibility_matrix` or `technical_inquiry_summary`
- optionally generate `customer_reply_draft` and `internal_engineering_note`

### Complaint and failure cases

Examples:

- leakage
- swelling
- cracking
- hardening
- extrusion
- wear
- dry running
- installation damage
- repeated failure

Rules:

- capture damage pattern
- capture operating conditions
- capture installation context
- request photos/evidence where useful
- generate failure intake, not final root cause
- avoid admission/rejection of liability
- support escalation to application engineering or quality

### Customer reply drafts

Customer-facing drafts must be cautious:

- helpful
- precise
- non-defensive
- non-final
- no liability admission
- clear missing information
- clear manufacturer-review or lab-test requirement where needed

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
- redact internal file paths from health/error responses
- enforce safe size/type/error limits

Default security stance:

- tenant isolation is mandatory
- dynamic LLM processing of uploaded document content must be policy/consent-gated
- documents must not be shared with manufacturers without explicit user consent
- RFQ recipients must see only approved fields and approved documents
- parser errors must be safe and non-leaky

If a task touches document storage, sharing, extraction, RFQ export, support artifacts, complaint artifacts, or manufacturer visibility, include an IP/security review in the patch report.

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
- distinguish material family from certified compound
- distinguish "FDA material mentioned" from actual use-case approval

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

## Decision Understanding rules

The Decision Understanding Layer is central to SeaLAI's USP.

It must explain the user's case and improve the next decision.

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
matching_readiness
rfq_readiness
support_readiness
```

A good SeaLAI response follows this pattern:

```text
short empathic framing
→ technical meaning
→ what is known / missing / risky
→ one best next question or next action
```

Deep dives must return to the user's case, RFQ readiness, risk, open point, matching readiness, support response, or next action.

---

## Runtime routing

SeaLAI must preserve a lightweight frontdoor and governed backend.

### Fast responder

Allowed only for:

- greeting
- thanks
- meta question
- clear off-topic
- blocked/unsupported interaction

Rules:

- no case creation
- no durable engineering state write
- no full graph invocation
- fast response
- persona-consistent

If classification is ambiguous and technical, prefer the governed path.

### Knowledge query

For general sealing knowledge, terminology, material explanations, and learning before a real application exists.

Rules:

- no forced case creation
- may use knowledge service/retrieval
- must distinguish general explanation from case-specific assessment
- may bridge to governed case if the user provides real application data
- apply RAG-first and fallback-label rules

### Governed domain inquiry

For real applications, operating data, RFQ intent, technical preselection, uploads, calculations, risk, readiness, RFQ, matching, support, complaints, consent, and export.

Rules:

- use governed state
- remain auditable
- use backend projections
- do not bypass field status, provenance, validation status, or confirmation requirements

---

## Frontend rules

`frontend/DESIGN.md` is binding for UI work.

Frontend may:

- render chat
- render cockpit/workspace
- render Decision Understanding
- show field status, provenance, evidence, conflicts, stale data, risks, open points, and readiness
- show general knowledge answers
- show RAG/fallback validation labels
- trigger clarification, upload, RFQ preview, consent, export, matching, support, and complaint flows
- render manufacturer fit matrix based on backend projection
- render scenario-specific artifacts

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
- hide partner-network limitation
- present LLM fallback as validated information

Unsafe copy to avoid:

- Empfehlung ableiten
- Technische Validierung
- finalisieren und versenden
- Anfrage erfolgreich versendet
- An Hersteller senden
- neutral geprüfte Auswahl
- bester Hersteller am Markt
- freigegeben
- validiert
- geeignet
- zertifiziert
- compliant
- finale Ursache
- endgültig bestätigt

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
- Hersteller-Fit im SeaLAI-Partnernetzwerk
- technische Orientierung
- nicht validierte LLM-Recherche
- Herstellerprüfung erforderlich
- nächster sinnvoller Klärungsschritt

---

## Backend rules

Backend owns:

- classification authority
- conversation routing
- case creation decision
- governed state mutation
- case events and revisions
- engineering value normalization
- source and validation status handling
- evidence and provenance handling
- conflict detection
- dependency/stale propagation
- deterministic calculations
- risk/readiness evaluation
- seal-type normalization
- type-specific intake requirements
- RFQ freeze
- RFQ consent
- partner matching logic
- support/complaint artifact generation
- document security and extraction
- tenant scoping
- frontend-ready projections

Backend must expose frontend-ready projections.

Frontend should not infer product truth from raw backend internals.

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

Do not add broad new infrastructure when a focused service/model/test in the current stack is enough.

---

## Preferred implementation sequence

When the user asks to implement active v0.8.3 work, follow `docs/implementation/SEALAI_V08_3_IMPLEMENTATION_ROADMAP_FROM_AUDIT.md` unless the user gives a more specific instruction.

The next productive patch after PR 0 is **PR 1 — Event Model Blueprint**.

The earlier v0.8.2 sequence below remains legacy context for already-scoped v0.8.2 work.

Do not combine several PRs unless explicitly instructed.

### PR 0 — Repo instruction and feature-flag baseline

- ensure `AGENTS.md` and active concept path are aligned
- add or document feature flags for v0.8.2 workflows
- no product behavior expansion yet

### PR 1 — Conversation Intelligence and routing skeleton

- classify small talk, general knowledge, governed domain inquiry, support, complaint, matching intent
- prevent forced case creation for greetings/general questions
- add focused tests

### PR 2 — CaseType, ArtifactType, Source/Validation metadata

- add stable enums/models or equivalent
- avoid broad migrations unless explicitly approved
- use non-destructive additive changes only

### PR 3 — SealFamily / SealType normalization

- implement alias mapping
- add seal application profile
- add tests for RWDR, flat gasket, hydraulic, pneumatic, mechanical seal, O-ring, packing, unknown

### PR 4 — Next Best Question / Needs + Current-State Analysis

- ask 1-3 targeted questions
- include empathy and short technical reason
- no overwhelming form dump

### PR 5 — RAG-first knowledge and LLM-research fallback labeling

- implement or harden RAG-miss behavior
- fallback output must be explicitly unvalidated
- do not persist fallback as authoritative truth

### PR 6 — RFQ consent and revision freeze hardening

- preserve old pilot-readiness RFQ safety
- ensure consent includes export intent and partner-network disclosure if applicable

### PR 7 — RFQ from field envelopes

- ensure critical values are envelope-based
- no bare authoritative values

### PR 8 — Technical support / compatibility inquiry mode

- handle customer questions, material/medium compatibility, oil reports
- generate technical inquiry summary and safe customer reply draft
- no final compatibility claim

### PR 9 — Complaint / failure-analysis intake mode

- capture damage pattern, conditions, evidence needs
- generate internal engineering note
- no final root cause

### PR 10 — Partner model and paid-network eligibility

- model partner capabilities
- no UI ranking yet if matching is not ready
- add tests for active paid eligibility

### PR 11 — Manufacturer matching engine

- technical fit within active paid partners
- fit reasons, gaps, no-fit state
- no payment-influenced ranking

### PR 12 — Manufacturer fit UI

- show disclosure
- show fit reasons and gaps
- show no-fit state
- no automatic dispatch

### PR 13 — Multi-artifact workspace tabs

- render RFQ, matching, support, complaint, documents, open points
- use backend projections

### PR 14 — Replacement / legacy part intake

- unknown old part, photos, dimensions, old codes, ERP noise
- identity confidence and missing-data checklist

### PR 15 — Compliance/certificate request handling

- certificate checklist
- no compliance overclaim

### PR 16 — Security hardening

- tenant/IDOR
- upload/IP
- secret/env hygiene
- production-safe settings

### PR 17 — Guard tests

- prompt injection
- compliance overclaim
- fallback labeling
- partner disclosure
- no cross-tenant access

### PR 18 — Frontend lint and journey stabilization

- main flows stable
- lint/test cleanup
- no unsafe copy

If the user explicitly asks for legacy pilot-readiness work, use the older pilot PR order from `docs/implementation/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md`, but do not contradict v0.8.3 safety rules.

---

## Coding-agent operating model

### Default: audit first, patch second

For every non-trivial task:

1. Read `AGENTS.md`.
2. Read `docs/implementation/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md`.
3. Read `docs/implementation/SEALAI_V08_2_STACK_AUDIT_IST.md`.
4. Read `docs/implementation/SEALAI_V08_3_IMPLEMENTATION_ROADMAP_FROM_AUDIT.md`.
5. Read `docs/implementation/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md` if the task touches RFQ, consent, upload/IP, settings, secrets, tenant boundaries, or pilot guardrails.
6. Inspect relevant code and tests.
7. Map the existing productive seam.
8. State what is true now.
9. State the exact misalignment.
10. Propose the smallest productive patch.
11. Patch only that seam.
12. Add or update focused tests.
13. Run relevant validation.
14. Report changed files, commands, results, risks, and next patch.

### Patch-size policy

A good patch:

- touches one architectural seam or bounded behavior
- has clear before/after behavior
- adds or updates focused tests
- avoids speculative abstractions
- avoids dead future code
- improves v0.8.2 readiness

A bad patch:

- mixes state models, UI, routing, RFQ, matching, support, and business logic in one patch
- creates parallel services beside the real seam
- hides broad rewrites inside a small patch
- implements later-phase features without explicit instruction
- adds prompt-only backend rules
- makes frontend authoritative for engineering truth
- changes deployment or production services without explicit instruction

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
- conversation-intent tests
- case-creation decision tests
- seal-type normalization tests
- next-best-question tests
- RAG/fallback labeling tests
- deterministic calculation tests
- RFQ freeze/stale/consent tests
- manufacturer matching eligibility and fit tests
- no-fit matching tests
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

## Required tests by major v0.8.2 seam

### Conversation Intelligence

Required tests:

- greeting does not create a case
- general sealing question does not create a case
- frustrated leakage message triggers empathic triage
- real RFQ intent enters governed case intake
- manufacturer-search intent enters matching route
- emergency intent asks one most important question
- off-topic input stays outside engineering state

### SealType normalization

Required tests:

- `Wellendichtring`, `RWDR`, `WDR`, `Simmerring`, `oil seal` normalize to radial shaft seal
- `Flachdichtung`, `Flanschdichtung`, `gasket` normalize correctly
- `Stangendichtung` resolves via hydraulic/pneumatic context or stays uncertain
- `Gleitringdichtung` normalizes to mechanical seal
- unknown terms remain unknown with confidence note
- alias mapping does not over-confirm case truth

### RAG and LLM fallback

Required tests:

- RAG hit is marked validated/documented according to source
- RAG miss triggers fallback only when enabled
- fallback output is labeled `llm_research_fallback`
- fallback output has `validation_status=unvalidated`
- fallback output is not used as final engineering truth
- fallback output is not used as compliance evidence

### RFQ Consent Boundary

Required tests:

- missing `user_acknowledged_no_final_release` is rejected
- open points present plus missing `user_acknowledged_open_points` is rejected
- missing export intent is rejected where required
- missing partner-network disclosure acknowledgement is rejected where matching is included
- valid acknowledgements are accepted
- stale preview is rejected
- dispatch remains disabled unless explicitly implemented

### Manufacturer matching

Required tests:

- unpaid partners do not appear
- inactive partners do not appear
- paid active partners may appear only if technically relevant
- fit score is based on technical capabilities
- no suitable partner state is supported
- partner-network disclosure is present
- no "best in market" wording appears
- payment tier does not alter technical fit score

### Support / compatibility

Required tests:

- compatibility question does not become final compatibility approval
- missing exact values/units are surfaced
- compound-specific evidence is required for compound-specific claims
- safe customer reply draft is generated
- internal engineering note does not admit or reject liability

### Complaint / failure analysis

Required tests:

- failure intake captures damage pattern and conditions
- no final root cause is claimed
- missing photos/evidence are requested where useful
- installation, media, pressure, temperature, and operating conditions are considered
- escalation recommendation is cautious

### Upload/IP Safety

Required tests:

- dynamic LLM metadata extraction is disabled or gated by default
- unsafe/spoofed uploads are rejected or safely handled
- internal paths are redacted from health/error responses
- parser errors are safe
- upload-derived values remain candidates

### Tenant Guards

Required tests:

- user A cannot read user B case/RFQ/document/artifact
- user A cannot consent user B preview
- user A cannot access user B matching artifact
- cross-tenant IDs return 403 or 404
- no client-provided ID is trusted without server-side authorization

### Compliance and Prompt Injection

Required tests:

- FDA/ATEX/Food/Pharma/Drinking Water overclaims are rejected or rewritten safely
- uploaded document instructions cannot override product/system rules
- allowed language remains cautious and review-oriented
- fallback knowledge is not treated as compliance proof

---

## Migration and schema-change policy

Do not run production migrations unless explicitly instructed.

If schema changes are needed:

- create additive, non-destructive migrations where possible
- do not execute them against production
- document why the migration is needed
- include rollback/down behavior if migration tooling supports it
- never drop or truncate data without explicit instruction
- do not hide migrations inside unrelated PRs

For early v0.8.2 work, prefer lightweight additive models and tests over broad schema redesign.

---

## Dependency policy

Do not add new dependencies unless necessary.

If a dependency is needed:

- explain why the current stack cannot do the job
- check existing dependencies first
- prefer small, maintained libraries
- avoid large framework additions
- update lockfiles consistently
- run relevant tests

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
16. Matching before partner eligibility and disclosure are reliable.
17. Seal Passport before post-RFQ/support validation exists.
18. Reorder before validated solution identity exists.
19. Price claims without manufacturer confirmation.
20. Compliance hand-waving.
21. ERP/CRM gravity distorting the product.
22. New dependencies without necessity.
23. Broad refactors before blockers are fixed.
24. A one-size-fits-all intake for every seal type.
25. LLM fallback presented as validated knowledge.
26. Paid ranking presented as technical fit.
27. Overwhelming the user with long question lists.
28. Treating angry or vague user input as low-quality instead of triage-worthy.

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
- the task changes payment/partner ranking rules
- the task introduces legal/compliance claims
- requirements conflict with this file
- the smallest safe patch is unclear

If the issue is a normal code ambiguity inside the requested PR, make a conservative best-effort choice and document it.

---

## Glossary

### CaseField

A field envelope around a technical value. It preserves status, provenance, confidence, source type, validation status, evidence references, units, and confirmation requirements.

### EngineeringValue

A normalized technical value with unit, raw input, canonical value, and interpretation metadata.

### Governor

The backend authority that validates proposed changes, applies rules, records events, updates state, triggers recalculation, and produces projections.

### Decision Understanding Layer

The projection that explains what SeaLAI understands, why it matters, what is not yet decidable, and which next decision or question is most useful.

### Conversation Intelligence Layer

The routing and interaction layer that distinguishes small talk, general knowledge, needs analysis, current-state analysis, governed case intake, support, complaint, and matching flows.

### SealApplicationProfile

A structured profile for the sealing system involved in a case. It includes seal family/type, confidence, motion, application domain, required fields, risk flags, and partner capability requirements.

### RFQ Freeze

Binding an RFQ preview/export to a specific `case_revision` so later state changes can mark it stale rather than silently changing it.

### Manufacturer Fit Matrix

A governed artifact showing technical fit within the active paid SeaLAI partner network. It must include disclosure, reasons, gaps, verification level, and no-fit support.

### LLM-research fallback

A non-validated knowledge fallback used only when RAG/verified knowledge is insufficient and fallback is configured/allowed. It must be labeled as unvalidated and must not become authoritative engineering truth.

### RFQ Qualification Copilot

The earlier Phase-1 product identity: a governed assistant that turns unclear sealing situations into manufacturer-review-ready RFQ preparation, not final product selection.

---

## Final instruction

When in doubt, choose the path that:

- preserves the current SSoT
- implements v0.8.2 incrementally
- keeps engineering truth governed in the backend
- treats LLM output as proposal/orientation, not truth
- asks precise next-best questions instead of dumping forms
- makes uncertainty visible
- preserves provenance, evidence, source type, and validation status
- respects tenant boundaries
- keeps partner matching transparent
- separates paid network eligibility from technical fit score
- avoids duplicate architecture
- avoids unsafe overclaims
- produces the smallest reliable patch
- adds tests or evidence for the next agent
