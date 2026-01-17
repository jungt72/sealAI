"""Rebuilt LangGraph v2 Definition for SealAI with new frontdoor/supervisor topology."""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Dict, List
from weakref import WeakKeyDictionary

import structlog
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableParallel
from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.constants import resolve_checkpointer_namespace_v2
from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer_async
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.llm_factory import LazyChatOpenAI
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.state_debug import log_state_debug

logger = structlog.get_logger("langgraph_v2.graph")


# ---------------------------------------------------------------------------
# Node Imports
# ---------------------------------------------------------------------------

from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node
from app.langgraph_v2.nodes.nodes_confirm import confirm_checkpoint_node, confirm_recommendation_node
from app.langgraph_v2.nodes.nodes_supervisor import (
    aggregator_node,
    panel_calculator_node,
    panel_material_node,
    supervisor_policy_node,
)
from app.langgraph_v2.nodes.response_node import response_node
from app.langgraph_v2.nodes.nodes_resume import (
    confirm_reject_node,
    confirm_resume_node,
    resume_router_node,
)
from app.langgraph_v2.nodes.nodes_critic import technical_critic_node, critic_router
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
    template_context = dict(base_context or {})
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
            "recommendation": recommendation,
            "calc_results": calc_results,
            "intent_high_impact_gaps": getattr(state.intent, "high_impact_gaps", []),
            "parameters": parameters,
            "flags": state.flags or {},
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


def _render_final_prompt_messages(payload: Dict[str, Any]) -> List[BaseMessage]:
    """
    Baut die endgültige Prompt-Message-Liste für das LLM.

    Wichtig: Wir geben hier **direkt** eine Liste von BaseMessages zurück,
    damit ChatOpenAI eine gültige Eingabe bekommt (kein dict!).
    """
    template_name = _select_final_answer_template(
        payload["template_context"].get("goal"),
        payload["template_context"].get("recommendation_go", False),
    )
    payload["template_context"].setdefault("is_micro_smalltalk", False)
    plan = payload["template_context"].get("plan") or {}
    style_profile = (plan.get("style_profile") or "senior_sealing_engineer_de") if isinstance(plan, dict) else "senior_sealing_engineer_de"
    include_policy = str(style_profile).strip().lower() not in {"off", "none", "disabled", "disable"}

    prompt_text = render_template(template_name, payload["template_context"])
    if include_policy:
        policy_text = render_template("senior_policy_de.j2", {})
        policy_text = (policy_text or "").strip()
        if policy_text:
            prompt_text = f"{policy_text}\n\n{(prompt_text or '').strip()}"
    meta = payload.get("meta") if isinstance(payload, dict) else None
    if isinstance(meta, dict):
        logger.info(
            "final_prompt_selected",
            goal=payload["template_context"].get("goal"),
            selected_template_name=template_name,
            senior_policy_enabled=bool(include_policy),
            phase=meta.get("phase"),
            last_node=meta.get("last_node"),
            run_id=meta.get("run_id"),
            thread_id=meta.get("thread_id"),
        )
    else:
        logger.info(
            "final_prompt_selected",
            goal=payload["template_context"].get("goal"),
            selected_template_name=template_name,
            senior_policy_enabled=bool(include_policy),
        )
    messages: List[BaseMessage] = [SystemMessage(content=prompt_text)]
    messages.extend(list(payload.get("messages") or []))
    return messages


