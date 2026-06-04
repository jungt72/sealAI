# SeaLAI — Phase 1a Implementation Plan

**Version:** 1.0
**Datum:** 2026-04-18
**Status:** Binding implementation contract. Codex CLI executes per sprint. Claude Code audits per audit-gate. Founder approves each gate transition.
**Scope:** Phase 1a — Backend-Core transition from current code state to Authority-conformant architecture per Founder Decisions Phase 1a.
**Prerequisite authority:** Product North Star, Base SSoT, Supplements v1/v2/v3, Engineering Depth Guide (PTFE-RWDR), Founder Decisions, Phase 1a Audit Report.
**Working parameters:** 30 hours/week founder availability. Tests green before every merge. No fixed deadline — quality first.

---

## 0. How to read this plan

This plan is executable. It is structured so that:

- A human reads **Part A** to understand the big picture
- Codex CLI reads **Part B** to know what to build next
- Claude Code reads **Part C** to know what to audit
- The founder reads **Part D** to know when to approve or halt

Every sprint has a Definition of Done. Every patch has an acceptance test. Every audit gate has specific checks. If any check fails, the sprint stalls until the issue is resolved — no silent work-arounds.

---

# PART A — Sequencing Strategy

## A.1 The ordering logic

The eight founder decisions are not independent. They form a dependency graph:

```
Decision #1 (Persistence foundation)
    ↓ (unblocks)
    ├── Decision #6 (Tenant model) ─────┐
    ├── Decision #5 (Classification)    │
    │       ↓                           │
    │   Decision #4 (RCA degrade)       │
    │                                   │
    ├── Decision #2 (Stack consolidation) ← (depends on Decision #1 + #5)
    │                                   │
    └── Decision #7 (Norm modules) ─────┤
                                        │
                              Decision #8 (Knowledge queries)
                                        │
                                        ↓
                              Supplement v3 operational services
                                        ↓
                              Legacy cleanup (final)
```

### Blocking rules

