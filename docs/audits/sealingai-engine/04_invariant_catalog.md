# Phase 4 - Invariant Catalog

Status key: Verified, Partially verified, Violated, Not testable yet.

## 1. Same canonical input + same engine version + same config => same sealed output

Status: Partially verified.

Evidence:

- Deterministic reducers/calculators exist: `backend/app/agent/state/reducers.py:620-798`, `backend/app/services/calculation_engine.py:49-92`.
- Tests cover specific deterministic paths: `backend/app/agent/tests/test_calculation_state_ledger.py:38-68`, `backend/app/agent/tests/graph/test_compute_node.py:1-31`.
- No full raw-input-to-sealed-output replay test was found.

Risk if broken: Same user case can produce different engineering state or visible answer.

Recommended test: Golden replay from stored `ObservedState` and from raw input with LLM/RAG disabled; assert canonical output equality across N runs and subprocesses.

Recommended fix: Define canonical output payload and isolate nondeterministic trace metadata.

## 2. Same canonical input + same engine version + same config => same hash/digest

Status: Violated for current decision hash if `normalized_at` is present.

Evidence:

- Hash includes normalized state: `backend/app/agent/state/persistence.py:83-85`.
- Critical normalization writes current time: `backend/app/agent/domain/normalization.py:704-714`.
- Existing hash test checks same object twice only: `backend/app/agent/tests/test_decision_basis_hash.py:32-40`.

Risk if broken: Same semantic case can produce different `decision_basis_hash`; snapshots become unreplayable.

Recommended test: Build two semantically equal states through normalization at different times and assert canonical decision hash equality.

Recommended fix: Strip `normalized_at` from canonical hash payload or inject a replay timestamp and include it explicitly.

## 3. Hash/signature/seal is generated from canonical data only

Status: Violated / not currently proven.

Evidence:

- `compute_decision_basis_hash` uses raw `state.normalized.model_dump(mode="json")`: `backend/app/agent/state/persistence.py:80-95`.
- Normalized state can include `engineering_value.normalized_at`: `backend/app/agent/state/models.py:140-149`.

Risk if broken: Hash is a state serialization fingerprint, not a stable engineering seal.

Recommended test: Assert volatile fields cannot affect canonical hash.

Recommended fix: Introduce `build_canonical_decision_basis(state)` with explicit included/excluded fields.

## 4. Equivalent input forms normalize to the same canonical representation

Status: Partially verified.

Evidence:

- Unit conversion tests for temperature and pressure: `backend/app/agent/tests/test_normalization.py:99-147`, `backend/app/agent/tests/test_normalization.py:154-197`.
- Critical field normalization tests start at `backend/app/agent/tests/test_normalization.py:199-240`.

Risk if broken: Equivalent engineering facts split into different states/hashes.

Recommended test: Metamorphic tests for unit variants, decimal comma/dot, casing, synonyms, and whitespace.

Recommended fix: Centralize canonical value/unit rendering and strip volatile metadata from comparison.

## 5. Non-equivalent inputs do not collapse accidentally

Status: Partially verified.

Evidence:

- Conflict reducer tests distinguish 80 vs 80.4 tolerance and Oil vs Water conflict: `backend/app/agent/tests/test_conflict_detection_reducer.py:5-32`.
- Pressure interpretation unknown requires confirmation: `backend/app/agent/domain/normalization.py:641-647`.

Risk if broken: Different media/pressure roles/units can collapse into a false confirmed case.

Recommended test: Fuzz normalization for near-collisions, pressure role ambiguity, unitless values, medium synonyms vs distinct media.

Recommended fix: Add explicit semantic equivalence classes and collision tests.

## 6. Sorting/ranking is stable and has deterministic tie-breakers

Status: Violated in multiple paths; verified in matching.

Evidence:

- Reducer field set iteration: `backend/app/agent/state/reducers.py:652-655`.
- RAG/factcard sorts only by score: `backend/app/services/rag/rag_orchestrator.py:384-403`, `backend/app/services/rag/rag_orchestrator.py:827-835`, `backend/app/services/knowledge/factcard_store.py:217-244`.
- Matching tie-breakers are present: `backend/app/agent/graph/nodes/matching_node.py:272-278`.

Risk if broken: Equal scores or Python hash seed can alter output order and potentially decisions.

Recommended test: Shuffle equal-score inputs and assert identical result ordering.

Recommended fix: Add stable tie-breakers everywhere: field name, source id, doc id, chunk id, candidate id.

## 7. Missing/invalid fields fail closed, not silently mutate semantics

Status: Partially verified.

Evidence:

- Empty input fails safe to domain inquiry: `backend/app/services/pre_gate_classifier.py:32-39`.
- Critical pressure unknown requires confirmation: `backend/app/agent/domain/normalization.py:641-647`.
- CaseService rejects invalid mutation payloads: `backend/tests/unit/services/test_case_service.py:501-740`.
- Evidence and compute nodes fail open: `backend/app/agent/graph/nodes/evidence_node.py:384-437`, `backend/app/agent/graph/nodes/compute_node.py:235-240`.

Risk if broken: Missing evidence or calculation errors can look like "no issue" instead of "unknown".

Recommended test: Inject calculation/RAG exceptions and assert explicit audit status blocks stronger claims.

Recommended fix: Replace silent fail-open with typed degraded state and guard-visible limitations.

