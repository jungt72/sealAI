# Patch Plan: LangGraph v2 Redis + RAG

## Findings recap
- **SSE replay backend**: Code defaults to memory (`SEALAI_SSE_REPLAY_BACKEND` default `memory`), no env set in compose/.env; Redis replay keys (`sse:seq:*`, `sse:buf:*`) are absent. Backend logs did not show replay backend selection or Redis errors.
- **Checkpointer TTL gaps**: Redis shows `lg:cp:*` keys with TTL `-1` (no expiry) alongside keys with TTL. AsyncRedisSaver supports `ttl` parameter, but not all key families appear to receive EXPIRE.
- **Tenant identity mismatch**: v2 scoping uses `canonical_user_id` from JWT claim as `user_id`. RAG tenant filter and Redis scoping use `state.user_id` (no dedicated `tenant_id`). This violates the multi-tenant requirement that tenant_id is the source of truth.
- **Checkpoint TTL units**: AsyncRedisSaver expects `ttl` as a dict with `default_ttl` in **minutes** (see `/usr/local/lib/python3.11/site-packages/langgraph/checkpoint/redis/__init__.py` in backend container; signature `ttl: Optional[Dict[str, Any]]`).

## Proposed minimal patches

### 1) Add explicit tenant_id claim handling and propagate to scoping
- **Goal**: Use a dedicated `tenant_id` claim (from Keycloak JWT) for Redis and RAG scoping; keep user_id for per-user features only.
- **Files**:
  - `backend/app/services/auth/dependencies.py` (extract tenant_id claim)
  - `backend/app/api/v1/endpoints/langgraph_v2.py` (use tenant_id for Redis/SSE/checkpointer scoping + metadata)
  - `backend/app/langgraph_v2/state/sealai_state.py` (add tenant_id field)
  - `backend/app/langgraph_v2/nodes/*` (pass `tenant_id` to RAG tool instead of `user_id`)
  - `backend/app/langgraph_v2/utils/rag_tool.py` (accept tenant_id parameter name consistently)
- **Diff scope**: small, mostly variable plumbing (no structural changes).
- **Risk**: medium; requires claim availability and potential migration of existing data keyed by user_id.

### 2) Ensure checkpointer TTL applies to all key families when enabled
- **Goal**: Avoid TTL `-1` keys when `LANGGRAPH_CHECKPOINT_TTL` is configured; ensure checkpoint, checkpoint_write, and auxiliary keys expire.
- **Files**:
  - `backend/app/langgraph_v2/utils/checkpointer.py` (post-init wrapper or hook to ensure TTL on created key families; log warnings when TTL not supported)
- **Diff scope**: minimal; add TTL enforcement or fallback cleanup if saver does not apply TTL to all keys.
- **Risk**: low-medium; must avoid breaking AsyncRedisSaver behavior or performance.

### 3) Make SSE replay backend explicit + add runtime logging
- **Goal**: Declare replay backend in config (redis vs memory), log selected backend once, and validate Redis availability on startup.
- **Files**:
  - `backend/app/services/sse_broadcast.py` (log backend choice and Redis availability)
  - `docker-compose.yml` / `.env.*` (set `SEALAI_SSE_REPLAY_BACKEND=redis`, TTL/maxlen)
- **Diff scope**: minimal; mostly env + one log line.
- **Risk**: low; ensures expected replay behavior is visible and configurable.

## Tests to add/update (pytest)

1) **Checkpointer TTL enforcement**
- Add a test that uses a fake Redis or integration Redis to assert TTL is set (not `-1`) on each key family created by `AsyncRedisSaver` (`checkpoint`, `checkpoint_write`, `checkpoint_blob`, `checkpoint_latest` if present) when `LANGGRAPH_CHECKPOINT_TTL` is configured.
- Suggested location: `backend/app/langgraph_v2/tests/test_checkpointer_ttl_applied.py`.

