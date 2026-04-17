# SeaLAI SSoT — Supplement v1.0 (Chapters 33–36)

**Status:** Binding supplement to `sealai_ssot_architecture_plan.md` v1.0.
**Scope:** Fills four architectural gaps in the base SSoT: LangGraph role boundary, consistency and error model, schema layering, and persistence strategy.
**Reader:** Written for consumption by Codex CLI and Claude Code during audit and patch phases. Rules are imperative, testable, and cross-referenced.
**Precedence:** Same precedence tier as the base SSoT. Where this supplement adds detail to a base chapter, both apply. Where this supplement introduces a new constraint, the constraint is binding.

---

## 33 — LangGraph orchestration role

### 33.1 Scope

This chapter defines the exact role of LangGraph within the SeaLAI backend. It amends chapters 4, 8, and 9 of the base SSoT by making the boundary between orchestration and decision-making explicit and enforceable.

The base SSoT is silent on LangGraph. Current code relies heavily on LangGraph for agent orchestration. Without this chapter, the SSoT's `LLM responsibilities` vs `deterministic rule engine` split cannot be reliably implemented in a LangGraph-based architecture.

### 33.2 Definition

LangGraph is the orchestration runtime. Its responsibilities are:

- routing control flow between graph nodes
- maintaining transient graph state during a conversation turn
- invoking LLMs for language tasks
- checkpointing graph state to Redis for resumption after interruption

LangGraph is NOT:

- the rule engine
- the source of truth for case state
- the owner of any business decision defined in base SSoT chapters 7, 10, 11, 21, 22, 24

### 33.3 Permitted actions for LangGraph nodes

A LangGraph node MAY:

- read from graph state (which is a read-only projection of case state plus run context — see 33.6)
- invoke an LLM for language tasks exclusively allowed by base SSoT §8.1 (normalize, extract, propose, prioritize, summarize, render)
- call deterministic services under `backend/app/services/`
- propose a mutation by calling `case_service.apply_mutation(...)` with the expected case revision
- update its own graph state with a refreshed read-only projection after a mutation

### 33.4 Forbidden actions for LangGraph nodes

A LangGraph node MUST NOT:

- write directly to Postgres
- mutate `routing.path`, `readiness.*`, `highest_valid_phase`, `is_confirmed`, risk score values, or any field owned by the rule engine per base SSoT §8.3
- contain business logic beyond trivial data shaping (format conversion, extraction of a single field from a structured response)
- invoke a subgraph that writes case state while bypassing `case_service`
- skip the mutation event mechanism defined in chapter 34

A graph node that violates any rule in 33.4 is a lint error and MUST fail CI.

### 33.5 Service boundary

All deterministic logic lives in `backend/app/services/`, organized by domain concern. Minimum required services:

- `case_service` — case CRUD, mutation application, revision management, projection retrieval
- `phase_gate_service` — phase transition evaluation per base SSoT §10
- `routing_service` — path selection and request-type finalization per base SSoT §7 and §9
- `projection_service` — `EngineeringCockpitView` generation per base SSoT §13
- `formula_library/` — calculations per base SSoT §20
- `risk_engine/` — risk score computation per base SSoT §21
- `compatibility_service` — chemical compatibility per base SSoT §22
- `output_validator` — output class enforcement per base SSoT §24
- `outbox_worker` — async recompute dispatch per chapter 34

Each service:

- is a plain Python module
- has no dependency on FastAPI, LangGraph, or request/response types
- is independently testable without graph fixtures or HTTP fixtures
- exposes a typed interface whose inputs and outputs are domain objects per chapter 35

### 33.6 Graph state contract

Graph state is defined in `backend/app/agent/state/consult_state.py` as a Pydantic `BaseModel` or `TypedDict`. Required fields:

```
case_id: UUID
case_projection: CaseReadProjection   # read-only, refreshed after mutations
run_context: RunContext               # turn metadata, last user message, channel
llm_scratchpad: dict                  # ephemeral, valid only within current turn
```

Graph state MUST NOT contain:

- mutable authoritative field values (those live in Postgres, accessed via projection)
- pending mutation intentions (those are turned into mutation events immediately)
- persistence side effects

