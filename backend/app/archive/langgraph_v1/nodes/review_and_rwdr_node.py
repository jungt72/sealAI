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
from app.langgraph.utils.streaming import ainvoke_with_config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Du validierst Anforderungen und entdeckst Risiken. Antworte immer als JSON mit den Feldern "
    "{validated_requirements, identified_issues, recommendations, fallback_reason}. "
    "Falls dir Informationen fehlen, setze fallback_reason und stelle eine freundliche Rückfrage."
)


def _use_offline_mode() -> bool:
    forced = os.getenv("LANGGRAPH_USE_FAKE_LLM", "")
    if forced.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return not api_key or api_key.lower() in {"dummy", "test"}


def _resolve_llm(config: RunnableConfig):
    cfg = (config.get("configurable") or {}) if isinstance(config, dict) else {}
    candidate = cfg.get("review_llm")
    if candidate and (hasattr(candidate, "ainvoke") or hasattr(candidate, "invoke")):
        return candidate
    model_name = getattr(settings, "openai_model", "gpt-5-mini")
    return ChatOpenAI(
        model=model_name,
        temperature=0.2,
        streaming=getattr(settings, "llm_streaming", True),
    )


def _flatten_messages(messages: List[BaseMessage]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = getattr(msg, "type", getattr(msg, "role", "unknown"))
        content = getattr(msg, "content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def _offline_payload(state: SealAIState) -> Dict[str, str]:
    slots = state.get("slots") or {}
    requirements = str(slots.get("requirements") or "Noch keine Anforderungen festgehalten.").strip()
    issues = "Bitte bestätige Medium, Druck und Temperatur, damit ich Risiken bewerten kann."
    recommendations = "Sammle fehlende Parameter zur Einbausituation und stimme dann das Profil ab."
    message = (
        f"Ich habe folgende Anforderungen festgehalten:\n{requirements}\n"
        f"Unsicherheiten/Risiken: {issues}\n"
        f"Empfehlung: {recommendations}"
    )
    return {
        "validated_requirements": requirements,
        "identified_issues": issues,
        "recommendations": recommendations,
        "fallback_reason": "",
        "message": message,
    }


def _normalize_payload(data: Dict[str, Any]) -> Dict[str, str]:
    validated = str(data.get("validated_requirements") or "").strip()
    issues = str(data.get("identified_issues") or "").strip()
    recs = str(data.get("recommendations") or "").strip()
    fallback_reason = str(data.get("fallback_reason") or "").strip()
    message = str(data.get("message") or "").strip()
    if not message:
        message = validated or "Ich benötige weitere Details, um die Anforderungen zu bestätigen."
    return {
        "validated_requirements": validated or message,
        "identified_issues": issues or "Keine Risiken genannt.",
        "recommendations": recs or "Bitte bestätige die nächsten Schritte.",
        "fallback_reason": fallback_reason,
        "message": message,
    }


async def review_and_rwdr_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        logger.info("review_and_rwdr_node: keine Nachrichten im State.")
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
            response = await ainvoke_with_config(llm, prompt, config)
            raw = getattr(response, "content", None)
            raw_text = raw if isinstance(raw, str) else str(response)
            payload = json.loads(raw_text)
            if not isinstance(payload, dict):
                raise ValueError("LLM output is not a dict")
        except Exception:
            logger.exception("review_and_rwdr_node: LLM-Parsing fehlgeschlagen, nutze Offline-Fallback.")
            payload = _offline_payload(state)

    normalized = _normalize_payload(payload)
    slots = dict(state.get("slots") or {})
    meta = dict(state.get("meta") or {})

    slots["requirements_validated"] = normalized["validated_requirements"]
    meta["review_issues"] = normalized["identified_issues"]
    meta["review_recommendations"] = normalized["recommendations"]

    ai_message = AIMessage(
        content=normalized["message"],
        additional_kwargs={"phase": "review", "label": "Review & RWDR"},
    )
    messages.append(ai_message)

    updates: Dict[str, Any] = {
        "messages": messages,
        "slots": slots,
        "meta": meta,
        "message_out": normalized["message"],
        "msg_type": "msg-review",
        "phase": "review",
    }

    if normalized["fallback_reason"]:
        state["message_out"] = normalized["message"]
        state["msg_type"] = "msg-review"
        interrupt({"prompt": normalized["message"], "reason": normalized["fallback_reason"]})

    return updates


__all__ = ["review_and_rwdr_node"]
