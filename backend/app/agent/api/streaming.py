import logging
import asyncio
import json
import dataclasses
import os
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal

from fastapi import HTTPException
from app.agent.state.models import GovernedSessionState, TurnContextContract
from app.agent.runtime.answer_trace import build_answer_trace, with_answer_trace
from app.agent.runtime.final_answer_layer import (
    FinalAnswerEnvelope,
    answer_mode_for_fast_classification,
    apply_final_answer_layer,
)
from app.agent.runtime.user_facing_reply import collect_unsafe_user_instruction_reply_with_trace
from app.agent.api.deps import (
    _is_light_runtime_mode,
    _canonical_scope,
    _GRAPH_MODEL_ID,
    VISIBLE_REPLY_PROMPT_VERSION,
    VISIBLE_REPLY_PROMPT_HASH,
)
from app.agent.api.utils import (
    _fast_response_run_meta,
    _with_case_event,
    _with_governed_conversation_turn,
    _light_case_active,
    _with_light_route_progress,
    _light_structured_state,
)
from app.agent.api.loaders import (
    _persist_live_governed_state,
    _build_light_runtime_context,
    _load_live_knowledge_session_context,
    _persist_live_knowledge_session_context,
    persist_mobile_triage_pending_question,
    persist_visible_governed_turn,
)
from app.agent.api.governed_runtime import GovernedGraphTurnResult, run_governed_graph_turn
from app.agent.api.sse_contract import SSEEventBuilder, stable_turn_id
from app.agent.api.assembly import (
    _build_governed_reply_context,
    _assemble_governed_stream_payload,
)
from app.agent.communication.governed_answer_composer import (
    GovernedAnswerComposer,
    GovernedAnswerComposerInput,
    is_governed_answer_composer_enabled,
    render_governed_contextual_fallback,
    safe_governed_answer_composer_error_reason,
)
from app.agent.communication.governed_answer_context import GovernedAnswerContext
from app.agent.domain.case_delta import build_assistant_delta_event
from app.agent.prompts import REASONING_PROMPT_HASH, REASONING_PROMPT_VERSION
from app.agent.runtime.response_renderer import render_chunk
from app.agent.v92.runtime_contract import (
    apply_async_adversarial_review_to_payload,
    apply_v92_contracts_to_payload,
)
from app.agent.communication.v7_contracts import (
    AnswerMode,
    RuntimeAction,
    RuntimeActionType,
    RuntimeAnswerBuilder,
    build_runtime_action_from_turn_decision,
)
from app.agent.state.case_state import (
    PROJECTION_VERSION,
    CASE_STATE_BUILDER_VERSION,
    DETERMINISTIC_SERVICE_VERSION,
    DETERMINISTIC_DATA_VERSION,
)
from app.services.auth.dependencies import RequestUser
from app.observability.langsmith import wrap_openai_client

_log = logging.getLogger(__name__)

_VISIBLE_STREAM_SEGMENT_CHARS = 32
_VISIBLE_STREAM_SEGMENT_DELAY_SECONDS = 0.018


def classify_message_as_knowledge_override(message: str) -> str | None:
    """Compatibility alias only; dispatch owns knowledge override routing."""

    from app.agent.graph.output_contract_assembly import (  # noqa: PLC0415
        classify_message_as_knowledge_override as _classify,
    )

    return _classify(message)


def _visible_stream_segments(text: str) -> list[str]:
    """Split larger LLM deltas into readable UI chunks without changing content."""

    clean = str(text or "")
    if not clean or len(clean) <= _VISIBLE_STREAM_SEGMENT_CHARS:
        return [clean] if clean else []
    segments: list[str] = []
    current = ""
    for token in re.findall(r"\S+\s*", clean):
        if current and len(current) + len(token) > _VISIBLE_STREAM_SEGMENT_CHARS:
            segments.append(current)
            current = token
        else:
            current += token
    if current:
        segments.append(current)
    return segments


def _graph_custom_event_to_sse_payload(progress: Any) -> dict[str, Any] | None:
    if not isinstance(progress, dict):
        return None
    event_type = str(progress.get("event_type") or progress.get("type") or "")
    if event_type == "governed_answer_text_chunk":
        return {
            "type": "progress",
            "data": {
                "event_type": "draft.created_internal",
                "source": "governed_answer_composer_node",
            },
        }
    if event_type == "text_chunk":
        return {
            "type": "progress",
            "data": {
                "event_type": "draft.created_internal",
                "source": "langgraph_custom",
            },
        }
    if event_type == "governed_answer_text_reset":
        return {
            "type": "progress",
            "data": {
                "event_type": "draft.revised_internal",
                "source": "governed_answer_composer_node",
            },
        }
    if event_type == "text_reset":
        return {
            "type": "progress",
            "data": {
                "event_type": "draft.revised_internal",
                "source": "langgraph_custom",
            },
        }
    if event_type in {"governed_answer_answer_final", "answer_final"}:
        return None
    return None


async def _yield_graph_progress_frame(
    progress: Any,
    *,
    event_builder: SSEEventBuilder | None = None,
) -> AsyncGenerator[str, None]:
    event_builder = event_builder or SSEEventBuilder(turn_id="turn:progress")
    payload = _graph_custom_event_to_sse_payload(progress)
    if payload is None:
        yield event_builder.frame({"type": "progress", "data": progress}, event_type="metadata")
        return
    yield event_builder.frame(payload, event_type="metadata")



def _v7_dispatch_answer_mode(dispatch: Any) -> str | None:
    decision = getattr(dispatch, "turn_decision", None)
    if decision is None:
        return None
    mode = getattr(decision, "answer_mode", None)
    return str(getattr(mode, "value", mode) or "") or None


def _v7_dispatch_runtime_action(dispatch: Any) -> RuntimeAction | None:
    runtime_action = getattr(dispatch, "runtime_action", None)
    if runtime_action is not None:
        return runtime_action
    decision = getattr(dispatch, "turn_decision", None)
    if decision is None:
        return None
    return build_runtime_action_from_turn_decision(
        decision,
        reason="runtime_action_synthesized_from_turn_decision",
    )


