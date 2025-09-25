from __future__ import annotations

import logging
from functools import lru_cache
from typing import TypedDict, List, Literal, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph
from langgraph.constants import END

from app.services.langgraph.tools import long_term_memory as ltm
from .intent_router import classify_intent
from .consult.build import build_consult_graph
from app.services.langgraph.llm_factory import get_llm

log = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def create_llm() -> ChatOpenAI:
    """Create a ChatOpenAI instance (streaming enabled) from the central LLM factory."""
    return get_llm(streaming=True)

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

@lru_cache(maxsize=1)
def _compiled_consult_graph():
    return build_consult_graph().compile()

def build_chat_builder(llm: Optional[ChatOpenAI] = None) -> StateGraph:
    """Erstellt den Supervisor-Graphen: Router -> (Consult|Chitchat)."""
    log.info("[supervisor] Initialisiere…")
    builder = StateGraph(ChatState)

    base_llm = llm or create_llm()
    llm_chitchat = base_llm.bind_tools(TOOLS)
    consult_graph = _compiled_consult_graph()

    def router_node(state: ChatState) -> ChatState:
        intent = classify_intent(base_llm, state.get("messages", []))
        return {"intent": intent}

    def chitchat_node(state: ChatState) -> ChatState:
        history = state.get("messages", [])
        result = llm_chitchat.invoke(history)
        ai_msg = result if isinstance(result, AIMessage) else AIMessage(content=getattr(result, "content", str(result)))
        return {"messages": [ai_msg]}

    def consult_node(state: ChatState) -> ChatState:
        result = consult_graph.invoke({"messages": state.get("messages", [])})
        out_msgs = result.get("messages") or []
        ai_txt = ""
        for m in reversed(out_msgs):
            if isinstance(m, AIMessage):
                ai_txt = (m.content or "").strip()
                break
        if not ai_txt:
            ai_txt = "Die Beratung wurde abgeschlossen."
        return {"messages": [AIMessage(content=ai_txt)]}

    builder.add_node("router", router_node)
    builder.add_node("chitchat", chitchat_node)
    builder.add_node("consult", consult_node)

    builder.set_entry_point("router")

    def decide(state: ChatState) -> str:
        intent = state.get("intent") or "chitchat"
        return "consult" if intent == "consult" else "chitchat"

    builder.add_conditional_edges("router", decide, {"consult": "consult", "chitchat": "chitchat"})
    builder.add_edge("consult", END)
    builder.add_edge("chitchat", END)

    log.info("[supervisor] Bereit.")
    return builder
