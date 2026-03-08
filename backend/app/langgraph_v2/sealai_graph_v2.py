"""Production LangGraph v2 topology and graph helpers.

The slow-brain mainline follows the v13 parallel pattern:
frontdoor -> P1 context extraction -> material/mechanical fan-out -> merge ->
answer quality gate.

The graph keeps a small compatibility surface for existing supervisor- and
RAG-related nodes, but the old sequential P1 -> P4 -> Knowledge path is no
longer the primary engineering route.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.core.memory import get_postgres_store
from app.langgraph_v2.agents.knowledge_agent import KnowledgeAgent
from app.langgraph_v2.nodes.answer_subgraph import answer_subgraph_node, answer_subgraph_node_async
from app.langgraph_v2.nodes.combinatorial_chemistry_guard import combinatorial_chemistry_guard_node
from app.langgraph_v2.nodes.node_router import node_router
from app.langgraph_v2.nodes.nodes_flows import (
    leakage_troubleshooting_node,
    material_agent_node,
    rag_support_node,
)
from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node
from app.langgraph_v2.nodes.nodes_confirm import (
    snapshot_confirmation_node,
    rfq_confirmation_node,
    draft_conflict_resolution_node,
)
from app.langgraph_v2.nodes.nodes_supervisor import (
    aggregator_node,
    calculator_agent_node,
    pricing_agent_node,
    safety_agent_node,
    supervisor_policy_node,
)
from app.langgraph_v2.nodes.profile_loader import profile_loader_node
from app.langgraph_v2.nodes.reasoning_core_node import reasoning_core_node
from app.langgraph_v2.nodes.request_clarification import request_clarification_node as _request_clarification_impl
from app.langgraph_v2.nodes.response_node import response_node
from app.langgraph_v2.nodes.safety_synonym_guard_node import safety_synonym_guard_node
from app.langgraph_v2.nodes.worm_evidence_node import worm_evidence_node
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer_async
from app.services.rag.nodes.p1_context import node_p1_context
from app.services.rag.nodes.p2_rag_lookup import node_p2_rag_lookup, node_p2_rag_synthesize
from app.services.rag.nodes.p4_live_calc import node_p4_live_calc
from app.services.rag.nodes.p4a_extract import node_p4a_extract

LANGSMITH_RUN_NAME = "sealai_langgraph_v2"
LANGSMITH_TRACE_TAGS: List[str] = [
    "sealai",
    "langgraph_v2",
    "phase_0_observability",
    "audit_schema_v1",
    "v13_parallel_pattern",
]

_GRAPH_LOCK = asyncio.Lock()
_GRAPH_CACHE: CompiledStateGraph | None = None


def _merge_nested_dict(base: Dict[str, Any] | None, patch: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in dict(patch or {}).items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict) and value:
            merged[key] = _merge_nested_dict(current, value)
        else:
            merged[key] = value
    return merged


def _node_router_dispatch(_state: SealAIState) -> str:
    """Route all entry classifications into the v13 frontdoor path."""
    return "frontdoor"


async def _node_router_dispatch_async(state: SealAIState) -> str:
    return _node_router_dispatch(state)


def _frontdoor_dispatch(state: SealAIState) -> str:
    """Route material-research turns into the existing supervisor/material path."""
    flags = dict(state.reasoning.flags or {})
    frontdoor_intent_category = str(flags.get("frontdoor_intent_category") or "").strip().upper()
    raw_intent = state.conversation.intent
    intent_goal = (
        str(raw_intent or "").strip().lower()
        if isinstance(raw_intent, str)
        else str(getattr(raw_intent, "goal", "") or "").strip().lower()
    )
    if (
        frontdoor_intent_category == "MATERIAL_RESEARCH"
        or (
            bool(state.reasoning.requires_rag or state.reasoning.need_sources)
            and intent_goal == "explanation_or_comparison"
        )
    ):
        return "knowledge"
    return "analysis"


async def _frontdoor_dispatch_async(state: SealAIState) -> str:
    return _frontdoor_dispatch(state)


def _knowledge_followup_dispatch(state: SealAIState) -> str:
    final_text = str(state.system.final_text or state.system.final_answer or "").strip()
    if not final_text:
        return "finalize"

    flags = dict(state.reasoning.flags or {})
    raw_intent = state.conversation.intent
    intent_goal = (
        str(raw_intent or "").strip().lower()
        if isinstance(raw_intent, str)
        else str(getattr(raw_intent, "goal", "") or "").strip().lower()
    )
    intent_category = (
        str(
            getattr(raw_intent, "intent_category", "")
            if raw_intent is not None and not isinstance(raw_intent, str)
            else ""
        ).strip().upper()
        or str(flags.get("frontdoor_intent_category") or "").strip().upper()
    )

    is_simple_knowledge = intent_goal in {"explanation_or_comparison", "material_research", "smalltalk"}
    is_material_research = intent_category == "MATERIAL_RESEARCH"
    return "response" if (is_simple_knowledge or is_material_research) else "finalize"


async def _material_analysis_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Failure-tolerant material branch for the slow-brain fan-out."""
    try:
        patch = material_agent_node(state, *_args, **_kwargs)
    except Exception as exc:
        return {
            "reasoning": {
                "diagnostic_data": {
                    "parallel_branches": {
                        "material_analysis": {
                            "status": "error",
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        }
                    }
                },
                "last_node": "material_analysis_node",
            }
        }

    reasoning_patch = patch.get("reasoning") if isinstance(patch.get("reasoning"), dict) else {}
    next_reasoning = dict(reasoning_patch)
    next_reasoning["diagnostic_data"] = _merge_nested_dict(
        reasoning_patch.get("diagnostic_data"),
        {"parallel_branches": {"material_analysis": {"status": "ok"}}},
    )
    next_reasoning["last_node"] = "material_analysis_node"
    patch["reasoning"] = next_reasoning
    return patch


