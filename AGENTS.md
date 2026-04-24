## Frontend Design Source of Truth



For all UI, layout, styling, motion, card, timeline, rail, cockpit, chat-workspace, and responsive frontend work, `frontend/DESIGN.md` is binding.



Agents must read and follow `frontend/DESIGN.md` before making any frontend change.

If `frontend/DESIGN.md` conflicts with ad-hoc stylistic guesses, `frontend/DESIGN.md` wins.

Do not invent a parallel design system.


# AGENTS.md

## Purpose

This repository builds **SeaLAI** as a **conversation-first engineering system for sealing technology**.

SeaLAI must feel to the user like a **very experienced senior sealing engineer**:

* calm
* precise
* friendly
* technically strong
* honest about uncertainty
* excellent at structured needs analysis
* capable of both general sealing knowledge dialogue and case qualification

At the same time, SeaLAI is **not** allowed to behave like a free-floating black-box chatbot.
Its engineering truth must remain governed, deterministic where required, provenance-aware, and auditable.

This file defines the binding operating rules for all coding agents working in this repository, especially Codex CLI, Claude Code, and similar autonomous patching agents.

---

## Product north star

Build SeaLAI as:

> **a conversation-first engineering runtime for sealing technology**
> that combines a human-feeling expert dialogue surface with a governed technical backend.

SeaLAI is **not** only an RFQ preparation tool.
SeaLAI is **not** only a chat UI.
SeaLAI is **not** only a matching engine.

SeaLAI must unify three things:

1. **Expert conversation**

   * greetings
   * smalltalk
   * meta questions
   * general sealing knowledge questions
   * technical explanation
   * structured clarification

2. **Governed engineering intelligence**

   * request typing
   * engineering path detection
   * provenance-aware parameter capture
   * deterministic calculations
   * proactive advisories
   * medium intelligence
   * readiness and blockers

3. **Neutral manufacturer-facing deliverables**

   * technical prequalification
   * transparent open points
   * problem-first manufacturer matching
   * JSON / PDF artifacts
   * manufacturer-ready inquiry packages

This direction is consistent with the product concept's chat-plus-cockpit model, structured technical clarification, transparent open points, and manufacturer-ready artifacts fileciteturn2file0L57-L99, and with the binding supplement requirements for Fast Responder, Problem-First Matching, Application Patterns, Proactive Advisory, Cascading Calculations, Medium Intelligence, Educational Output, Multimodal Intake, and Knowledge-to-Case Bridge fileciteturn2file2L1-L84 fileciteturn2file4L1-L41 fileciteturn2file5L1-L92 fileciteturn2file6L1-L23.

---

## Binding authority order

When multiple docs or code paths disagree, use this order:

1. `konzept/sealai_ssot_architecture_plan.md`
2. SSoT supplements v1 / v2 / v3
3. this `AGENTS.md`
4. current codebase behavior
5. older notes, legacy prompts, or convenience shortcuts

Important:

* Current code is **not automatically correct**.
* Existing behavior may be provisional, legacy, or too broad.
* Follow the SSoT intent, but do it through **small, evidence-based patches**.

---

## Non-negotiable invariants

### 1. One visible speaker

The user must experience **one coherent expert speaker**.
Even if multiple backend components contribute, the visible answer must read like a single experienced engineer.

### 2. One authoritative engineering truth

The LLM is **not** the engineering source of truth.
Authoritative engineering state must come from governed backend logic, structured state, deterministic services, provenance-aware extraction, and explicit service contracts.

### 3. Frontstage / backstage split

Always preserve this split:

* **Frontstage** = conversational engineer persona
* **Backstage** = governed system logic

Frontstage should feel human and natural.
Backstage should be strict, structured, testable, and auditable.

### 4. No silent certainty

SeaLAI must never present uncertainty as certainty.
Missing inputs, assumptions, derived values, and plausible-but-unverified medium facts must be visible as such.

### 5. No second architecture

Do **not** introduce a separate chatbot architecture beside the governed system.
Do **not** fork product logic into “chat mode” vs. “real mode” as separate apps.
Build modes and response paths inside the same architecture.

### 6. No duplicate truths

Do not create competing authorities across:

* frontend-derived state
* Redis-only state
* Postgres durable state
* LangGraph ephemeral state
* artifact-only state

Prefer an explicit truth hierarchy and stable backend projection.

### 7. No broad rewrites

Do not rewrite large areas just because they are complex.
Prefer minimal, seam-based refactors that move the system toward the target architecture.

### 8. Problem-first neutrality

Manufacturer matching must start from the user's structured problem and derive required capabilities.
It must not start from manufacturer claims and work backward.

### 9. Educational but not patronizing

SeaLAI should teach while qualifying, but never talk down to the user.
Assume the user may lack domain exposure, not intelligence.

### 10. Keep ERP/CRM out of core conversation flow initially

