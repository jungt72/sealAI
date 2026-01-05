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
    "Bewerte die Vertrauenswürdigkeit der aktuellen Beratung auf Basis der validierten Anforderungen "
    "und Empfehlungen.\n\nAntwortformat (JSON):\n{\n  \"confidence_score\": 0.0-1.0,\n"
    "  \"confidence_reason\": \"...\",\n  \"fallback_reason\": \"...\", // optional\n"
    "  \"message\": \"...\" // optional\n}"
)


def _use_offline_mode() -> bool:
    forced = os.getenv("LANGGRAPH_USE_FAKE_LLM", "")
    if forced.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return not api_key or api_key.lower() in {"dummy", "test"}


def _resolve_llm(config: RunnableConfig):
    cfg = (config.get("configurable") or {}) if isinstance(config, dict) else {}
    candidate = cfg.get("confidence_gate_llm")
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


def _offline_payload(state: SealAIState) -> Dict[str, Any]:
    slots = state.get("slots") or {}
    requirements_validated = str(slots.get("requirements_validated") or "").strip()
    issues = str((state.get("meta") or {}).get("review_issues") or "").strip()
    if not requirements_validated:
        return {
            "confidence_score": 0.5,
            "confidence_reason": "Validierte Anforderungen fehlen – bitte Review wiederholen.",
            "fallback_reason": "",
            "message": "Ich bin mir nicht sicher, ob die Anforderungen vollständig sind. Bitte bestätige sie.",
        }
    return {
        "confidence_score": 0.92,
        "confidence_reason": "Anforderungen konsistent, nur kleinere Hinweise.",
        "fallback_reason": "",
        "message": f"Die Anforderungen wirken plausibel. Hinweise: {issues or 'keine'}",
    }


def _normalize_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    score = data.get("confidence_score", 0.0)
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0.0
    reason = str(data.get("confidence_reason") or "").strip()
    fallback = str(data.get("fallback_reason") or "").strip()
    message = str(data.get("message") or "").strip()
    if not message:
        message = reason or "Ich benötige weitere Angaben, um die Empfehlung freizugeben."
    return {
        "confidence_score": max(0.0, min(1.0, score)),
        "confidence_reason": reason or "Keine Begründung angegeben.",
        "fallback_reason": fallback,
        "message": message,
    }


def confidence_gate_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        logger.info("confidence_gate_node: keine Nachrichten im State.")
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
            logger.exception("confidence_gate_node: LLM-Parsing fehlgeschlagen, nutze Offline-Fallback.")
            payload = _offline_payload(state)

    normalized = _normalize_payload(payload)
    meta = dict(state.get("meta") or {})
    meta["confidence_score"] = normalized["confidence_score"]
    meta["confidence_reason"] = normalized["confidence_reason"]

    ai_message = AIMessage(
        content=normalized["message"],
        additional_kwargs={"phase": "review", "label": "Confidence-Gate"},
    )
    messages.append(ai_message)

    updates: Dict[str, Any] = {
        "messages": messages,
        "meta": meta,
        "message_out": normalized["message"],
        "msg_type": "msg-confidence-gate",
        "phase": "review",
    }

    if normalized["fallback_reason"]:
        state["message_out"] = normalized["message"]
        state["msg_type"] = "msg-confidence-gate"
        interrupt({"prompt": normalized["message"], "reason": normalized["fallback_reason"]})

    if normalized["confidence_score"] < 0.8:
        updates["slots"] = dict(state.get("slots") or {})
        updates["slots"]["confidence_gate"] = "review_required"

    return updates


__all__ = ["confidence_gate_node"]
