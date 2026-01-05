from __future__ import annotations

from typing import Any, Dict

from langgraph.types import RunnableConfig

from app.langgraph.nodes.intent_classifier import CLARIFY_MSG_TYPE, build_clarify_message
from app.langgraph.state import SealAIState, new_assistant_message


def intent_clarify_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    Emits a professional clarification question instead of failing on low-confidence intent.
    """
    slots_source = state.get("slots") or {}
    user_query = str(slots_source.get("user_query") or "")
    clarify_text = build_clarify_message(user_query)

    slots = dict(state.get("slots") or {})
    slots["final_answer"] = clarify_text
    slots["final_answer_source"] = "intent_clarification"

    messages = list(state.get("messages") or [])
    messages.append(new_assistant_message(clarify_text, msg_id="msg-intent-clarify"))

    return {
        "slots": slots,
        "messages": messages,
        "message_out": clarify_text,
        "msg_type": CLARIFY_MSG_TYPE,
        "pending_intent_choice": True,
    }


__all__ = ["intent_clarify_node"]
