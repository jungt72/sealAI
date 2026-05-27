# Phase 5 - Existing Test and Coverage Audit

## Tests Run During Audit

Backend focused deterministic/guard suite:

```bash
PYTHONPATH=backend SEALAI_ENABLE_LLM_EXTRACTION=false .venv/bin/python -m pytest -q \
  backend/app/agent/tests/test_decision_basis_hash.py \
  backend/app/agent/tests/test_normalization.py \
  backend/app/agent/tests/test_conflict_detection_reducer.py \
  backend/app/agent/tests/test_calculation_state_ledger.py \
  backend/app/agent/tests/graph/test_compute_node.py \
  backend/app/agent/tests/v92/test_v92_runtime_contracts.py \
  backend/app/agent/tests/v92/test_turn_boundary.py \
  backend/app/agent/tests/test_governed_runtime_seam.py
```

Result:

```text
........................................................................ [ 34%]
........................................................................ [ 69%]
................................................................         [100%]
```

Backend Postgres snapshot/persistence suite:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_postgres_state_snapshots.py
```

Result:

```text
......................................                                   [100%]
```

Frontend stream contract suite:

```bash
npm --prefix frontend run test:run -- \
  src/hooks/useAgentStream.test.tsx \
  src/app/api/bff/agent/chat/stream/route.spec.ts \
  src/lib/streamWorkspace.test.ts
