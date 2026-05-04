import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.api.models import ChatRequest, ChatResponse, build_public_response_core
from app.agent.state.models import GovernedSessionState
from app.agent.graph import GraphState
from app.agent.runtime.answer_trace import build_answer_trace, with_answer_trace
from app.agent.runtime.final_answer_layer import (
    FinalAnswerEnvelope,
    answer_mode_for_fast_classification,
    apply_final_answer_layer,
)
from app.agent.runtime.user_facing_reply import _guard_unsafe_user_instruction
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
)
from app.agent.domain.case_delta import build_assistant_delta_event
from app.agent.api.streaming import event_generator, _build_fast_path_version_provenance
from app.agent.api.dispatch import _resolve_runtime_dispatch
from app.agent.api.knowledge_override import build_case_side_knowledge_response
from app.agent.communication.active_case_process_answer import (
    build_active_case_process_answer,
)

_log = logging.getLogger(__name__)



def _v7_dispatch_answer_mode(dispatch: Any) -> str | None:
    decision = getattr(dispatch, "turn_decision", None)
    if decision is None:
        return None
    mode = getattr(decision, "answer_mode", None)
    return str(getattr(mode, "value", mode) or "") or None


def _is_v7_active_case_side_question(dispatch: Any) -> bool:
    return _v7_dispatch_answer_mode(dispatch) == "active_case_side_question"


def _is_v7_active_case_process_question(dispatch: Any) -> bool:
    return _v7_dispatch_answer_mode(dispatch) == "active_case_process_question"


def _process_answer_trace(*, result: Any, decision: Any) -> dict[str, Any]:
    mutation_policy = str(getattr(decision, "mutation_policy", "forbidden") or "forbidden")
    resume_decision = getattr(result, "resume_decision", None)
    resume_trace = (
        resume_decision.as_trace()
        if hasattr(resume_decision, "as_trace")
        else {}
    )
    resume_strategy = str(resume_trace.get("resume_strategy") or getattr(decision, "resume_strategy", "") or "")
    trace = build_answer_trace(
        reply_source="governed_output_contract",
        answer_markdown_source=(
            "governed_composer"
            if getattr(result, "builder_succeeded", False)
            else "deterministic_fallback"
        ),
        final_visible_source="answer_markdown",
        composer_attempted=bool(getattr(result, "builder_attempted", False)),
        composer_succeeded=bool(getattr(result, "builder_succeeded", False)),
        fallback_reason=getattr(result, "fallback_reason", None),
    )
    trace.update(
        {
            "answer_mode": "active_case_process_question",
            "mutation_policy": mutation_policy,
            "resume_strategy": resume_strategy,
            "resume_reevaluation_attempted": True,
            "resume_reason": resume_trace.get("resume_reason"),
            "resume_target_field": resume_trace.get("resume_target_field"),
            "next_runtime_action": resume_trace.get("next_runtime_action"),
            "process_answer_builder_attempted": bool(getattr(result, "builder_attempted", False)),
            "process_answer_builder_succeeded": bool(getattr(result, "builder_succeeded", False)),
            "pending_question_restored": bool(
                resume_trace.get("pending_question_restored", getattr(result, "pending_question_restored", False))
            ),
            "governed_graph_bypassed": True,
            "latest_user_question_answered": True,
            "slot_answer_detected": bool(resume_trace.get("slot_answer_detected", False)),
            "case_delta_allowed": bool(resume_trace.get("case_delta_allowed", False)),
            "governed_graph_allowed": bool(resume_trace.get("governed_graph_allowed", False)),
        }
    )
    if resume_trace.get("detected_slot_field"):
        trace["detected_slot_field"] = resume_trace.get("detected_slot_field")
    return trace


async def _build_active_case_process_payload(
    *,
    message: str,
    governed_state: GovernedSessionState | None,
    decision: Any,
) -> dict[str, Any]:
    result = await build_active_case_process_answer(
        latest_user_message=message,
        governed_state=governed_state,
        turn_decision=decision,
    )
    answer_trace = _process_answer_trace(result=result, decision=decision)
    payload = build_public_response_core(
        reply=result.deterministic_fallback,
        structured_state=None,
        policy_path="governed_process",
        run_meta=with_answer_trace(None, answer_trace),
    )
    payload["answer_markdown"] = result.answer_markdown
    payload = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="governed_process",
            answer_mode="active_case_process_question",
            deterministic_fallback_reply=result.deterministic_fallback,
            existing_answer_markdown=payload.get("answer_markdown"),
            existing_answer_markdown_source=answer_trace.get("answer_markdown_source"),
            existing_reply_source=answer_trace.get("reply_source"),
            composer_tier="tier_a",
            fallback_reason=answer_trace.get("fallback_reason"),
        ),
    )
    payload["assistant_message"] = str(
        payload.get("answer_markdown") or payload.get("reply") or ""
    ).strip()
    payload["type"] = "state_update"
    return payload


