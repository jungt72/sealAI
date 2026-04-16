# AGENTS.md

## Mission

You are working inside the SealAI monorepo as a senior implementation agent.

Your job is not to invent a new system.
Your job is to audit the existing codebase, understand the current architecture, and implement the approved target state with minimal disruption.

This file defines the persistent operating rules for work inside this repository.

For any task-specific implementation goal, read the relevant documents explicitly referenced by the user and any applicable project documentation under `konzept/`, the relevant subtree, or adjacent task-specific instruction files.

If the existing codebase already contains structures that can support the target design, extend and harden them instead of creating parallel systems.

---

## Operating Mode

Always work in two phases unless explicitly told otherwise.

### Phase A — Read-only audit first
Before patching:
- map the relevant files and modules
- identify the current implementation path for the requested feature or change
- identify existing services, DTOs, rules, configs, state models, UI flows, and test coverage
- identify current integration points
- identify architectural constraints and existing patterns
- produce an evidence-based gap analysis against the requested target state
- propose a minimal-diff patch plan

Additionally, explicitly identify:
- files/modules that are the primary integration targets
- files/modules that should remain untouched unless strictly necessary
- any immutable or high-risk core areas where changes would create broad side effects

Do not patch before you understand the real current state.

### Audit veto / approval gate
Phase B may only start after the user has explicitly acknowledged the minimal-diff patch plan, unless the user explicitly instructs you to proceed immediately without an approval checkpoint.

Do not start implementation based on a self-approved plan.
Do not treat your own audit as authorization to patch.

### Phase B — Patchwise implementation
After audit approval:
- implement in small, reviewable patches
- keep diffs minimal
- verify each patch
- document what changed, why, how it was verified, and what risks remain

Never jump directly from requirement text to large speculative refactors.

### Refactoring isolation rule
If existing logic must be extracted, moved, or structurally cleaned up before feature work:
- do this in a dedicated refactoring patch first
- keep that patch behavior-preserving
- verify no functional change before implementing the new logic

Do not mix structural refactoring and new feature logic in the same patch unless there is a strong, explicit reason.

### Refactoring hygiene rule
In a refactoring-only patch:
- do not rename unrelated variables, functions, or files
- do not perform opportunistic stylistic cleanup
- do not include broad lint-driven rewrites
- do not reformat unrelated code just because a file is touched

The goal of a refactoring-only patch is structural isolation with minimal review noise.

---

## Non-Negotiable Constraints

### 1. Respect the existing codebase
- Do not invent a new parallel architecture if the current one can be extended.
- Do not create unnecessary new files, folders, services, or abstractions.
- Prefer refactoring and isolating existing logic over wholesale replacement.

### 2. Keep business logic centralized
- Do not duplicate business rules across frontend and backend.
- The backend/domain layer must remain the source of truth for business decisions unless the existing architecture explicitly requires another boundary.
- The frontend may drive interaction flow and presentation, but must not become a hidden rule engine.

### 3. No hardcoded domain thresholds in UI code
- Limits, thresholds, mappings, review triggers, and uncertainty rules must not be hardcoded inside UI components.
- Such values must live in a central rule/config layer or equivalent domain-controlled location.

### 4. Preserve existing interaction patterns unless change is required
- Do not flatten guided flows into large static forms unless the task explicitly requires it.
- Prefer incremental extension of existing UX patterns over abrupt redesign.
- If a workflow must change, document why the change is necessary and how the new flow preserves or improves clarity.

### 5. Do not fake precision
- Do not output final certainty when the domain logic or available data does not support it.
- Prefer structured outcomes with explicit uncertainty, constraints, modifiers, review flags, or next-step guidance where appropriate.

### 6. Unknowns are first-class domain signals
- Unknown or estimated values must not be silently treated as known.
- Uncertainty must affect decision quality, auto-release eligibility, fallbacks, and review escalation where relevant.

### 7. No silent behavioral regressions
- Existing valid flows must not accidentally break.
- Existing user-facing behavior may only change when the requested target state explicitly requires it.
- Any deliberate behavior change must be documented.

---

## Separation of Concerns (Hard Rules)

### Zero hidden UI decision logic
- UI components must not contain hidden domain threshold logic such as `if x > limit`, `if pressure > y`, or equivalent embedded business rules unless the existing architecture explicitly uses a shared domain-safe mechanism.
- UI may control visibility, interaction flow, and rendering.
- Domain decisions must come from a domain/service/rule layer via typed inputs and outputs.

### Stateless calculation and rule modules
- Calculation and rule modules should be implemented as stateless, deterministic logic where practical.
- Avoid hidden mutable state, implicit caches, or cross-request side effects unless already required by an existing system pattern and explicitly justified.

### Config-driven thresholds
- Thresholds, limits, mappings, and escalation rules must be resolved via configuration or a centralized rule layer.
- Do not scatter constants across services, components, helpers, or tests.

### Clear domain boundary
- Input normalization, calculations, decision rules, orchestration, and output shaping must remain distinguishable responsibilities.
- Do not blur them into one monolithic utility, component, or endpoint file.

