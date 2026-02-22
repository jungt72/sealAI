"""Rebuilt LangGraph v2 Definition for SealAI with new frontdoor/supervisor topology."""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Dict, List
import json

import structlog
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableParallel
from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from app.core.memory import get_postgres_store
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer_async
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.llm_factory import LazyChatOpenAI
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.threading import stable_thread_key
from app.langgraph_v2.utils.state_debug import log_state_debug
from app.mcp.knowledge_tool import discover_tools_for_scopes

logger = structlog.get_logger("langgraph_v2.graph")


# ---------------------------------------------------------------------------
# Node Imports
# ---------------------------------------------------------------------------

from app.langgraph_v2.nodes.profile_loader import profile_loader_node
from app.langgraph_v2.nodes.node_router import node_router
from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node
from app.langgraph_v2.nodes.nodes_confirm import confirm_checkpoint_node, confirm_recommendation_node
from app.langgraph_v2.nodes.nodes_supervisor import (
    aggregator_node,
    calculator_agent_node,
    panel_calculator_node,
    panel_material_node,
    pricing_agent_node,
    safety_agent_node,
    supervisor_policy_node,
)
from app.langgraph_v2.nodes.reducer import reducer_node
from app.langgraph_v2.nodes.response_node import response_node
from app.langgraph_v2.nodes.nodes_resume import (
    confirm_reject_node,
    confirm_resume_node,
    resume_router_node,
)
from app.langgraph_v2.nodes.nodes_error import smalltalk_node
from app.langgraph_v2.nodes.orchestrator import orchestrator_node
from app.langgraph_v2.nodes.nodes_flows import (
    build_final_answer_context,
    map_final_answer_to_state,
    material_agent_node,
    material_comparison_node,
    calculator_node,
    critical_review_node,
    discovery_schema_node,
    leakage_troubleshooting_node,
    parameter_check_node,
    product_explainer_node,
    product_match_node,
    profile_agent_node,
    rag_support_node,
    render_final_answer_draft,
    prepare_final_answer_llm_payload,
    troubleshooting_explainer_node,
    troubleshooting_pattern_node,
    validation_agent_node,
)


# ---------------------------------------------------------------------------
# State Helper
# ---------------------------------------------------------------------------


def _ensure_state_model(state: Any) -> SealAIState:
    """Akzeptiert dict/SealAIState und gibt garantiert ein SealAIState-Objekt zurück."""
    if isinstance(state, SealAIState):
        return state
    return SealAIState.model_validate(state or {})


# ---------------------------------------------------------------------------
# Final-Answer: Jinja-Templates & Context
# ---------------------------------------------------------------------------

SMALLTALK_TEMPLATE = "final_answer_smalltalk_v2.j2"
DISCOVERY_TEMPLATE = "final_answer_discovery_v2.j2"
RECOMMENDATION_TEMPLATE = "final_answer_recommendation_v2.j2"
EXPLANATION_TEMPLATE = "final_answer_explanation_v2.j2"
TROUBLESHOOTING_TEMPLATE = "final_answer_troubleshooting_v2.j2"
OUT_OF_SCOPE_TEMPLATE = "final_answer_out_of_scope_v2.j2"
SAFETY_CHECK_TEMPLATE = "check_1.1.0.j2"
SAFETY_CHECK_VERSION = "check_1.1.0"


def _select_final_answer_template(goal: str | None, recommendation_go: bool) -> str:
    if goal == "smalltalk":
        return SMALLTALK_TEMPLATE
    if goal == "design_recommendation":
        return RECOMMENDATION_TEMPLATE if recommendation_go else DISCOVERY_TEMPLATE
    if goal == "explanation_or_comparison":
        return EXPLANATION_TEMPLATE
    if goal == "troubleshooting_leakage":
        return TROUBLESHOOTING_TEMPLATE
    if goal == "out_of_scope":
        return OUT_OF_SCOPE_TEMPLATE
    return DISCOVERY_TEMPLATE