### 33.7 Canonical node pattern

Every LangGraph node follows this pattern:

```python
async def node_classify_request_type(state: ConsultState) -> ConsultState:
    # 1. Read from projection
    projection = state.case_projection
    last_message = state.run_context.last_user_message

    # 2. LLM task — language work only, no decisions
    extraction = await llm_extract_request_type_candidates(
        message=last_message,
        context_summary=projection.summary_for_llm(),
    )

    # 3. Delegate decision to service, producing a mutation event
    if extraction.should_propose:
        try:
            await case_service.apply_mutation(
                case_id=state.case_id,
                mutation=ProposeRequestTypeMutation(
                    candidate=extraction.candidate,
                    confidence=extraction.confidence,
                    source="llm_extraction",
                ),
                expected_revision=projection.revision,
            )
        except RevisionConflict:
            # Another turn modified the case; refetch and continue
            pass

    # 4. Refresh projection so downstream nodes see the new state
    state.case_projection = await case_service.get_projection(state.case_id)
    return state
```

This pattern is enforced by code review and by a lint rule checking that no node writes to `state.case_projection.*` directly.

### 33.8 Testability invariant

Every service under `backend/app/services/` MUST have unit tests that run without importing LangGraph or LangChain. If a service cannot be tested without LangGraph, it contains orchestration concerns that belong in a graph node.

CI MUST fail if any service module imports from `langgraph.*` or `langchain.*`. Exception: `langchain_core` types used as structured data containers are permitted; execution primitives are not.

### 33.9 Supervisor pattern

If `langgraph-supervisor` is used, the supervisor is subject to the same rules as any other graph node. A supervisor that routes between sub-agents is an orchestrator, not a decision-maker. Routing decisions that depend on case state MUST be delegated to `routing_service`.

### 33.10 Reconciliation of existing code

At the time of this supplement, the repository contains two parallel orchestration stacks: `backend/app/services/fast_brain/` and `backend/app/agent/graph/`. The target state is a single canonical graph entry point. Audit 1 will produce a concrete delta report and decide which stack becomes the canonical root; the other is migrated or removed.

Until reconciliation, new code MUST be added only to the stack designated as canonical by the audit.

---

## 34 — Consistency and error model

### 34.1 Scope

This chapter defines the concurrency, transaction, and failure semantics that implement the state regression rules of base SSoT chapter 11. It is a prerequisite for Patch 2 of the implementation sequence in base SSoT §30.

### 34.2 Optimistic locking

Every case-mutating API call MUST carry the client's known `case_revision` as `expected_revision`. The backend MUST reject any mutation whose `expected_revision` does not match the current persisted revision with HTTP 409:

```json
{
  "error": "revision_conflict",
  "expected_revision": 7,
  "current_revision": 9,
  "recommendation": "refetch_and_retry"
}
```

LangGraph nodes carry the expected revision from `state.case_projection.revision` at read time. Concurrent graph runs on the same case are serialized by this mechanism; the second run receives 409 and either retries against the refreshed projection or aborts with a logged error.

### 34.3 Mutation events as first-class entities

Every change to a case is represented by a `MutationEvent`, persisted in the `mutation_events` table (see §36.4). Mutation events are append-only and immutable.

Applying a mutation is a single database transaction containing:

1. `SELECT ... FOR UPDATE` or `WHERE version = :expected_version` on `cases`
2. `INSERT` into `mutation_events`
3. `UPDATE` on `cases` with new revision and updated payload
4. `INSERT` into `outbox` for any async downstream work

If any step fails, the entire transaction rolls back. No partial mutations are ever visible to any reader.

### 34.4 Mutation type enum (baseline)

The following mutation types are the canonical baseline. Adding a new mutation type requires updating both the enum and `case_service`:

```
field_updated
property_confirmed
document_attached
medium_context_refreshed
registry_lookup_applied
routing_path_proposed
routing_path_finalized
phase_transitioned
check_recomputed
risk_score_updated
readiness_downgraded
readiness_upgraded
rca_outcome_recorded
retrofit_handover_initiated
blocked_fields_added
blocked_fields_released
case_revalidation_marked
output_validation_failed
```

