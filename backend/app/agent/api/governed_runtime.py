from __future__ import annotations

import dataclasses
import inspect
import logging
import time
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
    emit_redacted_observation_span,
    langsmith_enabled,
    langsmith_redacted_observation_spans,
    langsmith_tracing_disabled,
    traceable,
)
from app.observability.sealai_quality import emit_quality_trace, redact_trace_value
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


def _runtime_action_answer_mode(runtime_action: Any | None) -> str | None:
    if runtime_action is None:
        return None
    value = getattr(runtime_action, "answer_mode", None)
    return str(getattr(value, "value", value) or "").strip() or None


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


def _graph_thread_config(
    *, current_user: RequestUser, session_id: str
) -> dict[str, Any]:
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


def _mapping_summary(value: Any) -> dict[str, Any]:
    mapping = _state_mapping(value)
    if not mapping:
        return {"type": type(value).__name__, "key_count": 0, "keys": []}
    keys = [str(key) for key in mapping.keys()]
    summary: dict[str, Any] = {
        "type": type(value).__name__,
        "key_count": len(keys),
        "keys": keys[:24],
    }
    status = mapping.get("status")
    if status is not None:
        summary["status"] = str(status)
    for key in (
        "output_response_class",
        "output_answer_markdown_source",
        "output_answer_markdown",
        "output_reply",
        "pending_question",
        "next_question",
        "clarification_question",
        "governed_answer_composer_error",
    ):
        if key in mapping:
            item = mapping.get(key)
            if isinstance(item, str):
                summary[key] = redact_trace_value(item, key=key)
            else:
                summary[f"{key}_present"] = item is not None
    return summary


def _interrupt_summary(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list | tuple) else [value]
    summaries: list[dict[str, Any]] = []
    for item in items[:8]:
        payload = getattr(item, "value", item)
        payload_mapping = (
            payload if isinstance(payload, dict) else _state_mapping(payload)
        )
        kind = (
            payload_mapping.get("kind") if isinstance(payload_mapping, dict) else None
        )
        message = (
            payload_mapping.get("message")
            if isinstance(payload_mapping, dict)
            else None
        )
        summaries.append(
            {
                "kind": str(kind or "interrupt"),
                "expected": True,
                "message": redact_trace_value(message, key="message"),
            }
        )
    if len(items) > 8:
        summaries.append({"_truncated_items": len(items) - 8})
    return summaries


def _graph_event_observation(
    *,
    index: int,
    mode: str | None,
    data: Any,
    elapsed_s: float,
) -> dict[str, Any]:
    mode_text = str(mode or "unknown")
    observation: dict[str, Any] = {
        "index": index,
        "mode": mode_text,
        "elapsed_s": round(elapsed_s, 4),
        "status": "observed",
    }
    if mode_text == "updates" and isinstance(data, dict):
        nodes = [str(key) for key in data.keys()]
        observation["nodes"] = nodes
        observation["node_count"] = len(nodes)
        if "__interrupt__" in data:
            observation["status"] = "expected_interrupt"
            observation["interrupts"] = _interrupt_summary(data.get("__interrupt__"))
        else:
            observation["updates"] = {
                str(node): _mapping_summary(payload)
                for node, payload in list(data.items())[:12]
            }
    elif mode_text == "custom":
        observation["custom_event"] = redact_trace_value(data)
    elif mode_text == "values":
        observation["value"] = _mapping_summary(data)
    else:
        observation["payload"] = redact_trace_value(data)
    return observation