def _build_final_answer_template_context(
    state: SealAIState,
    base_context: Dict[str, Any],
    *,
    draft: str,
    goal: str,
    coverage_score: float,
    coverage_gaps: List[str],
    coverage_gaps_text: str,
    recommendation_ready: bool,
    recommendation_go: bool,
    latest_user_text: str | None,
    is_micro_smalltalk: bool,
) -> Dict[str, Any]:
    parameters = state.parameters.as_dict()
    calc_results = state.calc_results.model_dump(exclude_none=True) if state.calc_results else {}
    recommendation = state.recommendation.model_dump(exclude_none=True) if state.recommendation else {}
    working_memory = state.working_memory.model_dump(exclude_none=True) if state.working_memory else {}
    sources = [src.model_dump(exclude_none=True) for src in (state.sources or [])]
    template_context = dict(base_context or {})
    available_mcp_tools = discover_mcp_tools_for_state(state)
    template_context.update(
        {
            "draft": draft,
            "goal": goal,
            "coverage_score": coverage_score,
            "coverage_gaps": coverage_gaps,
            "coverage_gaps_text": coverage_gaps_text,
            "recommendation_ready": recommendation_ready,
            "recommendation_go": recommendation_go,
            "user_text": latest_user_text,
            "latest_user_text": latest_user_text,
            "is_micro_smalltalk": is_micro_smalltalk,
            "discovery_summary": state.discovery_summary,
            "discovery_missing": state.discovery_missing or [],
            "discovery_coverage": state.discovery_coverage,
            "application_category": state.application_category,
            "motion_type": state.motion_type,
            "seal_family": state.seal_family,
            "plan": state.plan or {},
            "working_memory": working_memory,
            "sources": sources,
            "recommendation": recommendation,
            "calc_results": calc_results,
            "intent_high_impact_gaps": getattr(state.intent, "high_impact_gaps", []),
            "parameters": parameters,
            "flags": state.flags or {},
            "user_context": getattr(state, "user_context", {}) or {}, # INJECTED
            "available_mcp_tools": available_mcp_tools,
        }
    )
    return template_context


