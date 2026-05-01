import logging
import json
import dataclasses
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Literal, Optional

from fastapi import HTTPException
from langchain_core.messages import BaseMessage
from app.agent.state.models import GovernedSessionState, TurnContextContract
from app.agent.runtime.user_facing_reply import collect_governed_visible_reply, _guard_unsafe_user_instruction
from app.agent.graph.output_contract_assembly import (
    build_governed_conversation_strategy_contract,
    classify_message_as_knowledge_override,
)
from app.agent.runtime.turn_context import build_governed_turn_context
from app.agent.api.deps import (
    _resolve_payload_binding_level,
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
    _with_light_route_progress,
    _light_structured_state,
)
from app.agent.api.loaders import (
    _persist_live_governed_state,
    _build_light_runtime_context,
    _load_live_knowledge_session_context,
    _persist_live_knowledge_session_context,
)
from app.agent.api.governed_runtime import run_governed_graph_turn
from app.agent.api.assembly import (
    GovernedReplyAssemblyContext,
    _build_governed_reply_context,
    _assemble_governed_stream_payload,
    _build_fast_path_version_provenance,
    _build_structured_version_provenance,
)
from app.agent.domain.case_delta import build_assistant_delta_event
from app.agent.prompts import REASONING_PROMPT_HASH, REASONING_PROMPT_VERSION
from app.agent.state.case_state import (
    PROJECTION_VERSION,
    CASE_STATE_BUILDER_VERSION,
    DETERMINISTIC_SERVICE_VERSION,
    DETERMINISTIC_DATA_VERSION,
)
from app.services.auth.dependencies import RequestUser

_log = logging.getLogger(__name__)

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

async def _stream_fast_response(
    *,
    fast_response: Any,
) -> AsyncGenerator[str, None]:
    state_update_event = {
        "type": "state_update",
        "reply": fast_response.content,
        "response_class": "conversational_answer",
        "run_meta": _fast_response_run_meta(fast_response),
    }
    yield f"data: {json.dumps(state_update_event, default=str)}\n\n"
    yield "data: [DONE]\n\n"


async def _stream_knowledge_response(
    *,
    knowledge_response: Any,
) -> AsyncGenerator[str, None]:
    from app.agent.api.utils import _knowledge_response_run_meta  # noqa: PLC0415

    state_update_event = {
        "type": "state_update",
        "reply": knowledge_response.content,
        "response_class": knowledge_response.output_class,
        "structured_state": None,
        "policy_path": "knowledge",
        "run_meta": _knowledge_response_run_meta(knowledge_response),
    }
    yield f"data: {json.dumps(state_update_event, default=str)}\n\n"
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
) -> AsyncGenerator[str, None]:
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
        client = _openai.AsyncOpenAI()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            stream=True,
        )

        full_reply = ""
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                full_reply += delta

        safe, violation_category = check_fast_path_output(full_reply)
        if not safe:
            _log.warning(
                "exploration_output_guarded category=%s topic=%s",
                violation_category,
                query.topic[:64],
            )
            full_reply = FAST_PATH_GUARD_FALLBACK

        if full_reply:
            yield f"data: {json.dumps({'type': 'text_chunk', 'text': full_reply}, default=str)}\n\n"

        state_update_event = {
            "type": "state_update",
            "reply": full_reply,
            "response_class": "conversational_answer",
        }
        yield f"data: {json.dumps(state_update_event, default=str)}\n\n"
        yield f"data: {json.dumps({'type': 'turn_complete'}, default=str)}\n\n"
    except Exception as exc:  # noqa: BLE001
        _log.error("exploration_stream_failed: %s: %s", type(exc).__name__, exc)
        yield f"data: {json.dumps({'type': 'error', 'message': 'Vergleichsantwort momentan nicht verfuegbar - bitte erneut versuchen.'}, default=str)}\n\n"
    yield "data: [DONE]\n\n"

async def _stream_light_runtime(
    *,
    message: str,
    request: Any, # ChatRequest
    current_user: RequestUser,
    mode: Literal["CONVERSATION", "EXPLORATION"],
    governed_state_override: GovernedSessionState | None = None,
    direct_reply: str | None = None,
) -> AsyncGenerator[str, None]:
    from app.agent.runtime.conversation_runtime import stream_conversation  # noqa: PLC0415

    governed, history, case_summary = await _build_light_runtime_context(
        request=request,
        current_user=current_user,
        governed_state_override=governed_state_override,
    )
    final_reply = ""
    persisted_light_state: GovernedSessionState | None = None

    async def _persist_light_turn_once() -> GovernedSessionState:
        nonlocal governed, persisted_light_state
        if persisted_light_state is not None:
            return persisted_light_state
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
            await _persist_live_governed_state(
                current_user=current_user,
                session_id=request.session_id,
                state=updated,
                pre_gate_classification=mode,
            )
        persisted_light_state = updated
        governed = updated
        return updated

    if mode == "EXPLORATION" and request.session_id:
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
            yield frame
            continue

        if event_type == "state_update":
            final_reply += payload.get("reply") or ""
            state_for_projection = governed
            if request.session_id:
                state_for_projection = await _persist_light_turn_once()
            payload["response_class"] = "conversational_answer"
            payload["structured_state"] = _light_structured_state(state_for_projection)
            payload["policy_path"] = mode.lower()
            yield f"data: {json.dumps(payload, default=str)}\n\n"
            continue

        if event_type == "done":
            payload["run_meta"] = {
                "version_provenance": _build_fast_path_version_provenance(decision=None)
            }
            yield f"data: {json.dumps(payload, default=str)}\n\n"
            continue

        if event_type == "turn_complete":
            if request.session_id:
                await _persist_light_turn_once()
            yield frame
            continue
        if event_type == "error":
            yield frame

