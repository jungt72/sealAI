Binding execution rules for Codex CLI and autonomous coding agents in this repository.
This is not a product spec. For product vision, architecture, and domain logic, see the reference documents below.
---
1. Context
SealAI is a sealing-intelligence platform for sealing technology.
Product core: Guidance + Calculation + Qualification.
Governing principles:
Engineering before language
No silent certainty
Deterministic where it matters
Evidence-bound intelligence
One visible engineer, many internal paths
From ambiguity to qualification
Reference documents
Document	Purpose	Location
SealAI Gesamtkonzept	Product vision, modes, target architecture	`/docs/sealai_gesamtkonzept.md`
Case State & Live Case Build Spec	State schema, layers, invalidation, events, panel	`/docs/specs/case_state_spec.md`
Domain Contracts Spec	Qualification logic, material/RWDR rules, thresholds	`/docs/specs/domain_contracts_spec.md`
Runtime Architecture Spec	Router, paths, LangGraph scope, service boundaries	`/docs/specs/runtime_architecture_spec.md`
Conversation & UX Contract	Persona, prompts, verbindlichkeit language, style	`/docs/specs/conversation_contract.md`
When a task touches a specific domain, read the relevant spec before coding.
---
2. Execution doctrine
2.1 Read first, patch second
Before any non-trivial patch, search the codebase first. No write before read.
```bash
# Find where the affected state/function is actually used
grep -rn "case_state\|CaseState" services/ state/

# Find the real source of truth for a field
grep -rn "qualification_level" --include="*.py" .

# Find shadow or duplicate paths
grep -rn "def calculate_speed\|circumferential" services/

# Check actual dependency versions
cat pyproject.toml | grep -A5 "\[dependencies\]"

# Find all tests covering the affected path
grep -rn "test.*qualification\|def test_" tests/ --include="*.py" -l
```
From the search results, identify:
real runtime entrypoints (not test-only or dead paths)
real state transitions
real source of truth
real storage and orchestration paths
real tests covering the path
2.2 Extend, do not fork
Always extend the existing architecture.
Do not create parallel workflows, duplicate pipelines, shadow registries, or secondary sources of truth unless a human explicitly instructs it.
2.3 Smallest safe patch wins
Use the smallest correct intervention at the real binding point.
Do not refactor broadly if a local correction is sufficient.
CLI-specific: Do not rewrite entire files. Use precise, line-level edits. If a patch touches more than 50 lines in a single file, justify why a smaller intervention was not possible.
2.4 Evidence over intent
Decisions must be based on code evidence, runtime evidence, data model evidence, and test evidence.
Do not trust comments, stale docs, or intended behavior over actual code.
2.5 No silent certainty
If something is missing, ambiguous, or only partially wired into the real runtime path, say so explicitly.
Do not present partial implementation as completed architecture.
2.6 Determinism over cleverness
Prefer explicit contracts, typed state, deterministic rule paths, explicit blockers, explicit status transitions, and traceable evidence over soft heuristics and hidden inference.
2.7 No architecture drift
If the current implementation deviates from the target architecture, report it explicitly.
Do not silently normalize the mismatch.
---
3. Mandatory workflow
Every non-trivial task follows this sequence. No exceptions.
Step 1: Read-only audit
Identify:
the real productive path (not test-only or dead paths)
the real source of truth for the data/state being changed
duplicate or shadow paths that might conflict
the smallest safe integration point
what must not break
Step 2: Patch plan
Before writing code, state:
exact files to change
why this is the smallest correct patch
what behavior is preserved
which tests prove the patch
Step 3: One bounded patch
Each patch solves one coherent problem.
Do not mix unrelated concerns in one patch.
Step 4: Focused verification (Green-or-Revert)
Run the smallest directly relevant tests immediately.
Expand test scope only after the local patch is green.
```bash
# Priority 1: Unit test for the changed code
pytest tests/unit/path/to/affected_test.py -x -q

# Priority 2: Type check (mandatory for any state/ changes)
mypy services/affected_service/ state/

# Priority 3: Lint
ruff check . --fix
```
If tests fail after the patch: revert first, analyze second. Do not stack fixes on top of a broken patch. Return to the last green state, then re-evaluate the approach.
Step 5: Honest closeout
State:
what is now fixed
what remains intentionally open
whether the path is production-safe or only partially improved
---
4. Source-of-truth rules
4.1 No second source of truth
Never introduce a second truth for: routing, state, status progression, evidence readiness, qualification status, selection outcome, or provenance.
If one truth already exists in the productive path, extend that truth.
4.2 Structured state is authoritative
Operational decisions must be represented in explicit structured state or persisted metadata.
Do not make operational decisions depend on loose text interpretation.
4.3 Blockers must be visible
Missing critical data, unresolved contradictions, audit blockers, and review requirements must remain visible in the real state and API path.
Do not bury blockers in local helper logic.
---
5. Deterministic engineering path rules
5.1 Deterministic where it matters
Calculations, hard stops, qualification decisions, admissibility checks, and RFQ-relevant decisions must be deterministic.
5.2 No probabilistic logic inside the deterministic core
Inside qualification, calculation, and engineering signal services: no LLM reasoning, no semantic similarity as final arbiter, no hidden soft scoring, no free-form output as source of truth.
5.3 Fail closed
Missing critical data, unresolved contradictions, scope violations, or insufficient evidence must lead to: block, review, conservative downgrade, or manufacturer validation requirement. Never silently continue as if certainty existed.
5.4 No evidence escalation
Weak evidence must not be escalated into compound-grade certainty. Positive capability statements require evidence that actually supports them.
5.5 Stable rationale
Official rationale, qualification explanations, release blockers, and admissibility reasons must come from stable templates or deterministic mappings, not improvised generative text.
---
6. Four-layer case discipline
When working on anything related to case state, preserve the strict layer separation:
Layer	Contains	Written by	Rules
L1: Raw Inputs	User-provided or confirmed values	Intake/Extraction service only	Provenance required. Null = not yet provided.
L2: Derived Calculations	Deterministic calculations from L1	Calculation Service only	No LLM. No heuristics. Recompute on L1 change.
L3: Engineering Signals	Deterministic classifications from L1+L2	Signal Classification Service only	No LLM. Threshold-based. Boundary flagging mandatory.
L4: Qualification Results	Deterministic domain decisions from L1–L3	Qualification Engine only	Input snapshot required. No auto-requalification. User confirms.
Hard constraints:
No LLM may write to L2, L3, or L4. Ever.
Dependency direction is strictly L1 → L2 → L3 → L4. No reverse coupling.
L4 invalidation on L1 change requires user confirmation before re-run.
Every value must carry provenance. A value without provenance is a bug.
For full schema details, see Case State Spec.
---
7. LLM / Domain Service / RAG boundaries
Component	Responsible for	NOT responsible for
LLMs	Conversation, explanation, extraction, summarization, routing assistance, output projection	Calculations, qualification decisions, hard stops, engineering signals
Deterministic Services	Calculations, engineering signals, hard stops, qualification, RFQ classifications	Conversation, explanation
RAG	Knowledge, context, evidence, source binding	Final qualification decisions, material/geometry decisions in qualified paths
This separation is binding. If a task would move logic across these boundaries, stop and ask.
---
8. Testing rules
8.1 Test the real productive path
Prefer tests that exercise real entrypoints, real state transitions, real routing, real persistence, and real API visibility — not helper-only tests.
8.2 Each patch carries its own regression proof
Add or update the smallest set of tests that proves the patch in the productive path.
8.3 Tests do not justify shadow architecture
A green test on a non-productive path does not validate production behavior.
8.4 Preserve neighboring guarantees
After a patch: run directly affected tests first, then adjacent regressions, then broad suites only where needed.
Test commands
```bash
# Unit tests
pytest tests/unit/ -x -q

# Qualification path tests
pytest tests/qualification/ -x -q

# Calculation service tests
pytest tests/calculation/ -x -q

# Full suite
pytest tests/ -x -q

# Lint
ruff check .

# Type check
mypy services/
```
> **Note:** Adjust these commands if the repository structure changes. The commands above reflect the intended layout. If actual paths differ, use the real paths.
---
9. Migration and persistence rules
9.1 New fields must earn their existence
Every new persisted field must have a clear productive use in the current runtime path.
9.2 Normalized fields over encoded tags
When behavior depends on a value, use a typed, normalized field — not a raw tag or string convention.
9.3 No speculative growth
Do not add registries, staging models, or side stores without a real runtime need that the central model cannot safely carry.
---
10. File ownership and path rules
> **Note:** Update this section as the repository structure evolves. These are the intended boundaries.
Path	Domain	Key rules
`services/calculation/`	Deterministic calculations (L2)	No LLM code. Pure math. Full test coverage.
`services/signals/`	Engineering signal classification (L3)	No LLM code. Threshold-based only.
`services/qualification/`	Qualification engine (L4)	No LLM code. Governed evidence only. Input snapshot mandatory.
`services/knowledge/`	Knowledge / RAG path	LLM + RAG allowed. Not release-relevant.
`services/guidance/`	Guidance / intake orchestration	LLM for conversation. Extraction feeds L1 only.
`services/router/`	Interaction router	Rule-first, model-fallback. Auditable decisions.
`state/`	Case state schema and persistence	Single source of truth. No shadow state elsewhere.
`frontend/panel/`	Case panel UI	Renders backend state only. No business logic. No independent data.
`frontend/chat/`	Chat UI	Renders conversation. Does not compute engineering values.
`prompts/`	System prompts and templates	Persona-consistent. Verbindlichkeit-labeled.
`tests/`	All tests	Mirror service structure. Each service has own test dir.
Path-specific constraints
Any file in `services/calculation/`, `services/signals/`, `services/qualification/`: Zero LLM imports. Zero probabilistic logic. If you find yourself importing an LLM client here, stop — you are violating the architecture.
Any file in `state/`: Changes here affect everything downstream. Extra scrutiny required.
Any file in `services/router/`: Router changes affect every user interaction. Test with ambiguous inputs, not just clean ones.
---
11. Stop-and-ask rules
Codex must stop and request human confirmation before:
changing any qualification rule or threshold
adding or removing a field in CaseState
modifying router logic or escalation rules
changing a hard stop condition
adding a new external dependency
moving logic across the LLM / Deterministic / RAG boundary
creating a new service or module (rather than extending an existing one)
any change that affects more than 3 files in the deterministic core
When stopping, describe: what you would do, why, what it would affect, and what alternatives exist.
---
12. Branch and commit rules
```
Branch naming:    feat/<short-description>
                  fix/<short-description>
                  refactor/<short-description>

Commit messages:  Imperative mood, max 72 chars first line
                  Reference issue/ticket if applicable
                  Body: what changed and why (not how — the diff shows how)

Examples:
  feat: add circumferential-speed calculation to RWDR derived values
  fix: correct PV-value unit from MPa/s to MPa·m/s
  refactor: consolidate duplicate temperature-class thresholds
```
No force pushes to `main`.
No direct commits to `main` without review.
---
13. Reporting format
Quick format (for small patches, terminal output)
```
AUDIT:    [source of truth found, shadow paths: none/listed]
PLAN:     [file(s)] — [why this is minimal]
PATCH:    [what changed]
VERIFY:   [test command] → [pass/fail]
GAPS:     [what remains open, or "none"]
```
Full format (for non-trivial tasks)
1. Audit — Real entrypoints, source of truth, shadow paths, smallest integration point
2. Plan — Exact files, why minimal, what must not break, tests to run
3. Patch — Exact changes, what truth was extended/removed/consolidated
4. Verify — Commands run, results, regression assessment
5. Gaps — Remaining blockers, deferred work, production-safety assessment
---
14. Prohibited actions
Do not:
invent new architecture when local extension is enough
create second sources of truth
patch only tests and call production fixed
convert weak evidence into strong certainty
leave filter parameters nonfunctional
mix unrelated refactors into one patch
hide uncertainty behind confident prose
preserve dead code "just in case"
treat LangGraph as the universal path for everything
let RAG make final qualification decisions
put business logic in the frontend
use LLM output as input to deterministic services without extraction and validation
add untyped fields to CaseState
rewrite entire files when a line-level patch suffices
silently "fix" this AGENTS.md or specs to match drifted code — report the drift instead
---
15. Decision rule when unsure
When choosing between:
Option A	Option B	Choose
Broad refactor	Local fix	Local fix
New subsystem	Extend existing	Extend existing
Soft heuristic	Explicit rule	Explicit rule
Convenience path	Productive path	Productive path
Implicit behavior	Explicit contract	Explicit contract
Silent continuation	Stop and ask	Stop and ask
Unless a human explicitly instructs otherwise.
---
16. Environment
```
Python:     3.11+
Node:       20+
Package:    pip (with --break-system-packages if needed)
Lint:       ruff
Types:      mypy
Tests:      pytest
```
> **Note:** Verify actual versions and tools against the repository's own configuration files (pyproject.toml, package.json, etc.). If they differ, the repository config wins.
---
This file is the execution constitution. The product is defined elsewhere. Build discipline is defined here.
