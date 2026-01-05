# MIGRATION: Phase-2 - Discovery intake

from langchain_core.messages import HumanMessage

from ..state import SealAIState, new_assistant_message
from ..utils.ids import generate_message_id


async def discovery_intake(state: SealAIState) -> dict:
    # Analysiere letzte User-Message und stelle Fragen
    last_user_msg = next(
        (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
        None,
    )
    if not last_user_msg:
        questions = ["What is your query?"]
    else:
        # Dummy: Immer gleiche Fragen
        questions = ["What is the material?", "What are the conditions?", "Any specific parameters?"]
    content = "\n".join(questions)
    assistant_msg = new_assistant_message(content, msg_id=generate_message_id())
    slots = {**(state.get("slots") or {}), "coverage": 0.3}  # Dummy
    return {"messages": [assistant_msg], "slots": slots}
