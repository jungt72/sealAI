# Phase 2 - Architecture Map

## Executive Architecture Finding

Verified fact: the deterministic heart is not one single `engine.py`; it is a governed backend pipeline centered on the LangGraph runtime, reducers, calculation services, final guard, and snapshot persistence.

Primary deterministic backbone:

1. Turn boundary and route contract.
2. Observation into `ObservedState`.
3. Normalization into `NormalizedState`.
4. Assertion into `AssertedState`.
5. Evidence retrieval boundary.
6. Deterministic calculations and screening.
7. Governance and RFQ/matching decisions.
8. Output contract, final guard, dashboard projection.
9. Redis/Postgres persistence and snapshot hash.

## End-to-End Flow

Verified flow:

1. User input enters REST/SSE:
   - REST: `backend/app/agent/api/routes/chat.py`
   - SSE: `backend/app/agent/api/streaming.py`
   - Frontend BFF: `frontend/src/app/api/bff/agent/chat/stream/route.ts`
2. Pre-gate/dispatch classifies route:
   - Deterministic first: `backend/app/services/pre_gate_classifier.py:23-31`, `backend/app/services/pre_gate_classifier.py:41-168`
   - Optional LLM semantic router: `backend/app/services/semantic_intent_router.py:134-161`, `backend/app/services/semantic_intent_router.py:227-256`
3. Governed runtime loads state and builds graph input:
   - `backend/app/agent/api/governed_runtime.py:306-329`
4. LangGraph governed path executes:
   - Topology and invariants: `backend/app/agent/graph/topology.py:6-63`
   - Compiled nodes/edges: `backend/app/agent/graph/topology.py:301-382`
5. Intake observes raw user facts:
   - Regex extraction always runs: `backend/app/agent/graph/nodes/intake_observe_node.py:530-593`
   - LLM extraction runs by default unless disabled: `backend/app/agent/graph/nodes/intake_observe_node.py:27-30`, `backend/app/agent/graph/nodes/intake_observe_node.py:59-61`, `backend/app/agent/graph/nodes/intake_observe_node.py:594-623`
6. Normalize and assert:
   - Normalize node delegates to reducer: `backend/app/agent/graph/nodes/normalize_node.py:39-84`
   - `reduce_observed_to_normalized`: `backend/app/agent/state/reducers.py:620-798`
   - `reduce_normalized_to_asserted`: `backend/app/agent/state/reducers.py:860-1051`
7. Evidence boundary:
   - Structured query from asserted state: `backend/app/agent/graph/nodes/evidence_node.py:126-170`
   - RAG call: `backend/app/agent/evidence/retrieval.py:9-22`
   - Tenant RAG cascade: `backend/app/agent/services/real_rag.py:54-87`, `backend/app/agent/services/real_rag.py:91-229`
8. Compute/calculation:
   - Compute node: `backend/app/agent/graph/nodes/compute_node.py:198-251`
   - Cascading engine formulas: `backend/app/services/calculation_engine.py:49-92`, `backend/app/services/calculation_engine.py:124-201`
   - RWDR pure engine: `backend/app/agent/domain/rwdr_calc.py:149-315`
   - V9.2 calculator registry and stable hashes: `backend/app/agent/v92/calculator_registry.py:53-55`, `backend/app/agent/v92/calculator_registry.py:80-148`
9. Governance/matching/RFQ/output:
   - Governance node: `backend/app/agent/graph/nodes/governance_node.py:60-107`
   - Matching sorts by score, manufacturer name, candidate id: `backend/app/agent/graph/nodes/matching_node.py:235-289`
   - RFQ handover deterministic gates: `backend/app/agent/graph/nodes/rfq_handover_node.py:177-320`
   - Output contract claims no LLM and template-generated reply basis: `backend/app/agent/graph/output_contract_assembly.py:1-57`
10. Final output guard:
   - Turn envelope and final context: `backend/app/agent/v92/contracts.py:56-83`, `backend/app/agent/v92/contracts.py:123-164`
   - Guard validation: `backend/app/agent/v92/final_guard.py:90-228`
   - Runtime application: `backend/app/agent/v92/runtime_contract.py:378-541`
11. Persistence:
   - Decision basis hash: `backend/app/agent/state/persistence.py:80-95`
   - Snapshot save: `backend/app/agent/state/persistence.py:287-425`
   - Case mutation transaction: `backend/app/services/case_service.py:44-124`
   - Snapshot idempotency check: `backend/app/services/case_service.py:232-287`

