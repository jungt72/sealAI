# CLAUDE.md

## Purpose

This repository contains the SealAI monorepo.

SealAI is a domain-specific decision platform for sealing technology.
The system is intended to support:
- direct technical answers with low latency,
- guided technical clarification,
- deterministic calculations and rule checks,
- qualified technical cases,
- and later commercial handover to manufacturers / distributors.

This file defines the mandatory working rules for Claude Code in this repository.

---

## Source-of-truth hierarchy

SealAI currently has three distinct source documents with different roles.

### 1. Normative target architecture
- `/home/thorsten/sealai/konzept/Master_SealAI_Gesamtkonzept.md`

This defines the normative end-state architecture and product model.

### 2. Approved refactor execution plan
- `/home/thorsten/sealai/konzept/SealAI_Umbauplan_Single_Source_of_Truth.md`

This defines:
- the approved migration strategy,
- phase order,
- work packages,
- protected architectural zones,
- definitions of done,
- and explicit non-goals for each stage.

### 3. Claude execution rules
- `/home/thorsten/sealai/CLAUDE.md`

This file defines how Claude Code must behave while auditing and implementing changes in this repository.

### Interpretation rule
- For architecture audits, compare the runtime primarily against `Master_SealAI_Gesamtkonzept.md`, while also checking whether the current system can evolve along the path described in `SealAI_Umbauplan_Single_Source_of_Truth.md`.
- For implementation work, follow `SealAI_Umbauplan_Single_Source_of_Truth.md` first, and use `Master_SealAI_Gesamtkonzept.md` as the normative end-state reference.
- Do not invent a new roadmap, new phases, new migration order, or alternative architecture track unless explicitly asked to challenge the approved plan.

### Conflict rule
If the master concept defines the end-state but the refactor plan intentionally delays a capability to a later phase:
- do **not** pull that capability forward on your own,
- do **not** expand scope,
- do **not** treat later-phase ideas as current package requirements.

Respect:
- phase boundaries,
- package boundaries,
- protected zones,
- and explicit non-goals in the approved refactor plan.

---

## Core operating principles

### 1. Engineering before language
Do not accept a smooth narrative as proof.
Prefer runtime truth, explicit dataflow, contracts, schema, and tested behavior.

### 2. No silent certainty
If a conclusion is not clearly supported by code, config, tests, runtime behavior, or source data, say so.
Mark uncertainty explicitly.

### 3. Deterministic where it matters
Anything calculable, rule-bound, schema-bound, safety-relevant, qualification-relevant, tenant-relevant, or audit-relevant must not be delegated to free-form LLM behavior.

### 4. Evidence-bound analysis
Every important claim must be grounded in repository evidence:
- file path,
- symbol / function / module,
- line reference or excerpt,
- and a concrete explanation of why it matters.

### 5. Direct answer first, structured escalation only when needed
SealAI must preserve fast paths for direct user help.
Do not push every interaction into heavy stateful orchestration.
Architectural evaluation must explicitly check whether the current stack:
- supports direct low-latency help when appropriate,
- and only escalates when missing data, contradictions, deterministic calculations, review, or qualification make that necessary.

### 6. Minimal-diff evolution
Do not invent a parallel architecture if the existing code can be repaired.
Prefer the smallest viable change that moves the real system toward the target concept.

### 7. Repository reality beats theory
Do not recommend large-scale rewrites unless you can prove that bounded correction is not viable.

### 8. Preserve first, then refactor, then add
Strong existing architecture must be preserved where possible.
Do not destroy a strong core just because a cleaner abstraction could be imagined.

---

## Protected zones

These architectural zones are currently considered strong and must not be casually broken during refactor work unless a package explicitly requires it.

### Protected zone A — 5-layer sealing state
- `SealingAIState`
- observed / normalized / asserted / governance / cycle layers

### Protected zone B — deterministic firewall and guard mechanics
- guard / whitelist / invariant enforcement
- deterministic layer protection

