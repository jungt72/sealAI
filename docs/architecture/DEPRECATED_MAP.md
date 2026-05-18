# SeaLAI Deprecated / Compatibility Map

This map prevents future patches from accidentally treating historical layers as the active architecture.

## Active Compatibility Surfaces

| Surface | Status | Rule |
| --- | --- | --- |
| `/api/v1/state/workspace` | Compatibility read facade | May read canonical governed state and return `CaseWorkspaceProjection`. No mutations. |
| `/api/v1/langgraph/health` | Diagnostic compatibility alias | Health only. Must not grow new runtime behavior. |
| Frontend legacy aliases in contracts | Compatibility parsing | Allowed only for inbound normalization. New backend fields should use canonical names. |
| `backend/app/services/rag/state.py` legacy field helpers | Compatibility normalization | Allowed while old RAG metadata exists. Do not expand as a new state model. |

## Historical / Non-Productive Areas

| Area | Status | Rule |
| --- | --- | --- |
| `archive/**` | Historical | Read-only reference. Never patch as product runtime. |
| `_trash/**` | Historical | Ignore for product changes. |
| `_local_keep/**` | Local operational material | Never commit or use as SSoT. |
| `langgraph_backup/**` | Historical backup | Do not import or patch for productive runtime. |
| `backend/tests/contract/*` importing `app.langgraph_v2` | Removed historical test quarantines | Obsolete LangGraph v2 contract tests were deleted instead of kept as skipped modules. Current contracts live under `app.agent` tests and active contract tests. |
| `backend/app/agent/tests/*` pre-SSoT router-private tests | Removed historical test quarantines | Obsolete module-level skipped tests were deleted or migrated to current reducer/runtime/streaming tests. |
| `backend/app/agent/agent/*` | Removed historical shim layer | Old shim modules were deleted. Product code and tests must import canonical `runtime`, `domain`, `state`, `graph`, `prompts`, or `manufacturers` modules directly. |
| `backend/app/agent/api/sse_runtime.py` | Removed residual SSE seam | Productive streaming now lives in `backend/app/agent/api/streaming.py`; do not reintroduce the old agent SSE generator. |
| Obsolete facade and SSoT stream verification scripts | Removed historical cutover scripts | Old verification scripts encoded obsolete stream contracts. Use current tests instead. |

## Cleanup Backlog

1. Split `backend/app/api/v1/projections/case_workspace.py` into small modules while preserving response contract.
2. Keep active contract coverage under current `app.agent` surfaces only; do not reintroduce skipped LangGraph v2 tests.
3. Bring `backend/app/agent/tests` into the regular CI test surface after remaining environment-only tests are classified.
4. Replace frontend fallback engineering-path inference with explicit backend-truth-first behavior plus tests.
5. Add ownership headers or module docstrings to compatibility facades.
