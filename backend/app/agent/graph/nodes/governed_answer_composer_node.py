from __future__ import annotations

import logging

from app.agent.communication.governed_answer_composer import (
    GovernedAnswerComposer,
    GovernedAnswerComposerInput,
    is_governed_answer_composer_enabled,
    safe_governed_answer_composer_error_reason,
)
from app.agent.communication.governed_answer_context import GovernedAnswerContext
from app.agent.graph import GraphState

log = logging.getLogger(__name__)


async def governed_answer_composer_node(state: GraphState) -> GraphState:
    """Optionally compose natural governed answer_markdown after output_contract.

    Text-only node: it never writes governed technical truth, deltas, risks,
    readiness, RFQ state, matching, or cockpit projections. Failure is always
    a deterministic fallback to output_reply.
    """

    fallback_reply = str(state.output_reply or "").strip()
    existing_source = str(state.output_answer_markdown_source or "").strip()
    existing_answer = str(state.output_answer_markdown or "").strip()
    if existing_source in {"deterministic_reply", "governed_composer", "composer_fallback"} and existing_answer:
        return state

    if not is_governed_answer_composer_enabled():
        return state.model_copy(
            update={
                "output_answer_markdown": fallback_reply,
                "output_answer_markdown_source": "deterministic_reply",
                "governed_answer_composer_error": "",
            }
        )

    try:
        context = GovernedAnswerContext.model_validate(state.governed_answer_context or {})
        result = await GovernedAnswerComposer().compose(
            GovernedAnswerComposerInput(
                context=context,
                deterministic_reply=fallback_reply,
            )
        )
        return state.model_copy(
            update={
                "output_answer_markdown": result.answer_markdown,
                "output_answer_markdown_source": "governed_composer",
                "governed_answer_composer_error": "",
            }
        )
    except Exception as exc:  # noqa: BLE001
        reason = safe_governed_answer_composer_error_reason(exc)
        log.warning("[governed_answer_composer] fallback reason=%s", reason)
        return state.model_copy(
            update={
                "output_answer_markdown": fallback_reply,
                "output_answer_markdown_source": "composer_fallback",
                "governed_answer_composer_error": reason,
            }
        )
