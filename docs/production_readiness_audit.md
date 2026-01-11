# Production readiness audit (baseline)

Date: 2025-02-14
Scope: LangGraph v2 + Redis + Qdrant RAG + SSE + Keycloak. Baseline read-only audit.

## Operational surface (observed)
- Backend health endpoints: `/healthz`, `/readyz`, `/api/v1/ping`, `/api/v1/langgraph/health` (app + langgraph v2).
- SSE endpoints: `/api/v1/langgraph/...` (LangGraph v2 HTTP/SSE handlers).
- Keycloak: metrics enabled (`KC_METRICS_ENABLED=true`) and health enabled.
- Redis: `redis-stack-server` with password, AOF + RDB configured.
- Qdrant: storage volume configured.
- Telemetry module present: `backend/app/common/telemetry.py` (OTel + LangSmith optional).

## Runtime packages (backend container)
- Python: 3.11.14
- Imports: `langgraph`, `redis`, `qdrant_client` available.

## Persistence settings (docker-compose.yml)
- Redis: AOF enabled, RDB saves at 900/300/60 seconds, maxmemory=512mb, `allkeys-lru`, data volume `redis-data`.
- Qdrant: persistent storage volume `qdrant_storage` mounted to `/qdrant/storage`.
- Backend: no persistent DB for runtime state other than Redis/Qdrant; local volume `./data/backend:/app/data`.

## Observability
Findings:
- Structured logging configured via `structlog` (JSON renderer) in `backend/app/core/config.py`.
- Healthchecks configured for postgres, redis, backend, frontend, nginx in `docker-compose.yml`.
- OTel auto-instrumentation hook exists (`backend/app/common/telemetry.py`) gated by `ENABLE_OTEL` and LangSmith settings.

Gaps:
- No `/metrics` endpoint in backend for Prometheus scraping.
- No request correlation middleware; `X-Request-Id` is not consistently set or logged.
- SSE logs do not consistently include `tenant_id/user_id/chat_id/request_id` context.
- OTel exporter configuration and enablement are not documented in repo docs.

## Resilience (timeouts/retries/circuit breakers)
Findings:
- Qdrant RAG retrieval uses httpx with a timeout (`QDRANT_TIMEOUT_S`) and basic retry loop in `backend/app/services/rag/rag_orchestrator.py`.
- Redis client helper exists with socket timeouts and max connections in `backend/app/services/redis_client.py`.

Gaps:
- No centralized client factories for Redis/Qdrant/httpx to enforce consistent timeouts/retries across the app.
- No explicit circuit breaker or backoff strategy outside the RAG orchestrator.
- OpenAI/httpx calls (outside RAG) are not consistently wrapped with timeouts in a shared layer.

## Data safety (tenant isolation, PII, prompt injection)
Findings:
- Qdrant collection naming can be tenant-aware via `QDRANT_COLLECTION_PREFIX` (`qdrant_collection_name`).
- SSE replay has Redis backend option; default is in-memory.
- Deterministic RAG context sanitization (limits, injection/secret scrubbing) is implemented in `backend/app/services/rag/rag_safety.py`.

Gaps:
- Tenant isolation relies on optional collection prefix; if unset, tenants share base collection.

## Ops (backups, retention/TTL, resource limits)
Findings:
- Redis has AOF + RDB configured; volumes are present for Redis and Qdrant.
- Backend has healthcheck for `/api/v1/langgraph/health`.

Gaps:
- No documented backup/restore runbook for Redis AOF/RDB or Qdrant snapshots.
- Resource limits (cpu/mem) not defined in compose.
- TTLs for LangGraph checkpoints and SSE replay are configurable but not enforced by default (depends on env like `LANGGRAPH_CHECKPOINT_TTL`, `SEALAI_SSE_REPLAY_TTL_SEC`).
- No explicit retention policy documentation for Redis keys or Qdrant collections.

## Notes for next phase
- Add request correlation + structured log context, /metrics endpoint, optional OTEL enablement.
- Consolidate Redis/Qdrant/httpx timeout and retry behavior.
- Add RAG context sanitization (PII/secret patterns, max size, prompt injection guardrails).
- Document ops runbook (backup, restore, monitoring, TTL checks).
