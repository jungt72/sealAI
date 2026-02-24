from __future__ import annotations

"""Finalize verified answer text with last-mile numeric safety checks.

The No-New-Numbers guard compares numeric tokens from the verified draft
against the polished final candidate. If polishing introduces unseen numbers,
the node falls back to the verified draft as a final protection wall against
hallucinated quantitative claims.
"""

import re
from typing import Any, Dict, Set

import structlog
from langchain_core.messages import AIMessage, BaseMessage

from app.langgraph_v2.state.sealai_state import SealAIState

logger = structlog.get_logger("langgraph_v2.answer_subgraph.finalize")

_NUMBER_TOKEN_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")
# Citation markers like [1] or [1-3] are formatting references, not measured
# values. They are stripped before the No-New-Numbers comparison.
_BRACKET_REFERENCE_PATTERN = re.compile(r"\[\s*\d+(?:\s*[-,]\s*\d+)*\s*\]")
# Ordered-list prefixes ("1. ", "2. ") are structural text formatting and must
# not be interpreted as novel numeric claims.
_LIST_PREFIX_PATTERN = re.compile(r"(?m)^\s*\d+\.\s+")


def _strip_formatting_numbers(text: str) -> str:
    """Remove numeric formatting tokens before semantic number checks.

    Args:
        text: Candidate output text.

    Returns:
        Text without citation/list numbering artifacts.
    """
    sanitized = _BRACKET_REFERENCE_PATTERN.sub(" ", text or "")
    sanitized = _LIST_PREFIX_PATTERN.sub("", sanitized)
    return sanitized


def _extract_number_tokens(text: str) -> Set[str]:
    """Extract numeric tokens from sanitized text.

    Args:
        text: Candidate output text.

    Returns:
        Set of numeric token strings.
    """
    return set(_NUMBER_TOKEN_PATTERN.findall(_strip_formatting_numbers(text)))


def node_finalize(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Produce the user-visible final answer for the subgraph.

    Steps:
    1. Select polished final candidate (or fallback to draft).
    2. Apply No-New-Numbers guard against verified draft tokens.
    3. Persist ``final_text`` / ``final_answer`` and append AI message.

    Args:
        state: Current graph state.
        *_args: Unused positional arguments for LangGraph compatibility.
        **_kwargs: Unused keyword arguments for LangGraph compatibility.

    Returns:
        State patch containing final answer payload and optional error marker.
    """
    verified_draft = str(state.draft_text or "").strip()
    polished_text = str(state.final_text or state.final_answer or verified_draft).strip()
    candidate_final = polished_text or verified_draft

    verified_tokens = _extract_number_tokens(verified_draft)
    candidate_tokens = _extract_number_tokens(candidate_final)
    new_tokens = sorted(candidate_tokens - verified_tokens)

    blocked = bool(new_tokens)
    final_text = verified_draft if blocked else candidate_final
    if not final_text:
        final_text = verified_draft or "Unable to safely finalize response; please provide additional context."

    messages: list[BaseMessage] = list(state.messages or [])
    messages.append(AIMessage(content=final_text))

    if blocked:
        logger.warning(
            "finalize.no_new_numbers_guard_blocked",
            new_number_tokens=new_tokens,
        )
    else:
        logger.info("finalize.completed", final_length=len(final_text))

    patch: Dict[str, Any] = {
        "messages": messages,
        "final_text": final_text,
        "final_answer": final_text,
        "phase": state.phase or "final",
        "last_node": "node_finalize",
    }
    if blocked:
        patch["error"] = "No-New-Numbers guard blocked polished text; returning verified draft."
    return patch


__all__ = ["node_finalize"]