Each mutation type has:

- a Pydantic payload model in `backend/app/domain/events.py`
- a handler in `case_service` that validates inputs, applies the change atomically, declares downstream invalidations per base SSoT §11.2, and writes appropriate outbox rows
- at least one property-based test covering its invariants

### 34.5 Outbox pattern for async recomputes

The `outbox` table captures pending async work triggered by a mutation. A dedicated worker process (`outbox_worker`) polls the table using `SELECT ... FOR UPDATE SKIP LOCKED`, dispatches the job, and updates the row on completion or failure.

Jobs dispatched via the outbox include (non-exhaustive):

- `medium_intelligence_refresh` — medium context rebuild after medium change
- `compatibility_lookup` — compatibility engine rerun
- `risk_score_recompute` — risk engine rerun for affected dimensions
- `rca_reevaluation` — RCA path rerun when changed inputs affect cluster selection
- `export_invalidation` — invalidate stored RFQ PDFs, JSON exports
- `projection_cache_bust` — if projection caching is enabled

### 34.6 Retry budgets and dead-letter handling

Each `job_type` declares:

- `max_attempts` (default 5)
- `backoff_schedule` (default exponential with jitter, base 2s, cap 5min)
- `timeout_seconds` (default 60)

Upon exceeding `max_attempts`, the row transitions to status `dead`, the case is marked `needs_manual_recompute = true`, and a warning is emitted via structured logs and Prometheus metric `sealai_outbox_dead_total`.

The `EngineeringCockpitView.blockers` array MUST surface every dead outbox row affecting the current case. The frontend renders these as persistent blockers that require explicit operator action.

### 34.7 Idempotency

Every async handler MUST be idempotent. Re-running a handler with the same `(case_id, event_ref)` MUST produce the same result or a no-op. Handlers achieve idempotency by:

- keying output writes on `event_ref` (unique constraint enforces at most one row per event)
- short-circuiting if the resulting artifact already exists with matching `event_ref`
- avoiding incremental counters (use absolute values derived from inputs)

CI MUST include at least one test per handler that invokes the handler twice with identical inputs and asserts the final database state is identical.

### 34.8 Synchronous vs asynchronous work

Synchronous (inside the mutation transaction):

- increment `case_revision`
- mark dependent artifacts `stale` in `payload.artifacts`
- recompute `highest_valid_phase`
- downgrade `readiness` per base SSoT §11
- record `recompute_required[]` in the case payload
- write outbox rows for async work

Asynchronous (via outbox worker):

- refresh medium intelligence
- rerun compatibility lookups
- rerun risk score calculations
- rerun RCA evaluation
- invalidate exports and regenerate PDFs on demand

### 34.9 Worker failure policy

The `outbox_worker` sets a heartbeat timestamp when picking up a row. A heartbeat monitor reclaims rows whose heartbeat has not been updated within `heartbeat_timeout` (default 120s). Reclaimed rows return to `pending` and are re-picked; idempotency guarantees correctness.

If the worker crashes after completing work but before committing the status update, the next pickup re-runs the handler. Idempotency ensures this is safe.

A separate alert fires when any outbox row remains in `dead` state longer than `dead_row_alert_threshold` (default 1 hour in production, 5 minutes in staging).

### 34.10 Observability requirements

The outbox worker MUST expose Prometheus metrics:

```
sealai_outbox_pending_count{job_type}         gauge
sealai_outbox_processing_seconds{job_type}    histogram
sealai_outbox_attempts_total{job_type,outcome} counter
sealai_outbox_dead_count{job_type}            gauge
sealai_mutation_applied_total{mutation_type,actor_type} counter
sealai_revision_conflict_total                counter
```

These metrics MUST be visible in the existing Grafana instance alongside other backend metrics.

### 34.11 Replay and rebuild

The `mutation_events` table is the authoritative history. Any case MUST be rebuildable by replaying its mutation events in order starting from an empty case.

A CLI command MUST exist:

```
python -m app.cli rebuild-case <case_id> [--target-revision <n>]
```

Running this command against a clean database MUST produce a byte-identical case (modulo computed cache artifacts and timestamps) when compared to the live case at the same revision. A CI integration test MUST verify this property against a set of golden cases (base SSoT §29.2).

