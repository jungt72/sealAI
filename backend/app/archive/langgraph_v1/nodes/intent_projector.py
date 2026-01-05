# backend/app/langgraph/nodes/intent_projector.py
# HINWEIS:
# Es existiert ein intent_projector.de.j2-Template für eine mögliche LLM-basierte Erweiterung.
# Aktuell arbeitet dieser Node jedoch ausschließlich heuristisch und ruft kein LLM auf.
# Das Template bleibt als zukünftige Option bestehen, ist jedoch derzeit ungenutzt.
from __future__ import annotations

import re
from typing import Any, Dict

from app.langgraph.state import IntentPrediction, Routing, SealAIState

_GREETING_KEYWORDS = (
    "hallo",
    "hi",
    "hey",
    "guten morgen",
    "guten tag",
    "moin",
    "servus",
    "grüß",
)
_SMALLTALK_HINTS = (
    "wie geht",
    "alles gut",
    "was geht",
    "danke dir",
    "danke, und dir",
    "wie war dein tag",
)
_TECHNICAL_KEYWORDS = (
    "druck",
    "bar",
    "temperatur",
    "°c",
    "medium",
    "öl",
    "wasser",
    "chemie",
    "shaft",
    "welle",
    "durchmesser",
    "mm",
    "rpm",
    "drehzahl",
    "din",
    "iso",
    "norm",
    "ptfe",
    "nitril",
    "dichtung",
    "seal",
    "rwdr",
    "radialwellendichtung",
    "gleitring",
)
_MEASUREMENT_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:x|×)\s*\d+(?:[.,]\d+)?(\s*(?:x|×)\s*\d+(?:[.,]\d+)?)?", re.IGNORECASE)
_PARAMETER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:bar|°c|c|rpm)\b", re.IGNORECASE)


def _is_greeting(text: str) -> bool:
    return any(text.startswith(keyword) for keyword in _GREETING_KEYWORDS)


def _is_smalltalk(text: str) -> bool:
    return any(hint in text for hint in _SMALLTALK_HINTS)


def _is_technical(text: str) -> bool:
    return any(keyword in text for keyword in _TECHNICAL_KEYWORDS) or bool(_MEASUREMENT_PATTERN.search(text))


def _classify_intent(user_query: str) -> IntentPrediction:
    normalized = (user_query or "").strip()
    lowered = normalized.lower()
    if not lowered:
        return IntentPrediction(domain="none", kind="other", task="no_technical_consulting", confidence=0.0)

    if _is_greeting(lowered):
        return IntentPrediction(domain="none", kind="greeting", task="no_technical_consulting", confidence=0.95)
    if _is_smalltalk(lowered):
        return IntentPrediction(domain="none", kind="smalltalk", task="no_technical_consulting", confidence=0.9)

    if _is_technical(lowered):
        confidence = 0.8
        if _PARAMETER_PATTERN.search(lowered):
            confidence += 0.05
        if _MEASUREMENT_PATTERN.search(lowered):
            confidence += 0.05
        return IntentPrediction(
            domain="sealing",
            kind="technical_consulting",
            task="technical_consulting",
            confidence=min(1.0, confidence),
        )

    return IntentPrediction(domain="general", kind="discovery", task="general_chat", confidence=0.5)


def intent_projector(state: SealAIState) -> Dict[str, Any]:
    """
    Lightweight heuristic intent classifier that enriches the state for routing.
    """
    slots = state.get("slots") or {}
    user_query = str(slots.get("user_query") or "")
    intent = _classify_intent(user_query)
    existing = state.get("intent")
    if isinstance(existing, dict):
        classifier_type = existing.get("type")
        classifier_reason = existing.get("reason")
        classifier_confidence = existing.get("confidence")
        if classifier_type:
            intent["type"] = classifier_type  # type: ignore[index]
        if classifier_reason:
            intent["reason"] = classifier_reason  # type: ignore[index]
        if classifier_confidence is not None:
            intent["confidence"] = classifier_confidence  # type: ignore[index]

    routing: Routing = dict(state.get("routing") or {})
    coverage = float(state.get("requirements_coverage") or routing.get("coverage") or 0.0)
    routing["coverage"] = coverage

    if intent["kind"] == "technical_consulting":
        routing["primary_domain"] = "sealing"
        routing["domains"] = ["sealing"]
        routing["confidence"] = intent["confidence"]
        if routing["coverage"] == 0.0:
            routing["coverage"] = 0.2
    else:
        routing.setdefault("confidence", intent["confidence"])
        if intent["kind"] in {"greeting", "smalltalk"}:
            routing["primary_domain"] = "none"
            routing["domains"] = []
        else:
            routing.setdefault("primary_domain", "discovery")
            routing.setdefault("domains", ["discovery"])

    return {"routing": routing, "intent": intent}
