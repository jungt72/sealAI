# LangGraph v2 Optimization Plan
**Based on:** Ultra-Precision Audit 2026-02-24
**Graph version:** v4.4.0 (Post-KB-Integration, Post-Sprint-9)

---

## Phase 1: Critical Fixes (< 1 Day)

### Fix 1.1: Tenant ID Inconsistency in P2 RAG Lookup [C2 — P0]

**File:** `backend/app/services/rag/nodes/p2_rag_lookup.py:151`

**Problem:** `node_p2_rag_lookup` passes `state.user_id` as the `tenant_id` to Qdrant. If `tenant_id` (org ID) differs from `user_id` (individual), documents scoped to a different organization may leak.

**Fix:**
```python
# BEFORE (line 151):
payload = search_technical_docs(
    query=query,
    tenant_id=state.user_id,
    k=4,
)

# AFTER:
payload = search_technical_docs(
    query=query,
    tenant_id=state.tenant_id or state.user_id,
    k=4,
)
```

**Test:** Add assertion in `test_p2_rag_lookup.py` that when `state.tenant_id` is set, it is passed to `search_technical_docs` instead of `user_id`.

---

### Fix 1.2: Add `last_node` to 4 Missing Nodes [C4 — P1]

**Nodes:** `profile_loader_node`, `node_p2_rag_lookup` (skip path), `node_p3_gap_detection`, `orchestrator_node`

**Fix 1.2a — `profile_loader.py:81`:**
```python
# BEFORE:
return {
    "user_context": merged_context,
    "working_memory": wm,
}

# AFTER:
return {
    "user_context": merged_context,
    "working_memory": wm,
    "last_node": "profile_loader_node",
}
```

**Fix 1.2b — `p2_rag_lookup.py:127` (skip path):**
```python
# BEFORE:
return {}

# AFTER:
return {"last_node": "node_p2_rag_lookup"}
```

**Fix 1.2c — `p2_rag_lookup.py:201` (success path):**
```python
# BEFORE:
return {
    "working_memory": wm,
    "sources": sources,
    "context": rag_context,
    "retrieval_meta": retrieval_meta,
}

# AFTER:
return {
    "working_memory": wm,
    "sources": sources,
    "context": rag_context,
    "retrieval_meta": retrieval_meta,
    "last_node": "node_p2_rag_lookup",
}
```

**Fix 1.2d — `p3_gap_detection.py:122`:**
```python
# BEFORE:
return {
    "gap_report": gap_report,
}

# AFTER:
return {
    "gap_report": gap_report,
    "last_node": "node_p3_gap_detection",
}
```

**Fix 1.2e — `orchestrator.py:11`:** `orchestrator_node` is a thin wrapper that delegates to `supervisor_policy_node`. It does not set its own state. This is by design (v3.1 compat layer). Since it returns the `Command` object from `supervisor_policy_node`, `last_node` will be set by the delegate. **No fix needed** — document this in the code.

---

## Phase 2: Performance Optimization (1–2 Days)

### Opt 2.1: Add LLM Call Timeouts [C1 — P0]

**Problem:** No timeout on any LLM or Qdrant call. A hung call stalls the graph indefinitely.

**Approach:** Convert synchronous LLM-calling nodes to `async def` and wrap with `asyncio.wait_for`:

**Example fix for `nodes_frontdoor.py:245`:**
```python
# BEFORE:
def frontdoor_discovery_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    ...
    response = structured_llm.invoke(_build_frontdoor_messages(state, user_text))

# AFTER:
import asyncio

async def frontdoor_discovery_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    ...
    try:
        response = await asyncio.wait_for(
            structured_llm.ainvoke(_build_frontdoor_messages(state, user_text)),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.warning("frontdoor_llm_timeout", run_id=state.run_id)
        # Fallback: treat as design_recommendation intent
        return _build_frontdoor_fallback_result(state)
    except Exception as exc:
        logger.warning("frontdoor_llm_error", error=str(exc), run_id=state.run_id)
        return _build_frontdoor_fallback_result(state)
```

