"""V9 challenge node.

Runs the deterministic sealing-intelligence challenge layer after calculations
and before governance/output. The node writes only the canonical ChallengeState.
"""

from __future__ import annotations

import logging

from langgraph.config import get_stream_writer

from app.agent.domain.challenge_engine import build_challenge_state
from app.agent.graph import GraphState

log = logging.getLogger(__name__)


def _emit_progress_event(payload: dict) -> None:
    try:
        get_stream_writer()(payload)
    except RuntimeError:
        return


async def challenge_node(state: GraphState) -> GraphState:
    """Build V9 challenge findings, hypotheses and next-best question."""

    challenge = build_challenge_state(
        state,
        compute_results=list(state.compute_results or []),
    )
    log.debug(
        "[challenge_node] status=%s findings=%d hypotheses=%d next=%s",
        challenge.status,
        len(challenge.findings),
        len(challenge.hypotheses),
        bool(challenge.next_best_question),
    )
    _emit_progress_event(
        {
            "event_type": "challenge_ready",
            "status": challenge.status,
            "findings": len(challenge.findings),
            "hypotheses": len(challenge.hypotheses),
            "next_best_question": (
                challenge.next_best_question.question
                if challenge.next_best_question is not None
                else None
            ),
        }
    )
    return state.model_copy(update={"challenge": challenge})
