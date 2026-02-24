# PHASE_4_ARCHITECTURAL_FIX_SUMMARY.md

## Changes Made

### 1. New Node: route_after_frontdoor
- File: `backend/app/langgraph_v2/nodes/route_after_frontdoor.py`
- LOC: ~80
- Purpose: Route requests after `frontdoor_discovery_node` intent classification.
- Implemented paths:
  - `smalltalk_node` (social opening)
  - `frontdoor_parallel_fanout_node` (deterministic KB fast path)
  - `supervisor_policy_node` (troubleshooting/comparison)
  - `node_p1_context` (full P1-P4 design pipeline)

### 2. Graph Rewiring
- File: `backend/app/langgraph_v2/sealai_graph_v2.py`
- Changed router dispatch:
  - Before: `new_case/follow_up -> node_p1_context`
  - After: `new_case/follow_up -> frontdoor_discovery_node`
- Added node registration:
  - `route_after_frontdoor -> route_after_frontdoor_node`
- Added edge:
  - `frontdoor_discovery_node -> route_after_frontdoor`
- Kept existing KB integration path:
  - `frontdoor_parallel_fanout_node -> node_factcard_lookup_parallel + node_compound_filter_parallel -> node_merge_deterministic`

### 3. Step-1 Frontdoor Analysis
`frontdoor_discovery_node` returns:
- `intent: Intent(goal, confidence, needs_sources/need_sources, routing_hint, ...)`
- `working_memory` updates with:
  - `frontdoor_reply`
  - `design_notes.frontdoor_reasoning`
  - `design_notes.requested_quantity`
  - `design_notes.requested_sku`
- `flags` updates with:
  - `frontdoor_social_opening`
  - `frontdoor_task_intents`
  - `frontdoor_intent_category`
  - `frontdoor_bypass_supervisor`
  - `frontdoor_technical_cue_veto`
  - `frontdoor_technical_cue_matches`
  - `is_safety_critical`
  - `needs_pricing`
- `last_node: "frontdoor_discovery_node"`

### 4. State Conflict Check
- `frontdoor_discovery_node` writes `working_memory` (`frontdoor_reply` + `design_notes`).
- `node_p1_context` writes `working_profile` (not `working_memory`).
- Result: no direct field overwrite conflict.
- `node_p1_context` also does not overwrite `intent`, so frontdoor intent survives.

### 5. Routing Test Script
- Added: `test_routing.py`
- Runs a mocked frontdoor structured output and validates route decisions for 6 representative patterns.
- Result:
  - `Summary: 6/6 passed`

```
=== PHASE 4 ROUTING TEST ===
1. PASS  Was ist max Temp für PTFE?                      -> frontdoor_parallel_fanout_node
2. PASS  Material für 150°C, HF-Säure, Alu-Welle         -> frontdoor_parallel_fanout_node
3. PASS  Wir haben Leckage an PTFE-Dichtung              -> supervisor_policy_node
4. PASS  Pumpe für 200°C, 80 bar                         -> node_p1_context
5. PASS  PTFE vs FFKM für 150°C                          -> supervisor_policy_node
6. PASS  Was ist der Unterschied zwischen FKM und FFKM?  -> smalltalk_node
Summary: 6/6 passed
```

### 6. Test Adjustments
- Updated:
  - `backend/app/langgraph_v2/tests/test_sealai_graph_v2_supervisor_routing.py`
- Changes:
  - Graph topology assertion now checks `frontdoor_discovery_node -> route_after_frontdoor`
  - Replaced direct `_frontdoor_router` checks with `route_after_frontdoor_node` behavior checks

## Pattern Impact

| Pattern | Before | After | Improvement |
|---------|--------|-------|-------------|
| 1. Info | 3-5s | KB fast path | Faster path enabled |
| 2. Screening | 3-5s | KB fast path | Faster path enabled |
| 3. Troubleshooting | BROKEN | frontdoor -> supervisor | FIXED route entry |
| 4. Design | 3-5s | frontdoor -> P1-P4 | Unchanged (correct) |
| 5. Vergleich | 3-5s | frontdoor -> supervisor | Direct flow |
| 6. RFQ | <1s | <1s | Unchanged |
| 7. Smalltalk | 3-5s | frontdoor -> smalltalk | Fast path enabled |

## Validation Results

### Architecture / Syntax
- ✅ `backend/app/langgraph_v2/nodes/route_after_frontdoor.py` exists
- ✅ `node_router` dispatch no longer points `new_case` to `node_p1_context`
- ✅ `python -m py_compile` passed for:
  - `backend/app/langgraph_v2/nodes/route_after_frontdoor.py`
  - `backend/app/langgraph_v2/sealai_graph_v2.py`

### Phase 0/1/2/3 Integrity
- ✅ Security (tenant scope logic) still present in `p2_rag_lookup.py`
- ✅ Retry helper `_invoke_with_retry` present in `langgraph_v2/utils/llm_factory.py`
- ✅ Async signatures still present (`run_llm_async`, `node_p2_rag_lookup`)
- ✅ RAG cache integration still present (`rag_cache.get` / `rag_cache.set`)

### Notes on Automated Pytest in this Environment
- Attempted:
  - `pytest -q backend/app/langgraph_v2/tests/test_sealai_graph_v2_supervisor_routing.py`
- Blocked by environment/import prerequisites in sandbox:
  - BM25 writable path constraints
  - missing `settings.redis_url` during import
- Routing logic verification was therefore executed via `test_routing.py` (passed 6/6).

## Next Steps
- GAP-4: Quality gate alternatives
- GAP-6: Expand RFQ keywords
- GAP-8: Increase smalltalk max_tokens
