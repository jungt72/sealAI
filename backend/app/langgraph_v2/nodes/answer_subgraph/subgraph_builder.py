from __future__ import annotations

"""Build and execute the contract-first answer subgraph topology.

Topology:
START -> prepare_contract -> draft_answer -> verify_claims
verify_claims --pass--> finalize -> END
verify_claims --render_mismatch--> targeted_patch -> verify_claims (loop)
verify_claims --abort--> safe_fallback -> END

The loop implements Deterministic Patching: only bounded, rule-based edits are
allowed after verification failures. ``MAX_PATCH_ATTEMPTS`` prevents infinite
repair loops and guarantees termination.
"""

import asyncio
import hashlib
from typing import Any, Dict

import structlog
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.langgraph_v2.nodes.answer_subgraph.node_draft_answer import (
    build_low_quality_rag_fallback_text,
    node_draft_answer,
)
from app.langgraph_v2.nodes.answer_subgraph.node_finalize import node_finalize
from app.langgraph_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app.langgraph_v2.nodes.answer_subgraph.node_targeted_patch import node_targeted_patch
from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
from app.langgraph_v2.nodes.answer_subgraph.state import AnswerSubgraphState
from app.langgraph_v2.state.sealai_state import SealAIState, VerificationReport
from app.langgraph_v2.utils.assertion_cycle import stamp_patch_with_assertion_binding

logger = structlog.get_logger("langgraph_v2.answer_subgraph.builder")

MAX_PATCH_ATTEMPTS = 3
_ANSWER_SUBGRAPH_CACHE: CompiledStateGraph | None = None