ERPNext, CRM, and surrounding business systems are downstream integration edges.
Do not pull them into the core chat / qualification / governed runtime unless the patch explicitly targets an integration seam.

---

## Required architectural direction

### Runtime must converge toward two top-level layers

#### Layer 1 — Fast Responder

For:

* greeting
* short acknowledgement
* meta questions about SeaLAI
* blocked content

Properties:

* no case creation
* no graph invocation
* no durable case persistence
* fast response
* still persona-consistent

#### Layer 2 — Governed Flow

For:

* knowledge queries
* domain inquiries
* structured qualification
* calculations
* advisories
* medium intelligence
* matching
* artifacts

Properties:

* may use LangGraph
* may create durable state
* must remain provenance-aware and auditable

This split is binding and follows supplement v3 Fast Responder and Knowledge-to-Case bridge semantics fileciteturn2file2L1-L34 fileciteturn2file4L1-L41.

---

## SeaLAI persona contract

All user-visible reply work must preserve the intended persona.

SeaLAI should sound like:

* a senior sealing engineer
* empathetic, but not theatrical
* direct, but not cold
* technical, but not jargon-heavy unless the user is clearly advanced
* structured and calm
* honest about uncertainty
* able to explain trade-offs
* able to guide without sounding like a form wizard

SeaLAI should be able to handle:

* general sealing technology questions
* material comparisons
* request clarification
* retrofit and RCA entry points
* spare-part identification entry points
* structured engineering qualification
* light smalltalk without breaking trust

SeaLAI must **not** sound like:

* a generic AI assistant
* a marketing chatbot
* a rigid decision tree
* a manufacturer sales bot
* an overconfident technical oracle

---

## Coding-agent operating model

### Default mode: audit first, patch second

For any non-trivial task, agents must:

1. inspect current architecture and exact insertion points
2. identify the smallest productive seam
3. explain what is true now
4. explain what is misaligned
5. patch minimally
6. add or update tests
7. validate with concrete commands
8. stop

### Never do these things first

Do **not** start with:

* speculative refactors
* file explosions
* parallel abstractions
* framework replacement
* new orchestration layers without need
* frontend rewrites to hide backend problems

### Always optimize for

* minimal diff
* exact contracts
* explicit service seams
* backward safety
* testability
* architectural clarity

---

## Patch-size policy

Agents must prefer **small named patches**.

A good patch:

* changes one architectural seam or one bounded behavior
* is explainable in a short diagnosis
* has clear before/after behavior
* has focused tests
* does not hide broad rewiring inside a “small” claim

A bad patch:

* touches many unrelated files
* mixes routing, UI, data model, and business logic together
* adds abstractions before proving the seam
* introduces dead code or “future maybe” systems

---

## Required service seams

Agents should prefer to work through explicit services instead of route-heavy or node-heavy incidental logic.

Target first-class seams include:

* `fast_responder_service`
* `knowledge_service`
* `knowledge_session_context_service`
* `bridge_to_case_service`
* `pattern_matcher_service`
* `medium_intelligence_service`
* `advisory_engine`
* `calculation_cascade_service`
* `problem_first_matching_service`
* `cockpit_projection_service`
* `artifact_generation_service`

If equivalent seams already exist under different names, prefer **refactoring toward them** instead of duplicating them.

---

## State authority rules

Agents must preserve or improve a clear state authority hierarchy.

Preferred hierarchy:

1. **Postgres durable case truth**
2. **Redis live/session truth**
3. **LangGraph turn state**
4. **Frontend rendering state**

Rules:

* frontend must not be authoritative for engineering truth
* derived values need provenance
* changed upstream values must stale downstream dependents
* cockpit projection must come from backend authority, not UI inference

---

## Retrieval / knowledge rules

SeaLAI must support both:

* general knowledge dialogue
* case-specific governed qualification

Agents must preserve this distinction:

### Knowledge query path

Use when the user is:

* asking a general question
* learning concepts
* comparing materials in abstract terms
* exploring before committing to a case

### Domain inquiry path

Use when the user is:

* describing a real application
* providing operating parameters
* asking for a fit or recommendation for their case
* seeking manufacturers or a structured qualification

The bridge between both must be explicit and smooth, not a hard reset.

---

## Fast responder rules

Fast Responder is a hard architectural boundary.

It must only handle the explicitly allowed classes:

* GREETING
* META_QUESTION
* BLOCKED

It must not:

* create cases
* write durable case state
* invoke the full graph
* silently expand into more categories without explicit authority

If classification is ambiguous, fail safe toward the governed path.

---

## Matching rules

All manufacturer matching work must stay aligned with problem-first matching.

Required flow:

1. derive structured problem signature
2. derive required capabilities
3. hard-filter candidates on required capabilities where appropriate
4. score technical fit
5. expose rationale and gaps

Forbidden:

* capability-first ranking
* marketing-text-based matching
* sponsor bonus in technical ranking
* hiding zero-match outcomes

---

## Advisory and calculation rules

### Advisory engine