---

## 35 — Four-layer schema separation

### 35.1 Scope

This chapter defines the canonical layering for all case-related data structures. It supersedes any schema conventions in existing code and is binding for all new and refactored modules. It amends base SSoT chapter 12 by making the layering concrete.

### 35.2 The four layers

**Layer 1 — Domain** (`backend/app/domain/`)
Canonical data model. Framework-free Pydantic v2 models. This is the conceptual vocabulary of SeaLAI, aligned 1:1 with base SSoT chapters 12 and 14–19.

**Layer 2 — Persistence** (`backend/app/models/`)
SQLAlchemy v2 ORM entities. Maps domain objects to Postgres tables. Contains no business logic. Alembic migrations live alongside.

**Layer 3 — API** (`backend/app/schemas/`)
Pydantic v2 request and response models. May intentionally diverge from domain to omit internal fields, restructure for client convenience, or version contracts.

**Layer 4 — Graph state** (`backend/app/agent/state/`)
Pydantic v2 or TypedDict models for LangGraph transient state. References domain objects by id or carries read-only projections. Never owns authoritative values.

### 35.3 Domain layer contents

`backend/app/domain/` contains at minimum:

- `case.py` — `Case`, `EngineeringProperty`, `Phase`, `Readiness` (domain versions)
- `routing.py` — `RequestType`, `EngineeringPath`, `RoutingDecision`
- `medium.py` — `MediumInput`, `MediumContext`, `MediumRegistry`, `InferredProperties`, `ConfirmedProperties`
- `checks.py` — `CheckResult`, `CheckDefinition`, `CheckRegistry`
- `risk.py` — `RiskScore`, `RiskDimension`, `RiskEngineVersion`
- `rca.py` — `RcaEvidence`, `RcaOutcome`, `FailureModeCluster`
- `retrofit.py` — `RetrofitConstraints`, `RetrofitOutcome`
- `commercial.py` — `CommercialContext`, `ProductionMode`
- `norms.py` — `NormContext`, `NormApplicability`, `NormModuleVersion`
- `events.py` — `MutationEvent` enum and payload models per §34.4
- `output_classes.py` — output class enum and constraints per base SSoT §24

Import rules:

- Domain modules import only from standard library, `pydantic`, `typing`, and each other
- Domain modules MUST NOT import from `models/`, `schemas/`, `agent/`, `api/`, or `services/`

### 35.4 Persistence layer contents

`backend/app/models/` contains at minimum:

- `case.py` — `CaseORM` with JSONB payload plus indexed columns per §36.3
- `mutation_event.py` — `MutationEventORM`
- `outbox.py` — `OutboxORM`
- `risk_score.py` — `RiskScoreORM`
- `mappers.py` — pure mapping functions between domain and ORM

Required mapper signatures:

```python
def case_to_orm(case: Case) -> CaseORM: ...
def orm_to_case(orm: CaseORM) -> Case: ...
def mutation_to_orm(event: MutationEvent) -> MutationEventORM: ...
def orm_to_mutation(orm: MutationEventORM) -> MutationEvent: ...
```

Mappers are pure functions. Every domain type with an ORM counterpart MUST have a round-trip test verifying `orm_to_x(x_to_orm(instance)) == instance` for all fixture instances.

### 35.5 API layer contents

`backend/app/schemas/` contains at minimum:

- `case_api.py` — `CaseCreateRequest`, `CaseUpdateRequest`, `CaseResponse`, `CaseListItemResponse`
- `cockpit.py` — `EngineeringCockpitView` and sub-models per base SSoT §13
- `mutation_api.py` — per-mutation-type request models for `POST /cases/{id}/mutate/*` endpoints
- `error.py` — standardized error response models including `RevisionConflict`

API models MAY diverge from domain in three specific ways:

1. Omit internal fields (audit metadata, raw LLM scratchpad, outbox references)
2. Restructure for client rendering (flatten nested paths, group for UI sections, paginate lists)
3. Version variants — `CaseResponseV1`, `CaseResponseV2` — when contract changes

