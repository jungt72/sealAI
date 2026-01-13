# Phase 5.5: Multi-Tenancy Hardening Audit

## 1. Scope ID Construction
*   **Current State**: Constructed ad-hoc in `langgraph_v2.py` as `_sse_scope_id`.
*   **Risk**: String formatting drift. If one component changes the separator or order (e.g., `user:tenant`), isolation breaks.
*   **Mitigation**: Centralize in `app.services.auth.scope.build_scope_id`.

## 2. Chat ID Processing
*   **Current State**: Accepted from request body in `langgraph_v2.py`.
*   **Risk**:
    *   **Collision**: Clients generating simple IDs ("chat1") could collide if tenant isolation fails (defense-in-depth).
    *   **Spoofing**: Malicious clients reusing IDs.
*   **Mitigation**: Enforce UUIDv4. If empty, generate server-side.

## 3. Tenant ID in Redis
*   **Current State**:
    *   `sse_broadcast.py`: `sse:events:{tenant_id}:{chat_id}` (Hardcoded f-string).
    *   `checkpointer.py`: `tenant:{tenant_id}:{prefix}`.
*   **Risk**: Key Injection. Use of characters like `..` or `{` in `tenant_id` could alter key slotting or pathing.
*   **Mitigation**: Strict Regex Validation (`^[a-zA-Z0-9_-]+$`) in `canonical_tenant_id`.

## 4. Regressions
*   **Legacy Fallback**: `ALLOW_TENANT_FALLBACK=1` might allow weak IDs (emails as IDs). Validation should apply to fallback results too.