Advisories must be:

* deterministic
* parameter-triggered
* visible
* non-blocking unless explicitly compliance-hard
* phrased as engineering guidance, not command

### Calculation cascade

Calculations must be:

* synchronous where lightweight
* dependency-aware
* provenance-tagged
* stale-aware
* re-executed when required inputs change

Do not bury calculations inside prompt text if they can be implemented as governed services.

---

## Medium intelligence rules

Medium Intelligence may combine:

* registry-grounded facts
* LLM synthesis
* user-provided statements

But provenance must be explicit.

Never present plausible LLM synthesis as validated engineering truth.
If a separate medium card or surface exists, it must visually distinguish confidence / provenance tiers.

---

## Frontend rules

Frontend must remain a rendering and interaction layer.

Frontend may:

* render the visible expert answer
* render cockpit state
* render advisories and medium cards
* trigger clarification and explanation flows
* show progress / readiness / provenance surfaces

Frontend must not:

* compute authoritative engineering readiness
* own calculation truth
* silently reconcile conflicting backend states
* invent its own matching logic

---

## Tests and validation policy

Every meaningful patch must include validation.

### Minimum expectation

Provide:

* exact files changed
* why those files were chosen
* focused tests or updated tests
* concrete repo-root commands to verify behavior

### Preferred validation types

* unit tests for service seams
* route or contract tests for API envelopes
* projection tests for cockpit mapping
* regression tests for routing boundaries
* deterministic examples for calculations and advisories

### Repo-root command rule

Always provide commands from:

```bash
/home/thorsten/sealai
```

Do not provide validation commands from subdirectories unless explicitly required.

---

## Prompting rules for coding agents

When generating implementation plans or prompts, agents must be given:

* **Task Summary**
* **Architectural intent**
* **Current seam / suspected insertion point**
* **Files to inspect first**
* **Constraints / invariants**
* **Expected artifacts**
* **Tests required**
* **Validation commands**
* **Explicit forbidden moves**

This repo is not optimized for vague “improve this” prompting.
It is optimized for **evidence-based seam work**.

---

## Required reporting format for patches

Every patch review or implementation summary should follow this shape:

### 1. Short diagnosis

What is true now? What is the specific gap?

### 2. Exact files changed

List only the files actually changed.

### 3. Why these files

Explain the seam.

### 4. Exact behavioral delta

What changed at runtime?

### 5. Validation

Which commands/tests prove it?

### 6. Risks / limitations

What remains intentionally unresolved?

### 7. Next productive patch

What is the smallest sensible next move?

---

## Anti-patterns

Agents must actively avoid these anti-patterns:

### 1. Architecture cosplay

Inventing fancy abstractions that do not improve production behavior.

### 2. Hidden rewrites

Claiming a “small patch” while quietly broad-refactoring half the stack.

### 3. Prompt as backend

Encoding durable engineering rules only in prompts when they should be deterministic services.

### 4. UI concealment

Using the frontend to hide unresolved backend authority problems.

### 5. Duplicate seaming

Adding a new service because the old one is messy, instead of extracting or tightening the real seam.

### 6. Overeager persistence

Creating cases for every interaction, including greetings or casual learning.

### 7. Overblocking

Pushing lightweight human interactions into heavy governed workflows unnecessarily.

### 8. False empathy

Writing the product voice as exaggerated, gushy, emoji-heavy, or insincere.

### 9. Silent assumption loading

Auto-filling engineering-critical fields without clearly marking them as proposed and overrideable.

### 10. ERP gravity

Letting ERP / CRM integration concerns distort core conversation and qualification architecture too early.

---

## Current stack assumption

Agents should assume the current productive stack is approximately:

* FastAPI backend
* LangGraph-based governed orchestration
* Redis live/checkpoint layer
* Postgres durable case storage
* Qdrant retrieval layer
* Keycloak auth boundary
* Dockerized deployment behind nginx

This stack is sufficient for the target architecture.
The job is to **shape it correctly**, not replace it.

---

## Immediate implementation priority order

Unless a task explicitly overrides this, prefer this order:

1. pre-gate boundary hardening
2. fast responder seam
3. unified visible response contract
4. knowledge service
5. knowledge session context
6. bridge from knowledge to case
7. pattern selection and explicit prefills
8. medium intelligence
9. advisory engine
10. calculation cascade
11. problem-first matching hardening
12. artifact generation cleanup
13. cockpit projection normalization
14. explainability / educational surfaces

This order maximizes product feel early while preserving architectural safety.

---

## Final instruction

When in doubt, choose the option that:

* keeps the system conversation-first for the user
* keeps engineering truth governed in the backend
* preserves neutrality
* reduces architectural duplication
* produces the smallest reliable patch
* leaves clear evidence for the next agent

SeaLAI should increasingly feel like:

> **one experienced sealing engineer on the surface, backed by a disciplined engineering system underneath**

That is the standard all implementation work in this repository must serve.
