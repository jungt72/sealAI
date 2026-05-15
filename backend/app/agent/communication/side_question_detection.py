from __future__ import annotations

import re
from typing import Literal

from app.services.knowledge.material_comparison import is_material_comparison_question

KnowledgeSideQuestionClass = Literal["conversational_answer", "exploration_answer"]


_KNOWLEDGE_PATTERNS: tuple[str, ...] = (
    r"\bwas\s+(?:genau\s+|eigentlich\s+)?(?:ist|sind)\b",
    r"\bwas\s+bedeutet\b",
    r"\bwas\s+heisst\b",
    r"\bwas\s+hei[ßs]t\b",
    r"\bwas\s+kannst\s+du\s+(?:mir\s+)?(?:zu|ueber|über)\b",
    r"\b(?:sag|sage|erz[aä]hl|erzaehl)\w*\s+(?:mir\s+)?(?:etwas\s+|mehr\s+)?(?:zu|ueber|über)\b",
    r"\bwas\s+versteht\s+man\s+unter\b",
    r"\berkl[äa]r",
    r"\bwie\s+funktioniert\b",
    r"\bkannst\s+du.*erkl[äa]ren\b",
    r"\b(?:vertr[aä]glich|vertraeglich|kompatibel|best[aä]ndig|bestaendig)\b",
)

_COMPARISON_PATTERNS: tuple[str, ...] = (
    r"\bvergleich",
    r"\bunterschied\b",
    r"\bversus\b",
    r"\bvs\.?\b",
    r"\bbesser.*\boder\b",
    r"\boder.*\bbesser\b",
)

_PARAM_UPDATE_MARKERS: tuple[str, ...] = (
    r"\bstatt\b",
    r"\bkorrig",
    r"\bsondern\b",
    r"\bänder",
    r"\baender",
    r"\bkorrekt(?:ur)?\b",
)

_CONCRETE_CASE_MARKERS: tuple[str, ...] = (
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|barg|bara|psi|°?\s*[cCfF]|grad|rpm|u\.?/?min)\b",
    r"\b(salzwasser|wasser|öl|oel|ethanol|dampf|medium)\b.*\b(\d|bar|grad|welle|pumpe|ruehrwerk|rührwerk)\b",
    r"\b(rotierende?\s+welle|welle|pumpe|ruehrwerk|rührwerk|getriebe)\b.*\b(salzwasser|wasser|öl|oel|ethanol|medium|ptfe|fkm|nbr|epdm)\b",
)


def contains_concrete_case_marker(message: str) -> bool:
    lowered = str(message or "").strip().casefold()
    return any(
        re.search(pattern, lowered, re.IGNORECASE)
        for pattern in _CONCRETE_CASE_MARKERS
    )


def classify_message_as_knowledge_side_question(
    message: str,
) -> KnowledgeSideQuestionClass | None:
    """Classify pure knowledge/comparison questions before governed graph entry.

    This is the V8 communication-runtime side-question detector. It is deliberately
    independent of graph output assembly: the graph should receive only turns that
    are already allowed to mutate or validate governed state.
    """

    lowered = str(message or "").strip().casefold()
    if not lowered:
        return None

    if is_material_comparison_question(lowered):
        return "exploration_answer"

    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in _PARAM_UPDATE_MARKERS):
        return None

    if contains_concrete_case_marker(lowered):
        return None

    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in _COMPARISON_PATTERNS):
        return "exploration_answer"

    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in _KNOWLEDGE_PATTERNS):
        return "conversational_answer"

    return None