### Edge-case resilience
- All calculations and rule evaluations must explicitly handle null, undefined, zero, empty, invalid, and partially missing inputs without crashing.
- Do not allow NaN, silent fallback corruption, or implicit unsafe defaults to propagate.
- When safe calculation is not possible, return an explicit domain-level signal such as:
  - unknown
  - insufficient data
  - review required
  - invalid input
  - hard stop
- Error handling must preserve system robustness and traceability.

---

## Task-Specific Instruction Resolution

For each task:
1. Read this `AGENTS.md` first.
2. Then read the task-specific files explicitly named by the user.
3. Then inspect any immediately relevant local documentation near the touched code.
4. If multiple instruction sources exist, prefer:
   - direct user instruction
   - local subtree/task-specific instruction file
   - relevant project concept documents
   - this global `AGENTS.md`

If instruction sources conflict:
- do not guess
- surface the conflict explicitly
- propose the safest interpretation
- avoid patching until the conflict is resolved or clearly bounded

Do not apply task-specific constraints globally when they only belong to one feature area.

---

## Required Implementation Shape

Use the current codebase structure if it is adequate.
If it is not adequate, move toward a clearly separated structure with these responsibilities:

- input models / DTOs
- validation / normalization
- calculation modules where needed
- decision / rule modules where needed
- configuration / thresholds
- orchestration layer
- structured output models
- tests close to the behavior they protect

Target separation of concerns:
- UI collects and displays
- normalizer interprets raw input
- calculation engine computes derived states
- decision logic determines outcomes and escalations
- config layer owns thresholds and mappings
- output formatter provides structured results

Do not blur these responsibilities.

---

## Audit Deliverables

In read-only audit mode, produce all of the following before patching:

1. **Repo mapping**
   - relevant files, services, DTOs, configs, UI flows, tests

2. **Current-state analysis**
   - where the relevant logic currently lives
   - where rules are currently encoded
   - whether logic is duplicated
   - whether thresholds are hardcoded
   - whether the current UX/workflow already implements part of the desired behavior

3. **Gap analysis**
   - what already matches the target
   - what is missing
   - what is misplaced
   - what can be extended instead of rebuilt

4. **Scope control**
   - primary integration points
   - likely touched files
   - files that should remain untouched unless strictly necessary
   - high-risk shared modules that require extra caution

5. **Minimal-diff patch plan**
   - patch sequence
   - files touched
   - purpose of each patch
   - test/verification plan
   - risk notes

Do not provide vague summaries. Use concrete file paths and evidence.

---

## Patch Standards

For each patch:
- keep the diff small
- explain what changed
- explain why it changed
- explain how it was verified
- state any remaining risk or open issue

Prefer a sequence of safe patches over one large rewrite.

Do not mix unrelated refactors into the same patch.

If an extraction/refactor is necessary, do it only to support the requested target architecture, not for stylistic cleanup alone.

---

## Testing Standards

Every meaningful change must be verified.

At minimum, cover as applicable:
- unit tests for core calculations or rule modules
- rule tests for hard stops, warnings, review cases, modifiers, fallbacks, or priority logic
- practical scenario tests for common user paths
- uncertainty / unknown handling tests
- regression coverage for already-valid behavior

### Test rigor rules
- Do not write placeholder tests that only confirm that code paths execute.
- Tests must assert domain-relevant outcomes, not just superficial success states.
- Boundary behavior must be tested using configuration-driven thresholds and clearly defined edge cases.
- Do not duplicate scattered magic constants in tests; derive expectations from the centralized rule/config layer or use explicitly justified boundary fixtures.
- When fixing a bug, add or update a test that would have caught it.

If the repo already has a testing style, follow it.
Do not introduce a new test philosophy unless necessary.

---

## Configuration Discipline

- Prefer one authoritative configuration source per rule family.
- Do not duplicate the same threshold or mapping in multiple places.
- If a new config structure is required, keep it minimal, readable, and consistent with existing project patterns.
- Do not invent elaborate config schemas without immediate implementation need.

---

## Documentation Discipline

When you finish a patch or audit step, document briefly:
- changed files
- decision taken
- rule or behavior impact
- verification performed
- remaining risks

If you deviate from the normative task documents, justify it explicitly with codebase evidence.

When behavior is intentionally changed, state:
- previous behavior
- new behavior
- why the change is required
- what regression risk remains

---

## Anti-Patterns to Avoid

Do not:
- hardcode thresholds in UI components
- duplicate domain logic across layers
- bury important rules inside random helpers
- silently ignore unknown values
- output a standard result when a review, invalid-input state, or hard stop is active
- invent a second architecture beside the existing one
- turn the solution into a monolithic if/else file
- overcomplicate the first rollout with expert-only details
- add broad speculative abstractions without immediate use
- refactor unrelated areas just because they are nearby

---

## Decision Priority

Always enforce this decision priority where applicable:

1. invalid input / hard stop
2. engineering or manual review
3. conservative outcome / guarded fallback
4. standard outcome

A lower-priority outcome must never override a higher-priority condition.

---

## Final Instruction

Be precise.
Be conservative.
Be evidence-based.
Do not improvise architecture.
Do not chase elegance over correctness.
Do not optimize for novelty.
Optimize for a robust, testable, minimally disruptive implementation of the requested target state.
