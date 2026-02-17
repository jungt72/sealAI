# path: backend/app/langgraph_v2/sealai_graph_v2.py
"""Rebuilt LangGraph v2 Definition for SealAI with new frontdoor/supervisor topology."""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Dict, List

import structlog
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableParallel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.langgraph_v2.constants import CHECKPOINTER_NAMESPACE_V2
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer_async
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.llm_factory import get_chat_model, get_model_tier
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.state_debug import log_state_debug
from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id


logger = structlog.get_logger("langgraph_v2.graph")

# ---------------------------------------------------------------------------
# Node Imports
# ---------------------------------------------------------------------------

from app.langgraph_v2.nodes.nodes_confirm import (  # noqa: E402
    confirm_checkpoint_node,
    confirm_recommendation_node,
)
from app.langgraph_v2.nodes.nodes_flows import (  # noqa: E402
    build_final_answer_context,
    calculator_node,
    critical_review_node,
    discovery_schema_node,
    leakage_troubleshooting_node,
    map_final_answer_to_state,
    material_agent_node,
    material_comparison_node,
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
from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node  # noqa: E402
from app.langgraph_v2.nodes.nodes_resume import (  # noqa: E402
    confirm_reject_node,
    confirm_resume_node,
    resume_router_node,
)
from app.langgraph_v2.nodes.nodes_supervisor import (  # noqa: E402
    aggregator_node,
    panel_calculator_node,
    panel_material_node,
    supervisor_policy_node,
)
from app.langgraph_v2.nodes.response_node import response_node  # noqa: E402

# ---------------------------------------------------------------------------
# State Helper
# ---------------------------------------------------------------------------


def _ensure_state_model(state: Any) -> SealAIState:
    """Akzeptiert dict/SealAIState und gibt garantiert ein SealAIState-Objekt zur??ck."""
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
    rag_context: str | None = None,
) -> Dict[str, Any]:
    parameters = state.parameters.as_dict()
    calc_results = (
        state.calc_results.model_dump(exclude_none=True) if state.calc_results else {}
    )
    recommendation = (
        state.recommendation.model_dump(exclude_none=True)
        if state.recommendation
        else {}
    )
    working_memory = (
        state.working_memory.model_dump(exclude_none=True) if state.working_memory else {}
    )
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
            "intent_high_impact_gaps": getattr(state.intent, "high_impact_gaps", []) if state.intent else [],	
            "parameters": parameters,
            "flags": state.flags or {},
            "rag_context": rag_context,
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
    Baut die endg??ltige Prompt-Message-Liste f??r das LLM.

    Wichtig: Wir geben hier **direkt** eine Liste von BaseMessages zur??ck,
    damit ChatOpenAI eine g??ltige Eingabe bekommt (kein dict!).
    """
    template_name = _select_final_answer_template(
        payload["template_context"].get("goal"),
        payload["template_context"].get("recommendation_go", False),
    )
    payload["template_context"].setdefault("is_micro_smalltalk", False)
    plan = payload["template_context"].get("plan") or {}
    style_profile = (
        (plan.get("style_profile") or "senior_sealing_engineer_de")
        if isinstance(plan, dict)
        else "senior_sealing_engineer_de"
    )
    include_policy = str(style_profile).strip().lower() not in {
        "off",
        "none",
        "disabled",
        "disable",
    }

    prompt_text = render_template(template_name, payload["template_context"])
    if include_policy:
        policy_text = render_template("senior_policy_de.j2", payload["template_context"])
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
    llm = get_chat_model(
        model=get_model_tier("mini"), # Use MINI for debug stability
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
            rag_context=context.get("rag_context"),
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
                | RunnableLambda(_render_final_prompt_messages)
                | RunnableLambda(lambda x: print(f"DEBUG: Final Answer LLM Input: {x}", flush=True) or x)
                | llm
                | StrOutputParser()
            ),
        )
        | RunnableLambda(
            lambda d: map_final_answer_to_state(_ensure_state_model(d["state"]), d["draft"])
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
    """
    IMPORTANT: Route should consider pending_action as fallback, otherwise you get:
    pending_action=RUN_PANEL_NORMS_RAG but next_action missing -> FINALIZE -> END (RAG never runs).
    """
    next_action = getattr(state, "next_action", None) or None
    pending_action = getattr(state, "pending_action", None) or None
    return str(next_action or pending_action or "FINALIZE")


def _resume_router(state: SealAIState) -> str:
    if state.awaiting_user_confirmation and (state.confirm_decision or "").strip():
        decision = (state.confirm_decision or "").strip().lower()
        return "reject" if decision == "reject" else "resume"
    return "frontdoor"


def _confirm_checkpoint_router(state: SealAIState) -> str:
    if state.awaiting_user_confirmation:
        return "awaiting"
    return _supervisor_policy_router(state)


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


async def _confirm_checkpoint_router_async(state: SealAIState) -> str:
    return _confirm_checkpoint_router(state)


def _knowledge_target_router(state: SealAIState) -> str:
    intent = state.intent
    key = str(getattr(intent, "key", "") or "") if intent else ""
    if key == "knowledge_material" or getattr(intent, "knowledge_type", None) == "material":
        return "knowledge_material_node"
    if key == "knowledge_lifetime" or getattr(intent, "knowledge_type", None) == "lifetime":
        return "knowledge_lifetime_node"
    return "generic_sealing_qa_node"


async def _knowledge_target_router_async(state: SealAIState) -> str:
    return _knowledge_target_router(state)


def knowledge_entry_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return {
        "phase": getattr(state, "phase", None) or "knowledge",
        "last_node": "knowledge_entry_node",
    }


# ---------------------------------------------------------------------------
# Graph-Definition
# ---------------------------------------------------------------------------


def create_sealai_graph_v2(
    checkpointer: BaseCheckpointSaver, *, require_async: bool = True
) -> CompiledStateGraph:
    builder = StateGraph(SealAIState)
    logger.debug("create_sealai_graph_v2_start")

    # Import Autonomous Nodes
    from app.langgraph_v2.nodes.nodes_autonomous import (
        autonomous_supervisor_node,
        autonomous_router,
    )

    try:
        from app.langgraph_v2.nodes.nodes_knowledge import (
            generic_sealing_qa_node,
            knowledge_lifetime_node,
            knowledge_material_node,
        )
    except Exception:  # pragma: no cover
        def _knowledge_unavailable(node_name: str):
            def _node(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
                return {
                    "error": "knowledge_nodes_unavailable",
                    "last_node": node_name,
                    "phase": "error",
                }
            return _node

        generic_sealing_qa_node = _knowledge_unavailable("generic_sealing_qa_node")
        knowledge_lifetime_node = _knowledge_unavailable("knowledge_lifetime_node")
        knowledge_material_node = _knowledge_unavailable("knowledge_material_node")

    # --- NODE REGISTRATION ---
    
    # 1. Hub (Supervisor)
    builder.add_node("autonomous_supervisor_node", autonomous_supervisor_node)
    
    # 2. Entrypoint & Frontdoor
    builder.add_node("frontdoor_discovery_node", frontdoor_discovery_node)

    # 3. Workers (Spokes)
    # Knowledge Cluster
    builder.add_node("knowledge_entry_node", knowledge_entry_node)
    builder.add_node("knowledge_material_node", knowledge_material_node)
    builder.add_node("knowledge_lifetime_node", knowledge_lifetime_node)
    builder.add_node("generic_sealing_qa_node", generic_sealing_qa_node)
    
    # Design Cluster
    builder.add_node("design_worker", material_agent_node) # Alias for material_agent
    builder.add_node("calc_worker", calculator_node)       # Alias for calculator
    builder.add_node("product_worker", product_match_node) # Alias for product_match
    builder.add_node("product_explainer_node", product_explainer_node)

    # 3b. Troubleshooting Cluster (Digital Twin)
    builder.add_node("leakage_troubleshooting_node", leakage_troubleshooting_node)
    builder.add_node("rag_support_node", rag_support_node)
    
    # 3c. Quality Assurance
    builder.add_node("critical_review_node", critical_review_node)

    # 4. Utility / Finalize
    builder.add_node("final_answer_node", _build_final_answer_chain())
    builder.add_node("response_node", response_node)

    # Stable external contract nodes: keep registered for state update `as_node` calls.
    builder.add_node("confirm_recommendation_node", confirm_recommendation_node)
    builder.add_node("confirm_checkpoint_node", confirm_checkpoint_node)
    builder.add_node("supervisor_policy_node", supervisor_policy_node)

    # --- EDGES & ROUTING ---

    # Entry
    builder.add_edge(START, "frontdoor_discovery_node")

    # Frontdoor -> Supervisor (always upgrade connection)
    def _frontdoor_router(state: SealAIState) -> str:
        print(f"DEBUG_FRONTDOOR_ROUTER_ENTRY: next_action={state.next_action}, goal={getattr(state.intent, 'goal', 'N/A')}, requires_rag={state.requires_rag}", flush=True)
        
        # If technical path is explicitly required (e.g. RAG), go to supervisor regardless of next_action=None
        if state.requires_rag:
            print("DEBUG_FRONTDOOR_ROUTER: Decided supervisor (requires_rag override)", flush=True)
            return "supervisor"
            
        if state.next_action == "FINALIZE":
            print("DEBUG_FRONTDOOR_ROUTER: Decided finalize", flush=True)
            return "finalize"
            
        print("DEBUG_FRONTDOOR_ROUTER: Decided supervisor (default)", flush=True)
        return "supervisor"

    builder.add_conditional_edges(
        "frontdoor_discovery_node", 
        _frontdoor_router,
        {
            "finalize": "final_answer_node",
            "supervisor": "autonomous_supervisor_node"
        }
    )

    # Supervisor -> Workers (Hub to Spoke)
    builder.add_conditional_edges(
        "autonomous_supervisor_node",
        autonomous_router,
        {
            "knowledge": "knowledge_entry_node",
            "design": "design_worker",
            "calc": "calc_worker",
            "product": "product_worker",
            "troubleshoot": "leakage_troubleshooting_node",
            "review": "critical_review_node",
            "finalize": "final_answer_node",
        }
    )

    # Workers -> Hub (Spoke to Hub)
    # Knowledge Flow
    builder.add_conditional_edges(
        "knowledge_entry_node",
        _knowledge_target_router_async,
        {
            "knowledge_material_node": "knowledge_material_node",
            "knowledge_lifetime_node": "knowledge_lifetime_node",
            "generic_sealing_qa_node": "generic_sealing_qa_node",
            "__else__": "generic_sealing_qa_node",
        },
    )
    builder.add_edge("knowledge_material_node", "autonomous_supervisor_node")
    builder.add_edge("knowledge_lifetime_node", "autonomous_supervisor_node")
    builder.add_edge("generic_sealing_qa_node", "autonomous_supervisor_node")

    # Design Flow
    builder.add_edge("design_worker", "autonomous_supervisor_node")
    builder.add_edge("calc_worker", "autonomous_supervisor_node")
    
    # Product Flow
    # Product Flow
    builder.add_edge("product_worker", "product_explainer_node")
    builder.add_edge("product_explainer_node", "autonomous_supervisor_node")

    # Troubleshooting Flow
    builder.add_edge("leakage_troubleshooting_node", "autonomous_supervisor_node")

    # Critical Review Flow
    builder.add_conditional_edges(
        "critical_review_node",
        _critical_review_router_async,
        {
            "continue": "final_answer_node",
            "refine": "autonomous_supervisor_node",
            "reject": "autonomous_supervisor_node"
        }
    )

    # Exit
    builder.add_edge("final_answer_node", END)
    builder.add_edge("response_node", END)

    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Graph Cache & Config
# ---------------------------------------------------------------------------

_GRAPH_CACHE: CompiledStateGraph | None = None
_GRAPH_LOCK = asyncio.Lock()


async def _build_graph(require_async: bool = True) -> CompiledStateGraph:
    checkpointer = await make_v2_checkpointer_async(require_async=require_async)
    return create_sealai_graph_v2(checkpointer=checkpointer, require_async=require_async)


async def get_sealai_graph_v2() -> CompiledStateGraph:
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        async with _GRAPH_LOCK:
            if _GRAPH_CACHE is None:
                _GRAPH_CACHE = await _build_graph(require_async=True)
    return _GRAPH_CACHE


def build_v2_config(*, thread_id: str, user_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Common LangGraph config for v2 (includes run_id for observability).

    + recursion_limit explizit hochsetzen, damit komplexe Flows nicht bereits
      bei 25 Schritten abgebrochen werden.
    + Die harte Begrenzung erfolgt weiterhin ??ber den 45s-Timeout im SSE-Endpoint.
    """
    run_id = str(uuid.uuid4())
    checkpoint_thread_id = resolve_checkpoint_thread_id(
        tenant_id=tenant_id,
        user_id=user_id,
        chat_id=thread_id,
    )
    configurable: Dict[str, Any] = {
        "thread_id": checkpoint_thread_id,
        "checkpoint_ns": CHECKPOINTER_NAMESPACE_V2,
    }
    metadata: Dict[str, Any] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "run_id": run_id,
    }
    config = {
        "configurable": configurable,
        "metadata": metadata,
        "recursion_limit": 80,
    }
    from app.langgraph_v2.utils.config_guard import ensure_v2_config
    return ensure_v2_config(config)