**Priority order for async conversion:**
1. `frontdoor_discovery_node` (nodes_frontdoor.py) — blocking LLM call, every request
2. `node_p1_context` (p1_context.py) — blocking LLM call, every request
3. `supervisor_policy_node` (nodes_supervisor.py) — blocking LLM call, every non-trivial request
4. `node_p2_rag_lookup` (p2_rag_lookup.py) — blocking Qdrant call
5. `rag_support_node` (nodes_flows.py) — blocking Qdrant+LLM call

---

### Opt 2.2: Add Retry on LLM Calls [C5 — P1]

**Problem:** Transient OpenAI 429/503 errors cause immediate failure. Only `p4b_calc_render` has retry logic.

**Approach:** Add exponential backoff retry to the 3 highest-frequency LLM call sites.

**Example for `p1_context.py:114`:**
```python
# BEFORE:
def _invoke_extraction(user_text: str, history: List[Any]) -> _P1Extraction:
    ...
    result = structured_llm.invoke(messages)
    return result

# AFTER (using tenacity or manual loop):
import time

def _invoke_extraction_with_retry(user_text: str, history: List[Any], max_retries: int = 2) -> _P1Extraction:
    messages = _build_messages(user_text, history)
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return structured_llm.invoke(messages)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # 1s, 2s
    logger.warning("p1_context_extraction_failed_all_retries", error=str(last_exc))
    raise last_exc
```

**Nodes to add retry:**
- `frontdoor_discovery_node` (structured LLM)
- `node_p1_context` (structured extraction)
- `supervisor_policy_node` (routing LLM)

---

### Opt 2.3: RAG Result Cache [C8 — P2]

**Problem:** Identical queries (same parameters, same user) hit Qdrant on every message, adding ~150–400 ms.

**Implementation:**
```python
# New file: backend/app/services/rag/rag_cache.py
import hashlib
import json
from functools import lru_cache
from typing import Any, Dict, Optional
import redis.asyncio as redis

_cache: Optional[redis.Redis] = None

def _get_cache() -> Optional[redis.Redis]:
    global _cache
    if _cache is None:
        try:
            from app.core.config import get_settings
            _cache = redis.from_url(get_settings().REDIS_URL)
        except Exception:
            return None
    return _cache

def _cache_key(query: str, tenant_id: Optional[str]) -> str:
    raw = f"{query}:{tenant_id or 'default'}"
    return f"rag_cache:{hashlib.sha256(raw.encode()).hexdigest()}"

async def get_cached_rag(query: str, tenant_id: Optional[str]) -> Optional[Dict[str, Any]]:
    rc = _get_cache()
    if rc is None:
        return None
    try:
        raw = await rc.get(_cache_key(query, tenant_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None

async def set_cached_rag(query: str, tenant_id: Optional[str], payload: Dict[str, Any], ttl: int = 300) -> None:
    rc = _get_cache()
    if rc is None:
        return
    try:
        await rc.setex(_cache_key(query, tenant_id), ttl, json.dumps(payload))
    except Exception:
        pass
```

**Usage in `p2_rag_lookup.py`:**
```python
# Before Qdrant call:
cached = await get_cached_rag(query, tenant_id)
if cached:
    return _build_result_from_payload(cached, state)

# After successful Qdrant call:
await set_cached_rag(query, tenant_id, payload, ttl=300)
```

**Expected improvement:** Cache hit rate ~40–60% for repeat queries; P2 latency 400 ms → 5 ms on cache hit.

---

## Phase 3: Resilience (2–3 Days)

### Opt 3.1: Standardize Logging to structlog [C6 — P2]

**Files:** `nodes_supervisor.py:27`, `compound_filter.py:14`, `factcard_lookup.py:15`

