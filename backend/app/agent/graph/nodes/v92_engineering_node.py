"""V9.2 engineering-orchestrator node.

Additive deterministic layer: turns governed assertions and compute results
into V9.2 seal-system, calculation, compound, evidence and failure slices.
"""

from __future__ import annotations

import logging

from app.agent.graph import GraphState
from app.agent.v92.orchestrator import build_engineering_update

log = logging.getLogger(__name__)


async def v92_engineering_node(state: GraphState) -> GraphState:
    try:
        update = build_engineering_update(state)
    except Exception as exc:  # pragma: no cover - fail-open runtime guard
        log.warning(
            "[v92_engineering_node] V9.2 engineering update failed (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return state
    return state.model_copy(update=update)
