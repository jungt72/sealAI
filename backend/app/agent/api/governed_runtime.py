from __future__ import annotations

import dataclasses
import inspect
import logging
from typing import Any, Awaitable, Callable

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
from app.agent.graph.topology import get_governed_graph
from app.agent.state.models import GovernedSessionState
from app.agent.v92.runtime_contract import build_turn_envelope
from app.agent.v92.turn_boundary import resolve_turn_boundary
from app.core.config import settings
from app.observability.langsmith import (
    langsmith_tracing_disabled,
    traceable,
)
from app.observability.sealai_quality import emit_quality_trace
from app.services.auth.dependencies import RequestUser

_log = logging.getLogger(__name__)

ProgressCallback = Callable[[Any], Awaitable[None] | None]


@dataclasses.dataclass(frozen=True)
class GovernedGraphTurnResult:
    result_state: GraphState
    persisted_state: GovernedSessionState
    progress_events: list[Any]


def _state_mapping(state: Any) -> dict[str, Any]:
    if isinstance(state, dict):
        return state
    if hasattr(state, "model_dump"):
        try:
            dumped = state.model_dump(mode="python")
            return dumped if isinstance(dumped, dict) else {}
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _state_value(state: Any, *names: str) -> Any:
    mapping = _state_mapping(state)
    for name in names:
        if isinstance(mapping, dict) and name in mapping:
            return mapping.get(name)
        if hasattr(state, name):
            return getattr(state, name)
    return None


def _count_collection(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict | list | tuple | set):
        return len(value)
    return 1


def _open_points_count(*states: Any) -> int:
    keys = (
        "open_points",
        "open_questions",
        "coverage_gaps",
        "missing_fields",
        "required_missing_fields",
        "unresolved_findings",
    )
    for state in states:
        for key in keys:
            count = _count_collection(_state_value(state, key))
            if count:
                return count
    return 0


def _graph_thread_config(*, current_user: RequestUser, session_id: str) -> dict[str, Any]:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    return {
        "configurable": {
            "thread_id": f"sealai:{tenant_id}:{owner_id}:{session_id}",
        }
    }


def _stream_event_parts(event: Any) -> tuple[str | None, Any]:
    if isinstance(event, tuple) and len(event) == 2:
        return str(event[0]), event[1]
    if isinstance(event, dict):
        return str(event.get("type") or ""), event.get("data")
    return None, event


def build_governed_graph_input(
    *,
    governed_state: GovernedSessionState,
    message: str,
    current_user: RequestUser,
    session_id: str,
    defer_visible_answer_composer: bool = False,
    stream_visible_answer_composer: bool = False,
    append_user_message: bool = True,
    pre_gate_classification: str | None = None,
) -> GraphState:
    """Build the governed graph input from the live governed session state."""

    tenant_id, _, _ = _canonical_scope(current_user, case_id=session_id)
    governed_with_user = (
        _with_governed_conversation_turn(
            governed_state, role="user", content=message
        )
        if append_user_message
        else governed_state
    )
    boundary = resolve_turn_boundary(
        user_message=message,
        session_id=session_id,
        state=governed_state,
        route_hint="governed",
        runtime_mode="GOVERNED",
        pre_gate_classification=pre_gate_classification,
    )
    envelope = build_turn_envelope(
        session_id=session_id,
        user_message=message,
        route=boundary.route,
        state=governed_state,
        case_id=session_id,
        intent=boundary.intent,
    )
    payload = governed_with_user.model_dump(mode="python")
    payload.update(
        {
            "tenant_id": tenant_id,
            "session_id": session_id,
            "pending_message": message,
            "v92_turn_boundary_decision": boundary.model_dump(mode="json"),
            "v92_turn_envelope": envelope.model_dump(mode="json"),
            "defer_visible_answer_composer": bool(defer_visible_answer_composer),
            "stream_visible_answer_composer": bool(stream_visible_answer_composer)
            and not bool(defer_visible_answer_composer),
        }
    )
    return GraphState.model_validate(payload)


