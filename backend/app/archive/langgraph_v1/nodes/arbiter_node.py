from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.types import RunnableConfig

from app.core.config import settings
from app.langgraph.state import SealAIState
from app.langgraph.types import interrupt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Du wählst aus mehreren Vorschlägen die beste finale Empfehlung und begründest sie."
    " Antworte immer als JSON:\n"
    "{\n"
    '  "final_recommendation": "...",\n'
    '  "reasoning": "...",\n'
    '  "fallback_reason": "..." // optional\n'
    "}\n"
    "Wenn Informationen fehlen, setze fallback_reason und frage freundlich nach Details."
)


def _use_offline_mode() -> bool:
    forced = os.getenv("LANGGRAPH_USE_FAKE_LLM", "")
    if forced.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return not api_key or api_key.lower() in {"dummy", "test"}


def _resolve_llm(config: RunnableConfig):
    cfg = (config.get("configurable") or {}) if isinstance(config, dict) else {}
    candidate = cfg.get("arbiter_llm")
    if candidate and hasattr(candidate, "invoke"):
        return candidate
    model_name = getattr(settings, "openai_model", "gpt-5-mini")
    return ChatOpenAI(model=model_name, temperature=0.2, streaming=False)


def _flatten_messages(messages: List[BaseMessage]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = getattr(msg, "type", getattr(msg, "role", "unknown"))
        content = getattr(msg, "content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def _offline_payload(state: SealAIState) -> Dict[str, str]:
    slots = state.get("slots") or {}
    final_candidate = str(slots.get("candidate_answer") or "").strip()
    if not final_candidate:
        final_candidate = "Noch keine finale Empfehlung vorhanden. Bitte bestätige bevorzugte Richtung."
    reasoning = (
        "Basierend auf der letzten validierten Empfehlung erscheint dieser Vorschlag konsistent."
    )
    return {
        "final_recommendation": final_candidate,
        "reasoning": reasoning,
        "fallback_reason": "",
        "message": f"{final_candidate}\n\nBegründung: {reasoning}",
    }


def _normalize_payload(data: Dict[str, Any]) -> Dict[str, str]:
    recommendation = str(data.get("final_recommendation") or "").strip()
    reasoning = str(data.get("reasoning") or "").strip()
    fallback_reason = str(data.get("fallback_reason") or "").strip()
    message = str(data.get("message") or "").strip()
    if not message:
        parts = []
        if recommendation:
            parts.append(recommendation)
        if reasoning:
            parts.append(f"Begründung: {reasoning}")
        message = "\n\n".join(parts) or "Ich benötige weitere Informationen, um eine Empfehlung zu finalisieren."
    return {
        "final_recommendation": recommendation or message,
        "reasoning": reasoning or "Keine Begründung angegeben.",
        "fallback_reason": fallback_reason,
        "message": message,
    }


def arbiter_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        logger.info("arbiter_node: keine Nachrichten im State.")
        return {}

    use_offline = _use_offline_mode()
    payload: Dict[str, Any]
    if use_offline:
        payload = _offline_payload(state)
    else:
        llm = _resolve_llm(config)
        prompt = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_flatten_messages(messages)),
        ]
        try:
            response = llm.invoke(prompt)
            raw = getattr(response, "content", None)
            raw_text = raw if isinstance(raw, str) else str(response)
            payload = json.loads(raw_text)
            if not isinstance(payload, dict):
                raise ValueError("LLM output is not a dict")
        except Exception:
            logger.exception("arbiter_node: LLM-Parsing fehlgeschlagen, nutze Offline-Fallback.")
            payload = _offline_payload(state)

    normalized = _normalize_payload(payload)

    slots = dict(state.get("slots") or {})
    meta = dict(state.get("meta") or {})
    slots["final_recommendation"] = normalized["final_recommendation"]
    meta["arbiter_reasoning"] = normalized["reasoning"]

    ai_message = AIMessage(
        content=normalized["message"],
        additional_kwargs={"phase": "review", "label": "Arbiter"},
    )
    messages.append(ai_message)

    updates: Dict[str, Any] = {
        "messages": messages,
        "slots": slots,
        "meta": meta,
        "message_out": normalized["message"],
        "msg_type": "msg-arbiter",
        "phase": "review",
    }

    if normalized["fallback_reason"]:
        state["message_out"] = normalized["message"]
        state["msg_type"] = "msg-arbiter"
        interrupt({"prompt": normalized["message"], "reason": normalized["fallback_reason"]})

    return updates


__all__ = ["arbiter_node"]
