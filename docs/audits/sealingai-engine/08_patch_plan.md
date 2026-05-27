# Phase 8 - Patch Plan

No patches were implemented in this audit. This is a staged plan for a later approved patch phase.

## Stage 0 - Characterization and Golden Tests

Patch 0.1: Canonical replay fixture scaffold

- Files likely affected:
  - `backend/app/agent/tests/test_deterministic_replay.py` (new)
  - `backend/app/agent/tests/fixtures/deterministic_replay/*.json` (new)
- Rationale: Lock current behavior before code changes.
- Invariant protected: 1, 2, 15.
- Test to add first: Stored `ObservedState` plus evidence cards replays to stable canonical output.
- Expected behavior change: None.
- Rollback strategy: Remove test-only files.
- Risk: Low.

Patch 0.2: Hash volatility characterization

- Files likely affected:
  - `backend/app/agent/tests/test_decision_basis_hash.py`
- Rationale: Prove current timestamp/hash weakness before fixing.
- Invariant protected: 2, 3.
- Test to add first: Two equivalent normalized critical values with different `normalized_at` currently produce different raw basis; mark expected failure or assert canonical builder once added.
- Expected behavior change: None until Stage 2.
- Rollback strategy: Remove characterization test.
- Risk: Low.

Patch 0.3: Ordering characterization

- Files likely affected:
  - `backend/app/agent/tests/test_reducer_ordering.py` (new)
- Rationale: Demonstrate `set` iteration risk.
- Invariant protected: 6.
- Test to add first: Subprocess `PYTHONHASHSEED` replay of reducer.
- Expected behavior change: None until Stage 3.
- Rollback strategy: Remove test.
- Risk: Low.

## Stage 1 - Make Nondeterministic Inputs Explicit/Injected

Patch 1.1: Add deterministic clock/id context for test/replay paths

- Files likely affected:
  - `backend/app/agent/domain/normalization.py`
  - `backend/app/agent/v92/runtime_contract.py`
  - `backend/app/agent/state/models.py`
- Rationale: Stop hidden time/id generation from leaking into canonical paths.
- Invariant protected: 8, 15.
- Test to add first: Injected fixed clock/id yields byte-identical envelope and normalized critical value.
- Expected behavior change: None in production if defaults remain current time/random.
- Rollback strategy: Revert optional parameters/context object.
- Risk: Medium.

Patch 1.2: Persist explicit LLM/RAG boundary snapshots

- Files likely affected:
  - `backend/app/agent/graph/nodes/intake_observe_node.py`
  - `backend/app/services/semantic_intent_router.py`
  - `backend/app/agent/graph/nodes/evidence_node.py`
  - `backend/app/agent/state/models.py`
- Rationale: Replay from boundary outputs without external calls.
- Invariant protected: 9, 15.
- Test to add first: Replay with external calls disabled uses stored snapshots.
- Expected behavior change: Additional trace/audit metadata.
- Rollback strategy: Ignore new metadata on read.
- Risk: Medium.

## Stage 2 - Canonicalization and Stable Serialization

Patch 2.1: Add `build_canonical_decision_basis`

- Files likely affected:
  - `backend/app/agent/state/persistence.py`
  - `backend/app/agent/tests/test_decision_basis_hash.py`
- Rationale: Hash canonical engineering truth only.
- Invariant protected: 2, 3, 14, 15.
- Test to add first: Volatile fields excluded; version fields included.
- Expected behavior change: `decision_basis_hash` changes once canonical payload replaces current raw dump.
- Rollback strategy: Keep old hash as `legacy_decision_basis_hash` during rollout.
- Risk: Medium/high because persisted hash semantics change.

Patch 2.2: Canonical JSON utility

- Files likely affected:
  - `backend/app/agent/state/canonical_json.py` (new)
  - `backend/app/agent/v92/calculator_registry.py`
  - `backend/app/agent/state/persistence.py`
- Rationale: One stable JSON path for hashes.
- Invariant protected: 2, 3.
- Test to add first: Reject non-primitive values unless explicitly encoded.
- Expected behavior change: Hashing fails closed on unsupported types in new canonical path.
- Rollback strategy: Fallback to existing serializer behind feature flag.
- Risk: Medium.

## Stage 3 - Deterministic Sorting/Tie-Breakers

Patch 3.1: Sort reducer field names

- Files likely affected:
  - `backend/app/agent/state/reducers.py`
  - `backend/app/agent/tests/test_reducer_ordering.py`
- Rationale: Remove Python set-order nondeterminism.
- Invariant protected: 6.
- Test to add first: Cross-`PYTHONHASHSEED` reducer output equality.
- Expected behavior change: Stable parameter order, possibly changed display order.
- Rollback strategy: Revert one-line ordering change.
- Risk: Low.

Patch 3.2: Add RAG/BM25/FactCard tie-breakers

