from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import AIMessage, SystemMessage

from app.langgraph.state import SealAIState


async def general_answer_node(state: SealAIState, *, config: Dict[str, Any]) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    message_in = str(state.get("message_in") or slots.get("user_query") or "").strip()
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    llm = cfg.get("general_answer_llm") if isinstance(cfg, dict) else None
    if llm is None:
        return {}

    prompt = [
        SystemMessage(content="Du bist ein hilfreicher Assistent."),
        AIMessage(content=message_in),
    ]
    response = await llm.ainvoke(prompt, config=config)
    content = getattr(response, "content", None)
    answer = str(content or "").strip()

    slots["final_answer"] = answer
    slots["final_answer_source"] = "general_short_answer"

    return {
        "message_out": answer,
        "msg_type": "msg-general-answer",
        "slots": slots,
    }


__all__ = ["general_answer_node"]
