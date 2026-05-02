import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.api.models import ChatRequest, ChatResponse, build_public_response_core
from app.agent.state.models import GovernedSessionState
from app.agent.graph import GraphState
from app.agent.runtime.user_facing_reply import collect_governed_visible_reply, _guard_unsafe_user_instruction
from app.agent.graph.output_contract_assembly import (
    classify_message_as_knowledge_override,
)
from app.agent.api.deps import (
    _is_light_runtime_mode,
    get_current_request_user,
    RequestUser,
)
from app.agent.api.utils import (
    _with_case_event,
    _with_governed_conversation_turn,
    _with_light_route_progress,
    _light_structured_state,
)
from app.agent.api.loaders import (
    _persist_live_governed_state,
    _build_light_runtime_context,
)
from app.agent.api.governed_runtime import run_governed_graph_turn
from app.agent.api.assembly import (
    _build_governed_reply_context,
    _assemble_governed_stream_payload,
    _governed_composer_visible_answer,
)
from app.agent.domain.case_delta import build_assistant_delta_event
from app.agent.api.streaming import event_generator, _build_fast_path_version_provenance
from app.agent.api.dispatch import _resolve_runtime_dispatch

_log = logging.getLogger(__name__)

router = APIRouter()

async def _run_light_chat_response(
    *,
    message: str,
    request: ChatRequest,
    current_user: RequestUser,
    mode: Literal["CONVERSATION", "EXPLORATION"],
    governed_state_override: GovernedSessionState | None = None,
    direct_reply: str | None = None,
) -> ChatResponse:
    from app.agent.runtime.conversation_runtime import run_conversation  # noqa: PLC0415

    governed, history, case_summary = await _build_light_runtime_context(
        request=request,
        current_user=current_user,
        governed_state_override=governed_state_override,
    )

    result = await run_conversation(
        message,
        history=history,
        case_summary=case_summary,
        mode=mode,
        direct_reply=direct_reply,
    )
    structured_state: dict[str, Any] | None = None
    if result.reply_text:
        updated = _with_light_route_progress(
            governed,
            role="assistant",
            content=result.reply_text,
            pre_gate_classification=mode,
        )
        await _persist_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            state=updated,
            pre_gate_classification=mode,
        )
        structured_state = _light_structured_state(updated)

    return ChatResponse(
        session_id=request.session_id,
        **build_public_response_core(
            reply=result.reply_text,
            structured_state=structured_state,
            policy_path=mode.lower(),
            run_meta={
                "version_provenance": _build_fast_path_version_provenance(decision=None)
            },
        ),
    )

async def _run_governed_graph_once(
    request: ChatRequest,
    *,
    current_user: RequestUser,
    pre_gate_classification: str | None = None,
) -> tuple[GraphState, GovernedSessionState]:
    turn_result = await run_governed_graph_turn(
        request=request,
        current_user=current_user,
        pre_gate_classification=pre_gate_classification,
    )
    return turn_result.result_state, turn_result.persisted_state

async def _run_governed_chat_response(
    request: ChatRequest,
    *,
    current_user: RequestUser,
    pre_gate_classification: str | None = None,
) -> ChatResponse:
    result_state, persisted_state = await _run_governed_graph_once(
        request,
        current_user=current_user,
        pre_gate_classification=pre_gate_classification,
    )
    context = _build_governed_reply_context(
        result_state=result_state,
        persisted_state=persisted_state,
    )
    visible_reply = _governed_composer_visible_answer(result_state)
    if visible_reply is None:
        visible_reply = await collect_governed_visible_reply(
            response_class=context.response_class,
            turn_context=context.turn_context,
            fallback_text=context.deterministic_reply,
            latest_user_message=request.message,
        )

    if visible_reply:
        updated_state = _with_governed_conversation_turn(
            persisted_state,
            role="assistant",
            content=visible_reply,
        )
        case_event = build_assistant_delta_event(
            case_id=str(request.session_id or "default"),
            turn_index=int(getattr(result_state, "user_turn_index", 0) or result_state.analysis_cycle or 0),
            assistant_message=visible_reply,
            delta=context.proposed_case_delta,
            persistence_marker=persisted_state.persistence_marker,
        )
        updated_state = _with_case_event(updated_state, event=case_event)
        await _persist_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            state=updated_state,
            pre_gate_classification=pre_gate_classification,
        )

    return ChatResponse(
        session_id=request.session_id,
        **_assemble_governed_stream_payload(
            context=context,
            visible_reply=visible_reply,
        ),
    )