- Nothing depending on persistence (Decisions #6, #2, #7, all Supplement v3 services) can start before Decision #1's persistence extensions are merged and tested.
- Decision #5 (Pre-Gate Classifier + Output Classifier) can run in parallel with Decision #1 but merges after.
- Decision #2 (stack consolidation, removal of services/langgraph/ and services/fast_brain/) MUST be the last major transition, because it touches endpoints and breaks any lingering consumer of the legacy paths.
- Decision #3 (COI firewall log) is a documentation artifact; it can land anywhere but is required before external manufacturer onboarding.

### Parallelizable vs. serial

- **Serial (one at a time):** Database migrations, service_worker registration, endpoint deprecation.
- **Parallelizable (can run in parallel within a sprint):** Different new services that don't share tables (e.g., `knowledge_service` and `medium_intelligence_service` can be developed in parallel within the same sprint).

## A.2 The sprint structure

The plan defines six sprints (Sprint 0 through Sprint 5). Each sprint is self-contained with its own Definition of Done.

| Sprint | Focus | Rough duration at 30h/week | Blocking next? |
|--------|-------|---------------------------|----------------|
| **Sprint 0 — Safety & Prerequisites** | API key rotation, COI firewall log, baseline state capture | 3-5 days | Yes — all later sprints assume clean baseline |
| **Sprint 1 — Persistence Foundation** | case_service, mutation_events, outbox, extended cases schema | 2 weeks | Yes — unblocks nearly everything |
| **Sprint 2 — Classification Layer** | pre_gate_classifier, output_classifier, ResultForm removal | 1-2 weeks | Yes — unblocks Fast Responder + gate logic |
| **Sprint 3 — Service Layer Core** | terminology_service, capability tables, norm_modules, advisory_engine, inquiry_extract_service, anonymization_service | 2-3 weeks | Partial — Sprint 4 can start overlapping |
| **Sprint 4 — Supplement v3 Operationals** | fast_responder_service, knowledge_service, application_pattern_service, medium_intelligence_service, formula_library + cascading calculations | 3-4 weeks | No — Sprint 5 is cleanup |
| **Sprint 5 — Stack Consolidation & Cleanup** | Remove services/langgraph/, services/fast_brain/, legacy feature flags, endpoint deprecation, YAML rule migration | 1-2 weeks | End of Phase 1a |

Total realistic duration at 30h/week: **9-14 weeks.** This is intentionally not a deadline, it's a range.

## A.3 The audit-gate principle

Between every sprint, **Claude Code runs an audit** in read-only mode against the Authority set. The audit produces a pass/fail verdict and an Issue List. Sprint transitions only happen after the audit passes.

Claude Code audits NEVER rewrite code during a gate. They only diagnose. If issues are found, a remediation patch is scheduled and the gate reopens only after the remediation is merged.

The founder approves every gate transition explicitly. No silent progression.

## A.4 Work-splitting philosophy

**Codex CLI is the primary executor.** It gets precise, scoped patches with clear acceptance criteria. It produces code and tests per patch. It does NOT make architectural decisions.

**Claude Code is the architect and auditor.** It is invoked for:
- Writing the detailed implementation spec of ambiguous areas before Codex CLI sees them
- Running audit gates between sprints
- Reviewing any patch that crosses architectural boundaries
- Resolving interpretation ambiguities that Codex CLI surfaces

**The founder is the decision-maker.** For every gate, the founder sees the audit report and either approves progression or halts the sprint for remediation.

## A.5 Rollback strategy

Every sprint ends on a **releasable commit**. That means:
- All tests green
- No broken imports
- No half-migrated tables
- All feature flags in consistent state

If a sprint fails mid-way, the rollback is: `git reset --hard` to the start-of-sprint commit. This is why sprints are sized carefully — losing a full sprint of work is painful but survivable; losing three is existential.

Within a sprint, patches are either merged (tests green, passes local review) or abandoned. There is no "merge and fix later" policy.

---

# PART B — Sprint Definitions (Codex CLI Execution Guide)

## Sprint 0 — Safety & Prerequisites

**Goal:** Ensure the operating environment is safe and the baseline state is clearly captured before any architectural change begins.

**Duration estimate:** 3-5 days at 30h/week.

### Sprint 0 rationale

Before writing any new code, three prerequisites must be satisfied:
1. Known security incident (exposed API keys) must be resolved
2. COI firewall declaration must be a committed artifact
3. The current-state baseline must be captured so we have a reference point to compare against

### Sprint 0 Patches

---

**Patch 0.1 — Rotate OpenAI and LangChain API keys.**

**Owner:** Founder (manual action, not executable by agent).

**Actions:**
1. Revoke current OpenAI API key used by SeaLAI
2. Generate new OpenAI API key with spend cap at current level
3. Revoke current LangChain API key
4. Generate new LangChain API key
5. Update `.env` file on server with new values
6. Restart services (`docker compose down && docker compose up -d` or equivalent)
7. Verify services reach ready state

**Acceptance criteria:**
- Old keys return "invalid" when tested
- Services restart cleanly
- A health-check endpoint (existing or new) returns 200

**Claude Code audit:** Verify no keys are committed to git. Run `git log -p --all | grep -i -E "sk-|api[_-]key"` on the entire history. If any key is found, create an issue to rotate those historical references as well.

---

**Patch 0.2 — Create `konzept/coi_firewall_log.md`.**

**Owner:** Codex CLI (content written by Claude Code first, committed by Codex CLI).

**Content:** The formal declaration per Founder Decision #3, based on the content structure in `founder_decisions_phase_1a.md` Decision #3, section "Implementation implications".

**Required sections in the file:**
- Purpose statement (why the log exists)
- Covered SeaLAI artifacts list (KB-JSONs, YAML rules, prompts, Qdrant documents, golden cases, test fixtures)
- Founder declaration (explicit four-point clean statement)
- Review trigger events (quarterly, new manufacturer content, employer change, first external pilot, legal inquiry)
- Date and signature line (founder's name)

**Acceptance:**
- File exists at `konzept/coi_firewall_log.md`
- File is committed
- Founder has reviewed and electronically signed (by explicit git commit message including founder name)

**Claude Code audit:** None needed; this is documentation only.

---

**Patch 0.3 — Baseline state capture.**

**Owner:** Codex CLI.

**Actions:**

Create `audits/phase_1a_baseline_2026-04-XX.md` containing:
- Current branch SHA: `git rev-parse HEAD`
- Current test suite state (what passes, what fails) by running `pytest` and capturing output
- Current database state: schema dump via `pg_dump --schema-only sealai` (stored as companion artifact)
- Current file inventory under `backend/app/` (tree output, file counts, line counts per module)
- Current LangGraph node sizes (line counts): `wc -l backend/app/agent/graph/nodes/*.py`
- Frontend baseline: `npm test` or equivalent, capture output
- Linter baseline: `ruff check .` output, `mypy` output
- Current feature flags in `core/config.py`
- Current endpoint list: grep for router definitions

**Acceptance:**
- File exists at `audits/phase_1a_baseline_YYYY-MM-DD.md`
- File is committed
- All baseline measurements are reproducible (commands listed in the document)

**Claude Code audit:** Verify the baseline is complete. Cross-check against Phase 1a Audit Report (2026-04-17) — do the baseline measurements match the audit findings? If discrepancies exist, flag them.

---

### Sprint 0 Definition of Done

- Patch 0.1, 0.2, 0.3 all merged to branch
- `git log --oneline` shows the three commits
- Audit gate 0→1 passed (see Part C)

### Sprint 0 Audit Gate (Gate 0→1)

See `Part C, Gate 0→1`.

---

## Sprint 1 — Persistence Foundation

**Goal:** Implement Decision #1 in full. Create the new tables, the `case_service` module with `apply_mutation()`, the outbox worker scaffolding, and the extended `cases` table schema. All mutation writes go through a single service layer. No LangGraph node writes directly to Postgres.

**Duration estimate:** 2 weeks at 30h/week.

### Sprint 1 rationale

Every later feature depends on the `case_service.apply_mutation()` single-write-path. Without this foundation, every new service would create its own inconsistent data-access layer. This sprint is the single biggest unblocker.

### Sprint 1 Patches

---

**Patch 1.1 — Alembic migration 01: extend cases table schema.**

**Owner:** Codex CLI.

**Scope:** SQL migration only. No Python service code yet.

**Changes:**

Create migration `alembic/versions/XXXX_extend_cases_table_phase1a.py`.

Add columns to `cases`:
- `tenant_id UUID` (nullable initially, will be set NOT NULL in Patch 1.7)
- `case_revision INTEGER NOT NULL DEFAULT 0`
- `schema_version VARCHAR(32)` (for migration tracking per supplement v1 §36.3)
- `ruleset_version VARCHAR(32)`
- `calc_library_version VARCHAR(32)`
- `risk_engine_version VARCHAR(32)`
- `phase VARCHAR(32)` (per supplement v1 §36.3)
- `routing_path VARCHAR(32)` (transitional; will be phased out in Sprint 2)
- `pre_gate_classification VARCHAR(32)` (replaces routing_path in Sprint 2)
- `request_type VARCHAR(32)` (per AGENTS §5.1)
- `engineering_path VARCHAR(32)` (per AGENTS §5.1)
- `sealing_material_family VARCHAR(64)` (per supplement v2 §39)
- `application_pattern_id UUID` (FK to application_patterns — Sprint 4)
- `rfq_ready BOOLEAN NOT NULL DEFAULT false`
- `inquiry_admissible BOOLEAN NOT NULL DEFAULT false`
- `payload JSONB NOT NULL DEFAULT '{}'::jsonb` (structured case content)
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Add indexes:
- `CREATE INDEX idx_cases_tenant_id ON cases(tenant_id)`
- `CREATE INDEX idx_cases_engineering_path ON cases(engineering_path)`
- `CREATE INDEX idx_cases_request_type ON cases(request_type)`
- `CREATE INDEX idx_cases_updated_at ON cases(updated_at DESC)`
- `CREATE INDEX idx_cases_payload_sealing_family ON cases((payload->>'sealing_material_family'))`

**Data migration:** Delete existing cases (test data only per Decision #6):
```sql
DELETE FROM cases;
DELETE FROM case_state_snapshots;
```

Pre-existing records in related tables that FK to cases (if any) must be deleted in the correct order. Codex CLI must inspect foreign key relationships first and write the DELETE order correctly.

**Acceptance tests:**
- `alembic upgrade head` runs without error
- `alembic downgrade -1` successfully reverses the migration
- `SELECT count(*) FROM cases` = 0 after migration
- All expected columns exist with correct types (verified by `\d cases` in psql)

**Claude Code review:** Spot-check the migration SQL. Verify:
- No DROP statements on existing columns (non-destructive for unrelated columns)
- Index creation order is sensible
- Default values are compatible with NOT NULL constraints in later patches

---

**Patch 1.2 — Alembic migration 02: create mutation_events table.**

**Owner:** Codex CLI.

**Scope:** SQL migration only.

**Changes:**

Create migration `alembic/versions/XXXX_create_mutation_events.py`.

```sql
CREATE TABLE mutation_events (
  mutation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  tenant_id UUID,
  event_type VARCHAR(64) NOT NULL,
  payload JSONB NOT NULL,
  case_revision_before INTEGER NOT NULL,
  case_revision_after INTEGER NOT NULL,
  actor VARCHAR(128) NOT NULL,
  actor_type VARCHAR(32) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_mutation_events_case_id ON mutation_events(case_id);
CREATE INDEX idx_mutation_events_tenant_id ON mutation_events(tenant_id);
CREATE INDEX idx_mutation_events_event_type ON mutation_events(event_type);
CREATE INDEX idx_mutation_events_created_at ON mutation_events(created_at DESC);
```

`event_type` values initially defined:
- `case_created`
- `field_updated`
- `pattern_assigned`
- `compound_selected`
- `norm_check_result`
- `calculation_result`
- `medium_identified`
- `advisory_generated`
- `readiness_changed`
- `output_class_assigned`

(This enumeration lives in Python enum `MutationEventType`, defined in Patch 1.4.)

**Acceptance tests:**
- Migration applies
- Migration reverses
- `INSERT INTO mutation_events` with valid payload succeeds
- `INSERT` with missing required column fails with clear error

---

**Patch 1.3 — Alembic migration 03: create outbox table.**

**Owner:** Codex CLI.

**Scope:** SQL migration only.

```sql
CREATE TABLE outbox (
  outbox_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID REFERENCES cases(case_id) ON DELETE CASCADE,
  mutation_id UUID REFERENCES mutation_events(mutation_id),
  tenant_id UUID,
  task_type VARCHAR(64) NOT NULL,
  payload JSONB NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  priority INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT valid_status CHECK (status IN ('pending', 'in_progress', 'completed', 'failed_retryable', 'failed_permanent'))
);

CREATE INDEX idx_outbox_status_priority ON outbox(status, priority DESC, next_attempt_at);
CREATE INDEX idx_outbox_case_id ON outbox(case_id);
CREATE INDEX idx_outbox_tenant_id ON outbox(tenant_id);
```

`task_type` values initially defined:
- `risk_score_recompute`
- `notify_audit_log`
- `project_case_snapshot`

(More task types added in later sprints as services emerge.)

**Acceptance tests:**
- Migration applies / reverses
- Status check constraint works
- Foreign keys enforce correctly

---

**Patch 1.4 — Domain-layer mutation event types (Python).**

**Owner:** Codex CLI.

**Scope:** New Python module, no database.

**Files:**

Create `backend/app/domain/mutation_events.py`:

```python
from enum import Enum
from typing import Any
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

class MutationEventType(str, Enum):
    CASE_CREATED = "case_created"
    FIELD_UPDATED = "field_updated"
    PATTERN_ASSIGNED = "pattern_assigned"
    COMPOUND_SELECTED = "compound_selected"
    NORM_CHECK_RESULT = "norm_check_result"
    CALCULATION_RESULT = "calculation_result"
    MEDIUM_IDENTIFIED = "medium_identified"
    ADVISORY_GENERATED = "advisory_generated"
    READINESS_CHANGED = "readiness_changed"
    OUTPUT_CLASS_ASSIGNED = "output_class_assigned"

class ActorType(str, Enum):
    USER = "user"
    AGENT = "agent"
    SERVICE = "service"
    SYSTEM = "system"

@dataclass(frozen=True)
class MutationEvent:
    mutation_id: UUID
    case_id: UUID
    tenant_id: UUID | None
    event_type: MutationEventType
    payload: dict[str, Any]
    case_revision_before: int
    case_revision_after: int
    actor: str
    actor_type: ActorType
    created_at: datetime
```

**Acceptance tests:**

Create `backend/tests/unit/domain/test_mutation_events.py`:

- Test enum values exactly match the SQL CHECK constraint (if any)
- Test MutationEvent is immutable (frozen dataclass)
- Test serialization round-trip: Python → JSON → Python

**Claude Code audit:** Verify this module is in `backend/app/domain/` per supplement v1 §35 (domain layer). Verify no imports from `backend/app/models/`, `backend/app/schemas/`, `backend/app/agent/`. Domain layer MUST be the bottom of the import hierarchy.

---

**Patch 1.5 — Models layer: SQLAlchemy models for mutation_events and outbox.**

**Owner:** Codex CLI.

**Scope:** SQLAlchemy model definitions only.

**Files:**

`backend/app/models/mutation_event_model.py` — SQLAlchemy model matching the SQL migration 02.

`backend/app/models/outbox_model.py` — SQLAlchemy model matching SQL migration 03.

Also update `backend/app/models/case_model.py` to reflect new columns from Patch 1.1.

**Acceptance tests:**
- Models load without error
- A SQLAlchemy session can insert and query each model type
- Models respect the four-layer separation (supplement v1 §35): `backend/app/models/` imports only from `backend/app/domain/`, not vice versa

**Claude Code audit:** Verify import graph. Run `grep -r "from app.models" backend/app/domain/` — MUST return zero results. Run `grep -r "from app.agent" backend/app/models/` — MUST return zero results.

---

**Patch 1.6 — case_service module with apply_mutation().**

**Owner:** Codex CLI with detailed spec (this patch needs careful attention).

**Scope:** The single-write-path service. Most important patch of Sprint 1.

**Files:**

Create `backend/app/services/case_service.py`:

```python
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.domain.mutation_events import MutationEvent, MutationEventType, ActorType
from app.models.case_model import CaseModel
from app.models.mutation_event_model import MutationEventModel
from app.models.outbox_model import OutboxModel
from app.models.case_state_snapshot_model import CaseStateSnapshotModel

class CaseMutationError(Exception):
    """Base exception for case mutations."""

class OptimisticLockError(CaseMutationError):
    """The expected case_revision did not match; concurrent update detected."""

class InvalidMutationError(CaseMutationError):
    """The mutation payload failed validation."""

class CaseService:
    def __init__(self, session: Session):
        self._session = session

    def apply_mutation(
        self,
        case_id: UUID,
        event_type: MutationEventType,
        payload: dict[str, Any],
        expected_revision: int,
        actor: str,
        actor_type: ActorType,
        tenant_id: UUID | None = None,
    ) -> MutationEvent:
        """Apply a mutation to a case. Single write path.

        Transactional: mutation_event, case update, snapshot, outbox entry
        are all committed atomically.

        Raises:
            OptimisticLockError: expected_revision does not match current
            InvalidMutationError: payload fails validation
        """
        # 1. Load case with SELECT FOR UPDATE
        case = self._session.query(CaseModel).filter(
            CaseModel.case_id == case_id
        ).with_for_update().first()

        if case is None:
            raise InvalidMutationError(f"Case {case_id} does not exist")

        # 2. Optimistic lock check
        if case.case_revision != expected_revision:
            raise OptimisticLockError(
                f"Expected revision {expected_revision}, found {case.case_revision}"
            )

        # 3. Validate payload for event_type
        self._validate_payload(event_type, payload)

        # 4. Create MutationEvent record
        new_revision = case.case_revision + 1
        mutation = MutationEventModel(
            case_id=case_id,
            tenant_id=tenant_id,
            event_type=event_type.value,
            payload=payload,
            case_revision_before=expected_revision,
            case_revision_after=new_revision,
            actor=actor,
            actor_type=actor_type.value,
        )
        self._session.add(mutation)
        self._session.flush()  # get mutation_id

        # 5. Apply payload to case (deterministic application)
        self._apply_payload_to_case(case, event_type, payload)
        case.case_revision = new_revision

        # 6. Create case_state_snapshot (transitional per Decision #1)
        snapshot = CaseStateSnapshotModel(
            case_id=case_id,
            case_revision=new_revision,
            snapshot=self._serialize_case_state(case),
        )
        self._session.add(snapshot)

        # 7. Create outbox entry for downstream effects
        outbox = OutboxModel(
            case_id=case_id,
            mutation_id=mutation.mutation_id,
            tenant_id=tenant_id,
            task_type=self._outbox_task_for_event(event_type),
            payload={"event_type": event_type.value, "new_revision": new_revision},
            status="pending",
        )
        self._session.add(outbox)

        self._session.commit()

        return self._to_domain_event(mutation)

    def _validate_payload(self, event_type: MutationEventType, payload: dict) -> None:
        # Event-type-specific validation. Each event_type has required keys.
        # Raises InvalidMutationError on failure.
        ...

    def _apply_payload_to_case(
        self, case: CaseModel, event_type: MutationEventType, payload: dict
    ) -> None:
        # Event-type-specific application to case columns / payload JSONB.
        # Deterministic — no LLM, no external calls.
        ...

    def _serialize_case_state(self, case: CaseModel) -> dict[str, Any]:
        # Produce JSONB-serializable snapshot of case state.
        ...

    def _outbox_task_for_event(self, event_type: MutationEventType) -> str:
        # Map event types to outbox task types.
        ...

    def _to_domain_event(self, mutation: MutationEventModel) -> MutationEvent:
        # Convert ORM record to immutable domain type.
        ...
```

**Binding constraints on this module:**

- **NO LangGraph imports.** Per supplement v1 §33.8. Verify with `grep -r "langgraph" backend/app/services/case_service.py` — MUST return zero.
- **NO direct Postgres writes outside this service.** Every mutation goes through `apply_mutation()`.
- **Atomic transaction.** All steps commit together or rollback together.
- **Optimistic lock is mandatory.** No write path bypasses it.

**Acceptance tests:**

Create `backend/tests/unit/services/test_case_service.py` with:

- Test: apply_mutation with correct expected_revision succeeds
- Test: apply_mutation with wrong expected_revision raises OptimisticLockError
- Test: apply_mutation with non-existent case raises InvalidMutationError
- Test: apply_mutation with invalid payload for event_type raises InvalidMutationError
- Test: after successful apply_mutation, case.case_revision is incremented by 1
- Test: after successful apply_mutation, exactly one mutation_event is created
- Test: after successful apply_mutation, exactly one case_state_snapshot is created
- Test: after successful apply_mutation, exactly one outbox entry is created with status='pending'
- Test: concurrent apply_mutation calls (simulated) — one succeeds, one raises OptimisticLockError
- Test: apply_mutation is NOT invokable without a tenant_id if tenant isolation is enforced (Sprint 2 enforcement, test with skip marker for now)

All tests must be green before merge.

**Claude Code audit (critical):**

1. Verify no LangGraph imports in case_service.py
2. Verify case_service.py is the ONLY file in the codebase that writes to mutation_events, outbox, or case_state_snapshots tables
3. Verify transaction semantics: wrap test that intentionally raises mid-transaction and verify NO partial data is written
4. Verify no business logic in LangGraph nodes that could bypass apply_mutation() — grep for `session.add`, `session.commit` across `backend/app/agent/`
5. Report any remaining direct Postgres writes from nodes

---

**Patch 1.7 — Migration 04: set tenant_id NOT NULL on cases.**

**Owner:** Codex CLI.

**Prerequisite:** Patch 1.6 fully merged and all tests green.

**Actions:**

Since cases table is empty (per Patch 1.1 migration), setting tenant_id NOT NULL is safe:

```sql
ALTER TABLE cases ALTER COLUMN tenant_id SET NOT NULL;
```

Also add tenant_id NOT NULL on mutation_events and outbox:
```sql
ALTER TABLE mutation_events ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE outbox ALTER COLUMN tenant_id SET NOT NULL;
```

**Acceptance tests:**
- Migration applies
- Attempting to INSERT a case without tenant_id fails (expected)
- apply_mutation() called without tenant_id raises InvalidMutationError (update service accordingly)

**Claude Code audit:** Verify tenant_id is required at API layer (FastAPI dependency). Verify no code path exists to create a case without a tenant_id.

---

**Patch 1.8 — Outbox worker scaffold.**

**Owner:** Codex CLI.

**Scope:** Minimal worker process that polls outbox. Does NOT yet implement any task types — that happens per-task in later sprints.

**Files:**

Create `backend/app/services/outbox_worker.py`:

```python
from sqlalchemy.orm import Session
from app.models.outbox_model import OutboxModel

class OutboxWorker:
    def __init__(self, session: Session):
        self._session = session
        self._handlers: dict[str, callable] = {}

    def register_handler(self, task_type: str, handler: callable) -> None:
        """Register a handler for a task type."""
        self._handlers[task_type] = handler

    def process_batch(self, max_items: int = 10) -> int:
        """Process up to max_items pending outbox entries. Returns count processed."""
        # 1. SELECT FOR UPDATE SKIP LOCKED pending entries
        # 2. Mark in_progress
        # 3. Call handler
        # 4. On success: mark completed
        # 5. On failure: increment attempts; if attempts >= max_attempts, mark failed_permanent; else mark pending again with backoff
        # See supplement v1 §34.5
        ...
```

**Acceptance tests:**
- Worker can be instantiated
- register_handler adds to registry
- process_batch() with no pending items returns 0
- process_batch() with a pending item and registered handler calls handler and marks completed
- process_batch() with handler that raises marks item as failed_retryable (if attempts < max) or failed_permanent (if attempts >= max)
- SELECT FOR UPDATE SKIP LOCKED test: two workers running in parallel don't pick the same item

**Claude Code audit:** Verify worker has no LangGraph imports. Verify idempotency in case of handler partial success.

---

### Sprint 1 Definition of Done

- Patches 1.1 through 1.8 all merged
- All tests in `backend/tests/unit/services/test_case_service.py` green
- All tests in `backend/tests/unit/domain/test_mutation_events.py` green
- Database migration chain applies cleanly from scratch and reverses cleanly
- No LangGraph imports anywhere in `backend/app/services/`
- No direct Postgres writes from any LangGraph node
- Audit gate 1→2 passed

### Sprint 1 Audit Gate (Gate 1→2)

See `Part C, Gate 1→2`.

---

## Sprint 2 — Classification Layer

**Goal:** Implement Decision #5 — Pre-Gate Classifier with 5 values, remove ResultForm enum, extract output_classifier service from the oversized output_contract_node. Replace RoutingPath with PreGateClassification throughout.

**Duration estimate:** 1-2 weeks at 30h/week.

### Sprint 2 rationale

Classification is the entry point. Every later architectural layer (Fast Responder, Knowledge Service, full graph) branches based on Pre-Gate Classification. Getting this right before building the services that depend on it prevents ripple changes.

### Sprint 2 Patches

---

**Patch 2.1 — Pre-Gate Classification enum (domain layer).**

**Owner:** Codex CLI.

**Files:**

Create `backend/app/domain/classification.py`:

```python
from enum import Enum

class PreGateClassification(str, Enum):
    GREETING = "greeting"
    META_QUESTION = "meta_question"
    KNOWLEDGE_QUERY = "knowledge_query"
    BLOCKED = "blocked"
    DOMAIN_INQUIRY = "domain_inquiry"

class GateMode(str, Enum):
    CONVERSATION = "conversation"
    EXPLORATION = "exploration"
    GOVERNED = "governed"

class OutputClass(str, Enum):
    CONVERSATIONAL_ANSWER = "conversational_answer"
    STRUCTURED_CLARIFICATION = "structured_clarification"
    GOVERNED_STATE_UPDATE = "governed_state_update"
    TECHNICAL_PRESELECTION = "technical_preselection"
    RCA_HYPOTHESIS = "rca_hypothesis"  # deferred to Phase 2 per Decision #4
    CANDIDATE_SHORTLIST = "candidate_shortlist"
    INQUIRY_READY = "inquiry_ready"
```

**Acceptance tests:**
- Enum values exactly match authority documents
- All five PreGateClassification values exist
- All three GateMode values exist
- All seven OutputClass values exist
- No enum value called "FAST_PATH", "STRUCTURED_PATH", "DIRECT_ANSWER", etc. (legacy naming)

**Claude Code audit:** This is a trivial file but important as reference. Verify no imports. Verify it's in the domain layer.

---

**Patch 2.2 — pre_gate_classifier service.**

**Owner:** Codex CLI with spec from Claude Code.

**Files:**

Create `backend/app/services/pre_gate_classifier.py`:

```python
from dataclasses import dataclass
from app.domain.classification import PreGateClassification

@dataclass
class ClassificationResult:
    classification: PreGateClassification
    confidence: float  # 0.0 - 1.0
    reasoning: str  # short explanation for observability
    escalate_to_graph: bool  # if true, use DOMAIN_INQUIRY path as fail-safe

class PreGateClassifier:
    def classify(
        self,
        user_input: str,
        session_context: dict | None = None,
    ) -> ClassificationResult:
        """Classify user input into one of five pre-gate classes."""
        # Deterministic-first classification:
        # 1. Keyword/pattern match for GREETING (Hallo, Moin, Hi, Guten Tag, Danke, ...)
        # 2. Keyword/pattern match for META_QUESTION (Was kann SeaLAI, Wie funktioniert, ...)
        # 3. Content-safety check for BLOCKED
        # 4. Keyword/pattern match for KNOWLEDGE_QUERY (Was ist, Erkläre, Unterschied zwischen, Wie funktioniert ein ..., ...)
        # 5. Default: DOMAIN_INQUIRY
        # If uncertain between KNOWLEDGE_QUERY and DOMAIN_INQUIRY, LLM-assist may be called
        # If LLM-assist returns uncertain, default is DOMAIN_INQUIRY (fail-safe toward graph)
        ...
```

**Binding constraints:**

- **Deterministic-first.** Pattern matching handles the common cases. LLM is called only for ambiguous edge cases, never as primary classifier.
- **No LangGraph import.**
- **Fail-safe is DOMAIN_INQUIRY.** If in doubt, send to graph. Never fail into Fast Responder.

**Acceptance tests:**

Create `backend/tests/unit/services/test_pre_gate_classifier.py`:

- 20+ example inputs across all 5 classifications
- Test: "Hallo" → GREETING, confidence > 0.9
- Test: "Was kann SeaLAI?" → META_QUESTION, confidence > 0.8
- Test: "Was ist der Unterschied zwischen FKM und PTFE?" → KNOWLEDGE_QUERY, confidence > 0.7
- Test: "Ich brauche eine Dichtung für meine Pumpe" → DOMAIN_INQUIRY, confidence > 0.8
- Test: harassment input → BLOCKED
- Test: ambiguous input → escalate_to_graph = true
- Test: classifier is deterministic (same input, same output)

**Claude Code audit:**
- Verify no business logic embedded (classifier only classifies, doesn't do anything downstream)
- Verify the fail-safe: trace an "uncertain" path and confirm it leads to DOMAIN_INQUIRY
- Verify German and English are both handled

---

**Patch 2.3 — output_classifier service extraction.**

**Owner:** Codex CLI with spec from Claude Code. **This patch is large and risky.**

**Scope:** Move the deterministic output-class derivation logic from `output_contract_node.py` (1335 lines) into a dedicated service. Node becomes a thin orchestrator.

**Files:**

Create `backend/app/services/output_classifier.py`:

```python
from dataclasses import dataclass
from app.domain.classification import OutputClass, GateMode, PreGateClassification

@dataclass
class OutputClassificationInput:
    pre_gate: PreGateClassification
    gate_mode: GateMode | None  # None if pre_gate is not DOMAIN_INQUIRY
    engineering_path: str | None
    request_type: str | None
    readiness_state: str  # see base SSoT §11
    matching_available: bool
    inquiry_admissible: bool

@dataclass
class OutputClassificationResult:
    output_class: OutputClass
    reasoning: str  # deterministic trace

class OutputClassifier:
    def classify(self, input: OutputClassificationInput) -> OutputClassificationResult:
        """Deterministic mapping from state to output class per base SSoT §10 and supplement v2 §39.7."""
        # Deterministic decision tree.
        # No LLM.
        # No I/O.
        # Pure function of inputs.
        ...
```

The existing logic in `output_contract_node.py` is moved here, refactored, decomposed into testable sub-rules. The node shrinks from 1335 lines to an orchestrator of 100-200 lines.

**Acceptance tests:**

Create `backend/tests/unit/services/test_output_classifier.py` with coverage for:

- Every (pre_gate × gate_mode × readiness) valid combination → expected output_class
- RCA input → STRUCTURED_CLARIFICATION with degrade message (per Decision #4)
- GREETING / META_QUESTION / BLOCKED → CONVERSATIONAL_ANSWER
- KNOWLEDGE_QUERY → CONVERSATIONAL_ANSWER (Fast Responder and Knowledge Service converge on this class)
- Full DOMAIN_INQUIRY flows through EXPLORATION to GOVERNED correctly

At least 50 test cases.

**Claude Code audit (critical):**
- Diff before/after of `output_contract_node.py` — confirm node shrinks substantially
- Verify new service is pure function (no I/O)
- Verify no classifications use deprecated ResultForm
- Verify removed lines correspond to extracted logic, not dropped logic

---

**Patch 2.4 — Remove ResultForm enum.**

**Owner:** Codex CLI.

**Scope:** Remove `ResultForm` from `agent/runtime/policy.py` and every consumer. Replace consumers with `OutputClass`.

**Actions:**

1. `grep -r "ResultForm" backend/app/` — identify all consumers
2. For each consumer, replace with equivalent OutputClass reference
3. Remove the enum definition
4. Run test suite, fix any test-side references

**Acceptance tests:**
- `grep -r "ResultForm" backend/app/` returns zero matches
- All tests green
- No imports broken

**Claude Code audit:** Confirm clean removal. Verify no downstream comments still reference ResultForm semantics.

---

**Patch 2.5 — Replace RoutingPath with PreGateClassification.**

**Owner:** Codex CLI.

**Scope:** Transitional. `RoutingPath` enum becomes deprecated. Consumers migrate to `PreGateClassification` where semantically equivalent.

Mapping:
- `RoutingPath.GREETING_PATH` → `PreGateClassification.GREETING`
- `RoutingPath.META_PATH` → `PreGateClassification.META_QUESTION`
- `RoutingPath.BLOCKED_PATH` → `PreGateClassification.BLOCKED`
- `RoutingPath.FAST_PATH` → replaced by `GateMode.CONVERSATION` (within DOMAIN_INQUIRY context)
- `RoutingPath.STRUCTURED_PATH` → replaced by `GateMode.EXPLORATION` or `GateMode.GOVERNED` (within DOMAIN_INQUIRY context)

**Acceptance tests:**
- `grep -r "RoutingPath" backend/app/` returns zero matches (enum definition, imports, usage)
- All tests green
- Case records now use `pre_gate_classification` column (set in Sprint 1 Patch 1.1)

**Claude Code audit:**
- Verify mapping is semantically correct
- Verify no hidden logic depends on the old enum ordering
- Verify the Case schema reflects the new column

---

### Sprint 2 Definition of Done

- Patches 2.1 through 2.5 all merged
- All unit tests green
- No `ResultForm` or `RoutingPath` references remain in production code
- `output_contract_node.py` is dramatically smaller (target: under 400 lines)
- Audit gate 2→3 passed

### Sprint 2 Audit Gate (Gate 2→3)

See `Part C, Gate 2→3`.

---

## Sprint 3 — Service Layer Core

**Goal:** Build the foundational services that Sprint 4's product features depend on: terminology_service, manufacturer_capability tables + service, norm_modules, advisory_engine, inquiry_extract_service, anonymization_service.

**Duration estimate:** 2-3 weeks at 30h/week.

### Sprint 3 Patches

---

**Patch 3.1 — Migration 05: terminology registry tables.**

Per supplement v2 §40. Tables: `generic_concepts`, `product_terms`, `term_mappings`, `term_audit_log`.

**Acceptance:** migration applies/reverses, tables have expected columns and constraints.

---

**Patch 3.2 — Migration 06: manufacturer capability tables.**

Per supplement v2 §41. Tables: `manufacturer_profiles`, `manufacturer_capability_claims`.

Capability payload includes supplement v3 §47 small-quantity extension.

---

**Patch 3.3 — Migration 07: inquiry_extracts + golden_cases + rca_early_access tables.**

Per Decision #6.

---

**Patch 3.4 — terminology_service module.**

Implements supplement v2 §40 operations: lookup, normalization, provenance tracking.

**Acceptance:** 30+ test cases including seed mappings, unknown terms, ambiguous terms.

---

**Patch 3.5 — capability_service module.**

CRUD for manufacturer_capability_claims. Includes small-quantity-aware filtering.

**Acceptance:** tests for all CRUD operations plus hard-filter tests for `accepts_single_pieces`.

---

**Patch 3.6 — norm_modules framework + DIN 3760 / ISO 6194 module.**

Per Decision #7 and supplement v3 §47.6 cross-reference.

Abstract interface: `NormModule` base class with `applies_to`, `required_fields`, `check`, `escalation_policy`.

First concrete module: `din_3760_iso_6194.py`.

**Acceptance:** module tests + framework extensibility test (fake-module plug-in).

---

**Patch 3.7 — Norm modules: EU food contact + FDA food contact.**

Two more modules on the framework. Shared certification data structures.

---

**Patch 3.8 — ATEX capability flag (not full module).**

Per Decision #7. Capability-claim field only. Matching filter.

---

**Patch 3.9 — advisory_engine service.**

Per supplement v3 §48.

Deterministic rules in Python. Eight initial advisory categories. Integration point: called after every mutation_event or calculation.

**Acceptance:** 20+ test cases covering each advisory category with trigger/no-trigger scenarios.

---

**Patch 3.10 — inquiry_extract_service.**

Per Decision #6 + supplement v2 §37.

Pure function: Case → InquiryExtract. Enforces manufacturer-view boundaries. No PII.

**Acceptance:** tests for PII filtering, for field-level inclusion, for anonymization of article numbers.

---

**Patch 3.11 — anonymization_service.**

Per Decision #6.

PII detection and removal: names, company identifiers, email addresses, project codes, photo EXIF, article number customer parts.

**Acceptance:** 30+ test cases covering each PII category.

---

### Sprint 3 Definition of Done

- All eleven patches merged
- All tests green
- Database has 10+ new tables all migrated and indexed
- Five major new services functional
- Three norm modules + ATEX capability flag ready to be consumed by matching (Sprint 4)
- Audit gate 3→4 passed

### Sprint 3 Audit Gate (Gate 3→4)

See `Part C, Gate 3→4`.

---

## Sprint 4 — Supplement v3 Operationals

**Goal:** Build the Product North Star operationalized services: Fast Responder, Knowledge Service, Application Pattern Service, Medium Intelligence Service, Formula Library with cascading calculations, Problem-First Matching.

**Duration estimate:** 3-4 weeks at 30h/week. **Largest sprint.**

### Sprint 4 Patches

---

**Patch 4.1 — fast_responder_service.**

Per supplement v3 §44.

Handles GREETING / META_QUESTION / BLOCKED. Bounded LLM prompts per classification. No case creation. No persistence.

Wiring: routed to BEFORE graph invocation based on PreGateClassification result.

**Acceptance:** Latency test (p95 < 1.5s), classification boundary test (never handles KNOWLEDGE_QUERY or DOMAIN_INQUIRY), no-persistence test (no Case created, no Postgres writes).

---

**Patch 4.2 — Migration 08: application_patterns table.**

Per supplement v3 §46.

Table with all fields from §46.2 entity model.

---

**Patch 4.3 — application_pattern_service + 14 seed patterns.**

Per supplement v3 §46.

Service provides: pattern matching (triggering contexts → candidate patterns), field auto-population, educational notes.

14 patterns seeded with content from supplement v3 §46.3.

**Acceptance:** 14 explicit pattern-match tests with representative user inputs, plus pattern-library extensibility test.

---

**Patch 4.4 — Migration 09: medium_registry table.**

Per supplement v3 §50.

---

**Patch 4.5 — medium_intelligence_service + 50 seed entries.**

Per supplement v3 §50.

Service implements three-tier provenance, registry match, LLM-synthesis fallback with explicit uncertainty markers, caching.

50 seed entries covering: hydraulic oils, common acids/bases, food media (milk, chocolate, oils), aqueous media, solvents, pharmaceutical media, refrigerants, cleaning chemicals.

**Acceptance:** registry-match test, LLM-synthesis test (with mocked LLM), provenance tier test, consistency check test (e.g., name contains "acid" but LLM says "neutral" → flag).

---

**Patch 4.6 — formula_library module.**

Per supplement v3 §49.

CalculationDefinition framework. 7 PTFE-RWDR formulas:

- circumferential_speed
- contact_pressure
- pv_loading
- thermal_load_indicator
- extrusion_gap_check
- creep_gap_estimate_simplified
- compound_temperature_headroom

Each formula: unit test with known input/output pairs from engineering literature or depth guide.

---

**Patch 4.7 — cascading_calculation_engine.**

Per supplement v3 §49.6.

Execute to fixpoint. Synchronous. Dependency graph resolution. Guard against cycles.

**Acceptance:** cascade convergence test, cycle-detection test, stale-invalidation test, performance test (full cascade < 50ms).

---

**Patch 4.8 — knowledge_service + MVP knowledge base.**

Per Decision #8.

50-100 curated knowledge entries in PTFE-RWDR domain: material comparisons, seal type functions, construction fundamentals, norm explanations, application patterns.

Qdrant integration for retrieval. LLM for synthesis with mandatory source citation.

**Acceptance:** every factual claim test has a citation, every response has a confidence level, no-match test returns honest "I don't have this information".

---

**Patch 4.9 — Problem-First Matching service.**

Per supplement v3 §45.

Pipeline: problem → required capabilities → candidates → scored matches.

Integrated with small-quantity capability claims, norm modules, application patterns.

**Acceptance:** direction test (verify problem → capability, not reverse), zero-match graceful-degrade test, sponsored-separation test (sponsored never gets rank bonus).

---

**Patch 4.10 — Knowledge-to-Case Bridge.**

Per supplement v3 §53.

Transition signal detection. Context accumulation. Registration prompt flow.

**Acceptance:** transition detection test with 10+ user input sequences, context-preservation test (case has knowledge-session context in provenance).

---

**Patch 4.11 — Multimodal Input Processing contracts.**

Per supplement v3 §52.

Services: photo_analysis_service, article_number_decoder_service, datasheet_extraction_service.

**MVP scope is narrower than full spec:** photo analysis and article number decoder are production-ready; datasheet and sketch processing are scaffolded with limited functionality and explicit user-clarification fallback.

**Acceptance:** per-service test suite with representative inputs.

---

### Sprint 4 Definition of Done

- All eleven patches merged
- All tests green
- Full Supplement v3 operationalized
- User-facing end-to-end flow possible: greeting → knowledge query → bridge → case creation → pattern → cascading calculations → medium intelligence → advisories → problem-first matching → inquiry dispatch
- Audit gate 4→5 passed

### Sprint 4 Audit Gate (Gate 4→5)

See `Part C, Gate 4→5`.

---

## Sprint 5 — Stack Consolidation & Cleanup

**Goal:** Execute Decision #2. Remove services/langgraph/ and services/fast_brain/. Migrate YAML rules. Deprecate and remove legacy endpoints. Remove feature flags.

**Duration estimate:** 1-2 weeks at 30h/week.

### Sprint 5 Patches

---

**Patch 5.1 — YAML rule review and migration table.**

**Owner:** Claude Code (design-intensive, not mechanical).

Output: `audits/yaml_rule_migration_2026-XX-XX.md`.

For each rule in `services/langgraph/rules/common.yaml` and `rules/rwdr.yaml`:
- Classification: migrate-to-risk-engine / migrate-to-checks-registry / obsolete-delete
- If migrate: target service + specific integration point
- If delete: rationale

Founder reviews and approves the migration table before any deletion happens.

---

**Patch 5.2 — Migrate YAML rules to target services.**

**Owner:** Codex CLI, per Patch 5.1 table.

Each rule is implemented in its target service with unit tests.

**Acceptance:** for each migrated rule, a unit test in the target service validates equivalent behavior.

---

**Patch 5.3 — Remove services/langgraph/.**

**Owner:** Codex CLI.

After Patch 5.2 confirms all rules migrated:

```bash
git rm -r backend/app/services/langgraph/
```

Plus: remove all imports of `services.langgraph.*` from codebase.

**Acceptance:** `grep -r "services.langgraph" backend/app/` returns zero, full test suite green.

---

**Patch 5.4 — Remove services/fast_brain/.**

**Owner:** Codex CLI.

After fast_responder_service is confirmed operational (Sprint 4 Patch 4.1):

```bash
git rm -r backend/app/services/fast_brain/
```

Plus: remove imports and endpoint `fast_brain_runtime.py`.

**Acceptance:** no references remain, tests green, routing verified to go through fast_responder_service.

---

**Patch 5.5 — Deprecate and remove legacy endpoints.**

**Owner:** Codex CLI.

Endpoints to remove:
- `backend/app/api/v1/endpoints/langgraph_v2.py`
- `backend/app/api/v1/endpoints/fast_brain_runtime.py`

Plus feature flag cleanup in `core/config.py`:
- `ENABLE_LEGACY_V2_ENDPOINT` removed
- `SEALAI_ENABLE_BINARY_GATE` removed
- `SEALAI_ENABLE_CONVERSATION_RUNTIME` removed

**Acceptance:** frontend smoke-test verifies new SSoT endpoints work for basic flows.

---

**Patch 5.6 — Remove _legacy_v2 directories and interaction_policy.py shim.**

**Owner:** Codex CLI.

Final cleanup of historical code.

---

**Patch 5.7 — Final audit and documentation update.**

**Owner:** Claude Code.

Run comprehensive audit. Produce `audits/phase_1a_completion_2026-XX-XX.md` documenting:
- All founder decisions implemented
- All supplement v3 chapters operational
- Authority-invariant compliance verified
- Outstanding issues (if any)

**Acceptance:** Founder reviews and formally approves the completion audit.

---

### Sprint 5 Definition of Done

- All seven patches merged
- All tests green
- Backend is free of legacy code per Decision #2
- Phase 1a completion audit passes
- Founder approves phase completion

---

# PART C — Audit Gates (Claude Code Execution Guide)

## Gate 0→1 — Post-Safety Audit

**Trigger:** All Sprint 0 patches merged. Founder requests gate review.

**Duration:** 1-2 hours of Claude Code time.

**Checks:**

1. **Key hygiene.** Full git history scanned: `git log -p --all | grep -iE "sk-[a-zA-Z0-9]{32,}|api[_-]key[=:]\"[a-zA-Z0-9]+\""`. MUST return zero or flag findings.
2. **COI log present.** `konzept/coi_firewall_log.md` exists, committed, content matches Decision #3 implementation spec.
3. **Baseline document present.** `audits/phase_1a_baseline_YYYY-MM-DD.md` exists with all required sections.
4. **Baseline measurements match Phase 1a Audit findings.** Spot-check 5 findings.

**Pass criteria:** All four checks pass. No critical findings.

**Output:** `audits/gate_0_to_1_YYYY-MM-DD.md` with pass/fail verdict.

---

## Gate 1→2 — Post-Persistence Audit (CRITICAL GATE)

**Trigger:** All Sprint 1 patches merged.

**Duration:** 2-4 hours of Claude Code time.

**Checks:**

1. **Import hygiene (hard constraint).** `grep -r "from langgraph" backend/app/services/` MUST return zero. Any match is a BLOCKER.
2. **Single-write-path (hard constraint).** `grep -rE "session\.(add|commit)|INSERT INTO mutation_events|INSERT INTO outbox" backend/app/` — verify ONLY `case_service.py` writes to these tables.
3. **No direct postgres writes from nodes.** Inspect every file under `backend/app/agent/graph/nodes/` — none may call `session.add()` or similar. Matches are BLOCKERS.
4. **Optimistic lock correctness.** Read `apply_mutation()`. Verify SELECT FOR UPDATE precedes revision check. Verify revision-bump happens only inside the transaction.
5. **Transaction atomicity.** Read the test that simulates a mid-transaction failure. Verify no partial data is committed.
6. **Four-layer separation (supplement v1 §35).** `grep -r "from app.models" backend/app/domain/` returns zero. `grep -r "from app.agent" backend/app/models/` returns zero. `grep -r "from app.agent" backend/app/services/case_service.py` returns zero.
7. **Tenant_id requirements.** After Patch 1.7, verify no code path can create a case with tenant_id = NULL.
8. **Schema migration integrity.** Run `alembic downgrade base && alembic upgrade head` in a test database. Verify schema end-state matches expected.
9. **Test coverage.** `backend/tests/unit/services/test_case_service.py` has at least 10 test cases covering all documented scenarios.

**Pass criteria:** All nine checks pass. Any BLOCKER fails the gate.

**Output:** `audits/gate_1_to_2_YYYY-MM-DD.md` with detailed findings per check.

**Remediation:** If gate fails, Claude Code produces specific remediation patches. Sprint 2 does NOT start until remediation is merged and gate re-passes.

---

## Gate 2→3 — Post-Classification Audit

**Trigger:** All Sprint 2 patches merged.

**Checks:**

1. **Enum removal.** `grep -r "ResultForm\b" backend/app/` returns zero.
2. **RoutingPath removal.** `grep -r "RoutingPath\b" backend/app/` returns zero.
3. **PreGateClassification usage.** Every classification decision point uses `PreGateClassification`.
4. **Output_contract_node shrinkage.** Line count of `output_contract_node.py` dropped substantially (target: under 400 lines from 1335).
5. **Classifier fail-safe.** Read `pre_gate_classifier.py`. Verify ambiguous classifications default to DOMAIN_INQUIRY.
6. **Test coverage.** 20+ tests on PreGateClassifier, 50+ tests on OutputClassifier.

**Output:** `audits/gate_2_to_3_YYYY-MM-DD.md`.

---

## Gate 3→4 — Post-Service-Layer-Core Audit

**Checks:**

1. **Terminology service invariants.** Provenance tracked on every lookup.
2. **Capability service integrity.** Small-quantity filter behaves per supplement v3 §47.5 (HARD at ≤10 pieces).
3. **Norm module framework extensibility.** Plug-in test passes.
4. **Advisory engine determinism.** Same inputs produce same advisories.
5. **Inquiry extract privacy.** No PII fields in extract for any test case.
6. **Anonymization completeness.** All PII categories removed.
7. **Import graph.** All new services have no LangGraph imports.

**Output:** `audits/gate_3_to_4_YYYY-MM-DD.md`.

---

## Gate 4→5 — Post-Operationals Audit (CRITICAL GATE)

**Checks:**

1. **Fast Responder boundary.** `grep` for calls to fast_responder_service confirms it is never called for KNOWLEDGE_QUERY or DOMAIN_INQUIRY.
2. **No case creation from Fast Responder.** Trace a GREETING test through the full stack. Verify zero Case inserts.
3. **Cascading calculation convergence.** Run the full PTFE-RWDR cascade on a complete test case. Verify fixpoint reached in ≤20 iterations.
4. **Medium Intelligence three-tier provenance.** Every output field has a provenance tier. Visual-distinction test in frontend passes.
5. **Knowledge service attribution.** Every factual claim in a test knowledge response has a source reference.
6. **Problem-First Matching direction.** Unit test verifies the algorithm starts from problem, not from manufacturer.
7. **Application Pattern matching.** 14 seed patterns each have a positive-match and negative-match test.
8. **End-to-end smoke test.** A test user completes: greeting → knowledge query about FKM vs PTFE → bridge to case → pattern selection (e.g., chocolate processing) → parameter entry → cascade triggers → medium intelligence card renders → advisories emitted → matching produces candidates → inquiry extract generated. Test passes.

**Output:** `audits/gate_4_to_5_YYYY-MM-DD.md`.

---

## Gate 5 — Phase 1a Completion Audit

**Trigger:** Sprint 5 complete.

**Checks (comprehensive):**

All authority invariants from CLAUDE.md verified:
- Product North Star invariants (§4.3) — each of the 8 product invariants traceable in code
- Moat invariants (§4.4) — structural neutrality, technical translation, request qualification all enforced
- Five non-negotiables (§4.5) — each verifiable as absent
- Supplement v3 §44-§53 — each chapter's spec traceable to implementation
- All 8 founder decisions — each implementation evidence cited
- Selective Rewrite completion — all greenfield services exist, all strangler preservations verified, all removals confirmed

**Output:** `audits/phase_1a_completion_YYYY-MM-DD.md`. Comprehensive report.

**Founder approval:** Explicit sign-off required. Without it, Phase 1a is NOT closed.

---

# PART D — Founder Guidance

## D.1 Your role per sprint

You are not required to write code. You are required to:

1. **Approve gate transitions.** Between every sprint, Claude Code produces a gate audit. You read the summary (not the full 400-line doc). You either approve or ask for remediation.

2. **Resolve ambiguities when they arise.** Codex CLI and Claude Code will occasionally surface questions like "the authority doesn't specify X — what's the intent?" Your job is to answer, referencing North Star or explaining your intent.

3. **Decide on scope adjustments.** If a sprint takes significantly longer than estimated, you may need to decide: push through, descope, or add a sprint. You make this call.

4. **Prevent scope creep.** If Codex CLI or I suggest "we should also fix X while we're here," your default is **no unless it's a pure blocker**. Phase 1a finishes as planned.

## D.2 Red flags to watch for

These are signs that something is wrong and you should pause:

- Tests start failing and "will be fixed later." **Halt.** No merge.
- A patch grows to touch 20+ files. **Halt.** Ask for decomposition.
- A sprint extends more than 50% beyond estimate. **Halt.** Review and possibly descope.
- Claude Code audit finds repeat issues across gates. **Halt.** Something is systemically wrong.
- You feel rushed or confused. **Halt.** Quality beats velocity in Phase 1a.

## D.3 When to ask me for help

Within a sprint, Codex CLI should handle most questions. Call me when:

- An authority document contradicts another, and Codex CLI can't resolve
- A patch requires architectural judgment (e.g., "the spec says X but the existing code makes X hard — what do we do?")
- A gate audit fails and you want help interpreting findings
- You want to adjust sprint scope mid-flight

## D.4 Working habits for 30h/week

With 30 hours per week, realistic work cadence:

- 25 hours: actual coding / execution / review
- 3 hours: Codex CLI prompt preparation and patch review
- 2 hours: gate audits and founder-decision review

Daily pattern that works: 4-5 hours in focused blocks, with clear patch-level goals. Break between patches. Test green before leaving work for the day — never stop mid-merge.

---

# PART E — YAML Rule Migration Methodology (detailed)

This is the detailed methodology for Sprint 5 Patch 5.1.

## E.1 Review procedure

For each YAML file under `backend/app/services/langgraph/rules/`:

1. Read every rule (not just headers).
2. Classify using the decision tree:
   - Does this rule encode sealing engineering logic (compatibility, risk, norms)? → **migrate to risk_engine** or **migrate to checks_registry**
   - Does this rule encode routing logic (which path to take)? → **covered by Pre-Gate Classifier or Three-Mode Gate** (most likely obsolete)
   - Does this rule encode output-class logic? → **covered by output_classifier** (obsolete)
   - Does this rule encode something not covered anywhere? → **flag for founder decision**
3. For each migrate-target, specify:
   - File where the logic will live (e.g., `backend/app/services/risk_engine/compatibility_rules.py`)
   - Integration point (function / class)
   - Test that validates equivalent behavior

## E.2 Migration output format

Table format for `audits/yaml_rule_migration_YYYY-MM-DD.md`:

| Rule ID | File | Description | Classification | Target Location | Test Required |
|---------|------|-------------|----------------|-----------------|---------------|
| ... | ... | ... | ... | ... | ... |

Plus a summary: count of migrated vs. deleted rules, any flagged-for-founder-decision rules.

## E.3 Founder approval

Before deletion, founder reviews the table. Particular attention to "flagged for decision" rows. Only after founder signs off does migration proceed.

---

# PART F — Risk Register

Risks that could derail the plan, with mitigation.

**Risk 1: Authority contradictions surface during implementation.**
Mitigation: Claude Code resolves. If founder decision needed, Sprint pauses briefly for resolution.

**Risk 2: Codex CLI misinterprets a spec and produces non-conformant code.**
Mitigation: Gate audits catch this. Also patch-level review for critical services.

**Risk 3: A service turns out harder to implement than estimated.**
Mitigation: Sprint scope can be descoped. Worst case: push a service to Phase 1b.

**Risk 4: Performance regression after cascading calculations.**
Mitigation: Patch 4.7 has performance acceptance test (<50ms). If exceeded, optimize before merge.

**Risk 5: Database migrations fail in production.**
Mitigation: Every migration tested with downgrade. Baseline snapshot allows rollback.

**Risk 6: YAML rules contain knowledge not surfaced elsewhere.**
Mitigation: Patch 5.1 is Claude Code manual review, not automated. Unknown or critical-seeming rules flagged for founder.

**Risk 7: Frontend breaks due to backend contract changes.**
Mitigation: Contract-test layer between backend and frontend. Breaking changes documented per sprint. Frontend work is a follow-on phase (Phase 1b).

**Risk 8: Founder burnout.**
Mitigation: No fixed deadline. Quality over speed. Halt signals respected.

---

# PART G — Frontend Considerations (out of scope, but noted)

This plan is backend-focused. Frontend adjustments needed to expose the new services (Pre-Gate classifier results, Fast Responder path, Knowledge cards, Medium Intelligence cards, Advisory notes, Cascading calculation results) are **Phase 1b** work.

Frontend will be able to consume new SSoT endpoints once Sprint 5 is complete. Sprint 5 Patch 5.5 verifies basic endpoint availability via smoke test; full frontend integration is follow-on.

---

# PART H — Success Criteria (Phase 1a end-state)

Phase 1a is complete when:

- All six sprints pass their audit gates
- All founder decisions are implemented and verified
- Supplement v3 operationalized end-to-end
- No legacy code (services/langgraph/, services/fast_brain/, _legacy_v2/, ResultForm, etc.)
- No feature flags for deprecated paths
- Full test suite green
- Performance: PTFE-RWDR case intake to match-ready under 30 seconds
- End-to-end smoke test passes (greeting → knowledge → bridge → case → pattern → cascade → medium → advisory → matching → inquiry extract)
- Founder approves Phase 1a completion audit

At that point, SeaLAI is Phase 1a-ready. The next phase is Phase 1b: frontend modernization, external pilot onboarding preparation, first pilot manufacturer integration.

---

**Document end.**

This plan is binding for Phase 1a execution. It translates the Founder Decisions and Supplement v3 into executable sprints with clear ownership, acceptance, and audit gates.

The plan is living. If reality deviates, the plan is updated (versioned), founder approves the update, and execution continues. Silent deviation from this plan is forbidden.