def _build_final_answer_chain() -> Any:
    llm = LazyChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.15,
        max_tokens=800,
        streaming=True,
    )

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
                # Hier wird jetzt eine List[BaseMessage] erzeugt …
                | RunnableLambda(_render_final_prompt_messages)
                # … und direkt an das LLM übergeben.
                | llm
                | StrOutputParser()
            ),
        )
        | RunnableLambda(
            lambda d: map_final_answer_to_state(
                _ensure_state_model(d["state"]),
                d["draft"],
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


def _resume_router(state: SealAIState) -> str:
    if state.awaiting_user_confirmation and (state.confirm_decision or "").strip():
        decision = (state.confirm_decision or "").strip().lower()
        return "reject" if decision == "reject" else "resume"
    return "frontdoor"


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


# ---------------------------------------------------------------------------
# Graph-Definition
# ---------------------------------------------------------------------------


def create_sealai_graph_v2(checkpointer: BaseCheckpointSaver, *, require_async: bool = True) -> CompiledStateGraph:
    builder = StateGraph(SealAIState)
    logger.debug("create_sealai_graph_v2_start")

    # Node registration
    builder.add_node("resume_router_node", resume_router_node)
    builder.add_node("frontdoor_discovery_node", frontdoor_discovery_node)
    builder.add_node("supervisor_policy_node", supervisor_policy_node)
    builder.add_node("aggregator_node", aggregator_node)
    builder.add_node("panel_calculator_node", panel_calculator_node)
    builder.add_node("panel_material_node", panel_material_node)
    builder.add_node("discovery_schema_node", discovery_schema_node)
    builder.add_node("parameter_check_node", parameter_check_node)
    builder.add_node("calculator_node", calculator_node)
    builder.add_node("material_agent_node", material_agent_node)
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
    builder.add_node("technical_critic_node", technical_critic_node)
    builder.add_conditional_edges("technical_critic_node", critic_router, {"approve": "final_answer_node", "refine": "supervisor_policy_node"})

    # Entrypoint
    builder.add_edge(START, "resume_router_node")
    builder.add_conditional_edges(
        "resume_router_node",
        _resume_router_async,
        {
            "reject": "confirm_reject_node",
            "resume": "confirm_resume_node",
            "frontdoor": "frontdoor_discovery_node",
            "default": "response_node",
        },
    )
    builder.add_edge("frontdoor_discovery_node", "supervisor_policy_node")

    # MAI-DxO supervisor loop (feature flagged)
    builder.add_conditional_edges(
        "supervisor_policy_node",
        _supervisor_policy_router_async,
        {
            "ASK_USER": "final_answer_node",
            "RUN_PANEL_CALC": "panel_calculator_node",
            "RUN_PANEL_MATERIAL": "panel_material_node",
            "RUN_PANEL_NORMS_RAG": "rag_support_node",
            "RUN_COMPARISON": "material_comparison_node",
            "RUN_TROUBLESHOOTING": "leakage_troubleshooting_node",
            "RUN_CONFIRM": "confirm_recommendation_node",
            "REQUIRE_CONFIRM": "confirm_checkpoint_node",
            "FINALIZE": "final_answer_node",
            "__else__": "final_answer_node",
        },
    )
    builder.add_edge("panel_calculator_node", "aggregator_node")
    builder.add_edge("panel_material_node", "aggregator_node")
    builder.add_edge("rag_support_node", "aggregator_node")
    builder.add_edge("aggregator_node", "supervisor_policy_node")

    builder.add_conditional_edges(
        "confirm_resume_node",
        _supervisor_policy_router_async,
        {
            "ASK_USER": "final_answer_node",
            "RUN_PANEL_CALC": "panel_calculator_node",
            "RUN_PANEL_MATERIAL": "panel_material_node",
            "RUN_PANEL_NORMS_RAG": "rag_support_node",
            "RUN_COMPARISON": "material_comparison_node",
            "RUN_TROUBLESHOOTING": "leakage_troubleshooting_node",
            "RUN_CONFIRM": "confirm_recommendation_node",
            "REQUIRE_CONFIRM": "confirm_checkpoint_node",
            "FINALIZE": "final_answer_node",
            "__else__": "final_answer_node",
        },
    )

    # Design flow
    builder.add_edge("discovery_schema_node", "parameter_check_node")
    builder.add_conditional_edges(
        "parameter_check_node",
        _parameter_check_router_async,
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
        _critical_review_router_async,
        {
            "refine": "discovery_schema_node",
            "reject": "final_answer_node",
            "continue": "product_match_node",
            "__else__": "product_match_node",
        },
    )

    builder.add_conditional_edges(
        "product_match_node",
        _product_router_async,
        {
            "include": "product_explainer_node",
            "skip": "final_answer_node",
            "__else__": "final_answer_node",
        },
    )

    builder.add_edge("product_explainer_node", "technical_critic_node")

    # Comparison flow
    builder.add_edge("material_comparison_node", "supervisor_policy_node")
    builder.add_edge("rag_support_node", "supervisor_policy_node")

    # Troubleshooting flow
    builder.add_edge("leakage_troubleshooting_node", "troubleshooting_pattern_node")
    builder.add_edge("troubleshooting_pattern_node", "troubleshooting_explainer_node")
    builder.add_edge("troubleshooting_explainer_node", "final_answer_node")

    builder.add_edge("confirm_recommendation_node", END)
    builder.add_edge("confirm_checkpoint_node", END)
    builder.add_edge("confirm_reject_node", END)

    # Smalltalk / out-of-scope share final answer node (already defined in supervisor routing)
    builder.add_edge("final_answer_node", END)
    builder.add_edge("response_node", END)

    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Graph Cache & Config
# ---------------------------------------------------------------------------

_GRAPH_STORE: "WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, Any]]" = WeakKeyDictionary()


def _get_graph_store(loop: asyncio.AbstractEventLoop) -> dict[str, Any]:
    store = _GRAPH_STORE.get(loop)
    if store is None:
        # Cache graphs per tenant to ensure strict tenant isolation at the checkpointer layer.
        store = {"lock": asyncio.Lock(), "graphs": {}}
        _GRAPH_STORE[loop] = store
    return store


async def _build_graph(*, require_async: bool = True, tenant_id: str | None = None) -> CompiledStateGraph:
    base_namespace = resolve_checkpointer_namespace_v2()
    checkpoint_ns = _tenant_checkpoint_namespace(base_namespace, tenant_id)

    # Best effort: newer make_v2_checkpointer_async supports explicit namespace scoping.
    # Keep backwards compatibility if signature does not accept it.
    try:
        checkpointer = await make_v2_checkpointer_async(require_async=require_async, namespace=checkpoint_ns)
    except TypeError:
        checkpointer = await make_v2_checkpointer_async(require_async=require_async)

    return create_sealai_graph_v2(checkpointer=checkpointer, require_async=require_async)


async def get_sealai_graph_v2(*, tenant_id: str | None = None) -> CompiledStateGraph:
    loop = asyncio.get_running_loop()
    store = _get_graph_store(loop)
    graphs = store.get("graphs")
    if not isinstance(graphs, dict):
        graphs = {}
        store["graphs"] = graphs

    tenant_key = (tenant_id or "").strip() or "__none__"
    graph = graphs.get(tenant_key)
    if graph is not None:
        return graph

    async with store["lock"]:
        graph = graphs.get(tenant_key)
        if graph is None:
            graph = await _build_graph(require_async=True, tenant_id=(tenant_id or None))
            graphs[tenant_key] = graph
    return graph


def _tenant_checkpoint_namespace(base: str, tenant_id: str | None) -> str:
    if not tenant_id:
        return base
    clean_base = base.strip()
    clean_tenant = tenant_id.strip()
    if not clean_tenant:
        return clean_base
    if clean_base.endswith(":"):
        return f"{clean_base}{clean_tenant}"
    return f"{clean_base}:{clean_tenant}"


def build_v2_config(*, thread_id: str, user_id: str, tenant_id: str | None = None) -> Dict[str, Any]:
    """
    Common LangGraph config for v2 (includes run_id for observability).

    + recursion_limit explizit hochsetzen, damit komplexe Flows nicht bereits
      bei 25 Schritten abgebrochen werden.
    + Die harte Begrenzung erfolgt weiterhin über den 45s-Timeout im SSE-Endpoint.
    """
    run_id = str(uuid.uuid4())
    base_namespace = resolve_checkpointer_namespace_v2()
    checkpoint_ns = _tenant_checkpoint_namespace(base_namespace, tenant_id)
    configurable: Dict[str, Any] = {
        "thread_id": thread_id,
        "user_id": user_id,
    }
    metadata: Dict[str, Any] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "checkpoint_ns": checkpoint_ns,
        "run_id": run_id,
    }
    return {
        "configurable": configurable,
        "metadata": metadata,
        "recursion_limit": 80,
    }