Every API model has a mapper from domain. No FastAPI route returns a domain object directly. CI includes a test that asserts no FastAPI route handler's return type is a domain type.

### 35.6 Graph state contents

`backend/app/agent/state/` contains:

- `consult_state.py` — `ConsultState` per §33.6
- `read_projection.py` — `CaseReadProjection` (a slimmed-down domain view optimized for LLM context)
- `run_context.py` — per-turn metadata including message id, user id, channel, locale

Graph state MUST carry only: `case_id`, `case_projection`, `run_context`, `llm_scratchpad`. It MUST NOT carry mutable domain objects or persistence references.

### 35.7 Target directory layout

```
backend/app/
├── domain/
│   ├── __init__.py
│   ├── case.py
│   ├── routing.py
│   ├── medium.py
│   ├── checks.py
│   ├── risk.py
│   ├── rca.py
│   ├── retrofit.py
│   ├── commercial.py
│   ├── norms.py
│   ├── events.py
│   └── output_classes.py
├── models/
│   ├── __init__.py
│   ├── case.py
│   ├── mutation_event.py
│   ├── outbox.py
│   ├── risk_score.py
│   └── mappers.py
├── schemas/
│   ├── __init__.py
│   ├── case_api.py
│   ├── cockpit.py
│   ├── mutation_api.py
│   └── error.py
├── agent/
│   ├── state/
│   │   ├── __init__.py
│   │   ├── consult_state.py
│   │   ├── read_projection.py
│   │   └── run_context.py
│   ├── graph/
│   │   └── (canonical graph definition per §33.10)
│   ├── prompts/
│   └── runtime/
├── services/
│   ├── __init__.py
│   ├── case_service.py
│   ├── phase_gate_service.py
│   ├── routing_service.py
│   ├── projection_service.py
│   ├── formula_library/
│   ├── risk_engine/
│   ├── compatibility/
│   ├── output_validator.py
│   └── outbox_worker.py
└── api/
    └── v1/
        └── (FastAPI routes; thin handlers that delegate to services)
```

### 35.8 Import rules (enforced by CI)

The following import graph is binding. A module importing "upward" is a CI-blocking lint violation.

| Module        | May import from                                                           |
|---------------|---------------------------------------------------------------------------|
| `domain/`     | stdlib, `pydantic`, `typing`, other `domain/` modules                     |
| `models/`     | `domain/`, `sqlalchemy`, `alembic`                                        |
| `schemas/`    | `domain/`                                                                 |
| `agent/state/`| `domain/`                                                                 |
| `agent/graph/`| `agent/state/`, `services/`, `langgraph`, `langchain_core`                |
| `services/`   | `domain/`, `models/`; `schemas/` only where a service serves an API directly |
| `api/`        | `schemas/`, `services/`                                                   |

Enforcement: `ruff` with `flake8-tidy-imports` rules, or an equivalent custom check in CI.

### 35.9 Migration from current structure

Current code mixes concerns across `backend/app/agent/domain/`, `backend/app/models/`, `backend/app/schemas/`, and `backend/app/agent/state/`. The audit (Audit 1) produces the concrete delta. The resulting patch plan sequences the reorganization without breaking runtime by:

1. Extracting domain models first as the source of truth
2. Rewriting ORM entities with tested mappers
3. Rebuilding API schemas with tested mappers
4. Refactoring graph state into read-only projections
5. Removing orphaned duplicate definitions

### 35.10 Testing invariants

Every domain module MUST have unit tests covering:

- construction with valid inputs
- rejection of instances with invalid inputs via Pydantic validation
- round-trip through domain → ORM → domain for persistable types
- round-trip through domain → API schema → domain for API-facing types
- serialization stability: `model_dump_json()` output is byte-stable for fixture instances across runs

---

## 36 — Persistence model

### 36.1 Scope

This chapter fixes the persistence strategy for SeaLAI case data. It amends base SSoT chapter 12 with concrete storage mechanics. The design uses a JSONB-primary approach with selectively extracted indexed columns and dedicated tables for append-only audit data.

### 36.2 Source of truth

Postgres is the single source of truth for:

- `Case` objects (all fields per base SSoT §12.1)
- `MutationEvent` history
- `RiskScore` history
- `Outbox` rows
- any other long-lived engineering data

