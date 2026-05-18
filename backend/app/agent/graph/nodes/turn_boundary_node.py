from __future__ import annotations

from app.agent.graph import GraphState
from app.agent.v92.runtime_contract import build_turn_envelope
from app.agent.v92.turn_boundary import resolve_turn_boundary


async def turn_boundary_node(state: GraphState) -> GraphState:
    """Canonical V9.2 semantic boundary node.

    It makes the route, mutation policy, engine requirement and streaming policy
    an in-graph artifact before intake/extraction can mutate technical state.
    """

    boundary = resolve_turn_boundary(
        user_message=state.pending_message,
        session_id=state.session_id or "default",
        state=state,
        route_hint=(
            str(state.v92_turn_boundary_decision.get("route") or "")
            if isinstance(state.v92_turn_boundary_decision, dict)
            else ""
        )
        or "governed",
        runtime_mode="GOVERNED",
        pre_gate_classification=(
            str(state.v92_turn_boundary_decision.get("trace", {}).get("pre_gate_classification") or "")
            if isinstance(state.v92_turn_boundary_decision, dict)
            else ""
        ),
    )
    envelope = build_turn_envelope(
        session_id=state.session_id or "default",
        user_message=state.pending_message,
        route=boundary.route,
        state=state,
        case_id=state.session_id or None,
        intent=boundary.intent,
    )
    return state.model_copy(
        update={
            "v92_turn_boundary_decision": boundary.model_dump(mode="json"),
            "v92_turn_envelope": envelope.model_dump(mode="json"),
        }
    )
