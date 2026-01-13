# SealAI Multi-Tenancy Walkthrough

This document serves as the canonical reference for the Multi-Tenancy architecture implemented in SealAI. It reflects the "STRICT" isolation mode enforced across all layers (Identity, Database, Cache, Vector Store).

## 1. Multi-Tenancy Architecture

### A) Identity & Claims (Keycloak)
*   **Mechanism**: JWT Bearer Tokens.
*   **Critical Claims**:
    *   `tenant_id`: The primary isolation identifier.
    *   `sub` (User ID): Used for user-specific scoping within a tenant.
    *   `preferred_username`: Display name.
*   **Enforcement**:
    *   `canonical_tenant_id(user)`: Logic used in dependencies.
    *   **STRICT MODE**: If `tenant_id` claim is missing, the API responds with **403 Forbidden**.
    *   **Fallback**: Only allowed if `ALLOW_TENANT_FALLBACK=1` env var is set (Migration-only).
*   **Debug**:
    *   Check `X-Request-ID` in logs.
    *   Inspect `current_user` object in FastAPI dependencies for `tenant_id`.

### B) Postgres Schema
*   **Tables Enforcing Isolation**:
    *   `chat_transcripts`
    *   `chat_messages`
    *   `form_results`
*   **Schema & Migrations**:
    *   Column: `tenant_id` is **NOT NULL** on all critical tables.
    *   Indexes: `(tenant_id)` or `(tenant_id, ...)` exist for performance and lookups.
    *   **Head Revision**: `232d22b152c2` (Fixes & Tenant Enforcement).
*   **Recovery**:
    *   Check state: `alembic current` inside container.
    *   Inspect schema: `psql -U appuser -d appdb -c "\d+ chat_transcripts"` inside container.

### C) Redis Isolation
*   **Pattern**: Isolation via **Key Prefixes**.
*   **SSE Broadcast Keys**:
    *   MUST include tenant ID.
    *   Events: `sse:events:{tenant_id}:{chat_id}`
    *   Channels: `sse:channel:{tenant_id}:{chat_id}`
*   **LangGraph Checkpoint**:
    *   Prefix: `checkpoint:{tenant_id}:...` (configured in `checkpointer.py`).
*   **Verification**:
    *   `redis-cli KEYS "sse:*"` should show tenant IDs.
    *   Collisions are mathematically impossible if `tenant_id` is unique.

### D) Qdrant Isolation
*   **Strategy**: Single Collection + Strict Filtering.
*   **Collection Name**: `sealai_documents` (default).
*   **Enforcement**:
    *   `tenant_id` is stored in payload metadata.
    *   **Must-Filter**: Requests via `RagOrchestrator.hybrid_retrieve` **MUST** provide `tenant_id`.
    *   **Validation**: `hybrid_retrieve(..., tenant=None)` raises `ValueError`.
*   **Debug**:
    *   Filter JSON example:
        ```json
        {
          "must": [
            { "key": "payload.tenant_id", "match": { "value": "tenant-123" } }
          ]
        }
        ```
    *   Failure Mode: If search returns 0 results for known docs, check if `tenant_id` matches exactly.

### E) API Enforcement
*   **Endpoints**:
    *   SSE: `/api/v1/langgraph/chat/v2` ensures strict scoping.
    *   Chat History: `/api/v1/chat/conversations` & `/api/v1/chat/history/{id}`.
*   **Inputs**:
    *   `tenant_id` is derived implicitly from `RequestUser` (JWT). Clients do not manually send tenant ID in body/query to prevent spoofing.

## 2. Verification (Proof of Isolation)

Isolation is verified via automated tests running in the backend container.

### Run Verification Tests
```bash
# 1. Connect to Backend Container
docker compose exec backend bash

# 2. Redis Isolation (SSE Keys & Channels)
pytest -v /app/app/services/tests/test_redis_tenant_isolation.py

# 3. DB Persistence Scoping
pytest -v /app/app/services/chat/tests/test_persistence_tenant_scoping.py

# 4. Qdrant Strict Filter (Negative Test)
pytest -v /app/app/services/rag/tests/test_qdrant_tenant_filter_negative.py
```

*   **PASS** indicates that code strictly enforces tenant parameters even if mocked.

## 3. Operational Runbook

### "If something breaks..."

*   **403 Forbidden / "Tenant ID claim is mandatory"**:
    *   **Cause**: The JWT token from Keycloak is missing the `tenant_id` claim.
    *   **Fix**: Check Keycloak Client Scopes. Ensure a mapper for `tenant_id` exists and is added to the user's access token.

*   **SSE Connection Failures / "Cross-Talk"**:
    *   **Check**: Run `redis-cli monitor | grep sse`.
    *   **Expect**: Commands like `PUBLISH sse:channel:{tenant_id}:{chat_id}`.
    *   **Fix**: If `tenant_id` is missing in Redis keys, `sse_broadcast.py` or the caller (`langgraph_v2.py`) is misconfigured (check Code Patches).

*   **Qdrant Results Empty**:
    *   **Check**: Does the document in Qdrant actually have `payload.tenant_id`?
    *   **Fix**: Re-ingest documents with the correct `tenant_id`. The search filter is strict and will hide everything if the ID doesn't match.

## 4. Audit Report

For a detailed analysis of attack surfaces and guards, see:
[Multi-Tenant Isolation Audit](multi_tenant_isolation_audit.md)