def _runtime_action_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")

def _runtime_action_is_fast_smalltalk_llm(runtime_action: Any | None) -> bool:
    if runtime_action is None:
        return False
    return (
        _runtime_action_value(getattr(runtime_action, "answer_builder", None))
        == RuntimeAnswerBuilder.LIGHT_RUNTIME.value
        and _runtime_action_value(getattr(runtime_action, "answer_mode", None))
        == AnswerMode.SMALLTALK.value
        and str(getattr(runtime_action, "decision_source", "") or "").startswith(
            "pre_gate_llm_fast_responder"
        )
    )


def _is_v7_active_case_side_question(dispatch: Any) -> bool:
    runtime_action = _v7_dispatch_runtime_action(dispatch)
    if runtime_action is not None:
        return (
            _runtime_action_value(getattr(runtime_action, "answer_builder", None))
            == RuntimeAnswerBuilder.ACTIVE_CASE_SIDE.value
        )
    return _v7_dispatch_answer_mode(dispatch) == "active_case_side_question"


def _is_v7_active_case_process_question(dispatch: Any) -> bool:
    runtime_action = _v7_dispatch_runtime_action(dispatch)
    if runtime_action is not None:
        return (
            _runtime_action_value(getattr(runtime_action, "answer_builder", None))
            == RuntimeAnswerBuilder.ACTIVE_CASE_PROCESS.value
        )
    return _v7_dispatch_answer_mode(dispatch) == "active_case_process_question"


def _runtime_action_allows_graph(dispatch: Any) -> bool:
    runtime_action = _v7_dispatch_runtime_action(dispatch)
    if runtime_action is None:
        return True
    return (
        bool(getattr(runtime_action, "graph_allowed", False))
        and _runtime_action_value(getattr(runtime_action, "action_type", None))
        == RuntimeActionType.ENTER_GOVERNED_GRAPH.value
    )


def _runtime_action_trace(runtime_action: Any | None) -> dict[str, Any]:
    if hasattr(runtime_action, "as_trace"):
        return runtime_action.as_trace()
    return {}


def _with_runtime_action_trace(
    run_meta: dict[str, Any] | None,
    runtime_action: Any | None,
) -> dict[str, Any]:
    trace_update = _runtime_action_trace(runtime_action)
    if not trace_update:
        return dict(run_meta or {})
    meta = dict(run_meta or {})
    existing_trace = meta.get("answer_trace")
    answer_trace = dict(existing_trace) if isinstance(existing_trace, dict) else {}
    answer_trace.update(trace_update)
    meta["answer_trace"] = answer_trace
    return meta

def _with_engine_sidecar_trace_meta(
    run_meta: dict[str, Any] | None,
    sidecar_trace: dict[str, Any] | None,
) -> dict[str, Any]:
    meta = dict(run_meta or {})
    if not sidecar_trace:
        return meta
    existing_trace = meta.get("answer_trace")
    answer_trace = dict(existing_trace) if isinstance(existing_trace, dict) else {}
    answer_trace.update(sidecar_trace)
    meta["answer_trace"] = answer_trace
    return meta

def _engine_sidecar_trace(
    *,
    executed: bool,
    state_available: bool,
    error: Exception | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "conversation_first_runtime": True,
        "visible_runtime": "light_conversation",
        "engine_sidecar": "governed_langgraph",
        "governed_graph_sidecar_executed": executed,
        "governed_graph_visible_reply_suppressed": True,
        "engine_sidecar_state_available": state_available,
    }
    if error is not None:
        from app.agent.runtime.answer_trace import safe_fallback_reason  # noqa: PLC0415

        trace.update(
            {
                "engine_sidecar_error": safe_fallback_reason(error),
                "engine_sidecar_fallback": "visible_conversation_without_fresh_engine_state",
            }
        )
    return trace


@dataclass(frozen=True)
class GovernedReplyAssemblyContext:
    response_class: str
    structured_state: dict[str, Any] | None
    assertions_payload: dict[str, Any]
    conversation_strategy: Any
    turn_context: TurnContextContract
    run_meta: dict[str, Any]
    ui_payload: dict[str, Any]
    deterministic_reply: str
    domain_context: dict[str, Any] = dataclasses.field(default_factory=dict)

def _build_structured_version_provenance(*, decision: Any, rwdr_config_version: str | None = None) -> dict[str, Any]:
    vp = {
        "model_id": _GRAPH_MODEL_ID,
        "model_version": _GRAPH_MODEL_ID,
        "prompt_version": REASONING_PROMPT_VERSION,
        "prompt_hash": REASONING_PROMPT_HASH,
        "visible_reply_prompt_version": VISIBLE_REPLY_PROMPT_VERSION,
        "visible_reply_prompt_hash": VISIBLE_REPLY_PROMPT_HASH,
        "policy_version": getattr(decision, "policy_version", "interaction_policy_v1"),
        "projection_version": PROJECTION_VERSION,
        "case_state_builder_version": CASE_STATE_BUILDER_VERSION,
        "service_version": DETERMINISTIC_SERVICE_VERSION,
        "data_version": DETERMINISTIC_DATA_VERSION,
    }
    if rwdr_config_version is not None:
        vp["rwdr_config_version"] = rwdr_config_version
    return vp

def _build_fast_path_version_provenance(*, decision: Any) -> dict[str, Any]:
    return {
        "model_id": None,
        "model_version": None,
        "policy_version": getattr(decision, "policy_version", "interaction_policy_v1"),
        "projection_version": PROJECTION_VERSION,
        "case_state_builder_version": CASE_STATE_BUILDER_VERSION,
        "service_version": DETERMINISTIC_SERVICE_VERSION,
        "data_version": DETERMINISTIC_DATA_VERSION,
    }