**Fix pattern:**
```python
# BEFORE (nodes_supervisor.py:4,27):
import logging
logger = logging.getLogger(__name__)

# AFTER:
import structlog
logger = structlog.get_logger("langgraph_v2.nodes_supervisor")

# Structlog call with context (include trace IDs):
logger.info(
    "supervisor_policy_decision",
    action=action,
    run_id=state.run_id,
    thread_id=state.thread_id,
    round=state.round_index,
)
```

**Impact:** Enables correlation of supervisor decisions with LangSmith traces and Prometheus metrics via shared `run_id`.

---

### Opt 3.2: Add Logging to `profile_loader_node` [C9 — P3]

**File:** `backend/app/langgraph_v2/nodes/profile_loader.py`

```python
# Add at top of file:
import structlog
logger = structlog.get_logger("langgraph_v2.profile_loader")

# In profile_loader_node():
logger.info(
    "profile_loader_start",
    user_id=user_id,
    run_id=state.run_id,
)
# In except block:
logger.warning(
    "profile_loader_store_error",
    user_id=user_id,
    error=str(exc),  # exc already caught
    run_id=state.run_id,
)
# At end:
logger.info(
    "profile_loader_done",
    user_id=user_id,
    profile_keys=list(loaded_profile.keys()),
    run_id=state.run_id,
)
```

---

## Phase 4: Quality & Test Coverage (3–5 Days)

### Opt 4.1: Unit Tests for 7 Untested Nodes [C7 — P2]

**Priority order:**

**a) `test_p4b_calc_render.py`** — test retry logic:
```python
def test_p4b_calc_render_retries_on_first_failure(monkeypatch):
    """P4b should retry once if calc engine raises on first attempt."""
    calls = []
    def mock_calc(input_data):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("transient error")
        return CalcOutput(safety_factor=1.5, temperature_margin_c=50.0)
    monkeypatch.setattr("app.services.rag.nodes.p4b_calc_render.run_calculation", mock_calc)
    state = SealAIState(extracted_params={"pressure_max_bar": 50, "temperature_max_c": 200})
    result = node_p4b_calc_render(state)
    assert result["calc_results_ok"] is True
    assert len(calls) == 2
```

**b) `test_p3_5_merge.py`** — test merge deduplication:
```python
def test_p3_5_merge_deduplicates_sources():
    """P3.5 merge should deduplicate identical sources from P2 and P3."""
    source = Source(snippet="text", source="file.pdf")
    state = SealAIState(sources=[source])
    result = [
        {"sources": [source], "last_node": "node_p2_rag_lookup"},
        {"gap_report": {}, "last_node": "node_p3_gap_detection"},
    ]
    out = node_p3_5_merge(state, result)
    assert len(out["sources"]) == 1  # deduplicated
```

**c) `test_node_p5_procurement.py`** — test 4-stage matching:
```python
def test_p5_procurement_no_partners_returns_empty():
    """P5 procurement returns empty result when no partner registry exists."""
    state = SealAIState(
        parameters=TechnicalParameters(medium="Wasser"),
        working_profile=None,
    )
    result = node_p5_procurement(state)
    assert "procurement_result" in result
    assert result["last_node"] == "node_p5_procurement"
```

**d) `test_node_p4a_extract.py`** — test CalcInput mapping:
```python
def test_p4a_extract_maps_pressure_and_temperature():
    """P4a should map working_profile fields to extracted_params."""
    from app.services.rag.state import WorkingProfile
    profile = WorkingProfile(pressure_max_bar=100.0, temperature_max_c=300.0, medium="Steam")
    state = SealAIState(working_profile=profile)
    result = node_p4a_extract(state)
    assert result["extracted_params"]["pressure_max_bar"] == 100.0
    assert result["extracted_params"]["temperature_max_c"] == 300.0
```

**e) `test_compound_filter.py`** — test compound matrix filtering:
```python
def test_compound_filter_with_no_kb_data():
    """compound_filter should succeed even when KB matrix is absent (fail-open)."""
    state = SealAIState(kb_factcard_result={})
    result = node_compound_filter(state)
    assert "compound_filter_results" in result
    assert result["last_node"] == "node_compound_filter"
```

