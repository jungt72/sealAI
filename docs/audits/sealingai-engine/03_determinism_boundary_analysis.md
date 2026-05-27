# Phase 3 - Determinism Boundary Analysis

Classification key:

- A. Pure deterministic core
- B. Controlled deterministic dependency
- C. Nondeterministic boundary
- D. Unknown / not proven

## A. Pure Deterministic Core

### PreGateClassifier rule path

File and line evidence: `backend/app/services/pre_gate_classifier.py:23-31`, `backend/app/services/pre_gate_classifier.py:41-168`.

Why: Classification is regex/rule order only for fixed code and input.

How determinism can fail: Rule changes are not versioned in output; overlapping regexes mean rule order is semantically significant.

How to make stronger: Emit classifier version and matched rule id into turn metadata.

Test needed: Golden route matrix with classifier version and exact rule ids.

### TurnBoundaryOrchestrator

File and line evidence: `backend/app/agent/v92/turn_boundary.py:190-298`.

Why: Uses fixed regexes, hints, and state presence to produce route/policy.

How determinism can fail: Upstream hints may be LLM-derived; state presence depends on persistence.

How to make stronger: Include route inputs and boundary version in replay bundle.

Test needed: Same message/state/hints across N runs returns identical `TurnBoundaryDecision`.

### Calculation services

File and line evidence:

- `backend/app/services/calculation_engine.py:49-92`, `backend/app/services/calculation_engine.py:124-201`
- `backend/app/agent/domain/rwdr_calc.py:149-315`
- `backend/app/mcp/calculations/material_limits.py:225-244`
- `backend/app/mcp/calculations/chemical_resistance.py:245-...`

Why: Static tables and math formulas; no DB, network, time, random, or LLM found in these paths.

How determinism can fail: Floating-point exactness and output serialization are not centrally canonicalized.

How to make stronger: Use canonical numeric formatting/rounding at output/hash boundaries.

Test needed: Golden fixtures for all formula outputs and serialized calculator hashes.

### Matching sort after candidate scoring

File and line evidence: `backend/app/agent/graph/nodes/matching_node.py:235-289`; explicit sort at `272-278`.

Why: Sort key includes deterministic tie-breakers: negative score, manufacturer name, candidate id.

How determinism can fail: Provider data may be mutable or unordered before scoring.

How to make stronger: Version and snapshot provider data used for matching.

Test needed: Tied score candidates sort identically regardless of provider input order.

### Final guard rule engine

File and line evidence: `backend/app/agent/v92/final_guard.py:17-78`, `backend/app/agent/v92/final_guard.py:90-228`.

Why: Regex and context checks only.

How determinism can fail: Context can include nondeterministic state; regex changes are not separately versioned.

How to make stronger: Add guard ruleset version to `FinalGuardResult`.

Test needed: Golden forbidden-claim fixtures with exact blocked reasons.

## B. Controlled Deterministic Dependencies

### Decision basis hash

File and line evidence: `backend/app/agent/state/persistence.py:80-95`.

Why: Uses sorted JSON and SHA-256 for explicit state slices.

How determinism can fail:

- Included normalized state can contain wall-clock `normalized_at` from `backend/app/agent/domain/normalization.py:713`.
- List order inside normalized/conflicts/assumptions is not sorted by the hash function.
- Hash truncates SHA-256 to 16 hex chars.
- Hash omits model version, calculator versions, reducer/schema versions, and graph/runtime version.

How to make deterministic or bounded: Create a canonical decision payload that strips volatile metadata, sorts all lists by stable keys, includes schema/engine/calculator versions, and uses full or longer digest.

Test needed: Same semantic input normalized at two frozen timestamps yields same canonical hash; changed material/pressure/calculator version yields different hash.

### V9.2 calculator registry hashes

File and line evidence: `backend/app/agent/v92/calculator_registry.py:53-55`, `backend/app/agent/v92/calculator_registry.py:80-148`.

Why: Hashes sorted JSON snapshots and fixed calculator ids.

How determinism can fail: `default=str` can mask noncanonical object formatting; 16-char digest prefix reduces collision margin.

How to make deterministic or bounded: Reject non-JSON primitives before hashing and extend digest length.

Test needed: Hash rejects datetime/object inputs unless explicitly canonicalized.

### Prompt/model registry

File and line evidence: `backend/app/llm/registry.py:14-53`, `backend/app/llm/registry.py:59-82`.

Why: Role defaults are central and env-overridable.