- Files likely affected:
  - `backend/app/services/rag/rag_orchestrator.py`
  - `backend/app/services/rag/bm25_store.py`
  - `backend/app/services/knowledge/factcard_store.py`
- Rationale: Equal score ordering must be stable.
- Invariant protected: 6, 9.
- Test to add first: Equal-score shuffled inputs stable.
- Expected behavior change: Top-k order can change for ties.
- Rollback strategy: Restore old sort keys.
- Risk: Medium.

## Stage 4 - Idempotency/Replay Protections

Patch 4.1: Snapshot idempotency based on canonical payload

- Files likely affected:
  - `backend/app/services/case_service.py`
  - `backend/app/agent/state/persistence.py`
  - `backend/app/agent/tests/test_postgres_state_snapshots.py`
- Rationale: Trace-only volatility must not create duplicate revisions.
- Invariant protected: 10, 11.
- Test to add first: Independently constructed equivalent states dedupe.
- Expected behavior change: Fewer duplicate snapshots.
- Rollback strategy: Dual-write/compare old and new idempotency decision before enforcing.
- Risk: Medium/high.

Patch 4.2: Replay bundle schema

- Files likely affected:
  - `backend/app/agent/state/models.py`
  - `backend/app/agent/state/persistence.py`
  - tests under `backend/app/agent/tests`
- Rationale: Make historical replay explicit.
- Invariant protected: 15.
- Test to add first: Persisted replay bundle can be verified offline.
- Expected behavior change: Additional snapshot metadata.
- Rollback strategy: Additive schema field ignored by old readers.
- Risk: Medium.

## Stage 5 - Concurrency Safety

Patch 5.1: Case number generation retry/sequence

- Files likely affected:
  - `backend/app/agent/state/persistence.py`
  - possibly migration files, but migrations require explicit separate approval
- Rationale: Count-based monthly numbers are race-prone.
- Invariant protected: 12.
- Test to add first: Concurrent same-month creates do not collide.
- Expected behavior change: Case number allocation becomes DB-owned or retry-safe.
- Rollback strategy: Keep current format and retry only on unique violation.
- Risk: Medium.

Patch 5.2: Turn-level idempotency key at mutation boundary

- Files likely affected:
  - `backend/app/services/case_service.py`
  - `backend/app/models/mutation_event_model.py`
  - tests
- Rationale: Re-running same turn should not duplicate mutation/outbox.
- Invariant protected: 11, 12.
- Test to add first: Same turn idempotency key creates one mutation.
- Expected behavior change: Duplicate requests become no-op/read-existing.
- Rollback strategy: Additive field first, enforce later.
- Risk: Medium/high, especially if migrations are needed.

## Stage 6 - Observability/Versioning

Patch 6.1: Version all deterministic rule components

- Files likely affected:
  - `backend/app/services/pre_gate_classifier.py`
  - `backend/app/agent/state/reducers.py`
  - `backend/app/agent/v92/final_guard.py`
  - `backend/app/agent/v92/calculator_registry.py`
- Rationale: Replay must know which rule versions ran.
- Invariant protected: 14, 15.
- Test to add first: Technical payload contains expected versions.
- Expected behavior change: More trace metadata.
- Rollback strategy: Additive metadata.
- Risk: Low.

Patch 6.2: Typed degraded-state outcomes

- Files likely affected:
  - `backend/app/agent/graph/nodes/evidence_node.py`
  - `backend/app/agent/graph/nodes/compute_node.py`
  - `backend/app/agent/v92/final_guard.py`
- Rationale: Fail-open boundaries need auditable state.
- Invariant protected: 7, 13.
- Test to add first: Forced compute/RAG errors produce explicit limitations.
- Expected behavior change: More cautious final answers on degraded paths.
- Rollback strategy: Keep old empty outputs behind compatibility flag.
- Risk: Medium.

## Stage 7 - Optimize After Correctness

Patch 7.1: Determinism-safe RAG cache

- Files likely affected:
  - `backend/app/agent/services/real_rag.py`
  - `backend/app/services/rag/rag_orchestrator.py`
- Rationale: Reduce repeated retrieval latency.
- Invariant protected: 9, 15.
- Test to add first: Cache key includes tenant/user/corpus/retriever config.
- Expected behavior change: Faster repeated knowledge/evidence turns.
- Rollback strategy: Disable cache by env flag.
- Risk: High if attempted before Stage 3/4.

Patch 7.2: Projection memoization within a turn

- Files likely affected:
  - `backend/app/agent/v92/runtime_contract.py`
  - `backend/app/agent/state/projections.py`
- Rationale: Avoid repeated projection work.
- Invariant protected: 14.
- Test to add first: Projection equality before/after memoization.
- Expected behavior change: Performance only.
- Rollback strategy: Remove memoization.
- Risk: Low/medium.