async def _mechanical_analysis_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Failure-tolerant mechanical/tribology branch for the slow-brain fan-out."""
    try:
        patch = node_p4_live_calc(state, *_args, **_kwargs)
    except Exception as exc:
        return {
            "reasoning": {
                "diagnostic_data": {
                    "parallel_branches": {
                        "mechanical_analysis": {
                            "status": "error",
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        }
                    }
                },
                "last_node": "mechanical_analysis_node",
            }
        }

    reasoning_patch = patch.get("reasoning") if isinstance(patch.get("reasoning"), dict) else {}
    next_reasoning = dict(reasoning_patch)
    next_reasoning["diagnostic_data"] = _merge_nested_dict(
        reasoning_patch.get("diagnostic_data"),
        {"parallel_branches": {"mechanical_analysis": {"status": "ok"}}},
    )
    next_reasoning["last_node"] = "mechanical_analysis_node"
    patch["reasoning"] = next_reasoning
    return patch


def _merge_analysis_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Fan-in node that converts two branch patches into one quality-gate payload."""
    diagnostic_data = dict(state.reasoning.diagnostic_data or {})
    parallel_branches = (
        dict(diagnostic_data.get("parallel_branches") or {})
        if isinstance(diagnostic_data.get("parallel_branches"), dict)
        else {}
    )
    material_status = (
        parallel_branches.get("material_analysis")
        if isinstance(parallel_branches.get("material_analysis"), dict)
        else {}
    )
    mechanical_status = (
        parallel_branches.get("mechanical_analysis")
        if isinstance(parallel_branches.get("mechanical_analysis"), dict)
        else {}
    )
    partial_failure = any(
        str(branch.get("status") or "").lower() == "error"
        for branch in (material_status, mechanical_status)
    )

    working_memory = state.reasoning.working_memory
    design_notes = getattr(working_memory, "design_notes", {}) if working_memory else {}
    merged_design_notes = _merge_nested_dict(
        dict(design_notes or {}),
        {
            "parallel_analysis": {
                "material_analysis": material_status or {"status": "missing"},
                "mechanical_analysis": mechanical_status or {"status": "missing"},
                "partial_failure": partial_failure,
            }
        },
    )

    patch = {
        "reasoning": {
            "diagnostic_data": {
                "parallel_merge": {
                    "status": "partial_failure" if partial_failure else "ok",
                    "material_analysis": material_status or {"status": "missing"},
                    "mechanical_analysis": mechanical_status or {"status": "missing"},
                }
            },
            "working_memory": {"design_notes": merged_design_notes},
            "last_node": "merge_analysis_node",
        }
    }
    if partial_failure:
        patch["system"] = {"error": "partial_expert_failure"}
    return patch


async def _knowledge_agent_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return await KnowledgeAgent().run(state, llm=None)


async def _troubleshooting_wizard_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Compatibility wrapper for troubleshooting routes."""
    return await leakage_troubleshooting_node(state, *_args, **_kwargs)


def _human_review_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Terminal HITL handoff node used by deterministic safety guards."""
    text = str(state.system.final_answer or state.system.final_text or "").strip()
    if not text:
        text = "Die Anfrage wurde zur sicherheitsrelevanten Fachpruefung an einen Human Reviewer uebergeben."
    return {
        "conversation": {
            "messages": [AIMessage(content=[{"type": "text", "text": text}])],
        },
        "reasoning": {
            "last_node": "human_review_node",
        },
        "system": {
            "final_text": text,
            "final_answer": text,
        },
    }


