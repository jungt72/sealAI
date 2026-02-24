from __future__ import annotations

import hashlib
from typing import Any, Dict

import structlog
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.langgraph_v2.nodes.answer_subgraph.node_draft_answer import node_draft_answer
from app.langgraph_v2.nodes.answer_subgraph.node_finalize import node_finalize
from app.langgraph_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app.langgraph_v2.nodes.answer_subgraph.node_targeted_patch import node_targeted_patch
from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
from app.langgraph_v2.state.sealai_state import SealAIState, VerificationReport

logger = structlog.get_logger("langgraph_v2.answer_subgraph.builder")

MAX_PATCH_ATTEMPTS = 3
_ANSWER_SUBGRAPH_CACHE: CompiledStateGraph | None = None


def _verification_router(state: SealAIState) -> str:
    report = state.verification_report
    if report is None:
        return "abort"
    if report.status == "pass":
        return "pass"
    failure_type = str(report.failure_type or "").lower()
    if failure_type == "render_mismatch":
        attempts = int((state.flags or {}).get("answer_subgraph_patch_attempts") or 0)
        if attempts < MAX_PATCH_ATTEMPTS:
            return "render_mismatch"
    return "abort"


def _safe_fallback_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    fallback_text = str(state.draft_text or "").strip()
    if not fallback_text:
        fallback_text = "Unable to produce a verified answer. Please request clarification."

    messages: list[BaseMessage] = list(state.messages or [])
    messages.append(AIMessage(content=[{"type": "text", "text": fallback_text}]))

    report = state.verification_report
    if report is None:
        draft_hash = hashlib.sha256(str(state.draft_text or "").encode()).hexdigest()
        report = VerificationReport(
            contract_hash=str((state.flags or {}).get("answer_contract_hash") or ""),
            draft_hash=draft_hash,
            status="fail",
            failure_type="abort",
            failed_claim_spans=[{"reason": "safe_fallback_triggered"}],
        )

    logger.error(
        "answer_subgraph.safe_fallback",
        failure_type=report.failure_type,
        patch_attempts=int((state.flags or {}).get("answer_subgraph_patch_attempts") or 0),
    )
    return {
        "messages": messages,
        "final_text": fallback_text,
        "final_answer": fallback_text,
        "verification_report": report,
        "error": "Answer subgraph safe fallback activated.",
        "last_node": "node_safe_fallback",
    }


def build_answer_subgraph() -> CompiledStateGraph:
    global _ANSWER_SUBGRAPH_CACHE
    if _ANSWER_SUBGRAPH_CACHE is not None:
        return _ANSWER_SUBGRAPH_CACHE

    builder = StateGraph(SealAIState)
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
    if isinstance(value, SealAIState):
        return value
    return SealAIState.model_validate(value or {})


def _extract_patch(before: SealAIState, after: SealAIState) -> Dict[str, Any]:
    tracked_fields = [
        "answer_contract",
        "draft_text",
        "draft_base_hash",
        "verification_report",
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
    for field in tracked_fields:
        before_val = getattr(before, field, None)
        after_val = getattr(after, field, None)
        if after_val != before_val:
            patch[field] = after_val
    return patch


def answer_subgraph_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    before = _as_state(state)
    subgraph = build_answer_subgraph()
    result = subgraph.invoke(before)
    after = _as_state(result)
    patch = _extract_patch(before, after)
    patch.setdefault("last_node", "answer_subgraph_node")
    logger.info("answer_subgraph_node.completed", patch_keys=sorted(patch.keys()))
    return patch


async def answer_subgraph_node_async(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    before = _as_state(state)
    subgraph = build_answer_subgraph()
    result = await subgraph.ainvoke(before)
    after = _as_state(result)
    patch = _extract_patch(before, after)
    patch.setdefault("last_node", "answer_subgraph_node")
    logger.info("answer_subgraph_node_async.completed", patch_keys=sorted(patch.keys()))
    return patch


__all__ = [
    "build_answer_subgraph",
    "answer_subgraph_node",
    "answer_subgraph_node_async",
]