async def _persist_active_case_process_turn(
    *,
    request: ChatRequest,
    current_user: RequestUser,
    governed_state: GovernedSessionState | None,
    assistant_message: str,
    pre_gate_classification: str | None,
) -> None:
    if governed_state is None or not request.session_id or not assistant_message:
        return
    updated_state = _with_governed_conversation_turn(
        governed_state,
        role="user",
        content=request.message,
    )
    updated_state = _with_governed_conversation_turn(
        updated_state,
        role="assistant",
        content=assistant_message,
    )
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=request.session_id,
        state=updated_state,
        pre_gate_classification=pre_gate_classification,
    )

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
            run_meta=with_answer_trace(
                {
                    "version_provenance": _build_fast_path_version_provenance(decision=None)
                },
                build_answer_trace(
                    reply_source="light_conversation",
                    answer_markdown_source="light_conversation",
                    final_visible_source="answer_markdown",
                ),
            ),
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
    payload = _assemble_governed_stream_payload(context=context)
    assistant_message = str(
        payload.get("assistant_message")
        or payload.get("answer_markdown")
        or payload.get("reply")
        or ""
    ).strip()
    if assistant_message:
        updated_state = _with_governed_conversation_turn(
            persisted_state,
            role="assistant",
            content=assistant_message,
        )
        case_event = build_assistant_delta_event(
            case_id=str(request.session_id or "default"),
            turn_index=int(getattr(result_state, "user_turn_index", 0) or result_state.analysis_cycle or 0),
            assistant_message=assistant_message,
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
        **payload,
    )

async def _chat_response_from_fast_response(
    *,
    request: ChatRequest,
    fast_response: Any,
) -> ChatResponse:
    from app.agent.api.utils import _fast_response_run_meta # noqa: PLC0415

    payload = build_public_response_core(
        reply=fast_response.content,
        structured_state=None,
        policy_path="conversation",
        run_meta=_fast_response_run_meta(fast_response),
    )
    payload = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="fast",
            answer_mode=answer_mode_for_fast_classification(
                getattr(fast_response, "source_classification", None)
            ),
            deterministic_fallback_reply=fast_response.content,
            existing_answer_markdown=payload.get("answer_markdown"),
            existing_answer_markdown_source="fast_responder",
            existing_reply_source="fast_responder",
            composer_tier="tier_a",
        ),
    )
    return ChatResponse(session_id=request.session_id, **payload)


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
    answer_trace = getattr(knowledge_response, "answer_trace", None)
    answer_markdown_source = (
        answer_trace.get("answer_markdown_source")
        if isinstance(answer_trace, dict)
        else "knowledge_service"
    )
    composer_attempted = bool(
        answer_trace.get("composer_attempted") if isinstance(answer_trace, dict) else False
    )
    payload = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="knowledge",
            answer_mode="knowledge",
            deterministic_fallback_reply=knowledge_response.content,
            existing_answer_markdown=payload.get("answer_markdown"),
            existing_answer_markdown_source=answer_markdown_source,
            existing_reply_source="knowledge_service",
            composer_tier="tier_b" if composer_attempted else "tier_a",
        ),
    )
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
                run_meta=with_answer_trace(
                    {"guard": "unsafe_forced_case_claim"},
                    build_answer_trace(
                        reply_source="api_guard",
                        answer_markdown_source="deterministic_fallback",
                        final_visible_source="answer_markdown",
                        fallback_reason="unsafe_user_instruction_guard",
                    ),
                ),
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
        if _is_v7_active_case_process_question(dispatch):
            payload = await _build_active_case_process_payload(
                message=request.message,
                governed_state=dispatch.governed_state,
                decision=dispatch.turn_decision,
            )
            await _persist_active_case_process_turn(
                request=request,
                current_user=current_user,
                governed_state=dispatch.governed_state,
                assistant_message=str(payload.get("assistant_message") or ""),
                pre_gate_classification=dispatch.pre_gate_classification,
            )
            return ChatResponse(session_id=request.session_id, **payload)
        if _is_v7_active_case_side_question(dispatch):
            knowledge_response = await build_case_side_knowledge_response(
                message=request.message,
                override_class="exploration_answer",
                conversation_route=dispatch.conversation_route,
                governed_state=dispatch.governed_state,
            )
            return await _chat_response_from_knowledge_response(
                request=request,
                knowledge_response=knowledge_response,
            )
        _knowledge_override_json = classify_message_as_knowledge_override(request.message)
        if _knowledge_override_json is not None:
            knowledge_response = await build_case_side_knowledge_response(
                message=request.message,
                override_class=_knowledge_override_json,
                conversation_route=dispatch.conversation_route,
                governed_state=dispatch.governed_state,
            )
            return await _chat_response_from_knowledge_response(
                request=request,
                knowledge_response=knowledge_response,
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
