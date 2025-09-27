from __future__ import annotations

import logging
from typing import TypedDict, List, Literal, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langgraph.graph import StateGraph
from langgraph.constants import END
from langchain_core.runnables import RunnableLambda

from app.services.langgraph.tools import long_term_memory as ltm
from .intent_router import classify_intent
from .consult.build import build_consult_graph
from app.services.langgraph.llm_factory import get_llm
from .logging_utils import wrap_node_with_logging, log_branch_decision

log = logging.getLogger(__name__)
_GRAPH_NAME = "SupervisorGraph"

@tool
def ltm_search(query: str) -> str:
    """Durchsucht das Long-Term-Memory (Qdrant) nach relevanten Erinnerungen (MMR, top-k=5) und gibt einen zusammenhängenden Kontext-Text zurück."""
    ctx, _hits = ltm.ltm_query(query, strategy="mmr", top_k=5)
    return ctx or "Keine relevanten Erinnerungen gefunden."

@tool
def ltm_store(user: str, chat_id: str, text: str, kind: str = "note") -> str:
    """Speichert einen Text-Schnipsel im Long-Term-Memory (Qdrant). Parameter: user, chat_id, text, kind."""
    try:
        pid = ltm.upsert_memory(user=user, chat_id=chat_id, text=text, kind=kind)
        return f"Memory gespeichert (ID={pid})"
    except Exception as e:
        return f"Fehler beim Speichern: {e}"

TOOLS = [ltm_search, ltm_store]

class ChatState(TypedDict, total=False):
    messages: List[BaseMessage]
    intent: Literal["consult", "chitchat"]
    query_type: Literal["simple", "complex"]

def create_llm() -> ChatOpenAI:
    # LLM aus Factory – mit streaming=True
    return get_llm(streaming=True)


_CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Du analysierst Anfragen zur Dichtungstechnik und klassifizierst ihre Komplexität.",
        ),
        (
            "user",
            """
Klassifiziere die Query als "simple" oder "complex".

simple ⇒ Allgemeine Vergleiche/Eigenschaften ohne spezifischen Anwendungsfall oder Norm.
complex ⇒ Konkrete Anwendungen, Betriebsbedingungen, Normen, Maß-/Sicherheitsangaben.
Bei Unsicherheit gib "complex" zurück.

Query: {query}

Antwort ausschließlich mit simple oder complex.
""",
        ),
    ]
)


