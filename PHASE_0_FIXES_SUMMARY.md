# PHASE_0_FIXES_SUMMARY.md

## Fixed Issues

1. ✅ Security-Leak (tenant_id isolation)
2. ✅ profile_loader_node contract
3. ✅ node_p2_rag_lookup contract (3 return paths)
4. ✅ node_p3_gap_detection contract
5. ✅ orchestrator_node contract (Command.update injection)

## Changed Files

- `backend/app/services/rag/nodes/p2_rag_lookup.py` — FIX 1 + FIX 3
  - Line 151: `tenant_id=state.user_id` → `tenant_id=state.tenant_id`
  - `return {}` (sparse skip) → `return {"last_node": "node_p2_rag_lookup"}`
  - Exception return → added `"last_node": "node_p2_rag_lookup"`
  - Success return → added `"last_node": "node_p2_rag_lookup"`

- `backend/app/langgraph_v2/nodes/profile_loader.py` — FIX 2
  - Main return → added `"last_node": "profile_loader_node"`

- `backend/app/services/rag/nodes/p3_gap_detection.py` — FIX 4
  - Main return → added `"last_node": "node_p3_gap_detection"`

- `backend/app/langgraph_v2/nodes/orchestrator.py` — FIX 5
  - Captures Command from supervisor, injects `"last_node": "orchestrator_node"` into
    `cmd.update` if it is a dict (safe no-op if update is None or non-dict)

## Validation Results

```
=== Security Check ===
151:            tenant_id=state.tenant_id,

=== Contract Compliance Check ===
profile_loader.py:   1 last_node declaration(s)
p2_rag_lookup.py:    3 last_node declaration(s)
p3_gap_detection.py: 1 last_node declaration(s)
orchestrator.py:     1 last_node declaration(s)

=== Python Syntax Check ===
profile_loader.py: OK
p2_rag_lookup.py:  OK
p3_gap_detection.py: OK
orchestrator.py:   OK
```

## Notes

- `profile_loader.py` and `orchestrator.py` are untracked new files (git `??`);
  `git diff` produces no output for them — content verified via direct inspection.
- The diff for `p2_rag_lookup.py` includes pre-existing modifications from a prior
  sprint (knowledge-intent bypass, high-signal-field detection) that were already in
  the working tree before Phase 0 started.
- `orchestrator_node` wraps `supervisor_policy_node` which returns a `Command` object.
  The fix safely injects `last_node` into `cmd.update` only when it is already a dict,
  ensuring no breakage if `update` is None.

## Ready for Phase 1: YES
