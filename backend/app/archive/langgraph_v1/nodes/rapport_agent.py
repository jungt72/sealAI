from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.types import RunnableConfig

from app.langgraph.nodes.members import _use_offline_mode
from app.langgraph.prompts.prompt_loader import load_jinja_chat_prompt
from app.langgraph.state import SealAIState
from app.langgraph.utils.llm import create_llm_for_domain

logger = logging.getLogger(__name__)

RAPPORT_PROMPT = load_jinja_chat_prompt("rapport_agent.de.j2")


def _flatten_history(messages: List[BaseMessage]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = getattr(msg, "type", getattr(msg, "role", "msg"))
        content = getattr(msg, "content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _last_user_message(messages: List[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def _infer_user_name(slots: Dict[str, Any]) -> str:
    for key in ("contact_name", "user_name", "display_name"):
        value = slots.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    profile = slots.get("user_profile")
    if isinstance(profile, dict):
        value = profile.get("display_name") or profile.get("name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Kollegin"


def _infer_company(slots: Dict[str, Any]) -> str:
    for key in ("company_name", "company", "account"):
        value = slots.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Ihrem Unternehmen"


def _offline_response(user_name: str) -> str:
    return (
        f"Hallo {user_name}! Schön, dass Sie da sind. "
        "Wie läuft es aktuell bei Ihnen, bevor wir gemeinsam in die technischen Details gehen? "
        "Wenn es für Sie passt, würde ich im nächsten Schritt gern ein paar gezielte Fragen stellen."
    )


def _resolve_llm(config: RunnableConfig) -> BaseChatModel:
    cfg = (config.get("configurable") or {}) if isinstance(config, dict) else {}
    candidate = cfg.get("rapport_llm") or cfg.get("llm")
    if isinstance(candidate, BaseChatModel):
        return candidate
    return create_llm_for_domain("warmup")


def rapport_agent_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    messages: List[BaseMessage] = list(state.get("messages") or [])
    if not messages:
        logger.debug("rapport_agent: no messages to respond to.")
        return {"phase": "rapport"}

    slots = dict(state.get("slots") or {})
    if slots.get("rapport_phase_done"):
        return {}

    prompt_inputs = {
        "user_name": _infer_user_name(slots),
        "company": _infer_company(slots),
        "history": _flatten_history(messages),
        "latest_user_message": _last_user_message(messages),
    }

    if _use_offline_mode():
        reply_text = _offline_response(prompt_inputs["user_name"])
    else:
        prompt = RAPPORT_PROMPT.format_prompt(**prompt_inputs)
        llm = _resolve_llm(config)
        try:
            llm_result = llm.invoke(prompt.to_messages())
            reply_text = getattr(llm_result, "content", str(llm_result)) or ""
        except Exception:
            logger.exception("rapport_agent: LLM invocation failed, using offline fallback.")
            reply_text = _offline_response(prompt_inputs["user_name"])

    reply_text = reply_text.strip()
    if not reply_text:
        reply_text = _offline_response(prompt_inputs["user_name"])

    ai_message = AIMessage(content=reply_text, additional_kwargs={"phase": "rapport", "label": "Rapport"})
    messages.append(ai_message)

    summary = reply_text.split(".")[0].strip() if "." in reply_text else reply_text
    slots["rapport_summary"] = summary
    slots["rapport_phase_done"] = True

    return {
        "messages": messages,
        "slots": slots,
        "rapport_phase_done": True,
        "rapport_summary": summary,
        "phase": "rapport",
    }


__all__ = ["rapport_agent_node"]