def _rwdr_p0_pocket_cockpit_fields(
    message: str, governed_state: "GovernedSessionState | None" = None
) -> dict[str, Any]:
    """Additive backend-owned Pocket Cockpit fields for the governed RWDR P0 text
    case (``pocket_cockpit_patch`` + display-only ``action_chips``).

    Returns an empty dict for non-RWDR turns, so other governed/light/exploration
    turns are untouched. The patch is a deterministic projection (candidate facts,
    not confirmed truth) built by the RWDR service — no RFQ orchestration runs.

    ``rfq_status`` is single-sourced: when an active case exists it is the
    authoritative readiness (``pocket_rfq_status_from_state`` → the same
    ``evaluate_rfq_readiness`` SoT as REST/desktop), so the pocket agrees with the
    desktop/REST snapshot. Without an active case it stays the turn-local default.
    """

    authoritative_rfq_status: str | None = None
    if governed_state is not None:
        try:
            from app.agent.v92.dashboard_contract import (  # noqa: PLC0415
                pocket_rfq_status_from_state,
            )

            authoritative_rfq_status = pocket_rfq_status_from_state(governed_state)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "[rwdr_pocket_cockpit] authoritative rfq_status projection failed (%s: %s)",
                type(exc).__name__,
                exc,
            )

    try:
        from app.services.rwdr_mvp_brief import (  # noqa: PLC0415
            build_rwdr_p0_pocket_cockpit_patch,
        )

        result = build_rwdr_p0_pocket_cockpit_patch(
            str(message or ""), rfq_status=authoritative_rfq_status
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[rwdr_pocket_cockpit] projection failed (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return {}
    if result is None:
        return {}
    patch, chips = result
    return {
        "pocket_cockpit_patch": patch.model_dump(mode="json"),
        "action_chips": [chip.model_dump(mode="json") for chip in chips],
    }


def _mobile_triage_v16_fields(fast_response: Any) -> dict[str, Any]:
    """Optional, additive V1.6 envelope fields for a mobile-triage fast turn.

    The mobile triage envelope is an ``AssistantTurnEnvelope`` already built in
    dispatch and stored JSON-safe via ``model_dump(mode="json")`` on the
    ``_MobileTriageFastResponse`` carrier. Surface its public subset additively
    so the SSE client can read the pocket cockpit patch and action chips without
    changing the existing ``state_update`` workspace projection contract. Returns
    an empty dict for non-mobile / non-envelope turns, so regular fast responses
    never gain bogus V1.6 fields.
    """

    envelope = getattr(fast_response, "mobile_triage_envelope", None)
    if not isinstance(envelope, dict) or not envelope:
        return {}
    fields: dict[str, Any] = {"assistant_turn_envelope": envelope}
    pocket = envelope.get("pocket_cockpit_patch")
    if pocket is not None:
        fields["pocket_cockpit_patch"] = pocket
    chips = envelope.get("action_chips")
    if chips is not None:
        fields["action_chips"] = chips
    return fields


async def _stream_fast_response(
    *,
    request: Any,
    fast_response: Any,
    event_builder: SSEEventBuilder | None = None,
    runtime_action: Any | None = None,
) -> AsyncGenerator[str, None]:
    event_builder = event_builder or SSEEventBuilder.for_request(request)
    state_update_event = {
        "type": "state_update",
        "reply": fast_response.content,
        "answer_markdown": fast_response.content,
        "response_class": "conversational_answer",
        "run_meta": _with_runtime_action_trace(
            _fast_response_run_meta(fast_response),
            runtime_action,
        ),
    }
    state_update_event = apply_final_answer_layer(
        state_update_event,
        FinalAnswerEnvelope(
            route="fast",
            answer_mode=answer_mode_for_fast_classification(
                getattr(fast_response, "source_classification", None)
            ),
            deterministic_fallback_reply=fast_response.content,
            existing_answer_markdown=state_update_event.get("answer_markdown"),
            existing_answer_markdown_source="fast_responder",
            existing_reply_source="fast_responder",
            composer_tier="tier_a",
        ),
    )
    state_update_event = apply_v92_contracts_to_payload(
        state_update_event,
        session_id=str(request.session_id or "default"),
        user_message=request.message,
        state=None,
        route_hint="fast",
        case_id=str(request.session_id or "default") if request.session_id else None,
    )
    # Additive V1.6 wiring: mobile-triage turns carry an AssistantTurnEnvelope.
    # Merge its public subset into the final state_update without replacing the
    # workspace projection (v92_dashboard / turn_envelope / reply stay intact).
    state_update_event.update(_mobile_triage_v16_fields(fast_response))
    yield event_builder.frame(state_update_event, event_type="state_update", is_final=True)
    yield "data: [DONE]\n\n"


async def _stream_knowledge_response(
    *,
    request: Any,
    knowledge_response: Any,
    event_builder: SSEEventBuilder | None = None,
    runtime_action: Any | None = None,
) -> AsyncGenerator[str, None]:
    event_builder = event_builder or SSEEventBuilder.for_request(request)
    from app.agent.api.utils import _knowledge_response_run_meta  # noqa: PLC0415

    answer_markdown = str(getattr(knowledge_response, "answer_markdown", "") or "").strip()
    state_update_event = {
        "type": "state_update",
        "reply": knowledge_response.content,
        "answer_markdown": answer_markdown or knowledge_response.content,
        "response_class": knowledge_response.output_class,
        "structured_state": None,
        "policy_path": "knowledge",
        "run_meta": _with_runtime_action_trace(
            _knowledge_response_run_meta(knowledge_response),
            runtime_action,
        ),
    }
    answer_trace = getattr(knowledge_response, "answer_trace", None)
    answer_markdown_source = (
        answer_trace.get("answer_markdown_source")
        if isinstance(answer_trace, dict)
        else "knowledge_service"
    )
    composer_attempted = bool(
        answer_trace.get("composer_attempted") if isinstance(answer_trace, dict) else False
    )
    state_update_event = apply_final_answer_layer(
        state_update_event,
        FinalAnswerEnvelope(
            route="knowledge",
            answer_mode="knowledge",
            deterministic_fallback_reply=knowledge_response.content,
            existing_answer_markdown=state_update_event.get("answer_markdown"),
            existing_answer_markdown_source=answer_markdown_source,
            existing_reply_source="knowledge_service",
            composer_tier="tier_b" if composer_attempted else "tier_a",
        ),
    )
    state_update_event = apply_v92_contracts_to_payload(
        state_update_event,
        session_id=str(request.session_id or "default"),
        user_message=request.message,
        state=None,
        route_hint="knowledge",
        case_id=str(request.session_id or "default") if request.session_id else None,
    )
    yield event_builder.frame(state_update_event, event_type="state_update", is_final=True)
    yield "data: [DONE]\n\n"


def _classify_exploration_intent(message: str) -> str:
    lowered = (message or "").lower()
    if "vergleich" in lowered or "unterschied" in lowered or "gegenüber" in lowered:
        return "COMPARISON"
    if "warum" in lowered or "weshalb" in lowered or "ursache" in lowered:
        return "RCA_WHY"
    return "GENERAL_KNOWLEDGE"

def _detect_exploration_parameters(message: str) -> list[str]:
    import re as _re  # noqa: PLC0415
    lowered = (message or "").lower()
    patterns = {
        "pressure": r"\b(druck|bar|pascal|psi)\b",
        "temperature": r"\b(temp|grad|celsius|kelvin)\b",
        "speed": r"\b(drehzahl|u/min|rpm|geschwindigkeit|m/s)\b",
        "medium": r"\b(medium|fluid|wasser|öl|chemie|gas|dampf)\b",
        "material": r"\b(werkstoff|material|ptfe|fkm|nbr|epdm)\b",
    }
    detected = []
    for param_name, pattern in patterns.items():
        if _re.search(pattern, lowered, _re.IGNORECASE):
            detected.append(param_name)
    return detected

async def _retrieve_for_exploration_query(
    query: Any, # ExplorationQuery
    tenant_id: str,
) -> list[dict[str, Any]]:
    from app.agent.services.real_rag import retrieve_with_tenant  # noqa: PLC0415
    return await retrieve_with_tenant(query.topic, tenant_id, k=query.max_results)

async def _stream_exploration_reply(
    message: str,
    *,
    tenant_id: str,
    event_builder: SSEEventBuilder | None = None,
) -> AsyncGenerator[str, None]:
    event_builder = event_builder or SSEEventBuilder(turn_id=stable_turn_id(session_id="exploration", message=message))
    import openai as _openai  # noqa: PLC0415
    from app.agent.evidence.exploration_query import ExplorationQuery  # noqa: PLC0415
    from app.agent.prompts import prompts  # noqa: PLC0415
    from app.agent.runtime.output_guard import (  # noqa: PLC0415
        FAST_PATH_GUARD_FALLBACK,
        check_fast_path_output,
    )

    query = ExplorationQuery(
        topic=message,
        detected_parameters=_detect_exploration_parameters(message),
        query_intent=_classify_exploration_intent(message),  # type: ignore[arg-type]
        language="de",
        max_results=3,
    )

    rag_context = ""
    try:
        chunks = await _retrieve_for_exploration_query(query, tenant_id)
        if chunks:
            rag_context = "\n\n".join(
                f"[Dokument: {c.get('document_id')}]\n{c.get('text')}" for c in chunks
            )
    except Exception:
        _log.warning("exploration_retrieval_failed tenant=%s query=%s", tenant_id, query.topic[:64])

    try:
        system_prompt = prompts.render(
            "exploration/explore.j2",
            {
                "rag_context": rag_context,
                "intent": query.query_intent,
                "parameters": query.detected_parameters,
                "topic": message,
            },
        )

        model = (
            os.getenv("SEALAI_EXPLORATION_MODEL")
            or os.getenv("SEALAI_CONVERSATION_MODEL")
            or "gpt-4o-mini"
        )
        client = wrap_openai_client(_openai.AsyncOpenAI())
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            stream=True,
        )

        full_reply = ""
        preview_emitted = False
        was_guarded = False
        async for chunk in response:
            delta = render_chunk(chunk.choices[0].delta.content or "", path="CONVERSATION")
            if not delta:
                continue

            candidate_reply = full_reply + delta
            safe, violation_category = check_fast_path_output(candidate_reply)
            if not safe:
                _log.warning(
                    "exploration_output_guarded category=%s topic=%s",
                    violation_category,
                    query.topic[:64],
                )
                if preview_emitted:
                    yield event_builder.frame({"type": "text_reset"}, event_type="delta")
                full_reply = FAST_PATH_GUARD_FALLBACK
                was_guarded = True
                for segment in _visible_stream_segments(full_reply):
                    yield event_builder.frame(
                        {"type": "text_chunk", "text": segment},
                        event_type="delta",
                    )
                    if len(full_reply) > _VISIBLE_STREAM_SEGMENT_CHARS:
                        await asyncio.sleep(_VISIBLE_STREAM_SEGMENT_DELAY_SECONDS)
                break

            full_reply = candidate_reply
            for segment in _visible_stream_segments(delta):
                yield event_builder.frame(
                    {"type": "text_chunk", "text": segment},
                    event_type="delta",
                )
                preview_emitted = True
                if len(delta) > _VISIBLE_STREAM_SEGMENT_CHARS:
                    await asyncio.sleep(_VISIBLE_STREAM_SEGMENT_DELAY_SECONDS)

        if not was_guarded:
            safe, violation_category = check_fast_path_output(full_reply)
            if not safe:
                _log.warning(
                    "exploration_output_guarded category=%s topic=%s",
                    violation_category,
                    query.topic[:64],
                )
                if preview_emitted:
                    yield event_builder.frame({"type": "text_reset"}, event_type="delta")
                full_reply = FAST_PATH_GUARD_FALLBACK
                for segment in _visible_stream_segments(full_reply):
                    yield event_builder.frame(
                        {"type": "text_chunk", "text": segment},
                        event_type="delta",
                    )
                    if len(full_reply) > _VISIBLE_STREAM_SEGMENT_CHARS:
                        await asyncio.sleep(_VISIBLE_STREAM_SEGMENT_DELAY_SECONDS)

        state_update_event = {
            "type": "state_update",
            "reply": full_reply,
            "answer_markdown": full_reply,
            "response_class": "conversational_answer",
            "run_meta": with_answer_trace(
                None,
                build_answer_trace(
                    reply_source="exploration_stream",
                    answer_markdown_source="exploration_stream",
                    final_visible_source="answer_markdown",
                ),
            ),
        }
        # F1: run the assembled knowledge reply through the contract guard so the
        # L2 knowledge backstop (validate_final_output) also covers this streamed
        # path — it catches suitability forms L1 misses (e.g. the plural "sind
        # geeignet"). On a late L2 block the guard substitutes the safe fallback;
        # reuse the existing text_reset+fallback streaming so the visible text is
        # corrected (identical mechanism to the L1 post-assembly guard above).
        state_update_event = apply_v92_contracts_to_payload(
            state_update_event,
            session_id="exploration",
            user_message=message,
            state=None,
            route_hint="knowledge",
        )
        guarded_reply = str(state_update_event.get("answer_markdown") or "")
        if guarded_reply and guarded_reply != full_reply:
            _log.warning("exploration_output_guarded_l2 topic=%s", query.topic[:64])
            if preview_emitted:
                yield event_builder.frame({"type": "text_reset"}, event_type="delta")
            for segment in _visible_stream_segments(guarded_reply):
                yield event_builder.frame(
                    {"type": "text_chunk", "text": segment},
                    event_type="delta",
                )
                if len(guarded_reply) > _VISIBLE_STREAM_SEGMENT_CHARS:
                    await asyncio.sleep(_VISIBLE_STREAM_SEGMENT_DELAY_SECONDS)
            full_reply = guarded_reply
        yield event_builder.frame(state_update_event, event_type="state_update", is_final=True)
        yield event_builder.frame({"type": "turn_complete"}, event_type="done")
    except Exception as exc:  # noqa: BLE001
        _log.error("exploration_stream_failed: %s: %s", type(exc).__name__, exc)
        yield event_builder.frame(
            {
                "type": "error",
                "message": "Vergleichsantwort momentan nicht verfuegbar - bitte erneut versuchen.",
            },
            event_type="error",
            error_code="exploration_stream_failed",
        )
    yield "data: [DONE]\n\n"

async def _stream_light_runtime(
    *,
    message: str,
    request: Any, # ChatRequest
    current_user: RequestUser,
    mode: Literal["CONVERSATION", "EXPLORATION"],
    governed_state_override: GovernedSessionState | None = None,
    direct_reply: str | None = None,
    event_builder: SSEEventBuilder | None = None,
    runtime_action: Any | None = None,
    force_conversation_runtime: bool = False,
    sidecar_trace: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    from app.agent.runtime.conversation_runtime import stream_conversation  # noqa: PLC0415

    event_builder = event_builder or SSEEventBuilder.for_request(request)
    if _runtime_action_is_fast_smalltalk_llm(runtime_action):
        governed, history, case_summary = None, [], None
    else:
        governed, history, case_summary = await _build_light_runtime_context(
            request=request,
            current_user=current_user,
            governed_state_override=governed_state_override,
            create_if_missing=False,
        )
    if direct_reply is None and mode == "CONVERSATION":
        from app.agent.api.routes.chat import _open_case_ack_continue_reply  # noqa: PLC0415

        direct_reply = _open_case_ack_continue_reply(
            message=message,
            governed_state=governed,
        )
    final_reply = ""
    persisted_light_state: GovernedSessionState | None = None

    async def _persist_light_turn_once() -> GovernedSessionState | None:
        nonlocal governed, persisted_light_state
        if persisted_light_state is not None:
            return persisted_light_state
        if governed is None or not _light_case_active(governed):
            return governed
        updated = _with_light_route_progress(
            governed,
            role="user",
            content=message,
            pre_gate_classification=mode,
        )
        if final_reply:
            updated = _with_light_route_progress(
                updated,
                role="assistant",
                content=final_reply,
                pre_gate_classification=mode,
            )
        if mode == "EXPLORATION" and request.session_id and os.getenv("REDIS_URL"):
            try:
                from app.services.knowledge_case_bridge_service import KnowledgeCaseBridgeService  # noqa: PLC0415

                bridge_service = KnowledgeCaseBridgeService()
                knowledge_context = await _load_live_knowledge_session_context(
                    current_user=current_user,
                    session_id=request.session_id,
                )
                knowledge_context = bridge_service.update_context(
                    message,
                    context=knowledge_context,
                    session_id=request.session_id,
                    role="user",
                )
                if final_reply:
                    knowledge_context = bridge_service.update_context(
                        final_reply,
                        context=knowledge_context,
                        role="assistant",
                    )
                await _persist_live_knowledge_session_context(
                    current_user=current_user,
                    session_id=request.session_id,
                    context=knowledge_context,
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "[runtime_authority] exploration knowledge context persist failed (%s: %s)",
                    type(exc).__name__,
                    exc,
                )
        if os.getenv("REDIS_URL"):
            try:
                await _persist_live_governed_state(
                    current_user=current_user,
                    session_id=request.session_id,
                    state=updated,
                    pre_gate_classification=mode,
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "[runtime_authority] light governed state persist failed (%s: %s)",
                    type(exc).__name__,
                    exc,
                )
        persisted_light_state = updated
        governed = updated
        return updated

    if mode == "EXPLORATION" and request.session_id and not force_conversation_runtime:
        tenant_id, _, _ = _canonical_scope(current_user, case_id=request.session_id)
        frame_gen: AsyncGenerator[str, None] = _stream_exploration_reply(
            message,
            tenant_id=tenant_id,
        )
    else:
        frame_gen = stream_conversation(
            message,
            history=history,
            case_summary=case_summary,
            mode=mode,
            direct_reply=direct_reply,
        )

    async for frame in frame_gen:
        if not frame.startswith("data: "):
            yield frame
            continue

        raw_frame_data = frame[6:].strip()
        if raw_frame_data == "[DONE]":
            if request.session_id:
                await _persist_light_turn_once()
            yield frame
            continue

        try:
            payload = json.loads(raw_frame_data)
        except Exception:
            yield frame
            continue

        event_type = payload.get("type")
        if event_type == "text_chunk":
            yield event_builder.frame(payload, event_type="delta")
            continue

        if event_type == "state_update":
            final_reply += payload.get("reply") or ""
            state_for_projection = governed
            if request.session_id:
                state_for_projection = await _persist_light_turn_once()
            payload["response_class"] = "conversational_answer"
            payload["structured_state"] = (
                _light_structured_state(state_for_projection)
                if state_for_projection is not None
                else None
            )
            payload["policy_path"] = mode.lower()
            source = "exploration_stream" if mode == "EXPLORATION" else "light_conversation"
            payload["run_meta"] = with_answer_trace(
                payload.get("run_meta") if isinstance(payload.get("run_meta"), dict) else None,
                build_answer_trace(
                    reply_source=source,  # type: ignore[arg-type]
                    answer_markdown_source=source,  # type: ignore[arg-type]
                    final_visible_source="answer_markdown",
                ),
            )
            payload["run_meta"] = _with_runtime_action_trace(
                payload.get("run_meta"),
                runtime_action,
            )
            payload["run_meta"] = _with_engine_sidecar_trace_meta(
                payload.get("run_meta"),
                sidecar_trace,
            )
            payload = apply_v92_contracts_to_payload(
                payload,
                session_id=str(request.session_id or "default"),
                user_message=message,
                state=state_for_projection,
                route_hint=mode.lower(),
                case_id=str(request.session_id or "default") if request.session_id else None,
            )
            # Additive backend-owned Pocket Cockpit for the governed RWDR P0 text
            # case. No-op for non-RWDR turns; never replaces the workspace
            # projection (v92_dashboard / turn_envelope / reply stay intact).
            payload.update(_rwdr_p0_pocket_cockpit_fields(message, state_for_projection))
            yield event_builder.frame(payload, event_type="state_update", is_final=True)
            continue

        if event_type == "done":
            payload["run_meta"] = _with_runtime_action_trace(
                {
                    "version_provenance": _build_fast_path_version_provenance(decision=None)
                },
                runtime_action,
            )
            payload["run_meta"] = _with_engine_sidecar_trace_meta(
                payload.get("run_meta"),
                sidecar_trace,
            )
            yield event_builder.frame(payload, event_type="done")
            continue

        if event_type == "turn_complete":
            if request.session_id:
                await _persist_light_turn_once()
            yield event_builder.frame(payload, event_type="done")
            continue
        if event_type == "error":
            yield event_builder.frame(
                payload,
                event_type="error",
                error_code="conversation_stream_error",
            )

async def _stream_conversation_first_with_engine_sidecar(
    request: Any, # ChatRequest
    *,
    current_user: RequestUser,
    event_builder: SSEEventBuilder | None = None,
    pre_gate_classification: str | None = None,
    runtime_action: Any | None = None,
    governed_state: GovernedSessionState | None = None,
) -> AsyncGenerator[str, None]:
    event_builder = event_builder or SSEEventBuilder.for_request(request)
    sidecar_state = governed_state
    sidecar_error: Exception | None = None
    sidecar_executed = False
    try:
        turn_result = await run_governed_graph_turn(
            request=request,
            current_user=current_user,
            pre_gate_classification=pre_gate_classification,
            collect_progress=False,
            runtime_action=runtime_action,
        )
        sidecar_state = turn_result.persisted_state
        sidecar_executed = True
    except Exception as exc:  # noqa: BLE001
        sidecar_error = exc
        from app.agent.runtime.answer_trace import safe_fallback_reason  # noqa: PLC0415

        _log.exception(
            "[runtime_authority] conversation-first stream sidecar failed session=%s reason=%s",
            request.session_id,
            safe_fallback_reason(exc),
        )

    trace = _engine_sidecar_trace(
        executed=sidecar_executed,
        state_available=sidecar_state is not None,
        error=sidecar_error,
    )
    from app.agent.api.routes.chat import _open_sealing_invite_reply  # noqa: PLC0415

    async for frame in _stream_light_runtime(
        message=request.message,
        request=request,
        current_user=current_user,
        mode="EXPLORATION",
        governed_state_override=sidecar_state,
        direct_reply=_open_sealing_invite_reply(
            pre_gate_classification=pre_gate_classification,
            runtime_action=runtime_action,
            sidecar_state=sidecar_state,
        ),
        runtime_action=runtime_action,
        force_conversation_runtime=True,
        sidecar_trace=trace,
    ):
        yield frame

async def _stream_governed_graph(
    request: Any, # ChatRequest
    *,
    current_user: RequestUser,
    event_builder: SSEEventBuilder | None = None,
    pre_gate_classification: str | None = None,
    runtime_action: Any | None = None,
) -> AsyncGenerator[str, None]:
    event_builder = event_builder or SSEEventBuilder.for_request(request)
    progress_queue: asyncio.Queue[Any] = asyncio.Queue()
    live_progress_count = 0

    async def _on_graph_progress(progress: Any) -> None:
        await progress_queue.put(progress)

    turn_task: asyncio.Task[GovernedGraphTurnResult] = asyncio.create_task(
        run_governed_graph_turn(
            request=request,
            current_user=current_user,
            pre_gate_classification=pre_gate_classification,
            collect_progress=True,
            progress_callback=_on_graph_progress,
            runtime_action=runtime_action,
        )
    )
    try:
        while True:
            if turn_task.done():
                while not progress_queue.empty():
                    progress = progress_queue.get_nowait()
                    live_progress_count += 1
                    async for frame in _yield_graph_progress_frame(progress, event_builder=event_builder):
                        yield frame
                turn_result = await turn_task
                break
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            live_progress_count += 1
            async for frame in _yield_graph_progress_frame(progress, event_builder=event_builder):
                yield frame
    except HTTPException as exc:
        if exc.status_code == 404:
            yield event_builder.frame(
                {"type": "error", "message": "governed_state_not_found"},
                event_type="error",
                error_code="governed_state_not_found",
            )
            return
        raise
    finally:
        if not turn_task.done():
            turn_task.cancel()

    if live_progress_count == 0:
        for progress in turn_result.progress_events:
            async for frame in _yield_graph_progress_frame(progress, event_builder=event_builder):
                yield frame

    context = _build_governed_reply_context(
        result_state=turn_result.result_state,
        persisted_state=turn_result.persisted_state,
    )
    if (
        not str(getattr(context, "answer_markdown", "") or "").strip()
        and is_governed_answer_composer_enabled()
    ):
        try:
            governed_context = GovernedAnswerContext.model_validate(
                getattr(turn_result.result_state, "governed_answer_context", {}) or {}
            )
            deterministic_reply = str(context.deterministic_reply or "")
            composer_basis_reply = render_governed_contextual_fallback(
                governed_context,
                deterministic_reply,
            )
            if not str(composer_basis_reply or "").strip():
                composer_basis_reply = deterministic_reply
            composer = GovernedAnswerComposer()
            result = await composer.compose(
                GovernedAnswerComposerInput(
                    context=governed_context,
                    deterministic_reply=str(composer_basis_reply or ""),
                )
            )
            final_answer = result.answer_markdown

            if final_answer:
                run_meta = dict(context.run_meta or {})
                run_meta["governed_answer_composer"] = {
                    "source": "governed_composer",
                    "error": None,
                    "prompt_trace": (
                        result.prompt_trace.model_dump(mode="json")
                        if result.prompt_trace
                        else {}
                    ),
                }
                context = dataclasses.replace(
                    context,
                    answer_markdown=final_answer,
                    answer_markdown_source="governed_composer",
                    answer_markdown_error=None,
                    run_meta=run_meta,
                )
        except Exception as exc:  # noqa: BLE001
            reason = safe_governed_answer_composer_error_reason(exc)
            _log.warning("[governed_answer_composer_stream] fallback reason=%s", reason)
            fallback_answer = str(context.deterministic_reply or "").strip()
            try:
                governed_context = GovernedAnswerContext.model_validate(
                    getattr(turn_result.result_state, "governed_answer_context", {}) or {}
                )
                fallback_answer = render_governed_contextual_fallback(
                    governed_context,
                    fallback_answer,
                )
            except Exception:  # noqa: BLE001
                pass
            run_meta = dict(context.run_meta or {})
            run_meta["governed_answer_composer"] = {
                "source": "composer_fallback",
                "error": reason,
            }
            context = dataclasses.replace(
                context,
                answer_markdown=fallback_answer,
                answer_markdown_source="composer_fallback",
                answer_markdown_error=reason,
                run_meta=run_meta,
            )
    yield event_builder.frame(
        {"type": "progress", "data": {"event_type": "final_guard.running"}},
        event_type="metadata",
    )
    payload = _assemble_governed_stream_payload(
        context=context,
        session_id=str(request.session_id or "default"),
        user_message=request.message,
        state=turn_result.result_state,
    )
    payload = await apply_async_adversarial_review_to_payload(payload)
    final_guard_result = payload.get("final_guard_result") if isinstance(payload, dict) else None
    yield event_builder.frame(
        {
            "type": "progress",
            "data": {"event_type": "final_guard.done", "result": final_guard_result},
        },
        event_type="metadata",
    )
    assistant_message = str(
        payload.get("assistant_message")
        or payload.get("answer_markdown")
        or payload.get("reply")
        or ""
    ).strip()
    if assistant_message:
        updated_state = _with_governed_conversation_turn(
            turn_result.persisted_state,
            role="assistant",
            content=assistant_message,
        )
        case_event = build_assistant_delta_event(
            case_id=str(request.session_id or "default"),
            turn_index=int(getattr(turn_result.result_state, "user_turn_index", 0) or turn_result.result_state.analysis_cycle or 0),
            assistant_message=assistant_message,
            delta=context.proposed_case_delta,
            persistence_marker=turn_result.persisted_state.persistence_marker,
        )
        updated_state = _with_case_event(updated_state, event=case_event)
        await _persist_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            state=updated_state,
            pre_gate_classification=pre_gate_classification,
        )
    # Suffix version provenance from streaming.py locally without dropping
    # composer source/fallback metadata from the graph assembly layer.
    run_meta = dict(payload.get("run_meta") or {})
    run_meta["version_provenance"] = _build_structured_version_provenance(decision=None)
    payload["run_meta"] = _with_runtime_action_trace(run_meta, runtime_action)

    yield event_builder.frame(payload, event_type="state_update", is_final=True)
    yield "data: [DONE]\n\n"

async def event_generator(
    request: Any, # ChatRequest
    *,
    current_user: RequestUser,
) -> AsyncGenerator[str, None]:
    # P1-2 TEIL A: start the single per-turn timer at the streaming entry; the SSE
    # builder fills first_progress_ms/latency_ms from it on the final state_update.
    from app.agent.runtime.turn_timing import start_turn_timer  # noqa: PLC0415

    start_turn_timer()
    event_builder = SSEEventBuilder.for_request(request)
    early_guard_reply = await collect_unsafe_user_instruction_reply_with_trace(
        latest_user_message=request.message,
        turn_context=None,
    )
    if early_guard_reply is not None:
        state_update_event = {
            "type": "state_update",
            "reply": early_guard_reply.text,
            "answer_markdown": early_guard_reply.text,
            "response_class": "structured_clarification",
            "policy_path": "governed_guard",
            "run_meta": with_answer_trace(
                None,
                early_guard_reply.answer_trace,
            ),
        }
        state_update_event = apply_v92_contracts_to_payload(
            state_update_event,
            session_id=str(request.session_id or "default"),
            user_message=request.message,
            state=None,
            route_hint="unsafe_or_blocked",
            case_id=str(request.session_id or "default") if request.session_id else None,
        )
        yield event_builder.frame(state_update_event, event_type="state_update", is_final=True)
        yield "data: [DONE]\n\n"
        return

    from app.agent.api.routes.chat import _resolve_runtime_dispatch # noqa: PLC0415
    dispatch = await _resolve_runtime_dispatch(
        request,
        current_user=current_user,
    )

    if dispatch.rfq_response is not None:
        from app.agent.api.routes.chat import (  # noqa: PLC0415
            _build_rfq_readiness_payload,
        )

        payload = _build_rfq_readiness_payload(
            answer_markdown=dispatch.rfq_response,
            projection=getattr(dispatch, "rfq_readiness_projection", None),
            runtime_action=_v7_dispatch_runtime_action(dispatch),
        )
        payload = apply_v92_contracts_to_payload(
            payload,
            session_id=str(request.session_id or "default"),
            user_message=request.message,
            state=getattr(dispatch, "governed_state", None),
            route_hint="rfq_readiness",
            case_id=str(request.session_id or "default") if request.session_id else None,
        )
        yield event_builder.frame(payload, event_type="state_update", is_final=True)
        yield "data: [DONE]\n\n"
        return

    if dispatch.fast_response is not None:
        async for frame in _stream_fast_response(
            request=request,
            fast_response=dispatch.fast_response,
            runtime_action=_v7_dispatch_runtime_action(dispatch),
        ):
            yield frame
        # Bridge the mobile triage pending question after the instant reply is
        # fully streamed, so the next "Ja"/"Nein"/"Weiß ich nicht" turn binds via
        # the existing slot machinery. No-op for non-mobile fast responses.
        await persist_mobile_triage_pending_question(
            current_user=current_user,
            session_id=request.session_id,
            fast_response=dispatch.fast_response,
        )
        return
    if dispatch.knowledge_response is not None:
        async for frame in _stream_knowledge_response(
            request=request,
            knowledge_response=dispatch.knowledge_response,
            runtime_action=_v7_dispatch_runtime_action(dispatch),
        ):
            yield frame
        return

    if _is_light_runtime_mode(dispatch.runtime_mode):
        _log.debug(
            "[runtime_authority] stream session=%s authority=light_runtime mode=%s reason=%s",
            request.session_id,
            dispatch.runtime_mode,
            dispatch.gate_reason,
        )
        async for frame in _stream_light_runtime(
            message=request.message,
            request=request,
            current_user=current_user,
            mode=dispatch.runtime_mode,
            governed_state_override=dispatch.governed_state,
            direct_reply=dispatch.direct_reply,
            runtime_action=_v7_dispatch_runtime_action(dispatch),
        ):
            yield frame
        return

    if dispatch.runtime_mode == "GOVERNED":
        runtime_action = _v7_dispatch_runtime_action(dispatch)
        if _is_v7_active_case_process_question(dispatch):
            from app.agent.api.routes.chat import (  # noqa: PLC0415
                _build_active_case_process_payload,
                _persist_active_case_process_turn,
            )

            payload = await _build_active_case_process_payload(
                message=request.message,
                session_id=request.session_id,
                governed_state=dispatch.governed_state,
                decision=dispatch.turn_decision,
                runtime_action=runtime_action,
            )
            await _persist_active_case_process_turn(
                request=request,
                current_user=current_user,
                governed_state=dispatch.governed_state,
                assistant_message=str(payload.get("assistant_message") or ""),
                pre_gate_classification=dispatch.pre_gate_classification,
            )
            yield event_builder.frame(payload, event_type="state_update", is_final=True)
            yield "data: [DONE]\n\n"
            return
        if _is_v7_active_case_side_question(dispatch):
            from app.agent.api.routes.chat import (  # noqa: PLC0415
                _build_active_case_side_payload,
            )

            payload = await _build_active_case_side_payload(
                message=request.message,
                session_id=request.session_id,
                governed_state=dispatch.governed_state,
                decision=dispatch.turn_decision,
                conversation_route=dispatch.conversation_route,
                runtime_action=runtime_action,
                current_user=current_user,
            )
            await persist_visible_governed_turn(
                current_user=current_user,
                session_id=request.session_id,
                user_message=request.message,
                assistant_message=str(
                    payload.get("assistant_message")
                    or payload.get("answer_markdown")
                    or payload.get("reply")
                    or ""
                ),
                governed_state=dispatch.governed_state,
                pre_gate_classification=dispatch.pre_gate_classification,
            )
            yield event_builder.frame(payload, event_type="state_update", is_final=True)
            yield "data: [DONE]\n\n"
            return
        if not _runtime_action_allows_graph(dispatch):
            from app.agent.api.routes.chat import (  # noqa: PLC0415
                _runtime_action_blocked_graph_payload,
            )

            payload = _runtime_action_blocked_graph_payload(runtime_action)
            payload = apply_v92_contracts_to_payload(
                payload,
                session_id=str(request.session_id or "default"),
                user_message=request.message,
                state=dispatch.governed_state,
                route_hint="unsafe_or_blocked",
                case_id=str(request.session_id or "default") if request.session_id else None,
            )
            await persist_visible_governed_turn(
                current_user=current_user,
                session_id=request.session_id,
                user_message=request.message,
                assistant_message=str(
                    payload.get("assistant_message")
                    or payload.get("answer_markdown")
                    or payload.get("reply")
                    or ""
                ),
                governed_state=dispatch.governed_state,
                pre_gate_classification=dispatch.pre_gate_classification,
            )
            yield event_builder.frame(payload, event_type="state_update", is_final=True)
            yield "data: [DONE]\n\n"
            return

        _log.debug(
            "[runtime_authority] stream session=%s authority=conversation_first_sidecar reason=%s",
            request.session_id,
            dispatch.gate_reason,
        )
        async for frame in _stream_conversation_first_with_engine_sidecar(
            request,
            current_user=current_user,
            pre_gate_classification=dispatch.pre_gate_classification,
            runtime_action=runtime_action,
            governed_state=dispatch.governed_state,
        ):
            yield frame
        return

    async for frame in _stream_governed_graph(
        request,
        current_user=current_user,
        pre_gate_classification=dispatch.pre_gate_classification,
        runtime_action=_v7_dispatch_runtime_action(dispatch),
    ):
        yield frame