def _extract_langgraph_config(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Any | None:
    config = kwargs.get("config")
    if config is not None:
        return config
    if args:
        candidate = args[0]
        if isinstance(candidate, dict):
            return candidate
    return None


def _verification_router(state: AnswerSubgraphState) -> str:
    """Route verify results to finalize, deterministic patch loop, or abort.

    Args:
        state: Current graph state after ``node_verify_claims``.

    Returns:
        Route key: ``pass``, ``render_mismatch``, or ``abort``.
    """
    report = state.system.verification_report
    if report is None:
        return "abort"
    if report.status == "pass":
        return "pass"
    failure_type = str(report.failure_type or "").lower()
    if failure_type == "render_mismatch":
        attempts = int((state.reasoning.flags or {}).get("answer_subgraph_patch_attempts") or 0)
        if attempts < MAX_PATCH_ATTEMPTS:
            return "render_mismatch"
    return "abort"


def _safe_fallback_node(state: AnswerSubgraphState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Generate a safe terminal answer when verification cannot recover.

    Args:
        state: Current graph state.
        *_args: Unused positional arguments for LangGraph compatibility.
        **_kwargs: Unused keyword arguments for LangGraph compatibility.

    Returns:
        State patch with conservative fallback text and verification metadata.
    """
    report = state.system.verification_report
    patch_attempts = int((state.reasoning.flags or {}).get("answer_subgraph_patch_attempts") or 0)
    draft_text = str(state.system.draft_text or "").strip()
    contract = state.system.answer_contract
    has_empty_context = contract is None or contract.obsolete or (
        not contract.resolved_parameters
        and not contract.calc_results
        and not contract.selected_fact_ids
    )
    has_failure_state = report is None or report.status != "pass"
    use_sidekick_fallback = (
        patch_attempts >= MAX_PATCH_ATTEMPTS
        or has_empty_context
        or has_failure_state
        or not draft_text
    )
    fallback_text = build_low_quality_rag_fallback_text(state) if use_sidekick_fallback else draft_text

    messages: list[BaseMessage] = list(state.conversation.messages or [])
    messages.append(AIMessage(content=[{"type": "text", "text": fallback_text}]))

    if report is None:
        draft_hash = hashlib.sha256(str(state.system.draft_text or "").encode()).hexdigest()
        report = VerificationReport(
            contract_hash=str((state.reasoning.flags or {}).get("answer_contract_hash") or ""),
            draft_hash=draft_hash,
            status="fail",
            failure_type="abort",
            failed_claim_spans=[{"reason": "safe_fallback_triggered"}],
        )

    logger.error(
        "answer_subgraph.safe_fallback",
        failure_type=report.failure_type,
        patch_attempts=patch_attempts,
        use_sidekick_fallback=use_sidekick_fallback,
    )
    return stamp_patch_with_assertion_binding(state, {
               "conversation": {
                   "messages": messages,
               },
               "system": {
                   "governed_output_text": fallback_text,
                   "governed_output_status": "fallback",
                   "governed_output_ready": True,
                   "final_text": fallback_text,
                   "final_answer": fallback_text,
                   "verification_report": report,
                   "error": "Answer subgraph safe fallback activated.",
               },
               "reasoning": {
                   "last_node": "node_safe_fallback",
               },
           })


def build_answer_subgraph() -> CompiledStateGraph:
    """Compile and cache the answer subgraph.

    Returns:
        Compiled state graph instance for contract-first answer generation.
    """
    global _ANSWER_SUBGRAPH_CACHE
    if _ANSWER_SUBGRAPH_CACHE is not None:
        return _ANSWER_SUBGRAPH_CACHE

    builder = StateGraph(AnswerSubgraphState)
    builder.add_node("node_prepare_contract", node_prepare_contract)
    builder.add_node("node_draft_answer", node_draft_answer)
    builder.add_node("node_verify_claims", node_verify_claims)
    builder.add_node("node_targeted_patch", node_targeted_patch)
    builder.add_node("node_finalize", node_finalize)
    builder.add_node("node_safe_fallback", _safe_fallback_node)

    builder.add_edge(START, "node_prepare_contract")
    builder.add_edge("node_prepare_contract", "node_draft_answer")
    builder.add_edge("node_draft_answer", "node_verify_claims")
    builder.add_conditional_edges(
        "node_verify_claims",
        _verification_router,
        {
            "pass": "node_finalize",
            "render_mismatch": "node_targeted_patch",
            "abort": "node_safe_fallback",
        },
    )
    builder.add_edge("node_targeted_patch", "node_verify_claims")
    builder.add_edge("node_finalize", END)
    builder.add_edge("node_safe_fallback", END)

    _ANSWER_SUBGRAPH_CACHE = builder.compile()
    return _ANSWER_SUBGRAPH_CACHE


def _as_state(value: Any) -> SealAIState:
    """Normalize dict/model values into ``SealAIState``.

    Args:
        value: Raw state-like value.

    Returns:
        Materialized ``SealAIState`` instance.
    """
    if isinstance(value, SealAIState):
        return value
    return SealAIState.model_validate(value or {})


def _extract_patch(before: SealAIState, after: SealAIState) -> Dict[str, Any]:
    """Extract changed fields between pre/post subgraph states.

    Args:
        before: State snapshot before execution.
        after: State snapshot after execution.

    Returns:
        Minimal patch containing only changed tracked fields.
    """
    tracked_fields = [
        "answer_contract",
        "draft_text",
        "draft_base_hash",
        "verification_report",
        "governed_output_text",
        "governed_output_status",
        "governed_output_ready",
        "final_text",
        "final_answer",
        "final_prompt",
        "final_prompt_metadata",
        "messages",
        "flags",
        "error",
        "phase",
        "last_node",
    ]
    patch: Dict[str, Any] = {}
    def _field_value(state: Any, field: str) -> Any:
        if isinstance(state, SealAIState):
            if field in {"answer_contract", "draft_text", "draft_base_hash", "verification_report", "governed_output_text", "governed_output_status", "governed_output_ready", "final_text", "final_answer", "final_prompt", "final_prompt_metadata", "error"}:
                return getattr(state.system, field, None)
            if field in {"flags", "phase", "last_node"}:
                return getattr(state.reasoning, field, None)
            if field == "messages":
                return getattr(state.conversation, field, None)
        return getattr(state, field, None)

    for field in tracked_fields:
        before_val = _field_value(before, field)
        after_val = _field_value(after, field)
        if after_val != before_val:
            patch[field] = after_val
    # Ensure terminal answer payload is always available to parent graph/SSE,
    # even when equality checks accidentally classify it as unchanged.
    final_text = str(_field_value(after, "final_text") or _field_value(after, "final_answer") or "").strip()
    if final_text:
        patch.setdefault("final_text", final_text)
        patch.setdefault("final_answer", final_text)
    return patch


def _deep_merge_patch(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_patch(current, value)
        else:
            merged[key] = value
    return merged


def _merge_state_patch(state: SealAIState, patch: Dict[str, Any]) -> SealAIState:
    merged = _deep_merge_patch(state.model_dump(exclude_none=False), patch)
    return _as_state(merged)


def _resolve_live_calc_tile(state: SealAIState) -> Any | None:
    """Read ``live_calc_tile`` from the current nested state contract first."""
    working_profile = getattr(state, "working_profile", None)
    tile = getattr(working_profile, "live_calc_tile", None)
    if tile is not None:
        return tile
    return getattr(state, "live_calc_tile", None)


def _build_subgraph_state_input(before: SealAIState) -> AnswerSubgraphState:
    subgraph_input = before.model_dump(exclude_none=False)
    live_calc_tile = _resolve_live_calc_tile(before)
    if live_calc_tile is not None:
        subgraph_input["live_calc_tile"] = live_calc_tile
    subgraph_input["working_profile"] = before.working_profile
    return AnswerSubgraphState.model_validate(subgraph_input)


def _run_answer_subgraph_sync(initial_state: AnswerSubgraphState, config: Any | None) -> SealAIState:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("answer_subgraph_node cannot run synchronously inside an active event loop")

    state = _as_state(initial_state)
    state = _merge_state_patch(state, node_prepare_contract(state))
    state = _merge_state_patch(state, asyncio.run(node_draft_answer(state, config=config)))

    while True:
        state = _merge_state_patch(state, node_verify_claims(state))
        route = _verification_router(AnswerSubgraphState.model_validate(state.model_dump(exclude_none=False)))
        logger.info(
            "answer_subgraph.route_selected",
            route=route,
            verification_status=getattr(state.system.verification_report, "status", None),
            failure_type=getattr(state.system.verification_report, "failure_type", None),
        )
        if route == "pass":
            state = _merge_state_patch(state, node_finalize(state))
            return state
        if route == "render_mismatch":
            state = _merge_state_patch(state, node_targeted_patch(state))
            continue
        state = _merge_state_patch(state, _safe_fallback_node(state))
        return state


async def _run_answer_subgraph_async(initial_state: AnswerSubgraphState, config: Any | None) -> SealAIState:
    state = _as_state(initial_state)
    state = _merge_state_patch(state, node_prepare_contract(state))
    state = _merge_state_patch(state, await node_draft_answer(state, config=config))

    while True:
        state = _merge_state_patch(state, node_verify_claims(state))
        route = _verification_router(AnswerSubgraphState.model_validate(state.model_dump(exclude_none=False)))
        logger.info(
            "answer_subgraph.route_selected",
            route=route,
            verification_status=getattr(state.system.verification_report, "status", None),
            failure_type=getattr(state.system.verification_report, "failure_type", None),
        )
        if route == "pass":
            state = _merge_state_patch(state, node_finalize(state))
            return state
        if route == "render_mismatch":
            state = _merge_state_patch(state, node_targeted_patch(state))
            continue
        state = _merge_state_patch(state, _safe_fallback_node(state))
        return state


def answer_subgraph_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Run the answer subgraph synchronously and return a state patch.

    Args:
        state: Current graph state.
        *_args: Unused positional arguments for LangGraph compatibility.
        **_kwargs: Unused keyword arguments for LangGraph compatibility.

    Returns:
        Patch with changed output fields from subgraph execution.
    """
    before = _as_state(state)
    config = _extract_langgraph_config(_args, _kwargs)
    logger.info("answer_subgraph_node.start", initial_last_node=before.reasoning.last_node)
    after = _run_answer_subgraph_sync(_build_subgraph_state_input(before), config)
    patch = _extract_patch(before, after)
    patch["last_node"] = "answer_subgraph_node"
    logger.info("answer_subgraph_node.completed", patch_keys=sorted(patch.keys()))
    return patch


async def answer_subgraph_node_async(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Run the answer subgraph asynchronously and return a state patch.

    Args:
        state: Current graph state.
        *_args: Unused positional arguments for LangGraph compatibility.
        **_kwargs: Unused keyword arguments for LangGraph compatibility.

    Returns:
        Patch with changed output fields from async subgraph execution.
    """
    before = _as_state(state)
    config = _extract_langgraph_config(_args, _kwargs)
    logger.info("answer_subgraph_node_async.start", initial_last_node=before.reasoning.last_node)
    after = await _run_answer_subgraph_async(_build_subgraph_state_input(before), config)
    patch = _extract_patch(before, after)
    patch["last_node"] = "answer_subgraph_node"
    logger.info("answer_subgraph_node_async.completed", patch_keys=sorted(patch.keys()))
    return patch


__all__ = [
    "build_answer_subgraph",
    "answer_subgraph_node",
    "answer_subgraph_node_async",
]
