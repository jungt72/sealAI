# backend/app/langgraph/nodes/entry_frontend.py
# MIGRATION: Phase-2 - Entry point

from ..state import SealAIState, new_user_message
from ..utils.ids import generate_message_id

async def entry_frontend(state: SealAIState) -> dict:
    user_query = (state.get("slots") or {}).get("user_query", "")
    if not user_query:
        raise ValueError("user_query required in slots")

    message = new_user_message(
        user_query,
        user_id=state.get("meta", {}).get("user_id", "user"),
        msg_id=generate_message_id(),
    )
    slots = {**(state.get("slots") or {}), "last_query": user_query}
    return {"messages": [message], "slots": slots}