### Protected zone C — RWDR deterministic core
- RWDR orchestration and deterministic decision logic
- hard stops / review flags / deterministic qualification core

### Protected zone D — deterministic visible case projection
- visible case narrative generation
- deterministic case-state projection
- backend-as-source-of-truth rendering contract

### Protected zone E — frontend projection contracts
- case-state projection contracts
- typed frontend models
- backend primacy over reconstructed frontend semantics

Do not weaken these zones in the name of simplification.

---

## Default work mode

Unless explicitly instructed otherwise, start in:

**READ-ONLY ARCHITECTURE AUDIT MODE**

That means:
- do not edit code,
- do not create files,
- do not refactor,
- do not “helpfully” patch things while still investigating,
- do not generate implementation prompts during diagnosis,
- do not jump to solutions before proving the current state.

First map the system.
Then diagnose exactly.
Only after that may you propose patch plans.
Only after explicit implementation instruction may you change code.

---

## Implementation mode for approved refactor work

If implementation is explicitly requested, switch from READ-ONLY ARCHITECTURE AUDIT MODE to:

**BOUNDED REFACTOR IMPLEMENTATION MODE**

In this mode:

### 1. Work only against an explicitly named refactor package
Implementation work must be tied to a specific package from:
- `/home/thorsten/sealai/konzept/SealAI_Umbauplan_Single_Source_of_Truth.md`

Examples:
- `0A.1`
- `0A.2`
- `0A.3`
- `0B.1`

Do not implement “general improvements” outside a named package.

### 2. Do not combine unrelated packages
Do not merge multiple work packages into a single patch unless explicitly instructed.

### 3. Before editing, restate the package
Before changing code, explicitly state:
- package id,
- package title,
- target architectural effect,
- exact files expected to be touched,
- protected zones that must remain intact.

### 4. Preserve strong architecture
While implementing:
- preserve protected zones,
- prefer minimal-diff changes,
- do not opportunistically refactor unrelated systems,
- do not silently expand scope,
- do not rewrite stable subsystems because a new abstraction seems cleaner.

### 5. After implementation, map back to the package DoD
After each patch:
- state what changed,
- state what remains intentionally unfinished,
- state which package DoD items are now satisfied,
- and report exact tests run.

---

## Mandatory audit workflow

When asked to audit the current stack against the master concept, follow this order.

### Phase A — Repo and runtime mapping
Map the actual system before judging it.

You must identify at minimum:
- primary backend entrypoints,
- frontend entrypoints,
- API boundaries,
- chat/request lifecycle,
- state handling,
- streaming path / SSE path,
- current routing/orchestration path,
- deterministic calculation modules,
- RAG/retrieval path,
- structured domain data sources,
- data stores,
- auth / tenant isolation path,
- logging / audit path,
- export / review / resume path,
- commercial / handover path if present.

Do not rely on naming assumptions.
Trace real code paths.

### Phase B — Current architecture extraction
Extract the current architecture as implemented, not as intended.

You must explicitly determine:
- where the visible conversation is generated,
- where routing decisions happen,
- whether there is an explicit interaction policy or only implicit prompt logic,
- what currently counts as fast path vs structured path,
- where deterministic services begin and end,
- how case/state objects are shaped,
- what evidence / source binding exists,
- what auditability exists,
- what review / resume / export support exists,
- what commercial/handover logic exists,
- what versioning/reproducibility exists,
- and where the architecture currently violates the target model.

### Phase C — Delta against target concept
Audit the current stack against the target concept in `Master_SealAI_Gesamtkonzept.md`.

At minimum, evaluate the current implementation against these target areas:
1. direct answer vs structured escalation,
2. explicit interaction policy,
3. fast response layer,
4. structured case layer,
5. deterministic domain services,
6. domain data layer,
7. evidence / RAG separation,
8. governance / audit / review,
9. commercial / handover separation,
10. coverage / boundary communication,
11. reproducibility and versioning,
12. role-aware output projection,
13. human review hooks,
14. outcome / feedback readiness,
15. multimodal extensibility,
16. tenant-safe end-to-end boundaries,
17. normalization responsibilities.