async def _stream_governed_graph(
    request: Any, # ChatRequest
    *,
    current_user: RequestUser,
    pre_gate_classification: str | None = None,
) -> AsyncGenerator[str, None]:
    try:
        turn_result = await run_governed_graph_turn(
            request=request,
            current_user=current_user,
            pre_gate_classification=pre_gate_classification,
            collect_progress=True,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            yield f"data: {json.dumps({'type': 'error', 'message': 'governed_state_not_found'})}\n\n"
            return
        raise

    for progress in turn_result.progress_events:
        yield f"data: {json.dumps({'type': 'progress', 'data': progress}, default=str)}\n\n"

    context = _build_governed_reply_context(
        result_state=turn_result.result_state,
        persisted_state=turn_result.persisted_state,
    )
    visible_reply = await collect_governed_visible_reply(
        response_class=context.response_class,
        turn_context=context.turn_context,
        fallback_text=context.deterministic_reply,
        latest_user_message=request.message,
    )
    if visible_reply:
        updated_state = _with_governed_conversation_turn(
            turn_result.persisted_state,
            role="assistant",
            content=visible_reply,
        )
        case_event = build_assistant_delta_event(
            case_id=str(request.session_id or "default"),
            turn_index=int(getattr(turn_result.result_state, "user_turn_index", 0) or turn_result.result_state.analysis_cycle or 0),
            assistant_message=visible_reply,
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

    payload = _assemble_governed_stream_payload(
        context=context,
        visible_reply=visible_reply,
    )
    # Suffix version provenance from streaming.py locally
    payload["run_meta"] = {
        "version_provenance": _build_structured_version_provenance(decision=None)
    }

    yield f"data: {json.dumps(payload, default=str)}\n\n"
    yield "data: [DONE]\n\n"

async def event_generator(
    request: Any, # ChatRequest
    *,
    current_user: RequestUser,
) -> AsyncGenerator[str, None]:
    early_guard_reply = _guard_unsafe_user_instruction(
        latest_user_message=request.message,
        turn_context=None,
    )
    if early_guard_reply is not None:
        yield f"data: {json.dumps({'type': 'state_update', 'reply': early_guard_reply, 'response_class': 'structured_clarification', 'policy_path': 'governed_guard'}, default=str)}\n\n"
        yield "data: [DONE]\n\n"
        return

    from app.agent.api.routes.chat import _resolve_runtime_dispatch # noqa: PLC0415
    dispatch = await _resolve_runtime_dispatch(
        request,
        current_user=current_user,
    )

    if dispatch.fast_response is not None:
        async for frame in _stream_fast_response(fast_response=dispatch.fast_response):
            yield frame
        return
    if dispatch.knowledge_response is not None:
        async for frame in _stream_knowledge_response(
            knowledge_response=dispatch.knowledge_response,
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
        ):
            yield frame
        return

    if dispatch.runtime_mode == "GOVERNED":
        _knowledge_override = classify_message_as_knowledge_override(request.message)
        if _knowledge_override is not None:
            _override_mode: Literal["CONVERSATION", "EXPLORATION"] = (
                "CONVERSATION" if _knowledge_override == "conversational_answer" else "EXPLORATION"
            )
            async for frame in _stream_light_runtime(
                message=request.message,
                request=request,
                current_user=current_user,
                mode=_override_mode,
                governed_state_override=dispatch.governed_state,
            ):
                yield frame
            return

        _log.debug(
            "[runtime_authority] stream session=%s authority=governed_graph reason=%s",
            request.session_id,
            dispatch.gate_reason,
        )
        async for frame in _stream_governed_graph(
            request,
            current_user=current_user,
            pre_gate_classification=dispatch.pre_gate_classification,
        ):
            yield frame
        return

    async for frame in _stream_governed_graph(
        request,
        current_user=current_user,
        pre_gate_classification=dispatch.pre_gate_classification,
    ):
        yield frame
