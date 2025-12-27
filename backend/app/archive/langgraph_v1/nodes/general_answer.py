from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import RunnableConfig

from app.core.config import settings
from app.langgraph.state import SealAIState
from app.langgraph.utils.streaming import ainvoke_with_config

SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Assistent. Beantworte die folgende Frage direkt, "
    "sachlich und in maximal 4 Sätzen:"
)


def _resolve_question(state: SealAIState) -> str:
    message_in = state.get("message_in")
    if isinstance(message_in, str) and message_in.strip():
        return message_in.strip()
    slots = state.get("slots") or {}
    return str(slots.get("user_query") or "").strip()


def _resolve_llm(config: RunnableConfig | None) -> Any:
    cfg = (config.get("configurable") or {}) if isinstance(config, dict) else {}
    candidate = cfg.get("general_answer_llm") or cfg.get("llm_small")
    if candidate and (hasattr(candidate, "ainvoke") or hasattr(candidate, "invoke")):
        return candidate
    model_name = getattr(settings, "openai_model", "gpt-5-mini")
    return ChatOpenAI(model=model_name, temperature=0.2, streaming=getattr(settings, "llm_streaming", True))


async def _generate_answer(question: str, llm: Any, config: RunnableConfig | None) -> str:
    if not question:
        return "Ich gebe gerne kurze Antworten auf allgemeine Fragen, sobald du mir eine stellst."
    prompt = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]
    result = await ainvoke_with_config(llm, prompt, config)
    content = getattr(result, "content", None)
    text = content if isinstance(content, str) else str(result)
    return text.strip() or "Ich habe deine Frage erhalten und beantworte sie gerne."


async def general_answer_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    question = _resolve_question(state)
    llm = _resolve_llm(config)
    try:
        answer = await _generate_answer(question, llm, config)
    except Exception:
        answer = "Ich habe deine Frage erhalten und beantworte sie gerne kurz: Bitte stelle sie noch einmal."

    slots = dict(state.get("slots") or {})
    slots["candidate_answer"] = answer
    slots["final_answer"] = answer
    slots["final_answer_source"] = "general_short_answer"

    return {
        "slots": slots,
        "message_out": answer,
        "msg_type": "msg-general-answer",
        "phase": "exit",
    }


__all__ = ["general_answer_node"]