_SIMPLE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
Du bist SealAI, Fachberater für Dichtungstechnik.
Beantworte einfache Wissens- oder Vergleichsfragen präzise, knapp und ohne externe Quellen.
Sprache: Deutsch.
""",
        ),
        ("user", "Query: {query}\n\nAntwort:"),
    ]
)


def _last_user_text(messages: List[BaseMessage] | None) -> str:
    if not messages:
        return ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = (msg.content or "").strip()
            if content:
                return content
        elif isinstance(msg, dict):
            role = str(msg.get("role") or msg.get("type") or "").lower()
            if role in {"human", "user"}:
                text = str(msg.get("content") or "").strip()
                if text:
                    return text
    return ""


def build_chat_builder(llm: Optional[ChatOpenAI] = None) -> StateGraph:
    """Supervisor-Graph mit echtem Streaming:
    - chitchat als Runnable-Chain (liefert on_chat_model_stream)
    - consult als eingebetteter Subgraph (Events werden durchgereicht)
    - simple_response für Low-Complexity-Queries (ohne RAG)
    """
    log.info("[supervisor] Initialisiere…")
    builder = StateGraph(ChatState)

    base_llm = llm or create_llm()          # streaming=True
    llm_chitchat = base_llm.bind_tools(TOOLS)

    # Consult **als Subgraph** (NICHT kompilieren/aufrufen)
    consult_graph = build_consult_graph()

    classifier_llm = get_llm(streaming=False)
    simple_llm = base_llm
    classifier_chain = _CLASSIFIER_PROMPT | classifier_llm
    simple_chain = _SIMPLE_PROMPT | simple_llm

    # Router
    def router_node(state: ChatState) -> ChatState:
        intent = classify_intent(base_llm, state.get("messages", []))
        return {"intent": intent}

    def complexity_router_node(state: ChatState) -> ChatState:
        query = _last_user_text(state.get("messages", []))
        if not query:
            return {"query_type": "complex", "phase": "complexity_router"}
        try:
            result = classifier_chain.invoke({"query": query})
            classification = getattr(result, "content", str(result))
        except Exception as exc:
            log.warning("[supervisor] complexity_router_failed", exc=str(exc))
            classification = ""
        classification = (classification or "").strip().lower()
        query_type = "simple" if classification.startswith("simple") else "complex"
        return {"query_type": query_type, "phase": "complexity_router"}

    def simple_response_node(state: ChatState) -> ChatState:
        query = _last_user_text(state.get("messages", []))
        if not query:
            ai_msg = AIMessage(content="Ich habe keine konkrete Frage erkannt.")
            return {"messages": [ai_msg], "query_type": "simple", "phase": "simple_response"}
        try:
            resp = simple_chain.invoke({"query": query})
        except Exception as exc:
            log.warning("[supervisor] simple_response_failed", exc=str(exc))
            resp = AIMessage(content="Entschuldigung, ich konnte das gerade nicht beantworten.")
        ai_msg = resp if isinstance(resp, AIMessage) else AIMessage(content=getattr(resp, "content", str(resp)))
        return {"messages": [ai_msg], "query_type": "simple", "phase": "simple_response"}

    # Chitchat als Runnable-Chain → erzeugt on_chat_model_stream Events
    def _pick_msgs(s: ChatState):
        return s.get("messages", [])

    def _wrap_msg(m):
        ai = m if isinstance(m, AIMessage) else AIMessage(content=getattr(m, "content", str(m)))
        return {"messages": [ai]}

    chitchat_chain = RunnableLambda(_pick_msgs) | llm_chitchat | RunnableLambda(_wrap_msg)

    builder.add_node("router", wrap_node_with_logging(_GRAPH_NAME, "router", router_node))
    builder.add_node(
        "complexity_router",
        wrap_node_with_logging(_GRAPH_NAME, "complexity_router", complexity_router_node),
    )
    builder.add_node(
        "simple_response",
        wrap_node_with_logging(_GRAPH_NAME, "simple_response", simple_response_node),
    )
    builder.add_node("chitchat", chitchat_chain)
    builder.add_node("consult", consult_graph)

    builder.set_entry_point("router")

    def decide(state: ChatState) -> str:
        intent = state.get("intent") or "chitchat"
        branch = "consult" if intent == "consult" else "chitchat"
        log_branch_decision(_GRAPH_NAME, "router", "intent", branch, state)
        return branch

    def decide_complexity(state: ChatState) -> str:
        query_type = (state.get("query_type") or "complex").lower()
        branch = "simple" if query_type == "simple" else "complex"
        log_branch_decision(_GRAPH_NAME, "complexity_router", "query_type", branch, state)
        return branch

    builder.add_conditional_edges(
        "router",
        decide,
        {
            "consult": "complexity_router",
            "chitchat": "chitchat",
        },
    )
    builder.add_conditional_edges(
        "complexity_router",
        decide_complexity,
        {
            "simple": "simple_response",
            "complex": "consult",
        },
    )
    builder.add_edge("simple_response", END)
    builder.add_edge("consult", END)
    builder.add_edge("chitchat", END)

    log.info("[supervisor] Bereit (Streaming aktiviert).")
    return builder

def build_supervisor_graph(llm: Optional[ChatOpenAI] = None) -> StateGraph:
    """Wrapper für chat_ws._ensure_graph(): liefert einen *uncompilierten* StateGraph."""
    return build_chat_builder(llm)