Redis is used exclusively for:

- LangGraph checkpoint state (transient, per graph run)
- ephemeral caches with explicit TTL
- rate limiting and websocket session state

Redis MUST NOT hold any authoritative case field value. A complete Redis flush MUST NOT cause loss of engineering data — at most it aborts in-flight conversations, which clients resume with fresh context.

### 36.3 Case table schema

```sql
CREATE TABLE cases (
    case_id              UUID PRIMARY KEY,
    tenant_id            UUID NOT NULL,
    owner_user_id        UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- versioning
    case_revision        INTEGER NOT NULL DEFAULT 1,
    schema_version       TEXT NOT NULL,
    ruleset_version      TEXT NOT NULL,
    calc_library_version TEXT NOT NULL,
    risk_engine_version  TEXT NOT NULL,
    norm_module_versions JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- extracted indexed columns (hot query paths)
    request_type         TEXT,
    routing_path         TEXT,
    highest_valid_phase  SMALLINT,
    rfq_ready            BOOLEAN NOT NULL DEFAULT false,
    inquiry_admissible   BOOLEAN NOT NULL DEFAULT false,
    needs_revalidation   BOOLEAN NOT NULL DEFAULT false,
    needs_manual_recompute BOOLEAN NOT NULL DEFAULT false,

    -- authoritative case document
    payload              JSONB NOT NULL,

    -- optimistic locking
    version              INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_cases_tenant_owner ON cases (tenant_id, owner_user_id);
CREATE INDEX idx_cases_request_type ON cases (request_type);
CREATE INDEX idx_cases_routing_path ON cases (routing_path);
CREATE INDEX idx_cases_revalidation ON cases (needs_revalidation) WHERE needs_revalidation = true;
CREATE INDEX idx_cases_manual_recompute ON cases (needs_manual_recompute) WHERE needs_manual_recompute = true;
CREATE INDEX idx_cases_updated_at ON cases (updated_at DESC);

-- Selectively indexed JSONB paths for demonstrated hot queries only
CREATE INDEX idx_cases_medium_name ON cases ((payload -> 'medium' -> 'input' ->> 'name'));
```

Extracted columns are maintained by triggers or by `case_service.apply_mutation` — they are cached projections of fields that also exist in `payload`. Consistency is enforced by a CI check that reads every case, recomputes extracted columns from payload, and asserts equality.

New extracted columns MAY be added only when a specific query pattern demonstrates measurable benefit. The default answer to "should we extract this field?" is no.

### 36.4 Mutation events table schema

```sql
CREATE TABLE mutation_events (
    event_id             UUID PRIMARY KEY,
    case_id              UUID NOT NULL REFERENCES cases(case_id),
    occurred_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_type           TEXT NOT NULL,    -- 'user' | 'llm' | 'system' | 'worker'
    actor_id             TEXT,
    mutation_type        TEXT NOT NULL,
    payload              JSONB NOT NULL,
    resulting_revision   INTEGER NOT NULL,
    event_hash           TEXT NOT NULL,
    schema_version       TEXT NOT NULL,
    ruleset_version      TEXT NOT NULL
);

CREATE INDEX idx_mutation_events_case ON mutation_events (case_id, occurred_at);
CREATE INDEX idx_mutation_events_type ON mutation_events (mutation_type, occurred_at);
CREATE UNIQUE INDEX idx_mutation_events_case_revision ON mutation_events (case_id, resulting_revision);
```

Mutation events are strictly append-only. Neither `UPDATE` nor `DELETE` is ever permitted. Schema evolution of a specific mutation type's payload is handled by including a `payload_version` field within the payload and by maintaining forward-compatible handlers.

`event_hash` is a stable hash of `(case_id, mutation_type, payload, resulting_revision)` used for deduplication in client retries.

### 36.5 Risk scores table schema

Risk scores are persisted as time-series. Each recompute appends rows. The "current" score is the latest row per `(case_id, dimension)`.