async def _request_clarification_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Normalize clarification output into a terminal user-visible response."""
    patch = await _request_clarification_impl(state)
    system_patch = patch.get("system") if isinstance(patch.get("system"), dict) else {}
    reasoning_patch = patch.get("reasoning") if isinstance(patch.get("reasoning"), dict) else {}
    text = str(system_patch.get("final_answer") or system_patch.get("final_text") or "").strip()
    if not text:
        text = "Ich benoetige zusaetzliche Informationen, um die Anfrage belastbar zu beantworten."

    conversation_patch = patch.get("conversation") if isinstance(patch.get("conversation"), dict) else {}
    messages = list(conversation_patch.get("messages") or [])
    messages.append(AIMessage(content=[{"type": "text", "text": text}]))

    patch["conversation"] = {"messages": messages}
    patch["reasoning"] = {
        **reasoning_patch,
        "last_node": "request_clarification_node",
    }
    patch["system"] = {
        **system_patch,
        "final_text": text,
        "final_answer": text,
    }
    return patch


def create_sealai_graph_v2(
    checkpointer: BaseCheckpointSaver,
    store: BaseStore,
    *,
    require_async: bool = True,
    return_builder: bool = False,
) -> CompiledStateGraph | StateGraph:
    builder = StateGraph(SealAIState)
    node_router_dispatch = _node_router_dispatch_async if require_async else _node_router_dispatch
    frontdoor_dispatch = _frontdoor_dispatch_async if require_async else _frontdoor_dispatch

    builder.add_node("profile_loader_node", profile_loader_node)
    builder.add_node("safety_synonym_guard_node", safety_synonym_guard_node)
    builder.add_node("combinatorial_chemistry_guard_node", combinatorial_chemistry_guard_node)
    builder.add_node("human_review_node", _human_review_node)
    builder.add_node("node_router", node_router)
    builder.add_node("frontdoor_discovery_node", frontdoor_discovery_node)
    builder.add_node("node_p1_context", node_p1_context)
    builder.add_node("request_clarification_node", _request_clarification_node)
    builder.add_node("reasoning_core_node", reasoning_core_node)

    builder.add_node("material_analysis_node", _material_analysis_node)
    builder.add_node("mechanical_analysis_node", _mechanical_analysis_node)
    builder.add_node("merge_analysis_node", _merge_analysis_node)

    builder.add_node("material_agent", material_agent_node)
    builder.add_node("calculator_agent", calculator_agent_node)
    builder.add_node("pricing_agent", pricing_agent_node)
    builder.add_node("safety_agent", safety_agent_node)
    builder.add_node("aggregator_node", aggregator_node)
    builder.add_node("supervisor_policy_node", supervisor_policy_node)
    builder.add_node("knowledge_agent_node", _knowledge_agent_node)
    builder.add_node("troubleshooting_wizard_node", _troubleshooting_wizard_node)
    builder.add_node("rag_support_node", rag_support_node)

    builder.add_node("node_p2_rag_lookup", node_p2_rag_lookup)
    builder.add_node("node_p2_rag_synthesize", node_p2_rag_synthesize)
    builder.add_node("node_p4a_extract", node_p4a_extract)

    builder.add_node(
        "final_answer_node",
        answer_subgraph_node_async if require_async else answer_subgraph_node,
    )
    builder.add_node("response_node", response_node)
    builder.add_node("worm_evidence_node", worm_evidence_node)
    builder.add_node("snapshot_confirmation_node", snapshot_confirmation_node)
    builder.add_node("rfq_confirmation_node", rfq_confirmation_node)
    builder.add_node("draft_conflict_resolution_node", draft_conflict_resolution_node)

    builder.add_edge(START, "profile_loader_node")
    builder.add_edge("profile_loader_node", "safety_synonym_guard_node")
    builder.add_edge("safety_synonym_guard_node", "combinatorial_chemistry_guard_node")
    builder.add_edge("human_review_node", "worm_evidence_node")
    builder.add_edge("combinatorial_chemistry_guard_node", "node_router")
    builder.add_conditional_edges(
        "node_router",
        node_router_dispatch,
        {"frontdoor": "frontdoor_discovery_node"},
    )

    builder.add_conditional_edges(
        "frontdoor_discovery_node",
        frontdoor_dispatch,
        {
            "knowledge": "supervisor_policy_node",
            "analysis": "node_p1_context",
        },
    )
    builder.add_edge("node_p1_context", "material_analysis_node")
    builder.add_edge("node_p1_context", "mechanical_analysis_node")
    builder.add_edge("material_analysis_node", "merge_analysis_node")
    builder.add_edge("mechanical_analysis_node", "merge_analysis_node")
    builder.add_edge("merge_analysis_node", "final_answer_node")
    builder.add_edge("request_clarification_node", "worm_evidence_node")
    builder.add_edge("reasoning_core_node", "final_answer_node")

    builder.add_edge("calculator_agent", "aggregator_node")
    builder.add_edge("material_agent", "aggregator_node")
    builder.add_edge("pricing_agent", "aggregator_node")
    builder.add_edge("safety_agent", "aggregator_node")
    builder.add_edge("aggregator_node", "final_answer_node")
    builder.add_conditional_edges(
        "knowledge_agent_node",
        _knowledge_followup_dispatch,
        {
            "response": "response_node",
            "finalize": "final_answer_node",
        },
    )
    builder.add_edge("troubleshooting_wizard_node", "knowledge_agent_node")
    builder.add_edge("rag_support_node", "final_answer_node")

    builder.add_edge("node_p2_rag_lookup", "node_p2_rag_synthesize")
    builder.add_edge("node_p2_rag_synthesize", "node_p4a_extract")
    builder.add_edge("node_p4a_extract", "final_answer_node")

    builder.add_edge("final_answer_node", "response_node")
    builder.add_edge("snapshot_confirmation_node", "final_answer_node")
    builder.add_edge("rfq_confirmation_node", "final_answer_node")
    builder.add_edge("draft_conflict_resolution_node", "final_answer_node")
    builder.add_edge("response_node", "worm_evidence_node")
    builder.add_edge("worm_evidence_node", END)

    if return_builder:
        return builder

    compiled = builder.compile(
        checkpointer=checkpointer,
        store=store,
        name=LANGSMITH_RUN_NAME,
    )
    return compiled.with_config(
        {
            "run_name": LANGSMITH_RUN_NAME,
            "tags": list(LANGSMITH_TRACE_TAGS),
            "metadata": {
                "observability_phase": "phase_0",
                "audit_schema": "evidence_bundle_v1",
            },
        }
    )


def scope_v2_thread_id(*, thread_id: str, user_id: str) -> str:
    """Return the canonical user-scoped thread id used for checkpoints."""
    raw_thread_id = str(thread_id or "").strip()
    scoped_user_id = str(user_id or "").strip()
    if not raw_thread_id or not scoped_user_id:
        return raw_thread_id

    prefix, separator, suffix = raw_thread_id.partition(":")
    if not separator:
        return f"{scoped_user_id}:{raw_thread_id}"
    if prefix == scoped_user_id:
        return raw_thread_id
    if not suffix:
        return f"{scoped_user_id}:{prefix}"
    return f"{scoped_user_id}:{suffix}"


async def _build_graph(require_async: bool = True) -> CompiledStateGraph:
    checkpointer = await make_v2_checkpointer_async(require_async=require_async)
    store = await get_postgres_store()
    return create_sealai_graph_v2(
        checkpointer=checkpointer,
        store=store,
        require_async=require_async,
    )


async def get_sealai_graph_v2() -> CompiledStateGraph:
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        async with _GRAPH_LOCK:
            if _GRAPH_CACHE is None:
                _GRAPH_CACHE = await _build_graph(require_async=True)
    return _GRAPH_CACHE


def build_v2_config(*, thread_id: str, user_id: str) -> Dict[str, Any]:
    scoped_thread_id = scope_v2_thread_id(thread_id=thread_id, user_id=user_id)
    run_id = str(uuid.uuid4())
    return {
        "configurable": {
            "thread_id": scoped_thread_id,
            "user_id": user_id,
            "checkpoint_ns": "",
        },
        "metadata": {
            "thread_id": thread_id,
            "scoped_thread_id": scoped_thread_id,
            "user_id": user_id,
            "run_id": run_id,
        },
        "tags": list(LANGSMITH_TRACE_TAGS),
        "run_name": LANGSMITH_RUN_NAME,
        "recursion_limit": 80,
    }


__all__ = [
    "build_v2_config",
    "create_sealai_graph_v2",
    "get_sealai_graph_v2",
    "scope_v2_thread_id",
]
