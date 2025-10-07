from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph
from langgraph.constants import END

from app.services.langgraph.llm_factory import get_llm
from app.services.langgraph.graph.intent_router import classify_intent
from app.services.langgraph.agents.material_agent import get_material_agent
from app.services.langgraph.prompt_registry import get_agent_prompt
from app.services.rag.rag_orchestrator import hybrid_retrieve
from .logging_utils import wrap_node_with_logging, log_branch_decision


log = logging.getLogger(__name__)
_GRAPH_NAME = "MvpGraph"


class MvpState(TypedDict, total=False):
    messages: List[BaseMessage]
    intent: Literal["material", "llm", "unknown"]
    route: Literal["material", "llm", "fallback"]
    query: str
    retrieved_docs: List[Dict[str, Any]]
    final_text: str
    chat_id: str
    user_id: str


def _last_user_text(messages: List[BaseMessage] | None) -> str:
    if not messages:
        return ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            c = (m.content or "").strip()
            if c:
                return c
        elif isinstance(m, dict):
            role = str(m.get("role") or m.get("type") or "").lower()
            if role in {"human", "user"}:
                c = (m.get("content") or "").strip()
                if c:
                    return c
    return ""


_LLM_SIMPLE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Du bist SealAI, ein präziser Fachberater. Antworte kurz, korrekt und auf Deutsch.",
        ),
        ("user", "{query}"),
    ]
)


def build_mvp_graph() -> StateGraph:
    """Minimaler, professionell strukturierter MVP-Graph.

    Knoten:
      - entry: Intent-Klassifikation
      - route: Orchestrator (material | llm | fallback)
      - material_prep -> rag -> material_agent
      - llm_simple
      - output (END)
    """
    builder = StateGraph(MvpState)

    base_llm = get_llm(streaming=True)

    # Nodes
    def entry_node(state: MvpState) -> MvpState:
        label = classify_intent(base_llm, state.get("messages", []))
        intent = "material" if label == "material_select" else "llm"
        return {"intent": intent}

    def route_node(state: MvpState) -> MvpState:
        intent = (state.get("intent") or "unknown").lower()
        route: Literal["material", "llm", "fallback"]
        if intent == "material":
            route = "material"
        elif intent == "llm":
            route = "llm"
        else:
            route = "fallback"
        return {"route": route}

    def material_prep_node(state: MvpState) -> MvpState:
        q = (state.get("query") or "").strip()
        if not q:
            q = _last_user_text(state.get("messages", []))
        return {"query": q}

    def rag_node(state: MvpState) -> MvpState:
        q = (state.get("query") or "").strip()
        tenant = state.get("user_id") or None
        try:
            docs = hybrid_retrieve(query=q, tenant=tenant, k=6)
        except Exception:
            docs = []
        return {"retrieved_docs": docs}

    def material_agent_node(state: MvpState) -> MvpState:
        agent = get_material_agent()
        # Merge retrieved docs into state for prompt conditioning
        out = agent.invoke(state) or {}
        # Ensure AIMessage is present
        msgs = out.get("messages") if isinstance(out, dict) else None
        if not msgs:
            ai = AIMessage(content="Leider keine Antwort verfügbar.")
            return {"messages": [ai]}
        return {"messages": msgs}

    def llm_simple_node(state: MvpState) -> MvpState:
        q = _last_user_text(state.get("messages", []))
        try:
            chain = _LLM_SIMPLE_PROMPT | base_llm
            resp = chain.invoke({"query": q})
            ai = resp if isinstance(resp, AIMessage) else AIMessage(content=getattr(resp, "content", str(resp)))
        except Exception:
            ai = AIMessage(content="Entschuldigung, ich konnte das nicht beantworten.")
        return {"messages": [ai]}

    def output_node(state: MvpState) -> MvpState:
        # Pass-through; finalization done by runtime
        return {}

    # Register nodes with logging wrappers for traceability
    builder.add_node("entry", wrap_node_with_logging(_GRAPH_NAME, "entry", entry_node))
    builder.add_node("route", wrap_node_with_logging(_GRAPH_NAME, "route", route_node))
    builder.add_node("material_prep", wrap_node_with_logging(_GRAPH_NAME, "material_prep", material_prep_node))
    builder.add_node("rag", wrap_node_with_logging(_GRAPH_NAME, "rag", rag_node))
    builder.add_node("material_agent", wrap_node_with_logging(_GRAPH_NAME, "material_agent", material_agent_node))
    builder.add_node("llm_simple", wrap_node_with_logging(_GRAPH_NAME, "llm_simple", llm_simple_node))
    builder.add_node("output", wrap_node_with_logging(_GRAPH_NAME, "output", output_node))

    builder.set_entry_point("entry")

    def decide_intent(state: MvpState) -> str:
        intent = (state.get("intent") or "unknown").lower()
        branch = "material" if intent == "material" else ("llm" if intent == "llm" else "fallback")
        log_branch_decision(_GRAPH_NAME, "entry", "intent", branch, state)
        return branch

    builder.add_conditional_edges(
        "entry",
        decide_intent,
        {
            "material": "material_prep",
            "llm": "llm_simple",
            "fallback": "llm_simple",
        },
    )

    builder.add_edge("material_prep", "rag")
    builder.add_edge("rag", "material_agent")
    builder.add_edge("material_agent", "output")
    builder.add_edge("llm_simple", "output")
    builder.add_edge("output", END)

    log.info("[mvp] Graph ready (minimal routing: material|llm)")
    return builder


__all__ = ["build_mvp_graph"]

