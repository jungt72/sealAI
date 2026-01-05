from __future__ import annotations
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from app.langgraph.state import SealAIState, ensure_phase

def entry_frontend(state: SealAIState) -> Dict[str, Any]:
    """
    Nimmt den vom REST-Endpunkt gesetzten Slot 'user_query' und spiegelt ihn
    als HumanMessage in die State.messages. Damit können Supervisor/Resolver
    zuverlässig auf den Text zugreifen.
    """
    user_query = str((state.get("slots") or {}).get("user_query") or "").strip()
    if not user_query:
        return {"phase": ensure_phase(state)}

    msg = HumanMessage(content=user_query, id="msg-user-entry")
    return {"messages": [msg], "phase": ensure_phase(state)}