## Component Table

### Component: Chat REST route

Path: `backend/app/agent/api/routes/chat.py`
Lines: `90-125`, `740-780`
Responsibility: Accept chat requests, decide runtime path, assemble public payloads, apply final answer layer.
Inputs: Chat request, session id, current user, runtime flags.
Outputs: Public response payload with reply/answer_markdown, state/update metadata.
Deterministic: Partially. Response assembly and env flag parsing are deterministic for fixed inputs/env.
Nondeterministic dependencies: Environment flag `SEALAI_ENABLE_ACTIVE_CASE_SIDE_ANSWER_COMPOSER` at `109-110`, downstream LLM/RAG/DB.
Failure modes: Feature flag drift changes path; active-case side composer may introduce LLM text.
Notes: This is an orchestration entry point, not the deterministic core.

### Component: Chat SSE stream

Path: `backend/app/agent/api/streaming.py`
Lines: `111-156`, `949-970`
Responsibility: Convert graph progress to SSE, suppress technical draft text, emit final guard progress and final state update.
Inputs: Stream request, graph progress events, final payload.
Outputs: SSE frames.
Deterministic: Mapping of internal text chunk events to progress events is deterministic.
Nondeterministic dependencies: Event order from LangGraph, downstream final payload, optional async LLM reviewer.
Failure modes: If backend emits unexpected event types, raw progress can pass through at `152-156`.
Notes: Tests cover masking native answer tokens; see `backend/app/agent/tests/test_governed_runtime_seam.py:230-350`.

### Component: PreGateClassifier

Path: `backend/app/services/pre_gate_classifier.py`
Lines: `23-31`, `41-168`
Responsibility: Deterministic-first classification of input into greeting/meta/knowledge/domain/blocked/recovery.
Inputs: Raw user input.
Outputs: `ClassificationResult`.
Deterministic: Yes for fixed regex tables and helper functions.
Nondeterministic dependencies: None found in this class.
Failure modes: Regex order and rule overlap can route differently after code changes; phrase-specific coverage can miss semantics.
Notes: This is a controlled deterministic dependency: rule version is implicit in code, not versioned in output.

### Component: SemanticIntentRouter

Path: `backend/app/services/semantic_intent_router.py`
Lines: `103-161`, `227-256`
Responsibility: Optional LLM refinement between knowledge dialogue and governed case intake.
Inputs: Message, deterministic classification, recent history.
Outputs: `SemanticIntentRouterDecision` and possibly revised classification.
Deterministic: No. It calls `get_async_llm("semantic_intent_router")`.
Nondeterministic dependencies: OpenAI/model, prompt template, env enable flag, history content/order.
Failure modes: Same message can route differently if model output, model version, prompt, or environment changes.
Notes: Deterministic hard case fact guard exists at `123-124`, but the LLM can still affect boundary candidates.

### Component: TurnBoundaryOrchestrator

Path: `backend/app/agent/v92/turn_boundary.py`
Lines: `190-298`
Responsibility: Convert hints/message/state into route, mutation policy, streaming policy, guard requirements.
Inputs: User message, session id, state, route hints, payload metadata.
Outputs: `TurnBoundaryDecision`.
Deterministic: Yes for fixed inputs/state.
Nondeterministic dependencies: State presence from persistence; upstream classification/hints may be LLM-derived.
Failure modes: Regex overlap and hint precedence can change mutation policy.
Notes: Technical routes require status-only streaming and final guard. Evidence: `backend/app/agent/v92/turn_boundary.py:258-283`.

### Component: Governed graph topology

Path: `backend/app/agent/graph/topology.py`
Lines: `6-63`, `301-382`
Responsibility: Governed execution graph composition.
Inputs: `GraphState`.
Outputs: Updated `GraphState`.
Deterministic: Topology is deterministic. Some nodes are not.
Nondeterministic dependencies: Async checkpointer backend and fallback, LLM intake, RAG, answer composer.
Failure modes: Redis checkpoint unavailable falls back to in-memory at `221-233`, changing replay/durability behavior.
Notes: File documents intended invariant that only intake and answer composer may call LLM. Evidence: `backend/app/agent/graph/topology.py:55-59`.

### Component: Intake observe node

