from __future__ import annotations

import re
from typing import Any, Dict

from app.langgraph.state import SealAIState, StyleContract


_SINGLE_SENTENCE_TOKENS = ("ein satz", "in einem satz", "single sentence", "one sentence")
_NO_INTRO_TOKENS = ("keine einleitung", "ohne einleitung")
_NO_OUTRO_TOKENS = ("kein nachsatz", "ohne fazit", "keinen nachsatz")
_PLAIN_ONLY_TOKENS = ("nur", "lediglich", "keine erläuter", "keine erklär")
_COMMA_HINTS = ("durch kommas", "mit kommas", "comma-separated", "comma separated")


def _detect_number_range(text: str) -> tuple[int | None, int | None]:
    pattern = r"(?:(?:zahlen|numbers|nummern)\s+)?(\d{1,4})\s*(?:bis|to|-)\s*(\d{1,4})"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None, None
    start = int(match.group(1))
    end = int(match.group(2))
    if start <= end:
        return start, end
    return end, start


def _build_style_contract(user_query: str) -> StyleContract:
    lowered = user_query.lower()
    contract: StyleContract = StyleContract(raw_instruction=user_query)

    if any(token in lowered for token in _SINGLE_SENTENCE_TOKENS):
        contract["single_sentence"] = True
    if any(token in lowered for token in _NO_INTRO_TOKENS):
        contract["no_intro"] = True
    if any(token in lowered for token in _NO_OUTRO_TOKENS):
        contract["no_outro"] = True
    if ("zahlen" in lowered or "numbers" in lowered) and any(hint in lowered for hint in _COMMA_HINTS):
        contract["numbers_with_commas"] = True

    start, end = _detect_number_range(user_query)
    if start is not None and end is not None:
        contract["literal_numbers_start"] = start
        contract["literal_numbers_end"] = end
        contract["numbers_with_commas"] = True

    if any(token in lowered for token in _PLAIN_ONLY_TOKENS):
        contract["enforce_plain_answer"] = True

    if "ohne" in lowered and "zusatz" in lowered:
        contract["enforce_plain_answer"] = True

    return contract


def style_contract_node(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    user_query = str(slots.get("user_query") or "").strip()
    if not user_query:
        return {}

    contract = _build_style_contract(user_query)
    if not contract:
        return {}

    slots["style_contract"] = contract
    if contract.get("numbers_with_commas") or (
        isinstance(contract.get("literal_numbers_start"), int)
        and isinstance(contract.get("literal_numbers_end"), int)
    ):
        slots["task_mode_hint"] = "simple_direct_output"
    return {"slots": slots}


__all__ = ["style_contract_node"]
