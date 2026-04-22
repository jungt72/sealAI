from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class TransitionSignalKind(str, Enum):
    NONE = "none"
    CONCRETE_CASE = "concrete_case"


@dataclass(frozen=True, slots=True)
class TransitionSignal:
    kind: TransitionSignalKind
    confidence: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeSessionContext:
    session_id: str
    mentioned_parameters: Mapping[str, object] = field(default_factory=dict)
    explored_concepts: tuple[str, ...] = ()
    detected_intent: str | None = None
    transition_offered: bool = False


class KnowledgeCaseBridgeService:
    def detect_transition_signal(self, turn_text: str, context: KnowledgeSessionContext | None = None) -> TransitionSignal:
        reasons: list[str] = []
        text = turn_text.casefold()
        if re.search(r"\b(meine|mein|unsere|unser|my|our)\b", text):
            reasons.append("possessive_reference")
        if re.search(r"\d+(?:[.,]\d+)?\s*(mm|bar|rpm|u\.?/?min|c|grad)", text):
            reasons.append("concrete_parameter")
        if re.search(r"(welche|was soll|empfiehl|where do i buy|who makes|hersteller)", text):
            reasons.append("outcome_or_match_seeking")
        if context and context.mentioned_parameters:
            reasons.append("session_has_parameters")
        if not reasons:
            return TransitionSignal(TransitionSignalKind.NONE, 0.0, ())
        return TransitionSignal(TransitionSignalKind.CONCRETE_CASE, min(0.95, 0.35 + 0.2 * len(reasons)), tuple(reasons))

    def seed_case_context(self, context: KnowledgeSessionContext) -> dict[str, object]:
        return {"provenance": "knowledge_session_seed", "parameters": dict(context.mentioned_parameters), "explored_concepts": list(context.explored_concepts)}
