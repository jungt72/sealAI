"""V9.2 dossier node.

Completes the V9.2 quality layer after norm, RFQ and dispatch-contract slices
are available. No LLM call, no transport side effect.
"""

from __future__ import annotations

import logging

from app.agent.graph import GraphState
from app.agent.v92.orchestrator import build_dossier_update

log = logging.getLogger(__name__)


async def v92_dossier_node(state: GraphState) -> GraphState:
    try:
        update = build_dossier_update(state)
    except Exception as exc:  # pragma: no cover - fail-open runtime guard
        log.warning(
            "[v92_dossier_node] V9.2 dossier update failed (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return state
    return state.model_copy(update=update)