def _normalize_smalltalk_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = text.strip().lower()
    normalized = re.sub(r"[!?.]+$", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _collect_retrieved_facts(template_context: Dict[str, Any]) -> str:
    blocks: List[str] = []
    seen: set[str] = set()

    def _append(value: Any) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        blocks.append(text)

    _append(template_context.get("context"))
    _append(template_context.get("material_retrieved_context"))

    working_memory = template_context.get("working_memory")
    if isinstance(working_memory, dict):
        panel_material = working_memory.get("panel_material")
        if isinstance(panel_material, dict):
            _append(panel_material.get("rag_context"))
            _append(panel_material.get("reducer_context"))
        comparison_notes = working_memory.get("comparison_notes")
        if isinstance(comparison_notes, dict):
            _append(comparison_notes.get("rag_context"))

    return "\n\n".join(blocks).strip()


def _render_final_prompt_package(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build system prompt + metadata package for final answer generation.
    """
    goal = payload["template_context"].get("goal")
    template_name = _select_final_answer_template(
        goal,
        payload["template_context"].get("recommendation_go", False),
    )
    payload["template_context"].setdefault("is_micro_smalltalk", False)
    plan = payload["template_context"].get("plan") or {}
    style_profile = (plan.get("style_profile") or "senior_sealing_engineer_de") if isinstance(plan, dict) else "senior_sealing_engineer_de"
    include_policy = str(style_profile).strip().lower() not in {"off", "none", "disabled", "disable"}

    prompt_text = render_template(template_name, payload["template_context"])
    try:
        safety_check_text = render_template(SAFETY_CHECK_TEMPLATE, {})
    except FileNotFoundError:
        safety_check_text = ""
    safety_check_text = (safety_check_text or "").strip()
    if safety_check_text:
        prompt_text = f"{safety_check_text}\n\n{(prompt_text or '').strip()}"
    if include_policy:
        policy_text = render_template("senior_policy_de.j2", {})
        policy_text = (policy_text or "").strip()
        if policy_text:
            prompt_text = f"{policy_text}\n\n{(prompt_text or '').strip()}"
    plan = payload["template_context"].get("plan") or {}
    if isinstance(plan, dict):
        raw_system_instructions = plan.get("system_instructions")
        if isinstance(raw_system_instructions, list):
            cleaned = [str(item).strip() for item in raw_system_instructions if str(item).strip()]
            if cleaned:
                prompt_text = f"{prompt_text}\n\n" + "\n".join(cleaned)

    state: Dict[str, str] = {}
    retrieved_chunks = _collect_retrieved_facts(payload["template_context"])
    if retrieved_chunks:
        state["context"] = retrieved_chunks
    print(f"!!! FINAL LLM CONTEXT PAYLOAD: {state.get('context', 'EMPTY')} !!!")
    prompt_text = (
        f"{prompt_text}\n\n"
        "### BEANTWORTUNGS-REGELN (Blueprint v4.1):\n"
        "1. Beantworte die Anfrage basierend auf dem bereitgestellten RAG-KONTEXT.\n"
        "2. GROUNDED REASONING: Du darfst technische Schlussfolgerungen ziehen und Informationen aus verschiedenen Chunks kombinieren, "
        "sofern sie sich logisch aus dem Text ableiten lassen.\n"
        "3. KEINE HALLUZINATIONEN: Erfinde niemals Spezifikationen, Werte oder Materialeigenschaften, die nicht im Kontext erwähnt werden.\n"
        "4. Falls der Kontext absolut keine relevanten Informationen enthält, sage: 'Ich habe in der Datenbank derzeit keine spezifischen Details dazu gefunden.'"
    )
    if state.get("context"):
        prompt_text = f"{prompt_text}\n\nRETRIEVED KNOWLEDGE BASE FACTS:\n{state['context']}"
    else:
        # We still explicitly label empty context but the reasoning logic handles the "no info" message
        prompt_text = f"{prompt_text}\n\nRETRIEVED KNOWLEDGE BASE FACTS:\n[EMPTY]"

    # BaseStore User Context Injection
    user_context = payload["template_context"].get("user_context")
    if user_context:
        context_str = json.dumps(user_context, indent=2, ensure_ascii=False)
        prompt_text = f"{prompt_text}\n\nUSER CONTEXT (LONG-TERM MEMORY):\n{context_str}"

    available_tools = payload["template_context"].get("available_mcp_tools") or []
    if isinstance(available_tools, list) and available_tools:
        lines = ["MCP TOOLS AVAILABLE TO THIS USER:"]
        for item in available_tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            description = str(item.get("description") or "").strip()
            lines.append(f"- {name}: {description}")
        if len(lines) > 1:
            prompt_text = f"{prompt_text}\n\n" + "\n".join(lines)

    meta = payload.get("meta") if isinstance(payload, dict) else None
    if isinstance(meta, dict):
        logger.info(
            "final_prompt_selected",
            goal=goal,
            selected_template_name=template_name,
            safety_check_version=SAFETY_CHECK_VERSION,
            senior_policy_enabled=bool(include_policy),
            phase=meta.get("phase"),
            last_node=meta.get("last_node"),
            run_id=meta.get("run_id"),
            thread_id=meta.get("thread_id"),
        )
    messages: List[BaseMessage] = [SystemMessage(content=prompt_text)]
    messages.extend(list(payload.get("messages") or []))
    return {
        "state": payload.get("state"),
        "messages": messages,
        "prompt_text": prompt_text,
        "prompt_metadata": {
            "selected_template_name": template_name,
            "prompt_version": SAFETY_CHECK_VERSION,
            "safety_check_template": SAFETY_CHECK_TEMPLATE,
            "senior_policy_enabled": bool(include_policy),
        },
    }


def _render_final_prompt_messages(payload: Dict[str, Any]) -> List[BaseMessage]:
    package = _render_final_prompt_package(payload)
    return list(package.get("messages") or [])


def _extract_auth_scopes_from_state(state: SealAIState) -> List[str]:
    user_context = getattr(state, "user_context", {}) or {}
    raw_scopes = user_context.get("auth_scopes")
    if raw_scopes is None:
        return []
    if isinstance(raw_scopes, str):
        return [token for token in raw_scopes.replace(",", " ").split() if token]
    if isinstance(raw_scopes, list):
        return [str(token).strip() for token in raw_scopes if str(token).strip()]
    return []


def discover_mcp_tools_for_state(state: SealAIState) -> List[Dict[str, Any]]:
    auth_scopes = _extract_auth_scopes_from_state(state)
    tools = discover_tools_for_scopes(auth_scopes)
    logger.info(
        "mcp_tool_discovery",
        scope_count=len(auth_scopes),
        scopes=sorted(set(auth_scopes)),
        matched_scope_count=len(set(auth_scopes) & {"mcp:pim:read", "mcp:knowledge:read"}),
        tool_count=len(tools),
        tools=[str(tool.get("name") or "") for tool in tools if isinstance(tool, dict)],
    )
    return tools


def _build_final_answer_chain() -> Any:
    llm = LazyChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
        cache=False,
        max_tokens=800,
        streaming=True,
    )

    output_parser = StrOutputParser()

    def _prepare_inputs(state: Any) -> Dict[str, Any]:
        s = _ensure_state_model(state)
        messages = list(s.messages or [])
        log_state_debug("final_answer_node", s)

        context = build_final_answer_context(s)
        draft = render_final_answer_draft(context)

        goal = getattr(s.intent, "goal", "smalltalk") if s.intent else "smalltalk"
        ready = bool(getattr(s, "recommendation_ready", False))
        go = bool(getattr(s, "recommendation_go", False))

        coverage_score = (getattr(s, "coverage_score", 0.0) or 0.0)
        coverage_gaps = getattr(s, "coverage_gaps", []) or []
        coverage_gaps_text = ", ".join(str(item) for item in coverage_gaps if item)
        coverage_gaps_text = coverage_gaps_text or "keine"

        user_text = latest_user_text(messages)
        user_text_norm = _normalize_smalltalk_text(user_text)
        micro_greetings = {
            "hallo",
            "hi",
            "hey",
            "moin",
            "guten morgen",
            "guten tag",
            "guten abend",
            "servus",
        }
        is_micro_smalltalk = bool(
            goal == "smalltalk"
            and (len(user_text_norm) <= 12 or user_text_norm in micro_greetings)
        )

        template_context = _build_final_answer_template_context(
            state=s,
            base_context=context,
            draft=draft,
            goal=goal,
            coverage_score=coverage_score,
            coverage_gaps=coverage_gaps,
            coverage_gaps_text=coverage_gaps_text,
            recommendation_ready=ready,
            recommendation_go=go,
            latest_user_text=user_text,
            is_micro_smalltalk=is_micro_smalltalk,
        )
        template_context["user_text_norm"] = user_text_norm
        template_context["is_micro_smalltalk"] = is_micro_smalltalk
        return {
            "state": s,
            "messages": messages,
            "template_context": template_context,
        }

    chain = (
        RunnableLambda(_prepare_inputs)
        | RunnableParallel(
            state=RunnableLambda(lambda d: d["state"]),
            draft=(
                RunnableLambda(
                    lambda d: {
                        "state": d["state"],
                        "messages": d["messages"],
                        "template_context": d["template_context"],
                        "meta": {
                            "phase": getattr(d["state"], "phase", None),
                            "last_node": getattr(d["state"], "last_node", None),
                            "run_id": getattr(d["state"], "run_id", None),
                            "thread_id": getattr(d["state"], "thread_id", None),
                        },
                    }
                )
                | RunnableLambda(_render_final_prompt_package)
                | RunnableLambda(
                    lambda d: prepare_final_answer_llm_payload(
                        _ensure_state_model(d.get("state")),
                        system_prompt=d.get("prompt_text") or "",
                        rendered_messages=list(d.get("messages") or []),
                        user_messages=list(getattr(d.get("state"), "messages", []) or []),
                        prompt_metadata=d.get("prompt_metadata") or {},
                    )
                )
                | RunnableParallel(
                    text=RunnableLambda(
                        lambda d: (
                            d.get("forced_text")
                            if d.get("forced_text")
                            else output_parser.invoke(llm.invoke(d.get("messages") or []))
                        )
                    ),
                    prompt_text=RunnableLambda(lambda d: d.get("prompt_text") or ""),
                    prompt_metadata=RunnableLambda(lambda d: d.get("prompt_metadata") or {}),
                )
            ),
        )
        | RunnableLambda(
            lambda d: map_final_answer_to_state(
                _ensure_state_model(d["state"]),
                d["draft"].get("text") or "",
                final_prompt=d["draft"].get("prompt_text") or "",
                final_prompt_metadata=d["draft"].get("prompt_metadata") or {},
            )
        )
    )

    return chain


# ---------------------------------------------------------------------------
# Router-Helpers
# ---------------------------------------------------------------------------


def _critical_review_router(state: SealAIState) -> str:
    critical = state.critical or {}
    status = str(critical.get("status") or "").lower()
    if status == "needs_refinement":
        return "refine"
    if status == "reject":
        return "reject"
    return "continue"


def _product_router(state: SealAIState) -> str:
    wants_products = bool(state.plan.get("want_product_recommendation"))
    return "include" if wants_products else "skip"


def _parameter_check_router(state: SealAIState) -> str:
    ready = bool(getattr(state, "recommendation_ready", False))
    go = bool(getattr(state, "recommendation_go", False))
    if ready and go:
        return "calculator_node"
    return "supervisor_policy_node"


def _supervisor_policy_router(state: SealAIState) -> str:
    return str(getattr(state, "next_action", "FINALIZE") or "FINALIZE")


def _node_router_dispatch(state: SealAIState) -> str:
    classification = getattr(state, "router_classification", None) or "new_case"
    if classification in ("new_case", "follow_up", "resume"):
        return "resume_router"
    if classification == "clarification":
        return "clarification"
    if classification == "rfq_trigger":
        return "rfq_trigger"
    return "resume_router"


def _resume_router(state: SealAIState) -> str:
    if state.awaiting_user_confirmation and (state.confirm_decision or "").strip():
        decision = (state.confirm_decision or "").strip().lower()
        return "reject" if decision == "reject" else "resume"
    return "frontdoor"


def _frontdoor_router(state: SealAIState) -> str:
    flags = state.flags or {}
    if bool(flags.get("frontdoor_bypass_supervisor")):
        return "smalltalk"
    return "supervisor"


def _reducer_router(state: SealAIState) -> str:
    if bool(getattr(state, "requires_human_review", False)):
        return "human_review"
    return "standard"


async def _node_router_dispatch_async(state: SealAIState) -> str:
    return _node_router_dispatch(state)


async def _parameter_check_router_async(state: SealAIState) -> str:
    return _parameter_check_router(state)


async def _critical_review_router_async(state: SealAIState) -> str:
    return _critical_review_router(state)


async def _product_router_async(state: SealAIState) -> str:
    return _product_router(state)


async def _supervisor_policy_router_async(state: SealAIState) -> str:
    return _supervisor_policy_router(state)


async def _resume_router_async(state: SealAIState) -> str:
    return _resume_router(state)


async def _frontdoor_router_async(state: SealAIState) -> str:
    return _frontdoor_router(state)


async def _reducer_router_async(state: SealAIState) -> str:
    return _reducer_router(state)


def human_review_node(state: SealAIState) -> Dict[str, Any]:
    # This node is used only as HITL breakpoint target (interrupt_before).
    # If resumed, emit a compact response hint for manual approval flow.
    return {
        "phase": PHASE.CONFIRM,
        "last_node": "human_review_node",
        "awaiting_user_confirmation": True,
        "pending_action": "human_review",
        "confirm_status": "pending",
        "error": "Human review required before continuing.",
    }


# ---------------------------------------------------------------------------
# Graph-Definition
# ---------------------------------------------------------------------------


def create_sealai_graph_v2(checkpointer: BaseCheckpointSaver, store: BaseStore, *, require_async: bool = True) -> CompiledStateGraph:
    builder = StateGraph(SealAIState)
    logger.debug("create_sealai_graph_v2_start")
    node_router_dispatch = _node_router_dispatch_async if require_async else _node_router_dispatch
    resume_router = _resume_router_async if require_async else _resume_router
    supervisor_router = _supervisor_policy_router_async if require_async else _supervisor_policy_router
    parameter_router = _parameter_check_router_async if require_async else _parameter_check_router
    critical_router = _critical_review_router_async if require_async else _critical_review_router
    product_router = _product_router_async if require_async else _product_router
    frontdoor_router = _frontdoor_router_async if require_async else _frontdoor_router
    reducer_router = _reducer_router_async if require_async else _reducer_router

    # Node registration
    builder.add_node("profile_loader_node", profile_loader_node) # Long-term Memory
    builder.add_node("node_router", node_router)  # v4.4.0 Sprint 3: Router Node
    builder.add_node("resume_router_node", resume_router_node)
    builder.add_node("frontdoor_discovery_node", frontdoor_discovery_node)
    builder.add_node("smalltalk_node", smalltalk_node)
    builder.add_node("supervisor_policy_node", orchestrator_node)
    builder.add_node("supervisor_logic_node", supervisor_policy_node)
    builder.add_node("aggregator_node", aggregator_node)
    builder.add_node("reducer_node", reducer_node)
    builder.add_node("human_review_node", human_review_node)
    
    builder.add_node("panel_calculator_node", panel_calculator_node)
    builder.add_node("panel_material_node", panel_material_node)
    builder.add_node("calculator_agent", calculator_agent_node)
    builder.add_node("pricing_agent", pricing_agent_node)
    builder.add_node("safety_agent", safety_agent_node)
    builder.add_node("discovery_schema_node", discovery_schema_node)
    builder.add_node("parameter_check_node", parameter_check_node)
    builder.add_node("calculator_node", calculator_node)
    builder.add_node("material_agent_node", material_agent_node)
    builder.add_node("material_agent", material_agent_node)
    builder.add_node("profile_agent_node", profile_agent_node)
    builder.add_node("validation_agent_node", validation_agent_node)
    builder.add_node("critical_review_node", critical_review_node)
    builder.add_node("product_match_node", product_match_node)
    builder.add_node("product_explainer_node", product_explainer_node)
    builder.add_node("material_comparison_node", material_comparison_node)
    builder.add_node("rag_support_node", rag_support_node)
    builder.add_node("leakage_troubleshooting_node", leakage_troubleshooting_node)
    builder.add_node("troubleshooting_pattern_node", troubleshooting_pattern_node)
    builder.add_node("troubleshooting_explainer_node", troubleshooting_explainer_node)
    builder.add_node("confirm_checkpoint_node", confirm_checkpoint_node)
    builder.add_node("confirm_resume_node", confirm_resume_node)
    builder.add_node("confirm_reject_node", confirm_reject_node)
    builder.add_node("confirm_recommendation_node", confirm_recommendation_node)
    builder.add_node("final_answer_node", _build_final_answer_chain())
    builder.add_node("response_node", response_node)

    # Entrypoint: START -> profile_loader -> node_router -> [dispatch]
    builder.add_edge(START, "profile_loader_node")
    builder.add_edge("profile_loader_node", "node_router")

    # v4.4.0 Router dispatch
    builder.add_conditional_edges(
        "node_router",
        node_router_dispatch,
        {
            "resume_router": "resume_router_node",
            "clarification": "smalltalk_node",
            "rfq_trigger": "response_node",
        },
    )

    builder.add_conditional_edges(
        "resume_router_node",
        resume_router,
        {
            "reject": "confirm_reject_node",
            "resume": "confirm_resume_node",
            "frontdoor": "frontdoor_discovery_node",
            "default": "response_node",
        },
    )
    builder.add_conditional_edges(
        "frontdoor_discovery_node",
        frontdoor_router,
        {
            "smalltalk": "smalltalk_node",
            "supervisor": "supervisor_policy_node",
        },
    )
    builder.add_edge("smalltalk_node", "response_node")

    # Map-Reduce Flow
    # Workers route to Reducer
    builder.add_edge("panel_calculator_node", "reducer_node")
    builder.add_edge("panel_material_node", "reducer_node")
    builder.add_edge("material_agent", "reducer_node")
    builder.add_edge("calculator_agent", "reducer_node")
    builder.add_edge("pricing_agent", "reducer_node")
    builder.add_edge("safety_agent", "reducer_node")
    # Reducer routes either through HITL gate or to normal finalization.
    builder.add_conditional_edges(
        "reducer_node",
        reducer_router,
        {
            "human_review": "human_review_node",
            "standard": "final_answer_node",
        },
    )
    builder.add_edge("human_review_node", "response_node")

    # Back-links
    builder.add_edge("rag_support_node", "supervisor_policy_node")
    builder.add_edge("material_comparison_node", "supervisor_policy_node")
    builder.add_edge("confirm_resume_node", "supervisor_policy_node")

    # Design flow
    builder.add_edge("discovery_schema_node", "parameter_check_node")
    builder.add_conditional_edges(
        "parameter_check_node",
        parameter_router,
        {
            "calculator_node": "calculator_node",
            "supervisor_policy_node": "supervisor_policy_node",
            "__else__": "supervisor_policy_node",
        },
    )
    builder.add_edge("calculator_node", "material_agent_node")
    builder.add_edge("material_agent_node", "profile_agent_node")
    builder.add_edge("profile_agent_node", "validation_agent_node")
    builder.add_edge("validation_agent_node", "critical_review_node")

    builder.add_conditional_edges(
        "critical_review_node",
        critical_router,
        {
            "refine": "discovery_schema_node",
            "reject": "final_answer_node",
            "continue": "product_match_node",
            "__else__": "product_match_node",
        },
    )

    builder.add_conditional_edges(
        "product_match_node",
        product_router,
        {
            "include": "product_explainer_node",
            "skip": "final_answer_node",
            "__else__": "final_answer_node",
        },
    )

    builder.add_edge("product_explainer_node", "final_answer_node")

    # Troubleshooting flow
    builder.add_edge("leakage_troubleshooting_node", "troubleshooting_pattern_node")
    builder.add_edge("troubleshooting_pattern_node", "troubleshooting_explainer_node")
    builder.add_edge("troubleshooting_explainer_node", "final_answer_node")

    builder.add_edge("confirm_recommendation_node", END)
    builder.add_edge("confirm_checkpoint_node", END)
    builder.add_edge("confirm_reject_node", END)

    builder.add_edge("final_answer_node", END)
    builder.add_edge("response_node", END)

    return builder.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=["human_review_node"],
    )


# ---------------------------------------------------------------------------
# Graph Cache & Config
# ---------------------------------------------------------------------------

_GRAPH_CACHE: CompiledStateGraph | None = None
_GRAPH_LOCK = asyncio.Lock()


async def _build_graph(require_async: bool = True) -> CompiledStateGraph:
    # Initialize Checkpointer & Store (Async)
    checkpointer = await make_v2_checkpointer_async(require_async=require_async)
    store = await get_postgres_store()
    return create_sealai_graph_v2(checkpointer=checkpointer, store=store, require_async=require_async)


async def get_sealai_graph_v2() -> CompiledStateGraph:
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        async with _GRAPH_LOCK:
            if _GRAPH_CACHE is None:
                _GRAPH_CACHE = await _build_graph(require_async=True)
    return _GRAPH_CACHE


def build_v2_config(*, thread_id: str, user_id: str) -> Dict[str, Any]:
    """
    Common LangGraph config for v2 (includes run_id for observability).

    + recursion_limit explizit hochsetzen, damit komplexe Flows nicht bereits
      bei 25 Schritten abgebrochen werden.
    + Die harte Begrenzung erfolgt weiterhin über den 45s-Timeout im SSE-Endpoint.
    """
    run_id = str(uuid.uuid4())
    # Checkpointer identity must be stable per (user_id, thread_id) so that state
    # can be recovered reliably and isolated across users.
    checkpoint_thread_id = stable_thread_key(user_id, thread_id)
    configurable: Dict[str, Any] = {
        "thread_id": checkpoint_thread_id,
    }
    metadata: Dict[str, Any] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "run_id": run_id,
    }
    return {
        "configurable": configurable,
        "metadata": metadata,
        "recursion_limit": 80,
    }