async def _chat_response_from_fast_response(
    *,
    request: ChatRequest,
    fast_response: Any,
) -> ChatResponse:
    from app.agent.api.utils import _fast_response_run_meta # noqa: PLC0415
    return ChatResponse(
        session_id=request.session_id,
        **build_public_response_core(
            reply=fast_response.content,
            structured_state=None,
            policy_path="conversation",
            run_meta=_fast_response_run_meta(fast_response),
        ),
    )


async def _chat_response_from_knowledge_response(
    *,
    request: ChatRequest,
    knowledge_response: Any,
) -> ChatResponse:
    from app.agent.api.utils import _knowledge_response_run_meta # noqa: PLC0415
    payload = build_public_response_core(
        reply=knowledge_response.content,
        structured_state=None,
        policy_path="knowledge",
        run_meta=_knowledge_response_run_meta(knowledge_response),
    )
    answer_markdown = str(getattr(knowledge_response, "answer_markdown", "") or "").strip()
    if answer_markdown:
        payload["answer_markdown"] = answer_markdown
    return ChatResponse(
        session_id=request.session_id,
        **payload,
    )


async def chat_endpoint(request: ChatRequest, current_user: RequestUser):
    early_guard_reply = _guard_unsafe_user_instruction(
        latest_user_message=request.message,
        turn_context=None,
    )
    if early_guard_reply is not None:
        return ChatResponse(
            session_id=request.session_id,
            **build_public_response_core(
                reply=early_guard_reply,
                structured_state=None,
                policy_path="governed_guard",
                run_meta={"guard": "unsafe_forced_case_claim"},
            ),
        )

    dispatch = await _resolve_runtime_dispatch(request, current_user=current_user)
    if dispatch.fast_response is not None:
        return await _chat_response_from_fast_response(
            request=request,
            fast_response=dispatch.fast_response,
        )
    if dispatch.knowledge_response is not None:
        return await _chat_response_from_knowledge_response(
            request=request,
            knowledge_response=dispatch.knowledge_response,
        )

    if _is_light_runtime_mode(dispatch.runtime_mode):
        return await _run_light_chat_response(
            message=request.message,
            request=request,
            current_user=current_user,
            mode=dispatch.runtime_mode,
            governed_state_override=dispatch.governed_state,
            direct_reply=dispatch.direct_reply,
        )

    if dispatch.runtime_mode == "GOVERNED":
        _knowledge_override_json = classify_message_as_knowledge_override(request.message)
        if _knowledge_override_json is not None:
            _override_mode_json: Literal["CONVERSATION", "EXPLORATION"] = (
                "CONVERSATION" if _knowledge_override_json == "conversational_answer" else "EXPLORATION"
            )
            return await _run_light_chat_response(
                message=request.message,
                request=request,
                current_user=current_user,
                mode=_override_mode_json,
                governed_state_override=dispatch.governed_state,
            )
        _log.debug(
            "[runtime_authority] json session=%s authority=governed_graph reason=%s",
            request.session_id,
            dispatch.gate_reason,
        )
        return await _run_governed_chat_response(
            request,
            current_user=current_user,
            pre_gate_classification=dispatch.pre_gate_classification,
        )

    _log.warning(
        "[runtime_authority] json session=%s unexpected runtime_mode=%s — fail-closed to governed",
        request.session_id,
        dispatch.runtime_mode,
    )
    return await _run_governed_chat_response(
        request,
        current_user=current_user,
        pre_gate_classification=dispatch.pre_gate_classification,
    )

@router.post("/chat", response_model=ChatResponse)
async def chat_route(request: ChatRequest, current_user: RequestUser = Depends(get_current_request_user)):
    return await chat_endpoint(request, current_user=current_user)

@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest, current_user: RequestUser = Depends(get_current_request_user)):
    return StreamingResponse(event_generator(request, current_user=current_user), media_type="text/event-stream")
