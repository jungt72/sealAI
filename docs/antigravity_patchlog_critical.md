# Patch Log - Critical Fixes

## Patch 1 - Fix ChatTranscript tenant scoping
- **What changed**: Added \	enant_id\ to \ChatTranscript\ model and enforced scoping in \persist.py\. Fixed Alembic migration state.
- **Why**: Prevent cross-tenant transcript overwrites and leaks.
- **Tests run**: \pytest app/services/history/tests/test_persist_isolation.py- **Result**: PASSED
- **Risks**: Low. Only affects transcript storage which was partially broken.

## Patch 2 - Fix RAG endpoints tenant claim usage
- **What changed**: Replaced \current_user.user_id\ with \canonical_tenant_id(current_user)\ in RAG endpoints (\upload\, \get\, \list\).
- **Why**: Ensure RAG data is scoped to the tenant claim in the JWT, not just the user ID, for correct multi-tenancy.
- **Tests run**: \pytest app/api/tests/test_rag_tenant_claim.py- **Result**: PASSED
- **Risks**: Low. Only affects RAG metadata access.

## Patch 3 - Stable SSE Replay Sequences
- **What changed**: Integrated Redis \INCR\ for monotonic sequence tracking. Sequences are now stored within the event payload.
- **Why**: Prevent sequence reset/instability when the Redis replay list is trimmed by \LTRIM\.
- **Tests run**: \pytest app/services/tests/test_sse_stability.py- **Result**: PASSED
- **Risks**: Very low. Maintained backward compatibility for \Last-Event-ID\ parsing.

## Patch 4 - LWW Versioning for LLM Writes
- **What changed**: Updated \parameter_tools.py\, odes_frontdoor.py\, and odes_discovery.py\ to use \pply_parameter_patch_lww\.
- **Why**: Prevent LLM from overwriting newer user changes with stale data. Enforced version checks.
- **Tests run**: \pytest app/langgraph_v2/tests/test_lww_versioning.py- **Result**: PASSED
- **Risks**: Low. Only affects merged parameters.

## Patch 5 - Test Discovery & Synchronization
- **What changed**: Updated \pytest.ini\ to include service tests. Reconstructed missing \contracts.py\, \constants.py\, and \output_sanitizer.py\ components.
- **Why**: Enable comprehensive test discovery and fix \ImportError\ regression in V2 module.
- **Tests run**: \pytest --collect-only\ (165 tests found), \	est_lww_versioning.py\ (PASSED).
- **Result**: PASSED
- **Risks**: None. Only affects test infrastructure and missing utility restoration.
