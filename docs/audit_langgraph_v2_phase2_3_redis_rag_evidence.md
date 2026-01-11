# LangGraph v2 Redis + RAG Evidence (Phase 2/3)

## 1) Redis key patterns observed (no values)

### Keyspace summary (db0)
- `db0:keys=1802,expires=669,avg_ttl=90557720` (from `INFO keyspace`)

### SSE replay keys
- `sse:seq:*` scan: no keys returned (Redis scan output empty).
- `sse:buf:*` scan: no keys returned (Redis scan output empty).

### Dedup keys
- Example key:
  - `langgraph_v2:dedup:<user_id>:<chat_id>:<client_msg_id>`
- TTL/TYPE sample:
  - TTL: `510` seconds, TYPE: `string`.

### Checkpointer keys
- Example keys:
  - `lg:cp:consult.v1:checkpoint_write:<user_id>:thread-<chat_id>:__empty__:<run_id>:<checkpoint_id>:<seq>`
  - `lg:cp:consult.v1:checkpoint:<user_id>:thread-<chat_id>:__empty__:<run_id>`
  - `checkpoint_latest:<user_id>:thread-<chat_id>:__empty__`
- TTL/TYPE samples (first 5 keys scanned):
  - TTL: `27165`, TYPE: `ReJSON-RL`
  - TTL: `-1`, TYPE: `ReJSON-RL`
  - TTL: `27197`, TYPE: `ReJSON-RL`
  - TTL: `21550`, TYPE: `ReJSON-RL`
  - TTL: `-1`, TYPE: `ReJSON-RL`

Notes:
- `-1` indicates no expiry set on some checkpointer keys.
- Observed namespace fragment in key is `consult.v1` (not the default `sealai:v2:`).

## 2) Checkpointer key format conclusion

**Composition inferred from key pattern (Redis evidence):**
- Prefix: `lg:cp` (from `LANGGRAPH_CHECKPOINT_PREFIX`, default in `backend/app/langgraph_v2/utils/checkpointer.py`).
- Namespace appears embedded immediately after prefix: `lg:cp:<namespace>` (observed `consult.v1`).
- User-scoped component appears next: `<user_id>`.
- Thread-scoped component: `thread-<chat_id>` or `default`.
- Additional internal segments: `__empty__`, run/checkpoint identifiers, and a sequence counter for write buffers.

**Code corroboration:**
- Prefix + namespace assembly in `backend/app/langgraph_v2/utils/checkpointer.py` and `backend/app/langgraph_v2/constants.py`.
- `build_v2_config` provides `configurable.user_id` and `thread_id` in `backend/app/langgraph_v2/sealai_graph_v2.py`.

**Conclusion:**
- Keys are explicitly user_id + thread_id scoped, but **tenant_id is not explicit** in key names; isolation is tied to `configurable.user_id`.
- Observed namespace `consult.v1` may indicate mixed checkpointers in the same Redis instance (needs confirmation of namespace configuration).

## 3) RAG tenant filter verification (code path)

**Tenant path and filter usage:**
- `backend/app/langgraph_v2/nodes/nodes_knowledge.py` + `backend/app/langgraph_v2/nodes/nodes_flows.py` call `search_knowledge_base` with `tenant=state.user_id`.
- `backend/app/langgraph_v2/utils/rag_tool.py`:
  - Requires `tenant` (throws if missing).
  - Forces `metadata_filters = {"tenant_id": tenant}` (plus optional category).
- `backend/app/services/rag/rag_orchestrator.py`:
  - Uses `_collection_for_tenant(tenant)` (collection naming optionally tenant-aware).
  - Builds Qdrant filter: `filter.must` with `key == tenant_id` for all `metadata_filters` entries.

**Conclusion:**
- For v2 RAG tool usage, Qdrant filter.must always includes `tenant_id == tenant`, because the tool enforces `tenant` and injects `metadata_filters`.
- Collection naming is tenant-aware only when `QDRANT_COLLECTION_PREFIX` is set; otherwise `qdrant_collection_name` returns the base collection even if tenant is provided.

## 4) Risks (tenant_id vs user_id mismatch)

### P1
- **Tenant identity is tied to `user_id` claim rather than a dedicated `tenant_id`.**
  - Evidence: `backend/app/services/auth/dependencies.py` resolves `user_id` from JWT claim and `canonical_user_id` is used for scoping in `backend/app/api/v1/endpoints/langgraph_v2.py`.
  - RAG uses `tenant=state.user_id`, not an explicit `tenant_id` claim (`backend/app/langgraph_v2/utils/rag_tool.py`, `backend/app/langgraph_v2/nodes/nodes_knowledge.py`).
  - Redis keys (dedup + replay + checkpointer) use `user_id` in key path (e.g., `langgraph_v2:dedup:<user_id>...`, `lg:cp:...:<user_id>:thread-...`).

### P2
- **Some checkpointer keys have no TTL (TTL = -1).**
  - Evidence: Redis TTL samples for `lg:cp:*` include `-1`.
  - Risk: unbounded checkpoint growth if `LANGGRAPH_CHECKPOINT_TTL` is not configured or unsupported by saver signature.

### P2
- **SSE replay keys not found (`sse:seq:*`, `sse:buf:*` empty).**
  - Evidence: Redis scan returned no keys, implying either replay backend is memory or inactive.
  - Risk: replay might be unavailable in Redis (if expected) or relies on in-memory buffers only.

