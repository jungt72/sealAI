from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Sequence

from langchain_core.messages import BaseMessage, HumanMessage

from .config.routing import IntentSpec, RoutingConfig, load_routing_config


@dataclass
class IntentMatch:
    intent: str
    score: float
    synonyms: Sequence[str]


@dataclass
class RoutingDecision:
    candidate: Optional[IntentMatch]
    alternatives: List[IntentMatch]
    reason: Optional[str]


BUTTON_INTENTS = {"werkstoff", "profil", "validierung"}


def normalize_intent(intent: Optional[str]) -> Optional[str]:
    if intent is None:
        return None
    if not isinstance(intent, str):
        intent = str(intent)
    text = intent.strip().lower()
    return text or None


def _text_from_messages(messages: Sequence[BaseMessage]) -> str:
    if not messages:
        return ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = getattr(msg, "content", "") or ""
            if isinstance(content, str) and content.strip():
                return content.strip()
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _score_synonym(text: str, synonym: str) -> float:
    if not synonym:
        return 0.0
    syn = synonym.lower().strip()
    if not syn:
        return 0.0
    if syn in text:
        base = 0.88 + min(len(syn), 12) * 0.005
        return min(base, 0.97)
    ratio = SequenceMatcher(None, text, syn).ratio()
    return round(ratio * 0.75, 4)


def _match_intent(text: str, spec: IntentSpec) -> IntentMatch:
    best = 0.0
    for synonym in spec.synonyms:
        score = _score_synonym(text, synonym)
        if score > best:
            best = score
    return IntentMatch(intent=spec.key, score=best, synonyms=spec.synonyms)


def find_intent_from_text(messages: Sequence[BaseMessage]) -> RoutingDecision:
    cfg: RoutingConfig = load_routing_config()
    text = _text_from_messages(messages).lower()
    if not text:
        return RoutingDecision(candidate=None, alternatives=[], reason="empty_input")

    matches: List[IntentMatch] = []
    for spec in cfg.intents.values():
        matches.append(_match_intent(text, spec))

    matches.sort(key=lambda m: m.score, reverse=True)
    candidate = matches[0] if matches else None
    alternatives = matches[1:4] if len(matches) > 1 else []

    if candidate is None or candidate.score <= 0.0:
        return RoutingDecision(candidate=None, alternatives=alternatives, reason="no_match")

    if alternatives and candidate.score - alternatives[0].score < cfg.min_delta:
        return RoutingDecision(candidate=candidate, alternatives=alternatives, reason="low_delta")

    return RoutingDecision(candidate=candidate, alternatives=alternatives, reason=None)


def extract_button_payload(data: dict[str, object]) -> dict[str, object]:
    intent = normalize_intent(str(data.get("intent") or data.get("intent_seed") or ""))
    source = normalize_intent(str(data.get("source") or "")) or None
    confidence_raw = data.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else None
    except (TypeError, ValueError):
        confidence = None
    return {
        "intent_seed": intent if intent in BUTTON_INTENTS else intent,
        "source": source,
        "confidence": confidence,
    }


def suggestions_from_alternatives(alternatives: Sequence[IntentMatch]) -> List[dict[str, str]]:
    suggestions: List[dict[str, str]] = []
    cfg = load_routing_config()
    for alt in alternatives:
        spec = cfg.intents.get(alt.intent)
        if not spec:
            continue
        suggestions.append(
            {
                "intent": spec.key,
                "label": spec.button_label or spec.key.title(),
                "tooltip": spec.button_tooltip or "",
            }
        )
    return suggestions


def last_agent_suggestion(agent: Optional[str]) -> Optional[dict[str, str]]:
    if not agent:
        return None
    cfg = load_routing_config()
    spec = cfg.intents.get(agent)
    if not spec:
        return None
    return {
        "intent": spec.key,
        "label": spec.button_label or spec.key.title(),
        "tooltip": spec.button_tooltip or "",
        "kind": "last_agent",
    }


__all__ = [
    "BUTTON_INTENTS",
    "RoutingDecision",
    "IntentMatch",
    "find_intent_from_text",
    "extract_button_payload",
    "suggestions_from_alternatives",
    "last_agent_suggestion",
    "normalize_intent",
]