async def _emit_graph_event_observations(
    *,
    observations: list[dict[str, Any]],
    request: Any,
    current_user: RequestUser,
    session_id: str,
    collect_progress: bool,
) -> None:
    if not observations:
        return
    for observation in observations[:80]:
        status = str(observation.get("status") or "observed")
        await emit_redacted_observation_span(
            span_name="sealai.langgraph.event",
            component="governed_graph",
            status="success",
            inputs={
                "event_index": observation.get("index"),
                "event_mode": observation.get("mode"),
                "collect_progress": collect_progress,
            },
            outputs=observation,
            metadata={
                "session_id": getattr(request, "session_id", session_id),
                "event_mode": observation.get("mode"),
                "event_status": status,
                "node_names": observation.get("nodes"),
                "expected_interrupt": status == "expected_interrupt",
                "tenant_id": getattr(current_user, "tenant_id", None),
                "user_id": getattr(current_user, "user_id", None)
                or getattr(current_user, "sub", None),
            },
        )
    if len(observations) > 80:
        await emit_redacted_observation_span(
            span_name="sealai.langgraph.event_truncation",
            component="governed_graph",
            status="success",
            outputs={"emitted": 80, "total": len(observations)},
            metadata={"session_id": getattr(request, "session_id", session_id)},
        )


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
    runtime_action_answer_mode: str | None = None,
) -> GraphState:
    """Build the governed graph input from the live governed session state."""

    tenant_id, _, _ = _canonical_scope(current_user, case_id=session_id)
    governed_with_user = (
        _with_governed_conversation_turn(governed_state, role="user", content=message)
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
            "runtime_answer_mode": str(runtime_action_answer_mode or "").strip(),
            "runtime_answer_mode_source": (
                "runtime_action.answer_mode"
                if str(runtime_action_answer_mode or "").strip()
                else ""
            ),
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
    runtime_action: Any | None = None,
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
        runtime_action_answer_mode=_runtime_action_answer_mode(runtime_action),
    )
    graph_config = _graph_thread_config(
        current_user=current_user, session_id=session_id
    )
    governed_graph = await get_governed_graph()

    progress_events: list[Any] = []
    graph_event_observations: list[dict[str, Any]] = []
    graph_started_at = time.perf_counter()
    suppress_langgraph_child_traces = not bool(
        getattr(settings, "langsmith_trace_langgraph_children", False)
    )
    use_streaming_runtime = bool(
        (
            collect_progress
            or (langsmith_enabled() and langsmith_redacted_observation_spans())
        )
        and hasattr(governed_graph, "astream")
    )
    with langsmith_tracing_disabled(disabled=suppress_langgraph_child_traces):
        if use_streaming_runtime:
            latest_values: GraphState | dict[str, Any] = graph_input
            event_index = 0
            async for event in governed_graph.astream(
                graph_input,
                config=graph_config,
                stream_mode=["values", "updates", "custom"],
            ):
                event_index += 1
                mode, data = _stream_event_parts(event)
                if mode in {"updates", "custom"}:
                    graph_event_observations.append(
                        _graph_event_observation(
                            index=event_index,
                            mode=mode,
                            data=data,
                            elapsed_s=time.perf_counter() - graph_started_at,
                        )
                    )
                if mode == "values":
                    latest_values = _materialize_governed_graph_result(data)
                elif (
                    mode == "updates"
                    and isinstance(data, dict)
                    and "__interrupt__" in data
                ):
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

    await _emit_graph_event_observations(
        observations=graph_event_observations,
        request=request,
        current_user=current_user,
        session_id=session_id,
        collect_progress=collect_progress,
    )
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
        graph_event_observations_count=len(graph_event_observations),
        expected_interrupt_events_count=sum(
            1
            for observation in graph_event_observations
            if observation.get("status") == "expected_interrupt"
        ),
        pending_question_present=bool(
            _state_value(
                result_state,
                "pending_question",
                "next_question",
                "clarification_question",
            )
        ),
        open_points_count=_open_points_count(result_state, persisted_state),
        triggered_findings_count=_count_collection(
            _state_value(
                result_state, "triggered_findings", "challenge_findings", "findings"
            )
        ),
        risk_drivers_count=_count_collection(
            _state_value(result_state, "risk_drivers")
        ),
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
        v92_present=bool(
            _state_value(result_state, "seal_system", "engineering", "dossier")
        ),
        v92_engineering_status=getattr(
            _state_value(result_state, "engineering"), "status", None
        ),
        v92_dossier_status=getattr(
            _state_value(result_state, "dossier"), "status", None
        ),
    )

    return GovernedGraphTurnResult(
        result_state=result_state,
        persisted_state=persisted_state,
        progress_events=progress_events,
    )