### Phase D — Delta against approved refactor plan
When relevant, also audit whether the current repository can evolve along the approved path in `SealAI_Umbauplan_Single_Source_of_Truth.md`.

Determine:
- which refactor packages are already partially approximated,
- which ones require bounded refactor,
- which ones require deeper structural work,
- and which protected zones already provide a good migration anchor.

### Phase E — Severity-ranked findings
Classify findings using this severity model:
- **Critical**: architectural violation that undermines correctness, qualification, tenant safety, auditability, trust boundaries, or deterministic authority
- **High**: strong target mismatch that will materially block the concept or the approved refactor path
- **Medium**: important gap or weak seam
- **Low**: cleanup, clarity, or future-readiness issue

### Phase F — Minimal patch strategy
If asked for remediation, propose:
- smallest viable patch sequence,
- bounded by real file paths,
- tied to the approved package order where applicable,
- with expected behavior change,
- and validation commands/tests for each patch.

Never collapse everything into one giant rewrite plan unless absolutely unavoidable.

---

## Required output format for architecture audits

When auditing, structure the answer like this:

1. **Executive verdict**
   - short, sharp, evidence-based

2. **Current-state architecture map**
   - what actually exists today

3. **Target-concept delta**
   - where current stack aligns
   - where it diverges

4. **Refactor-plan relevance**
   - which packages from the approved plan are implicated
   - which protected zones matter

5. **Severity-ranked findings**
   - each with:
     - title
     - impact
     - evidence
     - why it matters against the master concept
     - why it matters against the approved refactor plan

6. **Recommended patch sequence**
   - minimal patches in correct dependency order

7. **Validation plan**
   - concrete commands / tests / runtime checks

8. **Risks / unknowns**
   - things not fully provable yet

Do not produce fluffy reviews.
Do not produce architecture theater.
Do not hide missing evidence.

---

## Hard constraints for implementation work

If and only if implementation is explicitly requested:

### 1. Patch in small increments
One bounded change set at a time.

### 2. Preserve existing repository structure where possible
Do not create unnecessary frameworks, wrappers, or abstraction layers.

### 3. Protect existing contracts
Be especially careful around:
- API schemas,
- SSE / streaming behavior,
- persisted state shape,
- auth / tenant boundaries,
- frontend projections,
- visible narrative contracts,
- qualification / result contracts.

### 4. Test every patch
Every code change must come with:
- exact tests run,
- exact results,
- and whether the patch changed behavior, contract, or only internals.

### 5. No speculative refactors
Do not perform opportunistic cleanup unrelated to the current package goal.

### 6. No fake completeness
If a concept is only partially implemented, say so clearly.
Do not pretend the architecture is complete because interfaces exist.

### 7. Every implementation response must map to a refactor package
For each implementation task, explicitly state:
- package id
- package title
- files touched
- protected zones checked
- tests run
- definition-of-done status

Do not present implementation work without mapping it back to the approved refactor plan.

---

## SealAI-specific architectural expectations

When auditing or changing the system, explicitly inspect these concept-critical areas.

### A. Interaction Policy
The target architecture requires an explicit interaction policy layer.
Audit whether the current stack has:
- deterministic routing gates,
- completeness checks,
- escalation rules,
- streaming mode selection,
- coverage checks,
- result-form distinction,
- or whether these concerns are hidden inside prompts or ad hoc controller logic.

### B. Fast path protection
Audit whether the current system preserves low-latency direct-response behavior for:
- explanation,
- material comparison,
- knowledge questions,
- simple technical help,
- and other safe direct answers.

Do not accept an architecture that turns every question into heavy orchestration.

### C. Guided recommendation vs qualified case separation
Audit whether the system distinguishes:
- orienting guidance,
- deterministic result,
- and binding/qualified case behavior.

Do not accept an architecture where guidance and qualification collapse into one undifferentiated heavy path.

### D. Deterministic boundary
Audit whether calculations and rule-bound decisions are truly outside LLM generation.

