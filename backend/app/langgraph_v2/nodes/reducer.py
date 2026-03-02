from __future__ import annotations

from typing import Any, Dict, List

from app.langgraph_v2.nodes.nodes_supervisor import aggregator_node
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, Source, WorkingMemory


def _working_memory_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, WorkingMemory):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _deep_merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _merge_working_memory_from_results(state: SealAIState, results: List[Dict[str, Any]]) -> WorkingMemory | None:
    merged = _working_memory_dict(state.working_memory)
    changed = False
    for result in results:
        if not isinstance(result, dict):
            continue
        wm_patch = _working_memory_dict(result.get("working_memory"))
        if not wm_patch:
            continue
        merged = _deep_merge_dict(merged, wm_patch)
        changed = True
    if not changed:
        return None
    return WorkingMemory.model_validate(merged)


def _coerce_sources(items: Any) -> List[Source]:
    sources: List[Source] = []
    if not isinstance(items, list):
        return sources
    for item in items:
        if isinstance(item, Source):
            sources.append(item)
        elif isinstance(item, dict):
            sources.append(Source.model_validate(item))
    return sources


def _merge_sources_from_results(state: SealAIState, results: List[Dict[str, Any]]) -> List[Source] | None:
    merged = _coerce_sources(state.sources or [])
    seen = {(src.source or "", src.snippet or "") for src in merged}
    changed = False
    for result in results:
        if not isinstance(result, dict):
            continue
        for src in _coerce_sources(result.get("sources")):
            key = (src.source or "", src.snippet or "")
            if key in seen:
                continue
            merged.append(src)
            seen.add(key)
            changed = True
    return merged if changed else None


