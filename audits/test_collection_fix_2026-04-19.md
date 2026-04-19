# Test Collection Fix — 2026-04-19

**Purpose:** Document how the 13 test collection errors from Gate 0→1 were resolved.
**Strategy:** Differentiated (Category A/B/C) per Founder Decision.

## Summary

- Category A (fixed imports): 2 tests
- Category B (added dependencies): 2 tests
- Category C (skipped with sprint reference): 9 tests
- Total: 13

## Per-file table

| File | Category | Error summary | Action | Sprint reference (if C) |
|------|----------|---------------|--------|--------------------------|
| backend/tests/agent/test_rag_injection.py | C | Imported removed `app.agent.agent.knowledge.FactCard` and targeted pre-Phase-1a agent RAG prompt injection. | Marked skipped with reason; kept a local `FactCard = dict` compatibility alias so the file remains parseable. | Sprint 4 Patch 4.2 |
| backend/tests/agent/test_selection.py | C | Imported removed `MISSING_INPUTS_REPLY` constant from legacy selection reply contract. | Marked skipped with reason; kept a local compatibility placeholder so the file remains parseable. | Sprint 2 Patch 2.3 |
| backend/tests/agent/test_version_provenance.py | A | Imported visible-reply prompt internals and runtime shim from stale paths. | Updated imports to `app.agent.graph.legacy_graph`, `app.agent.runtime.interaction_policy`, and `app.agent.runtime.policy`. |  |
| backend/tests/test_audit_logger.py | B | Missing installed package `asyncpg`. | Added `asyncpg==0.31.0` to `backend/requirements-dev.txt` and installed it locally. |  |
| backend/tests/test_golden_set.py | C | Imported removed `app.langgraph_v2` state and frontdoor nodes. | Added module-level skip before legacy imports. | Sprint 5 Patch 5.6 |
| backend/tests/test_langgraph_compile.py | C | Imported removed `app.langgraph_v2` graph factory. | Added module-level skip before legacy imports. | Sprint 5 Patch 5.6 |
| backend/tests/test_mcp_calc_engine.py | A | Imported `_is_critical_medium`, which moved behind the compliance calculation module. | Updated import to alias `app.mcp.calculations.compliance.is_critical_application`. |  |
| backend/tests/test_p4_live_calc.py | C | Imported removed `app.langgraph_v2` live-calc state and old live-calc pipeline. | Added module-level skip before legacy imports. | Sprint 4 Patch 4.6 / Sprint 4 Patch 4.7 |
| backend/tests/test_paperless_sync.py | B | Missing installed package `aiosqlite` for test SQLite async engine setup. | Added `aiosqlite==0.22.0` to `backend/requirements-dev.txt` and installed it locally. |  |
| backend/tests/test_param_snapshot.py | C | Targeted old mutation / parameter snapshot handling via legacy LangGraph v2 endpoint helpers. | Added module-level skip before legacy imports. | Sprint 1 Patch 1.6 |
| backend/tests/test_parameter_guardrails.py | C | Imported removed `app.langgraph_v2.utils.parameter_patch`. | Added module-level skip before legacy imports. | Sprint 1 Patch 1.6 |
| backend/tests/test_parameter_lww.py | C | Imported removed `app.langgraph_v2.utils.parameter_patch`. | Added module-level skip before legacy imports. | Sprint 1 Patch 1.6 |
| backend/tests/unit/test_number_verification.py | C | Imported removed `app.langgraph_v2.nodes.p4_6_number_verification`. | Added module-level skip before legacy imports. | Sprint 4 Patch 4.6 / Sprint 4 Patch 4.7 |

## Dependencies added (Category B aggregate)

- `backend/requirements-dev.txt`: `asyncpg==0.31.0`
- `backend/requirements-dev.txt`: `aiosqlite==0.22.0`

Both packages were installed in the local Python environment for collection verification.

## Tests skipped with reasons (Category C aggregate)

- `backend/tests/agent/test_rag_injection.py`: `Legacy test targeting pre-Phase-1a agent RAG prompt injection; replacement arrives in Sprint 4 Patch 4.2 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`
- `backend/tests/agent/test_selection.py`: `Legacy test targeting pre-Phase-1a selection reply constants; replacement arrives in Sprint 2 Patch 2.3 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`
- `backend/tests/test_golden_set.py`: `Legacy test targeting app.langgraph_v2; replacement arrives in Sprint 5 Patch 5.6 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`
- `backend/tests/test_langgraph_compile.py`: `Legacy test targeting app.langgraph_v2; replacement arrives in Sprint 5 Patch 5.6 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`
- `backend/tests/test_p4_live_calc.py`: `Legacy test targeting app.langgraph_v2 live calc pipeline; replacement arrives in Sprint 4 Patch 4.6 and Sprint 4 Patch 4.7 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`
- `backend/tests/test_param_snapshot.py`: `Legacy test targeting old mutation / param handling; replacement arrives in Sprint 1 Patch 1.6 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`
- `backend/tests/test_parameter_guardrails.py`: `Legacy test targeting old mutation / param handling; replacement arrives in Sprint 1 Patch 1.6 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`
- `backend/tests/test_parameter_lww.py`: `Legacy test targeting old mutation / param handling; replacement arrives in Sprint 1 Patch 1.6 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`
- `backend/tests/unit/test_number_verification.py`: `Legacy test targeting old calc engine number verification; replacement arrives in Sprint 4 Patch 4.6 and Sprint 4 Patch 4.7 per Implementation Plan. See audits/gate_0_to_1_2026-04-19.md §7.2.`

## Verification

```bash
pytest backend/tests/ --collect-only -q
```

Output tail:

```text
tests/test_visibility_filter.py::test_visibility_user_id_key_not_leaked_as_qdrant_field
tests/test_visibility_filter.py::test_hybrid_retrieve_injects_visibility_user_id
tests/test_visibility_filter.py::test_hybrid_retrieve_visibility_falls_back_to_tenant

525 tests collected in 4.85s
```

Additional note: the prompt's raw `grep -cE "ERROR|error"` check is a false-positive in this repository because collected test names contain `error` (for example `test_db_error_is_swallowed`). Pytest collection itself exits 0 and emits no error summary.

## Document end.
