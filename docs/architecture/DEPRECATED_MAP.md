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
| `backend/tests/contract/*` importing `app.langgraph_v2` | Legacy residue | Migrate to `app.agent` contracts or remove in cleanup. |
| `backend/tests/contract/test_optional_rag_contract.py` | Legacy quarantined | Imports removed LangGraph v2 optional-RAG graph contracts. Replace with current `app.agent` RAG/source tests. |
| `backend/tests/contract/test_prompt_render_contract.py` | Legacy quarantined | Imports removed LangGraph v2 prompt contracts. Replace with current prompt/service contracts. |
| `backend/tests/contract/test_tool_contracts.py` | Legacy quarantined | Imports removed LangGraph v2 tool contracts. Replace with current service/tool contracts. |
| `backend/tests/contract/test_sse_contract.py` | Legacy quarantined | Expects pre-SSoT router private SSE APIs. Replace with `app.agent.api.streaming` tests. |
| `backend/app/agent/tests/test_commercial_handover.py` | Legacy quarantined | Imports removed `app.agent.agent.graph` flow. Replace with current dispatch/commercial surface tests before re-enabling. |
| `backend/app/agent/tests/test_governed_stream_payload.py` | Legacy quarantined | Expects pre-SSoT router private APIs. Replace with assembly/streaming contract tests. |
| `backend/app/agent/tests/test_state_integration.py` | Legacy quarantined | Expects pre-SSoT post-graph router internals. Replace with reducer/loaders/persistence contract tests. |
| `backend/app/agent/agent/*` | Residual older agent layer | Verify import graph before editing. Prefer `backend/app/agent/runtime/*`, `backend/app/agent/graph/*`, `backend/app/agent/api/*`. |

## Cleanup Backlog

1. Split `backend/app/api/v1/projections/case_workspace.py` into small modules while preserving response contract.
2. Migrate or retire `backend/tests/contract/*` LangGraph v2 tests.
3. Keep legacy quarantines module-skipped and documented until replacement tests exist.
4. Bring `backend/app/agent/tests` into the regular CI test surface after collection/runtime issues are resolved.
5. Replace frontend fallback engineering-path inference with explicit backend-truth-first behavior plus tests.
6. Add ownership headers or module docstrings to compatibility facades.