How determinism can fail: Environment variable changes alter model ids without state/replay bundle necessarily recording them.

How to make deterministic or bounded: Record resolved model id and prompt hash in every LLM-derived observation/answer trace.

Test needed: Env override changes trace metadata and replay bundle, not silently.

### KnowledgeContextBuilder

File and line evidence: `backend/app/agent/communication/knowledge_context_builder.py:121-169`, `backend/app/agent/communication/knowledge_context_builder.py:171-248`.

Why: Truncates history/evidence with explicit limits and ordering.

How determinism can fail: Input history order comes from frontend/session persistence; evidence order can come from RAG.

How to make deterministic or bounded: Include history snapshot ids and evidence source ids in context trace.

Test needed: Same history/evidence tuples build byte-identical context dicts.

## C. Nondeterministic Boundaries

### Wall-clock timestamp in critical normalization

File and line evidence: `backend/app/agent/domain/normalization.py:704-714`, especially `713`.

Why: `normalized_at=datetime.now(timezone.utc).isoformat()` is written into `CriticalFieldNormalization`.

How it can fail determinism: Same raw critical input produces different `engineering_value.normalized_at`; normalized state is part of `compute_decision_basis_hash` at `backend/app/agent/state/persistence.py:83-85`. Therefore identical semantic input can produce different decision hashes and snapshots.

How to make deterministic or bounded: Inject timestamp from turn envelope or remove `normalized_at` from canonical decision basis.

Test needed: Normalize the same critical field twice with unfrozen time and assert canonical hash stays equal after volatile metadata is stripped.

### Set iteration in reducer

File and line evidence: `backend/app/agent/state/reducers.py:652-655`.

Why: `all_fields = set(...)` is iterated directly.

How it can fail determinism: Python set iteration order can vary across processes/hash seeds. This can change order of `parameters`, `conflicts`, `assumptions`, and downstream list serialization.

How to make deterministic or bounded: Iterate `for field_name in sorted(all_fields)`.

Test needed: Run reducer in subprocesses with different `PYTHONHASHSEED` and assert serialized normalized state is identical.

### LLM extraction in governed graph

File and line evidence: `backend/app/agent/graph/nodes/intake_observe_node.py:27-30`, `backend/app/agent/graph/nodes/intake_observe_node.py:59-61`, `backend/app/agent/graph/nodes/intake_observe_node.py:417-493`, `backend/app/agent/graph/nodes/intake_observe_node.py:594-623`.

Why: LLM extraction is enabled by default and writes observations.

How it can fail determinism: Model output can change with model version, backend provider behavior, prompt changes, or transient errors. Fail-open path returns regex-only state.

How to make deterministic or bounded: Treat LLM extraction as observed evidence with full prompt/model/version/raw-response snapshot; deterministic core should be replayed from stored observations.

Test needed: Replay from stored `ObservedState` with LLM disabled produces same normalized/asserted/decision output.

### Semantic intent router

File and line evidence: `backend/app/services/semantic_intent_router.py:134-161`, `backend/app/services/semantic_intent_router.py:227-256`.

Why: Optional LLM may override deterministic classification.

How it can fail determinism: Same message can become knowledge or case intake depending on LLM output.

How to make deterministic or bounded: Store semantic router decision, prompt hash, model id, and raw JSON result; replay should use stored decision or deterministic-only mode.

Test needed: Stored semantic decision replay bypasses LLM and reproduces route.

### RAG retrieval and evidence promotion

File and line evidence:

- RAG bridge: `backend/app/agent/evidence/retrieval.py:9-22`
- Real RAG cascade: `backend/app/agent/services/real_rag.py:54-87`, `backend/app/agent/services/real_rag.py:91-229`
- Evidence promotion: `backend/app/agent/graph/nodes/evidence_node.py:338-349`

Why: Qdrant/BM25/cross-encoder retrieval depends on external mutable indexes, model caches, scores, and failure modes.

How it can fail determinism: Different evidence cards or order can promote or not promote assertions, changing governance/output.

How to make deterministic or bounded: Snapshot evidence card ids, source versions, scores, rank order, retriever config, and corpus version into replay basis.

Test needed: Replay with stored evidence cards produces same asserted/governance state with live RAG disabled.

### RAG ranking without stable tie-breakers

File and line evidence:

- RRF sort only by score: `backend/app/services/rag/rag_orchestrator.py:384-403`
- Rerank sort only by score: `backend/app/services/rag/rag_orchestrator.py:827-835`
- BM25 fallback sort only by score: `backend/app/services/rag/bm25_store.py:193-196`, `backend/app/services/rag/bm25_store.py:255-257`
- FactCard sort only by score: `backend/app/services/knowledge/factcard_store.py:217-244`

