"""Centralized response node for Supervisor-controlled user messages."""

from __future__ import annotations

from typing import Dict, Any

from langchain_core.messages import AIMessage

from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.jinja import render_template


def response_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, object]:
    """
    Single point that turns structured state into a user-facing message.

    Responsibility:
    - select appropriate template based on response_kind/ask_missing/knowledge/error
    - append exactly one AIMessage
    - set final_text
    """
    wm: WorkingMemory = state.working_memory or WorkingMemory()
    ask_missing = state.ask_missing_request
    context = {
        "ask_missing_request": ask_missing,
        "response_kind": wm.response_kind,
        "response_text": wm.response_text,
        "knowledge_material": wm.knowledge_material,
        "knowledge_lifetime": wm.knowledge_lifetime,
        "knowledge_generic": wm.knowledge_generic,
        "error": state.error,
        "phase": state.phase or "final",
    }

    text = render_template("response_router.j2", context)
    messages = list(state.messages or [])
    messages.append(AIMessage(content=[{"type": "text", "text": text}]))

    return {
        "messages": messages,
        "phase": state.phase or "final",
        "last_node": "response_node",
        "final_text": text,
    }


__all__ = ["response_node"]