@traceable(name="sealai.governed_graph_turn", run_type="chain")
async def run_governed_graph_turn(
    *,
    request: Any,
    current_user: RequestUser,
    pre_gate_classification: str | None = None,
    collect_progress: bool = False,
    progress_callback: ProgressCallback | None = None,
    append_user_message: bool = True,
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
        defer_visible_answer_composer=False,
        # V9.2: governed technical draft tokens stay internal until the final
        # guard approves the complete answer. Progress still streams through
        # LangGraph custom events, but composer text does not.
        stream_visible_answer_composer=False,
        append_user_message=append_user_message,
        pre_gate_classification=pre_gate_classification,
    )
    graph_config = _graph_thread_config(current_user=current_user, session_id=session_id)
    governed_graph = await get_governed_graph()

    progress_events: list[Any] = []
    suppress_langgraph_child_traces = not bool(
        getattr(settings, "langsmith_trace_langgraph_children", False)
    )
    with langsmith_tracing_disabled(disabled=suppress_langgraph_child_traces):
        if collect_progress and hasattr(governed_graph, "astream"):
            latest_values: GraphState | dict[str, Any] = graph_input
            async for event in governed_graph.astream(
                graph_input,
                config=graph_config,
                stream_mode=["values", "updates", "custom"],
            ):
                mode, data = _stream_event_parts(event)
                if mode == "values":
                    latest_values = _materialize_governed_graph_result(data)
                elif mode == "updates" and isinstance(data, dict) and "__interrupt__" in data:
                    latest_values = _materialize_governed_graph_result(data)
                elif mode == "custom":
                    progress_events.append(data)
                    if progress_callback is not None:
                        callback_result = progress_callback(data)
                        if inspect.isawaitable(callback_result):
                            await callback_result
            result_state = _materialize_governed_graph_result(latest_values)
        else:
            if _lg_trace_enabled():
                _log.debug("[governed_graph] ainvoke session=%s", session_id)
            raw_result = await governed_graph.ainvoke(graph_input, config=graph_config)
            result_state = _materialize_governed_graph_result(raw_result)

    persisted_state = await _update_governed_state_post_graph(
        current_user=current_user,
        session_id=session_id,
        result_state=result_state,
        pre_gate_classification=pre_gate_classification,
    )
    emit_quality_trace(
        component="governed_graph",
        tags=("governed-graph", "challenge-engine", "v92"),
        request=request,
        current_user=current_user,
        session_id=session_id,
        pre_gate_classification=pre_gate_classification,
        collect_progress=collect_progress,
        progress_events_count=len(progress_events),
        pending_question_present=bool(
            _state_value(result_state, "pending_question", "next_question", "clarification_question")
        ),
        open_points_count=_open_points_count(result_state, persisted_state),
        triggered_findings_count=_count_collection(
            _state_value(result_state, "triggered_findings", "challenge_findings", "findings")
        ),
        risk_drivers_count=_count_collection(_state_value(result_state, "risk_drivers")),
        medium_intelligence_status=(
            result_state.medium_intelligence.get("validation_status")
            if isinstance(result_state.medium_intelligence, dict)
            else None
        ),
        answer_mode=_state_value(result_state, "answer_mode"),
        v92_route=(
            result_state.v92_turn_boundary_decision.get("route")
            if isinstance(result_state.v92_turn_boundary_decision, dict)
            else None
        ),
        v92_streaming_policy=(
            result_state.v92_turn_boundary_decision.get("streaming_policy")
            if isinstance(result_state.v92_turn_boundary_decision, dict)
            else None
        ),
        uncertainty_level=_state_value(result_state, "uncertainty_level"),
        forbidden_claim_check=_state_value(result_state, "forbidden_claim_check"),
        v92_present=bool(_state_value(result_state, "seal_system", "engineering", "dossier")),
        v92_engineering_status=getattr(_state_value(result_state, "engineering"), "status", None),
        v92_dossier_status=getattr(_state_value(result_state, "dossier"), "status", None),
    )

    return GovernedGraphTurnResult(
        result_state=result_state,
        persisted_state=persisted_state,
        progress_events=progress_events,
    )