Why: Equal scores preserve input/insertion order, which can be external or process-dependent.

How it can fail determinism: Ties can reorder evidence/snippets and alter selected cards or answer wording.

How to make deterministic or bounded: Add stable tie-breakers: source id, doc id, chunk index, card id.

Test needed: Equal-score hits from shuffled input always yield same order.

### Random ids and timestamps in envelopes/state/events

File and line evidence:

- `_new_idempotency_key`: `backend/app/agent/state/models.py:73-78`
- `ActionReadinessState.idempotency_key`: `backend/app/agent/state/models.py:830-839`
- `CaseEvent.event_id`: `backend/app/agent/state/models.py:1139-1143`
- Turn id and timestamp: `backend/app/agent/v92/runtime_contract.py:197-234`
- Mutation/outbox UUIDs: `backend/app/services/case_service.py:420-421`, `backend/app/services/case_service.py:493-495`
- Frontend no-case id fallback: `frontend/src/hooks/useAgentStream.ts:171-178`

Why: Uses ULID/UUID/time/random.

How it can fail determinism: Full state JSON equality and replay payloads differ run to run.

How to make deterministic or bounded: Separate trace/transport ids from canonical decision payload; inject ids in tests; store generated ids explicitly.

Test needed: Canonical replay hash excludes trace ids; full snapshot idempotency does not depend on fresh random defaults.

### Case number generation

File and line evidence: `backend/app/agent/state/persistence.py:719-735`.

Why: Uses `date.today()` and count of existing monthly cases.

How it can fail determinism: Same session/input on different dates gets different case number; concurrent creates can race to same `NNN`.

How to make deterministic or bounded: Derive one session-bound case id first; generate human case numbers inside DB sequence/unique retry loop.

Test needed: Concurrent `get_or_create_case` for same session results in one case; monthly number collision retries deterministically.

### LangGraph checkpointer fallback

File and line evidence: `backend/app/agent/graph/topology.py:189-240`.

Why: Redis checkpointer failure falls back to in-memory.

How it can fail determinism/replayability: Same deployment config but transient Redis failure changes durability and resume behavior.

How to make deterministic or bounded: Production should fail closed or explicitly mark degraded replayability in run metadata.

Test needed: Redis unavailable in production mode yields explicit degraded status or failure, not silent in-memory replay.

### Optional LLM answer/reviewer layers

File and line evidence:

- Governed answer composer allowed by topology invariant: `backend/app/agent/graph/topology.py:55-59`
- Async adversarial reviewer flag: `backend/app/agent/v92/runtime_contract.py:544-670`
- Knowledge LLM fallback: `backend/app/services/knowledge_service.py:450-501`

Why: LLM text/review/fallback can alter visible answer and guard path.

How it can fail determinism: Same deterministic state can produce different answer text/revision unless prompt/model/output are snapshotted.

How to make deterministic or bounded: Treat visible answer generation as nondeterministic boundary; persist prompt trace, model id, rendered prompt hash, raw LLM output.

Test needed: Final guard replay from stored answer text/context requires no LLM and reproduces final guard result.

## D. Unknown / Not Proven

### Full replay from raw chat input

Evidence: There are unit tests for hash, normalization, compute, guard, snapshots, and stream masking. No single test was found that runs the same raw chat input N times across isolated processes with LLM/RAG disabled and asserts byte-identical canonical output.

How it can fail: Any timestamp, random default, set ordering, cache state, or mutable provider can break replay.

Required proof: Golden replay harness from raw message to canonical decision payload.

### Stable seal/signature generation

Evidence: Decision basis hash exists at `backend/app/agent/state/persistence.py:80-95`; no cryptographic signing or separately named "seal signature" path was found.

How it can fail: There may be no actual signed seal to verify.

Required proof: Define what "sealed output" means: decision basis hash, RFQ dossier hash, snapshot hash, or another artifact.

### Cross-process/cross-runtime deterministic serialization

Evidence: Hash functions sort dict keys, but list ordering and volatile fields remain. `model_dump_json()` for Redis at `backend/app/agent/state/persistence.py:280-281` does not use sorted keys.

How it can fail: Same state serialized by different Pydantic/Python versions can differ unless canonical payload is explicit.

Required proof: Canonical JSON serializer contract and golden output fixtures.