Path: `backend/app/agent/graph/nodes/intake_observe_node.py`
Lines: `1-30`, `417-493`, `500-638`
Responsibility: Extract typed facts into `ObservedState`.
Inputs: Pending user message, pending question context, current graph state.
Outputs: `ObservedExtraction` and `UserOverride` changes in observed state.
Deterministic: Regex pass is deterministic; LLM pass is nondeterministic and enabled by default.
Nondeterministic dependencies: `SEALAI_ENABLE_LLM_EXTRACTION`, OpenAI model, prompt, JSON response shape.
Failure modes: LLM fail-open returns regex-only state; same input can include or omit LLM-only fields depending on availability.
Notes: LLM output is constrained to observed state, not direct normalized/asserted writes.

### Component: Normalization

Path: `backend/app/agent/domain/normalization.py`
Lines: `604-714`, `1300-1464`
Responsibility: Normalize raw fields, units, materials, media; extract regex parameters.
Inputs: Raw field/value/unit or message text.
Outputs: `CriticalFieldNormalization`, normalized entities, extracted params.
Deterministic: Mostly, but critical field normalization injects wall-clock time.
Nondeterministic dependencies: `datetime.now(timezone.utc).isoformat()` at `713`; optional LLM medium fallback at `1063-1117` and `1433-1448`.
Failure modes: Same value normalized at different times yields different `normalized_at`, which can enter hash/snapshot.
Notes: This is the highest-risk deterministic-core leak.

### Component: Observed to normalized reducer

Path: `backend/app/agent/state/reducers.py`
Lines: `620-798`
Responsibility: Resolve overrides/extractions into normalized parameters, conflicts, assumptions, statuses.
Inputs: `ObservedState`.
Outputs: `NormalizedState`.
Deterministic: Not fully proven. It uses a Python `set` for field order.
Nondeterministic dependencies: `all_fields = set(...)` at `653` and iteration at `655`.
Failure modes: Parameter/conflict/assumption order can vary across hash seeds/processes; equal confidence and turn ties preserve input order.
Notes: Sorting extractions by confidence and turn exists at `701-713`, but field order is not stable.

### Component: Normalized to asserted reducer

Path: `backend/app/agent/state/reducers.py`
Lines: `860-925`
Responsibility: Promote normalized parameters to asserted claims based on user override, explicit calculation input, and evidence.
Inputs: `NormalizedState`, optional evidence claims.
Outputs: `AssertedState`.
Deterministic: Deterministic for stable normalized/evidence order; not fully proven for tied evidence.
Nondeterministic dependencies: Iterates normalized dict order at `902`, evidence tie behavior at `889-895`.
Failure modes: Equal-confidence evidence claims for same field keep first-seen claim; RAG order can decide assertion.
Notes: Missing deterministic tie-breaker for evidence equality.

### Component: Evidence node and RAG

Path: `backend/app/agent/graph/nodes/evidence_node.py`
Lines: `126-170`, `243-264`, `309-437`
Responsibility: Build structured query from assertions, retrieve RAG evidence, derive source-backed claims and evidence state.
Inputs: Asserted/normalized state, tenant id.
Outputs: RAG cards, evidence audit, possibly revised asserted state.
Deterministic: Query construction mostly deterministic for stable assertion order; retrieval is nondeterministic/external.
Nondeterministic dependencies: Qdrant/BM25, vector scores, reranker, cache, tenant corpus, RAG failure.
Failure modes: Fail-open path at `384-437`; evidence card order can change which claim is first matched.
Notes: Evidence retrieval can feed assertion promotion at `347-349`.

### Component: Calculation engine

Path: `backend/app/services/calculation_engine.py`
Lines: `49-92`, `124-201`, `204-279`
Responsibility: Run dependency-based deterministic calculations over canonical field names.
Inputs: Input dict and calculation definitions.
Outputs: Derived dict and `CalcExecutionRecord`s.
Deterministic: Yes for same input and Python runtime.
Nondeterministic dependencies: Floating-point math and serialization outside this module.
Failure modes: Float representation/rounding is not centrally canonicalized.
Notes: No LLM/I/O in this service.

### Component: RWDR calculations

Path: `backend/app/agent/domain/rwdr_calc.py`
Lines: `149-315`
Responsibility: Pure RWDR tribology/extrusion calculations.
Inputs: Numeric case dict.
Outputs: Dn, surface speed, PV, warnings, notes, extrusion status.
Deterministic: Yes for same input and runtime.
Nondeterministic dependencies: Floating-point platform/runtime.
Failure modes: Cross-runtime numeric formatting can differ if not canonicalized.
Notes: File header explicitly declares pure-function/no LLM/no external dependencies. Evidence: `backend/app/agent/domain/rwdr_calc.py:1-14`.