## 8. All nondeterministic values are injected, versioned, or stored explicitly

Status: Violated.

Evidence:

- Normalization time is not injected: `backend/app/agent/domain/normalization.py:713`.
- Random idempotency/event ids: `backend/app/agent/state/models.py:73-78`, `backend/app/agent/state/models.py:830-839`, `backend/app/agent/state/models.py:1139-1143`.
- Turn id/timestamp are generated inside `build_turn_envelope`: `backend/app/agent/v92/runtime_contract.py:210-233`.
- Case numbers use `date.today()` and count: `backend/app/agent/state/persistence.py:719-735`.

Risk if broken: Replay creates different ids/timestamps/human numbers.

Recommended test: Determinism tests with injected clock/id provider.

Recommended fix: Introduce explicit `DeterminismContext` or turn metadata provider.

## 9. LLM/external outputs are excluded from deterministic core or snapshotted/versioned

Status: Partially verified by architecture intent, not fully enforced.

Evidence:

- Intake LLM only writes observed state: `backend/app/agent/graph/nodes/intake_observe_node.py:10-14`, `backend/app/agent/graph/nodes/intake_observe_node.py:417-493`.
- Semantic router returns trace fields including model: `backend/app/services/semantic_intent_router.py:86-100`.
- RAG source versions are extracted when available: `backend/app/agent/graph/nodes/evidence_node.py:173-192`.

Risk if broken: Live LLM/RAG can change case truth without replayable evidence.

Recommended test: Replay from snapshotted observed/evidence data with external calls disabled.

Recommended fix: Persist raw LLM/RAG boundary outputs with prompt/model/index versions.

## 10. Persistence is idempotent

Status: Partially verified.

Evidence:

- CaseService skips if latest `basis_hash` and full `state_json` match: `backend/app/services/case_service.py:256-263`.
- Test covers same state object: `backend/app/agent/tests/test_postgres_state_snapshots.py:554-578`.

Risk if broken: Semantically identical reruns create duplicate revisions because random/time fields differ.

Recommended test: Two independently constructed semantically identical states should not create duplicate snapshots.

Recommended fix: Idempotency should compare canonical snapshot payload or canonical decision basis, not full volatile `state_json`.

## 11. Re-running the engine does not create duplicate or contradictory records

Status: Partially verified.

Evidence:

- Snapshot idempotency test: `backend/app/agent/tests/test_postgres_state_snapshots.py:554-578`.
- Case mutation expected revision check: `backend/app/services/case_service.py:72-83`.

Risk if broken: Duplicate snapshots/outbox records or conflicting case revisions.

Recommended test: Run same turn twice with same session under fresh object construction.

Recommended fix: Add request/turn idempotency key stored at mutation boundary.

## 12. Concurrent executions produce one consistent result

Status: Partially verified for mutation, not proven for case creation.

Evidence:

- `apply_mutation` loads case for update and checks expected revision: `backend/app/services/case_service.py:67-83`.
- Case number generation is count-based without visible retry: `backend/app/agent/state/persistence.py:719-735`.

Risk if broken: Concurrent `get_or_create_case` can collide or one write can fail nondeterministically.

Recommended test: Concurrent create/write tests against real transactional DB or a DB-level integration harness.

Recommended fix: DB sequence/unique retry loop and session-level idempotency constraint.

## 13. Error paths are deterministic and auditable

Status: Partially verified.

Evidence:

- RAG failure writes `evidence_gaps=["retrieval_failed"]` and audit error: `backend/app/agent/graph/nodes/evidence_node.py:384-437`.
- LLM extraction failure logs and returns regex-only: `backend/app/agent/graph/nodes/intake_observe_node.py:491-493`.
- Compute failure fail-opens to no result: `backend/app/agent/graph/nodes/compute_node.py:235-240`.

Risk if broken: Same input can produce different output depending on transient error, and the final answer may not expose the degraded basis.

Recommended test: Forced boundary failures produce stable degraded states and final guard limitations.

Recommended fix: Use typed degraded-state objects instead of empty fallbacks.

## 14. Algorithm, schema, prompt, and model versions are traceable

Status: Partially verified.

Evidence:

- Prompt trace contract exists: `backend/app/agent/v92/contracts.py:43-53`.
- Streaming version provenance builder includes model/prompt/policy versions: `backend/app/agent/api/streaming.py:288-315`.
- Snapshot stores ontology, prompt, model versions: `backend/app/agent/state/persistence.py:357-369`, `backend/app/agent/state/persistence.py:398-405`.

Risk if broken: Cannot explain why replay differs after model/prompt/rules changes.

Recommended test: Every final technical payload contains model, prompt hash, guard version, calculator versions.

Recommended fix: Expand decision basis hash input to include all algorithm/schema/calculator versions.

## 15. A previously sealed result can be replayed and verified

Status: Not testable yet.

Evidence:

- There is a decision basis hash and snapshots, but no full replay verifier or signature path found.
- Snapshot reads are tested: `backend/app/agent/tests/test_postgres_state_snapshots.py:925-980`.

Risk if broken: Historical case output cannot be independently verified.

Recommended test: Persist canonical input/evidence/config, replay offline, compare full digest and final guard result.

Recommended fix: Add replay bundle format: canonical input, observed/evidence snapshots, engine/config versions, canonical output, digest, optional signature.

