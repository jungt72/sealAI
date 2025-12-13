"""Rebuilt LangGraph v2 Definition for SealAI with new frontdoor/supervisor topology."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List

import structlog
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableParallel
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.constants import CHECKPOINTER_NAMESPACE_V2
from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer_async
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.messages import latest_user_text

logger = structlog.get_logger("langgraph_v2.graph")
state_logger = logging.getLogger("langgraph_v2.state")


# ---------------------------------------------------------------------------
# Helper: Messages & Logging
# ---------------------------------------------------------------------------


def _flatten_message_content(message: Any) -> str | None:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                text_value = chunk.get("text") or chunk.get("content")
                if isinstance(text_value, str):
                    parts.append(text_value)
                else:
                    parts.append(str(text_value))
            else:
                parts.append(str(chunk))
        return "".join(parts).strip()
    if isinstance(content, dict):
        text_value = content.get("text") or content.get("content")
        if isinstance(text_value, str):
            return text_value.strip()
        return str(content).strip()
    if content is None:
        return None
    return str(content).strip()


def _collect_messages(state: Any) -> List[BaseMessage | Any]:
    if isinstance(state, dict):
        raw = state.get("messages")
    else:
        raw = getattr(state, "messages", None)
    if isinstance(raw, list):
        return list(raw)
    return []


def log_state_debug(node_name: str, state: Any) -> None:
    """Robustes Logging für Node-Start, ohne UnboundLocalError."""
    try:
        thread_id = getattr(state, "thread_id", None)
        user_id = getattr(state, "user_id", None)

        # Falls der State als dict durchgereicht wurde, ggf. thread_id/user_id aus config holen
        if isinstance(state, dict):
            config = state.get("config") or {}
            thread_id = thread_id or config.get("thread_id")
            user_id = user_id or config.get("user_id")

        messages = _collect_messages(state)
        messages_count = len(messages) if isinstance(messages, list) else None
        coverage_score = getattr(state, "coverage_score", None)
        recommendation_ready = getattr(state, "recommendation_ready", None)
        recommendation_go = getattr(state, "recommendation_go", None)

        last_user = None
        for msg in reversed(messages):
            role = getattr(msg, "type", None) or getattr(msg, "role", None)
            if role in ("human", "user"):
                candidate = _flatten_message_content(msg)
                if candidate:
                    last_user = candidate[:200]
                    break

        state_logger.info(
            "langgraph_v2_node_start node=%s thread_id=%s user_id=%s "
            "messages_count=%s coverage_score=%s ready=%s go=%s last_user=%r",
            node_name,
            thread_id,
            user_id,
            messages_count,
            coverage_score,
            recommendation_ready,
            recommendation_go,
            last_user,
        )
    except Exception:
        state_logger.exception("Failed to log LangGraph v2 state for node %s", node_name)


# ---------------------------------------------------------------------------
# Node Imports
# ---------------------------------------------------------------------------

from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node
from app.langgraph_v2.nodes.nodes_confirm import confirm_recommendation_node
from app.langgraph_v2.nodes.nodes_supervisor import (
    supervisor_logic_node,
    supervisor_route,
)
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


def _select_final_answer_template(goal: str | None, recommendation_go: bool) -> str:
    if goal == "smalltalk":
        return SMALLTALK_TEMPLATE
    if goal == "design_recommendation":
        return RECOMMENDATION_TEMPLATE if recommendation_go else DISCOVERY_TEMPLATE
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
    prompt_text = render_template(template_name, payload["template_context"])
    messages: List[BaseMessage] = [SystemMessage(content=prompt_text)]
    messages.extend(list(payload.get("messages") or []))
    return messages


def _build_final_answer_chain() -> Any:
    llm = ChatOpenAI(
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
        )
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
    return "supervisor_logic_node"


def _comparison_rag_router(state: SealAIState) -> str:
    return "rag" if bool(getattr(state, "requires_rag", False)) else "skip"


# ---------------------------------------------------------------------------
# Graph-Definition
# ---------------------------------------------------------------------------


def create_sealai_graph_v2(checkpointer: BaseCheckpointSaver, *, require_async: bool = True) -> CompiledStateGraph:
    builder = StateGraph(SealAIState)
    logger.debug("create_sealai_graph_v2_start")

    # Node registration
    builder.add_node("frontdoor_discovery_node", frontdoor_discovery_node)
    builder.add_node("supervisor_logic_node", supervisor_logic_node)
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
    builder.add_node("confirm_recommendation_node", confirm_recommendation_node)
    builder.add_node("final_answer_node", _build_final_answer_chain())

    # Entrypoint
    builder.add_edge(START, "frontdoor_discovery_node")
    builder.add_edge("frontdoor_discovery_node", "supervisor_logic_node")

    builder.add_conditional_edges(
        "supervisor_logic_node",
        supervisor_route,
        {
            "intermediate": "final_answer_node",
            "confirm": "confirm_recommendation_node",
            "design_flow": "calculator_node",
            "comparison": "material_comparison_node",
            "troubleshooting": "leakage_troubleshooting_node",
            "smalltalk": "final_answer_node",
            "out_of_scope": "final_answer_node",
            "__else__": "final_answer_node",
        },
    )

    # Design flow
    builder.add_edge("discovery_schema_node", "parameter_check_node")
    builder.add_conditional_edges(
        "parameter_check_node",
        _parameter_check_router,
        {
            "calculator_node": "calculator_node",
            "supervisor_logic_node": "supervisor_logic_node",
            "__else__": "supervisor_logic_node",
        },
    )
    builder.add_edge("calculator_node", "material_agent_node")
    builder.add_edge("material_agent_node", "profile_agent_node")
    builder.add_edge("profile_agent_node", "validation_agent_node")
    builder.add_edge("validation_agent_node", "critical_review_node")

    builder.add_conditional_edges(
        "critical_review_node",
        _critical_review_router,
        {
            "refine": "discovery_schema_node",
            "reject": "final_answer_node",
            "continue": "product_match_node",
            "__else__": "product_match_node",
        },
    )

    builder.add_conditional_edges(
        "product_match_node",
        _product_router,
        {
            "include": "product_explainer_node",
            "skip": "final_answer_node",
            "__else__": "final_answer_node",
        },
    )

    builder.add_edge("product_explainer_node", "final_answer_node")

    # Comparison flow
    builder.add_conditional_edges(
        "material_comparison_node",
        _comparison_rag_router,
        {
            "rag": "rag_support_node",
            "skip": "final_answer_node",
            "__else__": "final_answer_node",
        },
    )
    builder.add_edge("rag_support_node", "final_answer_node")

    # Troubleshooting flow
    builder.add_edge("leakage_troubleshooting_node", "troubleshooting_pattern_node")
    builder.add_edge("troubleshooting_pattern_node", "troubleshooting_explainer_node")
    builder.add_edge("troubleshooting_explainer_node", "final_answer_node")

    builder.add_edge("confirm_recommendation_node", END)

    # Smalltalk / out-of-scope share final answer node (already defined in supervisor routing)
    builder.add_edge("final_answer_node", END)

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
    checkpoint_thread_id = f"{user_id}|{thread_id}"
    configurable: Dict[str, Any] = {
        "thread_id": checkpoint_thread_id,
        "checkpoint_ns": CHECKPOINTER_NAMESPACE_V2,
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