### Component: V9.2 calculator registry

Path: `backend/app/agent/v92/calculator_registry.py`
Lines: `53-55`, `80-148`, `374-402`
Responsibility: Versioned calculator registration, input/output hashes, affected-calculation lookup.
Inputs: Calculator inputs and metadata.
Outputs: `CalculationResult`, stable snapshot hashes.
Deterministic: Mostly. Uses sorted JSON hashing with `default=str`.
Nondeterministic dependencies: `default=str` can hide noncanonical object/string formatting if non-primitive values leak in.
Failure modes: 16-char truncated hashes reduce collision margin.
Notes: Registry lists calculators sorted by id at `374-375`.

### Component: Matching node

Path: `backend/app/agent/graph/nodes/matching_node.py`
Lines: `235-289`
Responsibility: Deterministic manufacturer candidate scoring and sorting.
Inputs: State plus domain data provider records.
Outputs: Matching candidate refs and selected manufacturer.
Deterministic: Yes if provider records are stable.
Nondeterministic dependencies: Provider data version/order if external or mutable.
Failure modes: Data provider changes can change candidates; score semantics are not included in decision hash.
Notes: Sort tie-breakers are explicit: `-fit_score`, manufacturer name, candidate id at `272-278`.

### Component: Output contract

Path: `backend/app/agent/graph/output_contract_assembly.py`
Lines: `1-57`, `1791-1805`
Responsibility: Assemble outward public contract and deterministic reply basis.
Inputs: `GraphState`.
Outputs: `output_public`, response class, reply basis.
Deterministic: Mostly. Uses LangGraph interrupt for inquiry confirmation when RFQ-ready.
Nondeterministic dependencies: User interrupt/control flow, previous state, matching/RFQ state.
Failure modes: Runtime without checkpointer catches `RuntimeError` and uses no confirmation at `1849-1851`.
Notes: File states LLM does not call here at `14-16`.

### Component: Final answer contracts and guard

Path: `backend/app/agent/v92/runtime_contract.py`, `backend/app/agent/v92/final_guard.py`, `backend/app/agent/v92/contracts.py`
Lines: `runtime_contract.py:197-234`, `runtime_contract.py:303-375`, `runtime_contract.py:449-541`, `final_guard.py:90-228`, `contracts.py:56-83`
Responsibility: Create turn envelope/final context, validate final answer, revise/fallback if blocked.
Inputs: Payload, state, dashboard projection, answer text.
Outputs: `TurnEnvelope`, `FinalAnswerContext` or `NonTechnicalAnswerContext`, `FinalGuardResult`, guarded answer.
Deterministic: Guard regex/rule logic is deterministic; envelope injects UUID and wall-clock timestamp.
Nondeterministic dependencies: `uuid4()` at `runtime_contract.py:210`, `datetime.now(UTC)` at `runtime_contract.py:232`, optional LLM reviewer at `runtime_contract.py:544-670`.
Failure modes: Same answer/state gets different envelope ids/timestamps. This is acceptable as trace metadata only if excluded from deterministic seal/hash.
Notes: Technical direct streaming is rejected by model validator at `contracts.py:77-83`.

### Component: Decision basis hash

Path: `backend/app/agent/state/persistence.py`
Lines: `80-95`
Responsibility: Compact hash for current decision basis.
Inputs: `state.normalized`, `state.derived`, `state.evidence.source_versions`, ontology version, prompt version.
Outputs: 16-char SHA-256 hex prefix.
Deterministic: Intended deterministic via `json.dumps(... sort_keys=True ...)`.
Nondeterministic dependencies: Included normalized state may contain `normalized_at`; lists preserve potentially unstable order.
Failure modes: Same semantic input can produce different hash due to timestamps or list order. Hash omits model, calculator, reducer/schema versions.
Notes: This is currently not a complete replay/seal hash.

### Component: CaseService persistence

Path: `backend/app/services/case_service.py`
Lines: `44-124`, `232-287`, `407-508`
Responsibility: Create/apply case mutations, snapshots, outbox records.
Inputs: Case id, expected revision, event type, payload, actor.
Outputs: Mutation event, snapshot, outbox, case revision update.
Deterministic: Revision guard and payload validation are deterministic.
Nondeterministic dependencies: UUIDs for mutation/outbox, server timestamps, DB transaction order.
Failure modes: Snapshot idempotency requires both basis hash and full `state_json` equality at `256-263`; volatile state fields can force duplicate revisions.
Notes: Uses expected revision check and `with_for_update`; good concurrency foundation.