### E. Domain data vs RAG separation
Audit whether structured technical truth is stored and queried as structured data,
not buried inside retrieval-only document logic.

### F. Audit and reproducibility
Audit whether the system can later explain:
- what input it used,
- what source/version it used,
- what service version it used,
- what prompt/model/policy/projection version shaped the visible output.

### G. Human review readiness
Audit whether the state model can support later expert review without destructive redesign.

### H. Neutrality and commercial separation
Audit whether commercial or product matching logic contaminates technical qualification logic.

### I. Coverage and boundary communication
Audit whether the system can explicitly say:
- what it knows,
- what it does not know,
- when it is orienting,
- when it is calculating,
- when it is qualifying,
- and when it is out of scope.

### J. Tenant and security boundaries
SealAI is multi-tenant.
Audit whether tenant isolation is explicit and end-to-end:
- auth identity,
- state lookup,
- persistence,
- retrieval filters,
- structured data queries,
- session/cache behavior,
- and export/review paths.

### K. Streaming discipline
Audit whether only user-visible answer paths stream to the client,
and whether intermediate reasoning, tool, or graph-local output is leaking into the visible user stream.

### L. Placeholder/demo truth contamination
Audit whether demo data, placeholder registries, synthetic records, or ungoverned flat files are being treated as production truth.

---

## Current repository-specific expectations

Assume the repository is intended to evolve toward these patterns unless evidence shows otherwise:
- one visible conversational layer,
- explicit result-form distinction,
- explicit fast vs structured path behavior,
- deterministic services for calculations and rule checks,
- stateful case handling only where needed,
- strong auditability,
- evidence/source binding,
- tenant-safe architecture,
- explicit coverage/boundary communication,
- minimal-diff evolution,
- and concept-driven convergence toward the master concept via the approved refactor plan.

Do not assume the current code already satisfies these goals.
Prove or disprove them.

---

## Forbidden behaviors

Do not:
- invent missing architecture and describe it as if it already exists,
- infer behavior from filenames alone,
- rewrite major subsystems without proving necessity,
- hide uncertainty,
- use vague phrases like “appears fine” without evidence,
- recommend “use LangGraph everywhere” or any equivalent universal abstraction,
- move calculable logic into prompts,
- mix commercial ranking into technical qualification,
- collapse direct answers and structured qualification into one undifferentiated chat path,
- pull later-phase architecture into the current package without instruction,
- replace protected core architecture with a cleaner-but-bigger rewrite,
- treat demo/domain placeholder data as production truth,
- bypass the approved package sequence from `SealAI_Umbauplan_Single_Source_of_Truth.md`,
- weaken tenant boundaries, auditability, or deterministic authority in order to simplify implementation.

---

## Preferred style

Be blunt, precise, and technical.

Good:
- “`backend/app/.../router.py` still couples visible answer generation to qualification gating, so fast-path direct answers are not an explicit architectural layer.”
- “`...` stores normalized inputs but not source confidence or contradiction metadata, so the case model cannot represent fragmentary industrial inputs safely.”
- “`tenant_id` is extracted correctly but discarded in retrieval, so the repository has a local approximation of tenant safety only.”

Bad:
- “The architecture could be improved.”
- “Consider making it more modular.”
- “This may benefit from a cleaner design.”

---

## Definition of done for an audit

An audit is only complete when it:
1. maps the real current stack,
2. measures it against the master concept,
3. checks compatibility with the approved refactor plan where relevant,
4. identifies the highest-risk deltas,
5. proposes the smallest viable correction path,
6. names the protected zones that must survive the change,
7. and makes clear what is proven vs assumed.

---

## Definition of done for an implementation package

An implementation package is only complete when it:
1. maps to an explicit approved package id,
2. preserves the protected zones,
3. changes only the intended scope,
4. satisfies the package-level definition of done,
5. reports exact tests and results,
6. states what remains intentionally unfinished,
7. and leaves the repository in a stable, reviewable state.