---

### Opt 4.2: Missing Quality Gate Checks [C10 — P3]

**New check: Unit Consistency**
```python
def _check_unit_consistency(profile: Dict[str, Any]) -> QGateCheck:
    """Check for mixed pressure units (bar vs psi)."""
    pressure = profile.get("pressure_max_bar")
    # Values > 1000 bar are likely psi (1 psi ≈ 0.069 bar, typical seal 1–200 bar)
    if pressure is not None and float(pressure) > 1000.0:
        return QGateCheck(
            check_id="unit_consistency",
            name="Einheitenkonsistenz",
            severity="WARNING",
            passed=False,
            message=f"Druck {pressure} bar unplausibel — möglicherweise psi statt bar eingegeben.",
            details={"pressure_max_bar": pressure, "suspicion": "psi_input"},
        )
    return QGateCheck(
        check_id="unit_consistency",
        name="Einheitenkonsistenz",
        severity="WARNING",
        passed=True,
        message="Einheiten plausibel.",
        details={},
    )
```

**New check: Physics Plausibility**
```python
def _check_physics_plausibility(profile: Dict[str, Any]) -> QGateCheck:
    """Check that temperature/pressure values are in physically plausible ranges."""
    temp = profile.get("temperature_max_c")
    pressure = profile.get("pressure_max_bar")
    reasons = []
    if temp is not None and float(temp) > 650.0:
        reasons.append(f"Temperatur {temp}°C überschreitet metallische Schmelzpunkte — unplausibel")
    if pressure is not None and float(pressure) > 1000.0 and pressure != 0:
        reasons.append(f"Druck {pressure} bar unphysikalisch für Dichtungsanwendungen")
    passed = len(reasons) == 0
    return QGateCheck(
        check_id="physics_plausibility",
        name="Physikalische Plausibilität",
        severity="CRITICAL" if not passed else "WARNING",
        passed=passed,
        message="; ".join(reasons) if reasons else "Alle Werte physikalisch plausibel.",
        details={"reasons": reasons},
    )
```

---

## Metrics & KPIs

| Metric | Current | Target (after all phases) |
|--------|---------|--------------------------|
| P50 total latency (design_recommendation) | ~3.9 s | ~3.2 s (−18%, async + cache) |
| Async node ratio | 8.6% | ≥40% (after Phase 2 conversions) |
| Nodes with last_node | 46/50 | 50/50 (after Fix 1.2) |
| Error handling score avg | 2.1/4 | ≥3.0/4 (after retry additions) |
| Test functions | ~540 | ≥580 (after Phase 4) |
| Tenant isolation issues | 1 (P2) | 0 (after Fix 1.1) |
| Logging standard compliance | 13/17 files use structlog | 17/17 (after Opt 3.1) |
| Quality gate checks | 8 | 10 (after Opt 4.2) |

---

## Implementation Order (Recommended)

```
Day 1 (morning):
  [ ] Fix 1.1 — tenant_id in p2_rag_lookup (1 line, 15 min)
  [ ] Fix 1.2 — last_node in 4 nodes (4 lines, 30 min)
  [ ] Run test suite to verify no regressions

Day 1 (afternoon):
  [ ] Opt 3.2 — add logging to profile_loader (30 min)
  [ ] Opt 3.1 — standardize logging in supervisor + compound + factcard (1h)
  [ ] Opt 4.1 e) — compound_filter tests (1h)

Day 2:
  [ ] Opt 2.1 — async conversion for frontdoor + p1_context (2–3h each)
  [ ] Opt 2.2 — retry logic for top-3 LLM callers (1h)

Day 3:
  [ ] Opt 2.3 — RAG cache implementation + integration (3h)
  [ ] Opt 4.1 a–d) — remaining unit tests (4h)

Days 4–5:
  [ ] Opt 2.1 continued — supervisor_policy_node async conversion (complex)
  [ ] Opt 4.2 — new quality gate checks (2h)
  [ ] Full regression test run
```