```

Result:

```text
Test Files  2 passed (2)
Tests  28 passed (28)
```

Note: Vitest reported 2 files, not 3, for the requested file list. This should be checked separately if `src/lib/streamWorkspace.test.ts` is expected to be included by the current Vitest config.

No external API calls, migrations, deployments, package installs, or production data mutations were run.

## Coverage Found

### Hash tests

Files:

- `backend/app/agent/tests/test_decision_basis_hash.py`

Evidence:

- Same state object same hash: `backend/app/agent/tests/test_decision_basis_hash.py:32-40`.
- Normalized changes alter hash: `backend/app/agent/tests/test_decision_basis_hash.py:43-63`.
- Derived changes alter hash: `backend/app/agent/tests/test_decision_basis_hash.py:66-70`.
- Evidence source version changes alter hash: `backend/app/agent/tests/test_decision_basis_hash.py:73-79`.
- Some artifacts outside hash basis do not alter hash: `backend/app/agent/tests/test_decision_basis_hash.py:82-92`.

Gap:

- Does not prove equivalent canonical input across two independently constructed states.
- Does not cover `normalized_at`.
- Does not test list ordering, Python hash seed, or full canonical JSON.

### Normalization tests

Files:

- `backend/app/agent/tests/test_normalization.py`

Evidence:

- Temperature conversion and passthrough: `backend/app/agent/tests/test_normalization.py:99-147`.
- Pressure conversion and passthrough: `backend/app/agent/tests/test_normalization.py:154-197`.
- Critical field contract begins at `backend/app/agent/tests/test_normalization.py:199-240`.

Gap:

- No test asserts `normalized_at` exclusion or injection.
- No property/metamorphic test over equivalent forms.
- No cross-process serialization/hash replay test.

### Reducer/conflict tests

Files:

- `backend/app/agent/tests/test_conflict_detection_reducer.py`
- `backend/app/agent/tests/test_calculation_state_ledger.py`

Evidence:

- Tolerance-aware conflict handling: `backend/app/agent/tests/test_conflict_detection_reducer.py:5-17`.
- Real conflict for medium: `backend/app/agent/tests/test_conflict_detection_reducer.py:20-32`.
- User-stated RWDR inputs reach asserted state and calculation ledger: `backend/app/agent/tests/test_calculation_state_ledger.py:38-68`.

Gap:

- No test for set iteration order at `backend/app/agent/state/reducers.py:652-655`.
- No tie-breaker test for same confidence and same turn index.
- No evidence tie-breaker test in `reduce_normalized_to_asserted`.

### Calculation tests

Files:

- `backend/app/agent/tests/graph/test_compute_node.py`
- `backend/app/agent/tests/test_calculation_state_ledger.py`

Evidence:

- Compute node invariants are documented in test header: `backend/app/agent/tests/graph/test_compute_node.py:1-31`.
- DIN 3760 surface speed reference test: `backend/app/agent/tests/graph/test_compute_node.py:190-200`.
- Optional fields forwarded: `backend/app/agent/tests/graph/test_compute_node.py:214-220`.

Gap:

- No golden master for all formulas and serialized calculator result hashes.
- No cross-runtime numeric canonicalization test.
- Fail-open calculation error is accepted behavior but not audited as final-answer limitation.

### Final guard and streaming tests

Files:

- `backend/app/agent/tests/v92/test_v92_runtime_contracts.py`
- `backend/app/agent/tests/test_governed_runtime_seam.py`
- `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts`

Evidence:

- Technical direct streaming rejected: `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:34-52`.
- Final guard blocks unscoped suitability, product claims, norm conformity, placeholders: `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:55-139`.
- Stale calculation usage revised: `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:142-165`.
- SSE masks native technical answer chunks until guarded final: `backend/app/agent/tests/test_governed_runtime_seam.py:230-350`.
- BFF drops legacy preview chunks and streams only final answer: `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts:80-120`.
- BFF forwards V9.2 turn/guard/dashboard contracts: `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts:652-730`.

Gap:

- Guard tests are phrasing fixtures, not property tests.
- No final guard replay test from persisted final context.
- Optional LLM adversarial reviewer is not proven deterministic; it is intentionally boundary behavior.

### Snapshot/idempotency tests

Files:

- `backend/app/agent/tests/test_postgres_state_snapshots.py`
- `backend/tests/unit/services/test_case_service.py`

Evidence:

- Snapshot creation and version fields: `backend/app/agent/tests/test_postgres_state_snapshots.py:520-551`.
- Same state object is idempotent: `backend/app/agent/tests/test_postgres_state_snapshots.py:554-578`.
- Snapshot revision advances on changed state: `backend/app/agent/tests/test_postgres_state_snapshots.py:581-599`.
- Snapshot read latest revision: `backend/app/agent/tests/test_postgres_state_snapshots.py:925-960`.
- Case mutation expected revision and transaction path: `backend/tests/unit/services/test_case_service.py:412-433`.
- Invalid delta contracts rejected: `backend/tests/unit/services/test_case_service.py:501-740`.

Gap:

- Idempotency test uses the same state object; it does not cover two semantically identical fresh states with different random/time defaults.
- No real concurrent create/write test for `get_or_create_case`.
- No DB unique-collision retry test for monthly case number.

### Legacy/adjacent concurrency tests

Files:

- `backend/tests/agent/test_concurrency.py`

Evidence:

- Detects concurrency conflict in `save_structured_case`: `backend/tests/agent/test_concurrency.py:52-81`.
- Tests token extraction and parity: `backend/tests/agent/test_concurrency.py:84-218`.

Gap:

- This appears to target a legacy history persistence path, not the current governed `CaseService` snapshot path.

## Missing Test Types

Priority P0/P1:

1. Golden replay test from stored `ObservedState` and evidence snapshots to canonical decision output.
2. Hash canonicalization test proving `normalized_at`, UUIDs, turn ids, and timestamps do not affect canonical digest.
3. Reducer order test across subprocesses with different `PYTHONHASHSEED`.
4. Deterministic sorting/tie-breaker tests for RAG, FactCard, BM25, evidence claims.
5. Idempotency test using independently constructed but semantically identical states.
6. Concurrent case creation/write test for same session/case number.
7. RAG/LLM boundary replay tests where stored boundary outputs are replayed with external calls disabled.
8. Property/metamorphic normalization tests for units, decimal separators, casing, whitespace, synonyms.
9. Final guard replay test from persisted `FinalAnswerContext` and visible answer.
10. Full sealed artifact verification test once "seal" is formally defined.

## Current Trust Assessment

- Deterministic calculations: reasonably covered for core RWDR paths, but not all formulas and hashes.
- Final guard and SSE masking: well covered for representative cases.
- Hash stability: under-covered and currently unsafe due timestamp inclusion.
- Replayability: not proven.
- Idempotency: partially proven for same object, not for semantic reruns.
- Concurrency: mutation path has useful tests; case creation and snapshot dedupe under real concurrency are not proven.

