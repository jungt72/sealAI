"""P3.5 Merge Node for SEALAI v4.4.0 (Sprint 5).

Aggregates parallel results from P2 (RAG Material-Lookup) and P3 (Gap-Detection)
into a single state update before continuing to resume_router_node.

Follows the same reducer pattern as reducer_node in nodes/reducer.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, Source, WorkingMemory

logger = structlog.get_logger("rag.nodes.p3_5_merge")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge_sources(state: SealAIState, results: List[Dict[str, Any]]) -> List[Source]:
    """Merge sources from parallel results, deduplicating."""
    merged: List[Source] = list(state.sources or [])
    seen = {(src.source or "", src.snippet or "") for src in merged}
    for result in results:
        if not isinstance(result, dict):
            continue
        for item in result.get("sources") or []:
            if isinstance(item, Source):
                src = item
            elif isinstance(item, dict):
                src = Source.model_validate(item)
            else:
                continue
            key = (src.source or "", src.snippet or "")
            if key not in seen:
                merged.append(src)
                seen.add(key)
    return merged


def _extract_gap_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Find the gap_report from P3 in the results list."""
    for result in results:
        if not isinstance(result, dict):
            continue
        gap_report = result.get("gap_report")
        if isinstance(gap_report, dict) and gap_report:
            return gap_report
    return {}


def _merge_working_memory(
    state: SealAIState, results: List[Dict[str, Any]]
) -> WorkingMemory:
    """Merge working_memory from P2 result into existing state."""
    wm = state.working_memory or WorkingMemory()
    for result in results:
        if not isinstance(result, dict):
            continue
        result_wm = result.get("working_memory")
        if result_wm is None:
            continue
        if isinstance(result_wm, WorkingMemory):
            patch = result_wm.model_dump(exclude_none=True)
        elif isinstance(result_wm, dict):
            patch = {k: v for k, v in result_wm.items() if v is not None}
        else:
            continue
        if patch:
            wm = wm.model_copy(update=patch)
    return wm


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_p3_5_merge(
    state: SealAIState, results: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """P3.5 Merge — aggregate P2 (RAG) and P3 (Gap) results.

    Receives parallel worker results via LangGraph Send/reduce pattern.
    Continues to resume_router_node.
    """
    worker_results = list(results or [])

    logger.info(
        "p3_5_merge_start",
        result_count=len(worker_results),
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    # --- Gap report from P3 ---
    gap_report = _extract_gap_report(worker_results)

    # --- Sources & working_memory from P2 ---
    merged_sources = _merge_sources(state, worker_results)
    merged_wm = _merge_working_memory(state, worker_results)

    # --- Context from P2 ---
    context_parts: List[str] = []
    if state.context:
        context_parts.append(str(state.context).strip())
    for result in worker_results:
        if not isinstance(result, dict):
            continue
        ctx = result.get("context")
        if isinstance(ctx, str) and ctx.strip():
            ctx_stripped = ctx.strip()
            if ctx_stripped not in context_parts:
                context_parts.append(ctx_stripped)
    merged_context = "\n\n".join(context_parts).strip() or None

    # --- Retrieval meta from P2 ---
    retrieval_meta: Dict[str, Any] = dict(state.retrieval_meta or {})
    rag_turn_count = int(getattr(state, "rag_turn_count", 0) or 0)
    for result in worker_results:
        if not isinstance(result, dict):
            continue
        meta = result.get("retrieval_meta")
        if isinstance(meta, dict) and meta:
            retrieval_meta["p2_rag_lookup"] = meta
        
        worker_rag_turns = int(result.get("rag_turn_count") or 0)
        if worker_rag_turns > rag_turn_count:
            rag_turn_count = worker_rag_turns

    # --- Build update ---
    update: Dict[str, Any] = {
        "phase": PHASE.FRONTDOOR,
        "last_node": "node_p3_5_merge",
        "working_memory": merged_wm,
        "rag_turn_count": rag_turn_count,
    }

    if gap_report:
        update["gap_report"] = gap_report
        update["discovery_missing"] = gap_report.get("missing_critical", [])
        update["coverage_score"] = gap_report.get("coverage_ratio", 0.0)
        update["coverage_gaps"] = (
            gap_report.get("missing_critical", [])
            + gap_report.get("missing_optional", [])
        )
        update["recommendation_ready"] = gap_report.get("recommendation_ready", False)

    if merged_sources:
        update["sources"] = merged_sources

    if merged_context:
        update["context"] = merged_context

    if retrieval_meta:
        update["retrieval_meta"] = retrieval_meta

    logger.info(
        "p3_5_merge_done",
        gap_report_present=bool(gap_report),
        source_count=len(merged_sources),
        context_len=len(merged_context) if merged_context else 0,
        recommendation_ready=gap_report.get("recommendation_ready", False),
        run_id=state.run_id,
    )

    return update


__all__ = ["node_p3_5_merge"]
