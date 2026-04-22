from __future__ import annotations

import dataclasses
import logging
from typing import Any

from fastapi import HTTPException

from app.agent.api.deps import _canonical_scope, _lg_trace_enabled
from app.agent.api.loaders import (
    _load_live_governed_state,
    _update_governed_state_post_graph,
)
from app.agent.api.utils import (
    _materialize_governed_graph_result,
    _with_governed_conversation_turn,
)
from app.agent.graph import GraphState
from app.agent.graph.topology import GOVERNED_GRAPH
from app.agent.state.models import GovernedSessionState
from app.services.auth.dependencies import RequestUser

_log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class GovernedGraphTurnResult:
    result_state: GraphState
    persisted_state: GovernedSessionState
    progress_events: list[Any]


def build_governed_graph_input(
    *,
    governed_state: GovernedSessionState,
    message: str,
    current_user: RequestUser,
    session_id: str,
) -> GraphState:
    """Build the governed graph input from the live governed session state."""

    tenant_id, _, _ = _canonical_scope(current_user, case_id=session_id)
    governed_with_user = _with_governed_conversation_turn(
        governed_state, role="user", content=message
    )
    payload = governed_with_user.model_dump(mode="python")
    payload.update(
        {
            "tenant_id": tenant_id,
            "session_id": session_id,
            "pending_message": message,
        }
    )
    return GraphState.model_validate(payload)


async def run_governed_graph_turn(
    *,
    request: Any,
    current_user: RequestUser,
    pre_gate_classification: str | None = None,
    collect_progress: bool = False,
) -> GovernedGraphTurnResult:
    """Run one governed graph turn and commit it using the current live-state behavior."""

    session_id = str(request.session_id or "default")
    governed = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=True,
    )
    if not governed:
        raise HTTPException(status_code=404, detail="Governed state not found")

    graph_input = build_governed_graph_input(
        governed_state=governed,
        message=request.message,
        current_user=current_user,
        session_id=session_id,
    )

    progress_events: list[Any] = []
    if collect_progress and hasattr(GOVERNED_GRAPH, "astream"):
        latest_values: GraphState | dict[str, Any] = graph_input
        async for mode, data in GOVERNED_GRAPH.astream(
            graph_input, stream_mode=["values", "updates", "custom"]
        ):
            if mode == "values":
                latest_values = _materialize_governed_graph_result(data)
            elif mode == "custom":
                progress_events.append(data)
        result_state = _materialize_governed_graph_result(latest_values)
    else:
        if _lg_trace_enabled():
            _log.debug("[governed_graph] ainvoke session=%s", session_id)
        raw_result = await GOVERNED_GRAPH.ainvoke(graph_input)
        result_state = _materialize_governed_graph_result(raw_result)

    persisted_state = await _update_governed_state_post_graph(
        current_user=current_user,
        session_id=session_id,
        result_state=result_state,
        pre_gate_classification=pre_gate_classification,
    )

    return GovernedGraphTurnResult(
        result_state=result_state,
        persisted_state=persisted_state,
        progress_events=progress_events,
    )