## Inferred Input Schema

Primary raw input:

- `message`: string. Evidence: frontend contract `frontend/src/lib/contracts/agent.ts:3-7`; governed runtime uses `request.message` at `backend/app/agent/api/governed_runtime.py:315-327`.
- `caseId` or `conversationId`: optional string. Evidence: `frontend/src/lib/contracts/agent.ts:3-7`; frontend hook payload at `frontend/src/hooks/useAgentStream.ts:392-396`.
- Auth context: user id, tenant id. Evidence: governed runtime uses `current_user` and session id at `backend/app/agent/api/governed_runtime.py:306-329`.

Primary internal schemas:

- `ObservedExtraction`: raw field/value/unit/confidence/source/turn.
- `NormalizedParameter`: field/value/unit/confidence/source/provenance/engineering value.
- `AssertedClaim`: field/asserted value/confidence.
- `GraphState`: carries pending message and all governed state slices.
- `GovernedSessionState`: durable case-level aggregate.
- `TurnEnvelope`, `FinalAnswerContext`, `FinalGuardResult`: V9.2/V10 output boundary.

## Inferred Output Schema

Public output includes:

- `reply`
- `answer_markdown`
- `response_class`
- `turn_envelope`
- `turn_boundary_decision`
- `final_answer_context` or `nontechnical_answer_context`
- `final_guard_result`
- `v92_dashboard`
- `ui`, `assertions`, RFQ readiness projection as available

Evidence: `frontend/src/app/api/bff/agent/chat/stream/route.ts:400-470`, `backend/app/agent/v92/runtime_contract.py:501-531`.

## Where Key Behaviors Happen

- Validation:
  - Pydantic contracts: `backend/app/agent/v92/contracts.py:56-83`, `backend/app/agent/v92/contracts.py:123-164`
  - Mutation payload validation: `backend/app/services/case_service.py:44-64`, `backend/app/services/case_service.py:549-708`
- Normalization/canonicalization:
  - `backend/app/agent/domain/normalization.py:604-714`
  - `backend/app/agent/state/reducers.py:395-416`, `backend/app/agent/state/reducers.py:620-798`
- Scoring/ranking/decision:
  - Pre-gate: `backend/app/services/pre_gate_classifier.py:41-168`
  - Governance: `backend/app/agent/graph/nodes/governance_node.py:60-107`
  - Matching: `backend/app/agent/graph/nodes/matching_node.py:235-289`
  - RAG ranking: `backend/app/services/rag/rag_orchestrator.py:384-403`, `backend/app/services/rag/rag_orchestrator.py:812-835`
- Hashes/seals:
  - Decision basis hash: `backend/app/agent/state/persistence.py:80-95`
  - Calculator snapshot hash: `backend/app/agent/v92/calculator_registry.py:53-55`
  - No cryptographic signing of sealed outputs was found.
- Persistence:
  - Redis state: `backend/app/agent/state/persistence.py:213-285`, `backend/app/agent/state/persistence.py:628-654`
  - Postgres snapshots: `backend/app/agent/state/persistence.py:287-425`, `backend/app/services/case_service.py:232-287`
- Caches:
  - FactCard singleton: `backend/app/services/knowledge/factcard_store.py:89-100`
  - RAG embedder/reranker globals: `backend/app/services/rag/rag_orchestrator.py:96-103`, `backend/app/services/rag/rag_orchestrator.py:812-835`
  - LangGraph singleton/checkpointer: `backend/app/agent/graph/topology.py:116-119`, `backend/app/agent/graph/topology.py:243-254`
- Retries:
  - Qdrant retry backoff uses random jitter: `backend/app/services/rag/rag_orchestrator.py:420-423`
  - Case mutation relies on transaction rollback and expected revision; no retry loop found in `CaseService.apply_mutation`.
- Observability:
  - Governed graph quality traces: `backend/app/agent/api/governed_runtime.py:394-438`
  - V9.2 output quality traces: `backend/app/agent/v92/runtime_contract.py:84-140`
  - RAG logs/timing: `backend/app/agent/services/real_rag.py:88-229`