def _merge_new_data_from_results(state: SealAIState, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    merged_material_choice = dict(state.material_choice or {})
    material_changed = False
    calc_results = None
    calc_results_ok = bool(state.calc_results_ok)
    saw_retrieval = False
    requires_human_review = bool(getattr(state, "requires_human_review", False))
    rag_turn_count = int(getattr(state, "rag_turn_count", 0) or 0)

    for result in results:
        if not isinstance(result, dict):
            continue

        worker_rag_turns = int(result.get("rag_turn_count") or 0)
        if worker_rag_turns > rag_turn_count:
            rag_turn_count = worker_rag_turns

        if result.get("calc_results") is not None:
            calc_results = result.get("calc_results")
            calc_results_ok = True

        if isinstance(result.get("calc_results_ok"), bool):
            calc_results_ok = calc_results_ok or bool(result.get("calc_results_ok"))

        material_choice = result.get("material_choice")
        if isinstance(material_choice, dict) and material_choice:
            merged_material_choice = _deep_merge_dict(merged_material_choice, material_choice)
            material_changed = True

        retrieval_meta = result.get("retrieval_meta")
        if isinstance(retrieval_meta, dict) and retrieval_meta:
            saw_retrieval = True
        direct_context = result.get("context")
        if isinstance(direct_context, str) and direct_context.strip():
            saw_retrieval = True

        # HITL: safety worker can escalate with severity >= 4.
        if str(result.get("last_node") or "").strip() == "safety_agent":
            safety_review = result.get("safety_review")
            severity = None
            if isinstance(safety_review, dict):
                raw = safety_review.get("severity")
                try:
                    severity = int(raw) if raw is not None else None
                except (TypeError, ValueError):
                    severity = None
            if severity is None:
                critical = result.get("critical")
                if isinstance(critical, dict):
                    raw = critical.get("severity")
                    try:
                        severity = int(raw) if raw is not None else None
                    except (TypeError, ValueError):
                        severity = None
            if (severity or 0) >= 4:
                requires_human_review = True

    wm_patch = _merge_working_memory_from_results(state, results)
    if wm_patch is not None:
        patch["working_memory"] = wm_patch
        panel_material = wm_patch.panel_material if isinstance(wm_patch.panel_material, dict) else {}
        rag_context = panel_material.get("rag_context") or panel_material.get("reducer_context")
        docs = panel_material.get("technical_docs")
        if (isinstance(rag_context, str) and rag_context.strip()) or (isinstance(docs, list) and docs):
            saw_retrieval = True

    sources_patch = _merge_sources_from_results(state, results)
    if sources_patch is not None:
        patch["sources"] = sources_patch

    if calc_results is not None:
        patch["calc_results"] = calc_results
    if calc_results_ok != bool(state.calc_results_ok):
        patch["calc_results_ok"] = calc_results_ok

    if material_changed and merged_material_choice != dict(state.material_choice or {}):
        patch["material_choice"] = merged_material_choice

    if rag_turn_count > int(getattr(state, "rag_turn_count", 0) or 0):
        patch["rag_turn_count"] = rag_turn_count

    if saw_retrieval:
        # Retrieval demand has been fulfilled in this map-reduce cycle.
        patch["requires_rag"] = False
        patch["need_sources"] = False

    if calc_results_ok and bool((merged_material_choice or {}).get("material")):
        # Mark map phase complete for this recommendation turn.
        patch["next_action"] = None
    if requires_human_review:
        patch["requires_human_review"] = True

    return patch


def _merge_retrieval_from_results(
    state: SealAIState,
    results: List[Dict[str, Any]],
) -> tuple[WorkingMemory | None, Dict[str, Any] | None, str | None]:
    if not results:
        return None, None, None

    context_blocks: List[str] = []
    retrieval_entries: List[Dict[str, Any]] = []

    for result in results:
        if not isinstance(result, dict):
            continue
        meta = result.get("retrieval_meta")
        if isinstance(meta, dict):
            retrieval_entries.append(meta)
        direct_context = result.get("context")
        if isinstance(direct_context, str) and direct_context.strip():
            context_blocks.append(direct_context.strip())

        wm_dict = _working_memory_dict(result.get("working_memory"))
        panel_material = wm_dict.get("panel_material")
        if isinstance(panel_material, dict):
            for key in ("rag_context", "reducer_context"):
                rag_context = panel_material.get(key)
                if isinstance(rag_context, str) and rag_context.strip():
                    context_blocks.append(rag_context.strip())

    if not context_blocks and not retrieval_entries:
        return None, None, None

    wm = state.working_memory or WorkingMemory()
    panel_material = dict(wm.panel_material or {})
    existing_context = str(panel_material.get("reducer_context") or "").strip()
    existing_state_context = str(state.get("context") or "").strip()
    merged_context_parts: List[str] = []
    seen_context: set[str] = set()
    for part in [existing_context, existing_state_context, *context_blocks]:
        normalized = str(part or "").strip()
        if not normalized or normalized in seen_context:
            continue
        seen_context.add(normalized)
        merged_context_parts.append(normalized)
    merged_context = "\n\n".join(merged_context_parts).strip()
    panel_material["reducer_context"] = merged_context
    wm = wm.model_copy(update={"panel_material": panel_material})

    merged_meta: Dict[str, Any] = dict(state.retrieval_meta or {})
    if retrieval_entries:
        merged_meta["reducer"] = {"count": len(retrieval_entries), "items": retrieval_entries}
    return wm, merged_meta or None, merged_context or None


def reducer_node(state: SealAIState, results: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Aggregates results from parallel worker executions (Map-Reduce reducer).
    In addition to the classic aggregator merge, this consolidates RAG context
    emitted by workers so downstream prompts can consume retrieval context.
    """
    worker_results = list(results or [])
    result = aggregator_node(state)
    result.update(_merge_new_data_from_results(state, worker_results))

    reducer_state = state.model_copy(update=result)
    wm_patch, retrieval_meta_patch, context_patch = _merge_retrieval_from_results(reducer_state, worker_results)
    if wm_patch is not None:
        result["working_memory"] = wm_patch
    if retrieval_meta_patch is not None:
        result["retrieval_meta"] = retrieval_meta_patch
    if context_patch is not None:
        result["context"] = context_patch
    result["last_node"] = "reducer_node"
    result["phase"] = PHASE.AGGREGATION
    return result