```sql
CREATE TABLE risk_scores (
    id                   BIGSERIAL PRIMARY KEY,
    case_id              UUID NOT NULL REFERENCES cases(case_id),
    dimension            TEXT NOT NULL,    -- 'flashing_risk', 'fit_risk', ...
    score                SMALLINT NOT NULL,
    label                TEXT NOT NULL,
    reason_codes         TEXT[] NOT NULL,
    inputs_used          JSONB NOT NULL,
    missing_inputs       TEXT[] NOT NULL,
    computed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    triggered_by_event   UUID REFERENCES mutation_events(event_id),
    engine_version       TEXT NOT NULL
);

CREATE INDEX idx_risk_scores_case_dim_latest ON risk_scores (case_id, dimension, computed_at DESC);
```

Latest-per-dimension queries use the index. A materialized view `current_risk_scores` MAY be added when query load justifies it; the view is a performance concern, never a source-of-truth concern.

Retention: risk score rows are retained for the lifetime of the case. Periodic archival MAY move rows older than N months to cold storage but MUST preserve retrievability.

### 36.6 Outbox table schema

```sql
CREATE TABLE outbox (
    id                   UUID PRIMARY KEY,
    case_id              UUID NOT NULL REFERENCES cases(case_id),
    event_ref            UUID REFERENCES mutation_events(event_id),
    job_type             TEXT NOT NULL,
    payload              JSONB NOT NULL,
    status               TEXT NOT NULL DEFAULT 'pending',
    attempts             INTEGER NOT NULL DEFAULT 0,
    max_attempts         INTEGER NOT NULL DEFAULT 5,
    next_attempt_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    picked_up_at         TIMESTAMPTZ,
    picked_up_by         TEXT,
    heartbeat_at         TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    last_error           TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outbox_pickup ON outbox (status, next_attempt_at)
    WHERE status IN ('pending', 'in_progress');
CREATE INDEX idx_outbox_case ON outbox (case_id, created_at DESC);
CREATE INDEX idx_outbox_dead ON outbox (status) WHERE status = 'dead';
CREATE UNIQUE INDEX idx_outbox_event_job ON outbox (event_ref, job_type)
    WHERE event_ref IS NOT NULL;
```

The unique constraint on `(event_ref, job_type)` prevents duplicate job enqueuing during mutation retry.

### 36.7 Schema versioning and migration

Alembic is the authoritative migration tool. Every schema change MUST:

- be expressible as a forward Alembic migration with a tested downgrade
- be reviewable in isolation (one logical change per revision)
- bump `schema_version` in application configuration if domain models change

Payload JSONB changes that remain backwards-compatible do not require a DB migration but MUST:

- bump `schema_version`
- include a lazy-upgrade path in `case_service.load_case` that migrates the payload on read
- be covered by a migration test asserting that old-format cases load correctly after the change

Breaking payload changes require a full migration pass that updates every existing row, gated by a maintenance window or run as a background job with progress tracking.

### 36.8 Query patterns and performance targets

Read patterns (ordered by expected frequency):

| Pattern                                         | Target p99 | Notes                                          |
|-------------------------------------------------|------------|------------------------------------------------|
| Get case by `case_id`                           | < 10ms     | Single row lookup, hot path                    |
| Get `EngineeringCockpitView` by `case_id`       | < 100ms    | Reads case + latest risk scores, computes view |
| List cases by tenant + status filter            | < 200ms    | Uses `(tenant_id, owner_user_id)` index        |
| Get mutation history for case                   | < 150ms    | Paginated, ordered by `occurred_at`            |
| List dead outbox rows                           | N/A        | Diagnostic, not latency-critical               |

Write patterns:

| Pattern                                         | Target p99 | Notes                                          |
|-------------------------------------------------|------------|------------------------------------------------|
| Apply mutation                                  | < 50ms     | Single transaction; optimistic lock            |
| Outbox pickup                                   | < 20ms     | `SELECT ... FOR UPDATE SKIP LOCKED`            |
| Risk score recompute write-back                 | < 80ms     | INSERT risk_scores + UPDATE cases metadata     |

These targets are validated in a load-test CI stage that exercises fixture cases against a real Postgres instance.

### 36.9 Redis usage rules

Permitted Redis uses:

- LangGraph checkpoint state — key pattern `lg:checkpoint:{thread_id}`, TTL 24h
- Medium context cache — key pattern `mctx:{medium_hash}`, TTL 6h
- Rate limiter counters — TTL matching window
- Websocket session state — TTL on disconnect

Forbidden Redis uses:

- Case state caching. If read latency demands caching, use in-process memoization bounded to the current request scope.
- Mutation event queuing. Use the `outbox` table.
- Authoritative risk score storage.
- Any storage that would not survive a full Redis flush.

### 36.10 Backup and recovery

Postgres MUST be backed up daily with point-in-time recovery enabled.

Monthly recovery drill (required CI or ops task):

1. Restore latest backup to a test instance
2. Verify `SELECT count(*) FROM cases` matches the last-known value
3. Sample 10 random cases and replay their mutation events per §34.11 to verify rebuild correctness
4. Sample 5 dead outbox rows and verify they are still recoverable

Redis is not backed up. Loss of Redis data results in:

- active graph runs abort; client retries with a fresh conversation turn
- caches warm from Postgres on demand

This behaviour is acceptable because no authoritative data lives in Redis.

### 36.11 Multi-tenancy provision

`tenant_id` is present on `cases` and propagates through `mutation_events`, `outbox`, and `risk_scores` via `case_id` foreign key. All list queries MUST filter by `tenant_id` before any other filter.

A PostgreSQL row-level security policy on `cases` MAY be introduced for defense-in-depth; if so, every service invocation MUST execute under the tenant's database role, and application-level filters remain as primary enforcement.

This provision is required for the manufacturer account model referenced in the product concept (see `SEALAI_KONZEPT_FINAL.md` chapter 6), where user accounts and manufacturer accounts see disjoint case sets.

### 36.12 Authorization boundary

Fields whose `is_confirmed` status may be set to `true` MUST be writable only by actors with an Engineering-Clearance role. Manufacturer accounts MUST NOT be able to confirm engineering properties on a user's case.

Enforcement is two-layered:

1. FastAPI dependency injection verifies the Keycloak token's roles before dispatching to `case_service`
2. `case_service.apply_mutation` re-verifies actor permissions against the mutation type before persisting

Defense-in-depth is intentional. Either layer alone is insufficient for audit-grade guarantees.

### 36.13 Integration into implementation sequence

This chapter is a prerequisite for Patch 2 (canonical schema + cockpit projection) per base SSoT §30. Patch 2 MUST include:

- Alembic migrations creating the tables defined in §36.3 through §36.6
- Domain models per §35.3
- ORM models per §35.4 with tested mappers
- `case_service` with `apply_mutation`, `get_case`, and `get_projection` as minimum public API
- A health check endpoint verifying all required tables exist and are readable
- Load tests validating the performance targets in §36.8

Patches 3 through 10 depend on this foundation and MUST NOT introduce alternative persistence paths.

---

## Cross-reference index

For Codex CLI and Claude Code during audit and patch phases:

| Base SSoT chapter | Amended or extended by |
|-------------------|------------------------|
| §4 (Product definition) | §33 |
| §8 (LLM responsibilities) | §33.2–33.4 |
| §9 (Phase model) | §33.5 |
| §10 (Phase transition rules) | §33.5, §34.8 |
| §11 (State regression) | §34 in full |
| §12 (Canonical data model) | §35, §36 |
| §13 (Cockpit projection) | §35.5 |
| §20 (Formula library) | §33.5 |
| §21 (Risk-score engine) | §33.5, §36.5 |
| §22 (Chemical compatibility) | §33.5 |
| §24 (Output classes) | §33.5 |
| §28 (API surface) | §34.2, §35.5 |
| §29 (Validation strategy) | §33.8, §34.7, §34.11, §35.10, §36.8 |
| §30 (Implementation sequence) | §34.12, §36.13 |

## Final binding rule

Where this supplement and the base SSoT agree, both are binding. Where this supplement adds a constraint not present in the base SSoT, the constraint is binding. Where this supplement and the base SSoT disagree on any specific rule, this supplement takes precedence because it is the newer document and addresses gaps explicitly identified during architectural review.

Codex CLI and Claude Code MUST treat both documents as a unified source of truth when auditing, planning patches, or implementing changes.
