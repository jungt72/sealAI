from __future__ import annotations

import json
import logging
import os
import asyncio
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import RunnableConfig

from app.core.config import settings
from app.langgraph.state import IntentPrediction, SealAIState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Entscheide, ob die Nutzereingabe eine allgemeine Frage ist oder eine "
    "produktbezogene Beratung erfordert. Gib JSON zurück mit "
    "{type: 'general'|'consulting', confidence: float, reason: str}."
)
CLARIFY_TEMPLATE = (
    "Vielen Dank für Ihre Nachricht.\n"
    "Damit ich Sie gezielt unterstützen kann: Wünschen Sie eher\n"
    "1) eine kurze Übersicht zu den wichtigsten Eigenschaften (z. B. zu {topic}) oder\n"
    "2) eine ausführlichere technische Beratung mit konkreten Empfehlungen für Ihre Anwendung?\n"
    "Wenn Sie möchten, können Sie kurz etwas zu Medium, Temperatur, Druck und Bewegungsart Ihrer Anwendung schreiben."
)
CLARIFY_MSG_TYPE = "msg-intent-clarify"
INTENT_CLARIFY_CONFIDENCE_THRESHOLD = 0.8
_SHORT_HINTS = ("kurz", "knapp", "kurze", "short", "schnell")
_CONSULT_HINTS = ("beratung", "ausführlich", "detail", "detailliert", "consult", "beratungsgespräch")


def _extract_user_query(state: SealAIState) -> str:
    slots = state.get("slots") or {}
    return str(slots.get("user_query") or "").strip()


def _normalize_topic(raw: str) -> str:
    cleaned = " ".join((raw or "").split())
    if not cleaned:
        return "Ihrem Anliegen"
    return cleaned[:160]


def build_clarify_message(user_query: str) -> str:
    topic = _normalize_topic(user_query)
    return CLARIFY_TEMPLATE.format(topic=topic)


def _resolve_llm(config: RunnableConfig | None) -> Any:
    cfg = (config.get("configurable") or {}) if isinstance(config, dict) else {}
    candidate = cfg.get("intent_classifier_llm")
    if candidate and hasattr(candidate, "invoke"):
        return candidate
    model_name = os.getenv("INTENT_CLASSIFIER_MODEL") or getattr(settings, "llm_small", "gpt-5-nano")
    return ChatOpenAI(model=model_name, temperature=0.0)


def _extract_content(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if content is not None:
        return str(content)
    return str(response)


def _parse_prediction(raw_text: str) -> IntentPrediction:
    default = IntentPrediction(
        type="consulting",
        confidence=1.0,
        reason="Fallback decision.",
        domain="dichtungstechnik",
        kind="consulting",
    )
    try:
        data = json.loads(raw_text)
    except Exception:
        logger.warning("intent_classifier: JSON parse failed, using fallback.")
        return default

    prediction: IntentPrediction = IntentPrediction()
    intent_type = str(data.get("type") or "").strip().lower()
    if intent_type not in {"general", "consulting"}:
        intent_type = "consulting"
    try:
        confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(data.get("reason") or "").strip() or "Keine Begründung angegeben."
    domain = str(data.get("domain") or "dichtungstechnik").strip() or "dichtungstechnik"
    kind = str(data.get("kind") or ("consulting" if intent_type == "consulting" else "general")).strip()

    prediction["type"] = intent_type  # type: ignore[index]
    prediction["confidence"] = confidence  # type: ignore[index]
    prediction["reason"] = reason  # type: ignore[index]
    prediction["domain"] = domain  # type: ignore[index]
    prediction["kind"] = kind  # type: ignore[index]
    return prediction


def _infer_choice_from_text(text: str) -> str:
    lowered = text.lower()
    stripped = lowered.strip()
    if stripped.startswith(("2", "2)", "2.", "option 2", "wahl 2")):
        return "consultation"
    if stripped.startswith(("1", "1)", "1.", "option 1", "wahl 1")):
        return "general_answer"
    if any(hint in lowered for hint in _SHORT_HINTS):
        return "general_answer"
    if any(hint in lowered for hint in _CONSULT_HINTS):
        return "consultation"
    return "general_answer"


def _choice_pending(state: SealAIState) -> tuple[bool, str]:
    pending_value = state.get("pending_intent_choice")
    if isinstance(pending_value, str):
        text = pending_value.strip()
        if text:
            return True, text
    if pending_value:
        choice_text = str(state.get("message_in") or "").strip()
        return True, choice_text
    return False, ""


async def intent_classifier_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    pending, choice_text = _choice_pending(state)
    if pending:
        resolved = _infer_choice_from_text(choice_text)
        prediction = IntentPrediction(type=resolved, confidence=1.0, reason="user_choice")
        return {
            "intent": prediction,
            "pending_intent_choice": False,
            "intent_confidence": 1.0,
            "intent_reason": "user_choice",
        }

    user_query = _extract_user_query(state)
    if not user_query:
        return {}

    llm = _resolve_llm(config)
    prompt = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_query)]
    try:
        ainvoke = getattr(llm, "ainvoke", None)
        if callable(ainvoke):
            response = await ainvoke(prompt, config=config)
        else:
            response = await asyncio.to_thread(llm.invoke, prompt)
    except Exception:
        logger.exception("intent_classifier: LLM invocation failed, defaulting to consulting flow.")
        prediction = IntentPrediction(type="consulting", confidence=0.5, reason="Fallback nach Fehler.")
    else:
        raw_text = _extract_content(response)
        prediction = _parse_prediction(raw_text)

    confidence = float(prediction.get("confidence") or 0.0)
    reason = prediction.get("reason") or "model"
    intent_type = str(prediction.get("type") or "").strip().lower()
    updates: Dict[str, Any] = {
        "intent": prediction,
        "intent_confidence": confidence,
        "intent_reason": reason,
    }

    needs_clarification = intent_type == "general" or confidence < INTENT_CLARIFY_CONFIDENCE_THRESHOLD
    if needs_clarification:
        clarify_text = build_clarify_message(user_query)
        updates["pending_intent_choice"] = True
        updates["message_out"] = clarify_text
        updates["msg_type"] = CLARIFY_MSG_TYPE
    else:
        updates["pending_intent_choice"] = False

    return updates


__all__ = ["intent_classifier_node", "build_clarify_message", "CLARIFY_TEMPLATE", "CLARIFY_MSG_TYPE"]