2) **SSE replay backend selection + Redis key creation**
- Unit test to verify `SEALAI_SSE_REPLAY_BACKEND=redis` uses Redis backend (and `memory` when unset).
- Integration test (if Redis available) to create a replay event and assert `sse:seq:*` and `sse:buf:*` keys exist.
- Suggested location: `backend/app/services/tests/test_sse_replay_backend.py` (extend existing tests).

3) **Tenant scoping correctness**
- Test that tenant_id claim is extracted and used for RAG filters (metadata must include `tenant_id`).
- Test that Redis scoping uses tenant_id for dedup and replay keys (pattern includes tenant_id).
- Suggested locations: `backend/app/langgraph_v2/tests/test_auth_user_id_claim.py` and new `backend/app/langgraph_v2/tests/test_tenant_scoping.py`.

## How to verify

### Runtime
- Backend logs (replay backend selection):
  - `docker compose logs -n 200 backend | rg -n "sse_replay|backend_name|redis"`
- Redis keys (replay + dedup + checkpointer):
  - `docker compose exec -T redis /bin/sh -c 'redis-cli -a "$REDIS_PASSWORD" --scan --pattern "sse:seq:*" | head -n 50'`
  - `docker compose exec -T redis /bin/sh -c 'redis-cli -a "$REDIS_PASSWORD" --scan --pattern "sse:buf:*" | head -n 50'`
  - `docker compose exec -T redis /bin/sh -c 'redis-cli -a "$REDIS_PASSWORD" --scan --pattern "langgraph_v2:dedup:*" | head -n 50'`
  - `docker compose exec -T redis /bin/sh -c 'redis-cli -a "$REDIS_PASSWORD" --scan --pattern "lg:cp*" | head -n 100'`
- TTL sampling:
  - `docker compose exec -T redis /bin/sh -c 'for k in $(redis-cli -a "$REDIS_PASSWORD" --scan --pattern "lg:cp*" | head -n 10); do echo "KEY $k"; redis-cli -a "$REDIS_PASSWORD" TTL "$k"; redis-cli -a "$REDIS_PASSWORD" TYPE "$k"; done'`

### Smoke (requires token)
- `ACCESS_TOKEN='…' BASE_URL='http://localhost:3000' ops/smoke_chat_v2_sse.sh`
- Then rescan `sse:seq:*` and `sse:buf:*` keys.

### SSE replay env (recommended)
- `SEALAI_SSE_REPLAY_BACKEND=redis`
- `SEALAI_SSE_REPLAY_TTL_SEC=3600`
- `SEALAI_SSE_REPLAY_MAXLEN=500`
- **Operational effect**: enables Redis-backed SSE replay (`sse:seq:*`, `sse:buf:*` keys) instead of in-memory replay; memory remains the default when unset.

### Tests
- `pytest -q`

## TTL verification evidence (runtime)
- `langgraph` version: `None` (no `__version__` attribute in module).
- AsyncRedisSaver module: `/usr/local/lib/python3.11/site-packages/langgraph/checkpoint/redis/__init__.py`
- AsyncRedisSaver signature: `ttl: Optional[Dict[str, Any]]` with checkpoint prefixes as kwargs.
- Redis TTL sampling (current runtime, pre-redeploy): `lg:cp:*` contains `checkpoint_write` keys with `TTL=-1` (no expiry) and others with `TTL>0`.
- Key family with TTL=-1 observed: `lg:cp:consult.v1:checkpoint_write:*` (examples in Redis scan output).

## If TTL -1 persists after redeploy
- **Minimal corrective diff** (proposal only): set `refresh_on_read=True` in ttl config to allow TTL refresh on reads and add a best-effort warning when `ttl_config` is missing or `default_ttl` is not applied.
- **Operational check**: after redeploy and a new checkpoint write, rescan `lg:cp:*` and verify TTL > 0 for newly created keys.
