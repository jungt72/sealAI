from __future__ import annotations

import re
from typing import Any, Dict, Set

import structlog
from langchain_core.messages import AIMessage, BaseMessage

from app.langgraph_v2.state.sealai_state import SealAIState

logger = structlog.get_logger("langgraph_v2.answer_subgraph.finalize")

_NUMBER_TOKEN_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _extract_number_tokens(text: str) -> Set[str]:
    return set(_NUMBER_TOKEN_PATTERN.findall(text or ""))


def node_finalize(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    verified_draft = str(state.draft_text or "").strip()
    polished_text = str(state.final_text or state.final_answer or verified_draft).strip()
    candidate_final = polished_text or verified_draft

    verified_tokens = _extract_number_tokens(verified_draft)
    candidate_tokens = _extract_number_tokens(candidate_final)
    new_tokens = sorted(candidate_tokens - verified_tokens)

    blocked = bool(new_tokens)
    final_text = verified_draft if blocked else candidate_final
    if not final_text:
        final_text = "Unable to safely finalize response; please provide additional context."

    messages: list[BaseMessage] = list(state.messages or [])
    messages.append(AIMessage(content=[{"type": "text", "text": final_text}]))

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

