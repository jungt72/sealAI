# Phase 7 - Optimization Analysis

Correctness priority: no optimization should precede canonicalization, replay tests, and deterministic sorting fixes.

## Observed Bottleneck Classes

Verified facts:

- RAG retrieval embeds queries, may call Qdrant, BM25, and a cross-encoder reranker. Evidence: `backend/app/services/rag/rag_orchestrator.py:840-1024`.
- RAG retry backoff includes random jitter. Evidence: `backend/app/services/rag/rag_orchestrator.py:420-423`.
- Knowledge/RAG uses singleton and module-global caches for factcards, embedders, sparse embedder, and reranker. Evidence: `backend/app/services/knowledge/factcard_store.py:89-100`, `backend/app/services/rag/rag_orchestrator.py:96-103`.
- Snapshot persistence compares full `state_json`. Evidence: `backend/app/services/case_service.py:256-263`.
- Frontend BFF synthesizes final answer token streaming with sleeps. Evidence: `frontend/src/app/api/bff/agent/chat/stream/route.ts:19-20`, `frontend/src/app/api/bff/agent/chat/stream/route.ts:86-103`.

## Optimization Ideas

### O-001 - Canonical payload builder before hash and snapshot comparison

Safe for determinism: Yes, if it is additive first and protected by golden tests.

Invariant protected: Invariants 1, 2, 3, 10, 15.

Required tests before implementation:

- Golden canonical JSON fixture.
- Volatile field exclusion test.
- Equivalent fresh-state idempotency test.

Impact: High.

Risk: Medium. It can change snapshot dedupe behavior, so stage behind tests and compare old/new hash in metadata initially.

### O-002 - Stable sorted reducer iteration

Safe for determinism: Yes.

Invariant protected: Invariant 6.

Required tests:

- `PYTHONHASHSEED` subprocess test.
- Existing reducer conflict tests.

Impact: Medium.

Risk: Low. It may alter display/order of parameters but should not alter semantics.

### O-003 - Stable tie-breakers in RAG/BM25/FactCard ranking

Safe for determinism: Yes, provided existing top-score behavior is preserved as primary key.

Invariant protected: Invariants 6 and 9.

Required tests:

- Equal-score hit ordering with shuffled inputs.
- Golden material answer sources.

Impact: Medium.

Risk: Medium. Top-k documents can change when scores tie.

### O-004 - Cache deterministic RAG query results by canonical query + tenant + corpus version

Safe for determinism: Conditionally. Cache key must include tenant, user visibility, retriever config, embedding/rerank model ids, corpus/source versions, and top-k.

Invariant protected: Invariants 9 and 15.

Required tests:

- Cache hit returns byte-identical evidence cards.
- Corpus version change invalidates cache.
- Tenant/private visibility cannot cross-contaminate.

Impact: High for latency.

Risk: High if cache key is incomplete.

### O-005 - Avoid repeated full dashboard/projection builds in one turn

Safe for determinism: Yes, if projection input state and projection version are explicit.

Invariant protected: Invariant 14.

Required tests:

- Projection equality before/after memoization.
- Guard still receives current dashboard projection.

Impact: Medium.

Risk: Medium. Stale projection would be dangerous.

### O-006 - Full digest for sealed artifacts and short display hash separately

Safe for determinism: Yes.

Invariant protected: Invariants 2, 3, 15.

Required tests:

- Full digest remains stable.
- Display hash derives from full digest.

Impact: Low for runtime, high for auditability.

Risk: Low, if additive.

### O-007 - Canonical numeric formatting at calculation output boundary

Safe for determinism: Yes, if done at serialization/hash boundary rather than changing internal formulas.

Invariant protected: Invariants 1, 2, 15.

Required tests:

- Golden numeric fixtures.
- Rounding policy documented and versioned.

Impact: Medium.

Risk: Medium. Visible numbers may change slightly if rounding policy differs.

### O-008 - Replace full `state_json` idempotency comparison with canonical snapshot comparison

Safe for determinism: Yes after characterization.

Invariant protected: Invariants 10 and 11.

Required tests:

- Same semantic fresh state saves once.
- Trace-only changes do not create snapshot.
- Actual engineering fact changes create snapshot.

Impact: High for database churn.

Risk: Medium/high. Must not suppress meaningful audit changes.

### O-009 - Batch source-version extraction and evidence claim construction

Safe for determinism: Yes, if card ordering is stable first.

Invariant protected: Invariant 9.

Required tests:

- Same cards in same canonical order produce same evidence state.

Impact: Low/medium.

Risk: Low after RAG tie-breakers.

### O-010 - Remove synthetic frontend delay for final answer chunks in test/replay mode

Safe for determinism: Yes for replay/test mode only. User-facing UX may rely on streaming feel.

Invariant protected: Not a core engineering invariant; improves test determinism.

Required tests:

- BFF still streams final answer only.
- UI finalizes once.

Impact: Low.

Risk: Low.

## What Not To Optimize Yet

- Do not memoize governed graph outputs before deterministic canonicalization exists.
- Do not cache LLM extraction/semantic router results without prompt/model/raw-response snapshots.
- Do not broaden RAG cache without tenant/user/corpus/version keys.
- Do not remove fail-open behavior before guard-visible degraded states are designed.
- Do not collapse state slices to reduce snapshot size until replay bundle semantics are defined.

