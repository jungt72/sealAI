import asyncio
import json
import logging
import os
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.api.models import ChatRequest, ChatResponse, build_public_response_core
from app.agent.state.models import GovernedSessionState
from app.agent.graph import GraphState
from app.agent.runtime.answer_trace import (
    build_answer_trace,
    safe_fallback_reason,
    with_answer_trace,
)
from app.agent.runtime.final_answer_layer import (
    FinalAnswerEnvelope,
    answer_mode_for_fast_classification,
    apply_final_answer_layer,
)
from app.agent.runtime.user_facing_reply import (
    collect_unsafe_user_instruction_reply_with_trace,
)
from app.agent.api.deps import (
    _is_light_runtime_mode,
    get_current_request_user,
    RequestUser,
)
from app.agent.api.utils import (
    _with_case_event,
    _with_governed_conversation_turn,
    _light_case_active,
    _with_light_route_progress,
    _light_structured_state,
)
from app.agent.api.loaders import (
    _persist_live_governed_state,
    _build_light_runtime_context,
    persist_mobile_triage_pending_question,
    persist_visible_governed_turn,
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
from app.agent.v92.runtime_contract import (
    apply_async_adversarial_review_to_payload,
    apply_v92_contracts_to_payload,
)
from app.agent.communication.active_case_process_answer import (
    build_active_case_process_answer,
)
from app.agent.communication.active_case_resume import (
    reevaluate_active_case_resume,
)
from app.agent.communication.active_case_side_claim_policy import (
    build_active_case_side_speakable_facts,
    build_active_case_side_evidence_context,
    enrich_active_case_side_answer_with_evidence,
    enforce_active_case_side_claim_policy,
)
from app.agent.communication.templates import render_communication_template
from app.agent.communication.v7_contracts import (
    AnswerMode,
    RuntimeAction,
    RuntimeActionType,
    RuntimeAnswerBuilder,
    build_runtime_action_from_turn_decision,
)
from app.observability.langsmith import traceable
from app.observability.sealai_quality import emit_quality_trace
from app.services.rwdr_mvp_brief import build_rwdr_p0_leakage_guidance

_log = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "y", "on", "enabled"}
_OPEN_INVITE_FACT_FIELDS = {
    "medium",
    "pressure_bar",
    "pressure_at_seal_bar",
    "pressure_delta_bar",
    "temperature_c",
    "shaft_diameter_mm",
    "speed_rpm",
    "sealing_type",
    "motion_type",
    "installation",
    "application",
    "geometry_context",
    "failure_mode",
}
_OPEN_CASE_ACK_RE = re.compile(
    r"^\s*(?:prima+|super|klasse|top|perfekt|passt|sehr\s+gut|gut|"
    r"gern(?:e)?|klar|ok(?:ay)?|los\s+geht'?s|"
    r"lass\s+uns\s+(?:loslegen|starten)|ich\s+bin\s+(?:auch\s+)?gespannt)"
    r"[\s.!?]*$",
    re.IGNORECASE | re.UNICODE,
)
_ACTIVE_CASE_SIDE_GROUNDED_LIMIT = 6_000
_ACTIVE_CASE_SIDE_MESSAGE_LIMIT = 900
_ACTIVE_CASE_SIDE_CONTEXT_MESSAGES = 8
_ACTIVE_CASE_SIDE_FACT_LIMIT = 24
_ACTIVE_CASE_SIDE_OPEN_POINT_LIMIT = 16


def _active_case_side_answer_composer_enabled() -> bool:
    return (
        os.getenv("SEALAI_ENABLE_ACTIVE_CASE_SIDE_ANSWER_COMPOSER", "true")
        .strip()
        .lower()
        in _TRUE_VALUES
    )


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


def _runtime_action_blocked_graph_payload(runtime_action: Any | None) -> dict[str, Any]:
    reply = render_communication_template(
        "runtime_action_blocked",
        fallback=(
            "Ich moechte das sauber einordnen. Bitte formuliere die naechste "
            "technische Angabe oder Frage noch einmal; wenn es nur um Wissen geht, "
            "beantworte ich es allgemein ohne Fallanlage."
        ),
    )
    trace = build_answer_trace(
        reply_source="runtime_action_guard",
        answer_markdown_source="deterministic_fallback",
        final_visible_source="answer_markdown",
        fallback_reason="runtime_action_disallowed_graph_invocation",
    )
    trace.update(_runtime_action_trace(runtime_action))
    payload = build_public_response_core(
        reply=reply,
        structured_state=None,
        policy_path="runtime_action_guard",
        run_meta=with_answer_trace(None, trace),
    )
    payload = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="runtime_action_guard",
            answer_mode=str(
                trace.get("runtime_action_answer_mode") or "runtime_action_guard"
            ),
            deterministic_fallback_reply=reply,
            existing_answer_markdown=payload.get("answer_markdown"),
            existing_answer_markdown_source=trace.get("answer_markdown_source"),
            existing_reply_source=trace.get("reply_source"),
            composer_tier="fallback",
            fallback_reason=trace.get("fallback_reason"),
        ),
    )
    payload["type"] = "state_update"
    return payload


def _build_rfq_readiness_payload(
    *,
    answer_markdown: str,
    projection: dict[str, Any] | None = None,
    runtime_action: Any | None = None,
) -> dict[str, Any]:
    answer = str(answer_markdown or "").strip()
    projection_payload = dict(projection or {})
    trace = build_answer_trace(
        reply_source="governed_output_contract",
        answer_markdown_source="deterministic_fallback",
        final_visible_source="answer_markdown",
    )
    trace.update(
        {
            "answer_mode": "rfq_readiness",
            "mutation_policy": "forbidden",
            "rfq_readiness_answer_builder": "deterministic_rfq_readiness_v1",
            "governed_graph_bypassed": True,
            "case_delta_allowed": False,
            "latest_user_question_answered": True,
        }
    )
    if projection_payload:
        trace.update(
            {
                "rfq_readiness_projection_built": True,
                "manufacturer_review_ready": bool(
                    projection_payload.get("manufacturer_review_ready", False)
                ),
                "rfq_basis_ready": bool(
                    projection_payload.get("rfq_basis_ready", False)
                ),
                "known_missing_fields_count": len(
                    projection_payload.get("known_missing_fields") or []
                ),
                "open_points_count": len(projection_payload.get("open_points") or []),
                "blocking_reasons_count": len(
                    projection_payload.get("blocking_reasons") or []
                ),
                "preview_available": bool(
                    projection_payload.get("preview_available", False)
                ),
                "preview_possible": bool(
                    projection_payload.get("preview_possible", False)
                ),
                "preview_requires_explicit_endpoint": bool(
                    projection_payload.get("preview_requires_explicit_endpoint", True)
                ),
                "preview_action_available": bool(
                    projection_payload.get("preview_action_available", False)
                ),
                "preview_action_name": projection_payload.get("preview_action_name"),
                "preview_endpoint": projection_payload.get("preview_endpoint"),
                "preview_creation_requires_explicit_user_intent": bool(
                    projection_payload.get(
                        "preview_creation_requires_explicit_user_intent", True
                    )
                ),
                "preview_export_requires_consent": bool(
                    projection_payload.get("preview_export_requires_consent", True)
                ),
                "preview_service_boundary": projection_payload.get(
                    "preview_service_boundary"
                ),
                "preview_blocking_reason": projection_payload.get(
                    "preview_blocking_reason"
                ),
                "projection_version": projection_payload.get("projection_version"),
            }
        )
    trace.update(_runtime_action_trace(runtime_action))
    payload = build_public_response_core(
        reply=answer,
        structured_state=None,
        policy_path="rfq_readiness",
        run_meta=with_answer_trace(None, trace),
    )
    payload["answer_markdown"] = answer
    payload = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="rfq_readiness",
            answer_mode="rfq_readiness",
            deterministic_fallback_reply=answer,
            existing_answer_markdown=payload.get("answer_markdown"),
            existing_answer_markdown_source=trace.get("answer_markdown_source"),
            existing_reply_source=trace.get("reply_source"),
            composer_tier="tier_a",
        ),
    )
    payload["assistant_message"] = str(
        payload.get("answer_markdown") or payload.get("reply") or ""
    ).strip()
    payload["rfq_ready"] = bool(
        projection_payload.get("rfq_basis_ready", trace.get("rfq_ready", False))
    )
    if projection_payload:
        payload["rfq_readiness_projection"] = projection_payload
        payload["qualified_action_gate"] = {
            "consent_required": bool(projection_payload.get("consent_required", True)),
            "dispatch_allowed": False,
            "external_contact_allowed": False,
            "preview_available": bool(
                projection_payload.get("preview_available", False)
            ),
            "preview_possible": bool(projection_payload.get("preview_possible", False)),
            "preview_action_available": bool(
                projection_payload.get("preview_action_available", False)
            ),
            "preview_action_name": projection_payload.get("preview_action_name"),
            "preview_endpoint": projection_payload.get("preview_endpoint"),
            "preview_creation_requires_explicit_user_intent": bool(
                projection_payload.get(
                    "preview_creation_requires_explicit_user_intent", True
                )
            ),
            "preview_export_requires_consent": bool(
                projection_payload.get("preview_export_requires_consent", True)
            ),
        }
        payload["result_contract"] = {
            "artifact_type": "rfq_readiness_projection",
            "projection_version": projection_payload.get("projection_version"),
            "manufacturer_review_ready": bool(
                projection_payload.get("manufacturer_review_ready", False)
            ),
            "no_external_dispatch": True,
            "preview_action_name": projection_payload.get("preview_action_name"),
            "preview_endpoint": projection_payload.get("preview_endpoint"),
            "preview_service_boundary": projection_payload.get(
                "preview_service_boundary"
            ),
        }
    payload["type"] = "state_update"
    return payload


async def _chat_response_from_rfq_readiness(
    *,
    request: ChatRequest,
    answer_markdown: str,
    projection: dict[str, Any] | None = None,
    runtime_action: Any | None = None,
    state: Any | None = None,
) -> ChatResponse:
    payload = _build_rfq_readiness_payload(
        answer_markdown=answer_markdown,
        projection=projection,
        runtime_action=runtime_action,
    )
    payload = apply_v92_contracts_to_payload(
        payload,
        session_id=str(request.session_id or "default"),
        user_message=request.message,
        state=state,
        route_hint="rfq_readiness" if state is not None else "knowledge_general",
        case_id=str(request.session_id or "default")
        if request.session_id and state is not None
        else None,
    )
    return ChatResponse(
        session_id=str(request.session_id or "default"),
        **payload,
    )


def _process_answer_trace(
    *,
    result: Any,
    decision: Any,
    runtime_action: Any | None = None,
) -> dict[str, Any]:
    mutation_policy = str(
        getattr(decision, "mutation_policy", "forbidden") or "forbidden"
    )
    resume_decision = getattr(result, "resume_decision", None)
    resume_trace = (
        resume_decision.as_trace() if hasattr(resume_decision, "as_trace") else {}
    )
    resume_strategy = str(
        resume_trace.get("resume_strategy")
        or getattr(decision, "resume_strategy", "")
        or ""
    )
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
            "process_answer_builder_attempted": bool(
                getattr(result, "builder_attempted", False)
            ),
            "process_answer_builder_succeeded": bool(
                getattr(result, "builder_succeeded", False)
            ),
            "pending_question_restored": bool(
                resume_trace.get(
                    "pending_question_restored",
                    getattr(result, "pending_question_restored", False),
                )
            ),
            "governed_graph_bypassed": True,
            "latest_user_question_answered": True,
            "slot_answer_detected": bool(
                resume_trace.get("slot_answer_detected", False)
            ),
            "case_delta_allowed": bool(resume_trace.get("case_delta_allowed", False)),
            "governed_graph_allowed": bool(
                resume_trace.get("governed_graph_allowed", False)
            ),
        }
    )
    if resume_trace.get("detected_slot_field"):
        trace["detected_slot_field"] = resume_trace.get("detected_slot_field")
    trace.update(_runtime_action_trace(runtime_action))
    return trace


def _side_answer_trace(
    *,
    knowledge_response: Any,
    resume_decision: Any,
    decision: Any,
    claim_policy_result: Any,
    evidence_context: Any,
    evidence_used_in_answer: bool,
    composer_attempted: bool = False,
    composer_succeeded: bool = False,
    fallback_reason: str | None = None,
    runtime_action: Any | None = None,
) -> dict[str, Any]:
    existing_trace = getattr(knowledge_response, "answer_trace", None)
    trace = (
        dict(existing_trace)
        if isinstance(existing_trace, dict)
        else build_answer_trace(
            reply_source="knowledge_service",
            answer_markdown_source="knowledge_service",
            final_visible_source="answer_markdown",
        )
    )
    resume_trace = (
        resume_decision.as_trace() if hasattr(resume_decision, "as_trace") else {}
    )
    trace.update(
        {
            "answer_mode": "active_case_side_question",
            "mutation_policy": str(
                getattr(decision, "mutation_policy", "forbidden") or "forbidden"
            ),
            "resume_strategy": str(
                resume_trace.get("resume_strategy")
                or getattr(decision, "resume_strategy", "")
                or ""
            ),
            "resume_reevaluation_attempted": True,
            "resume_reason": resume_trace.get("resume_reason"),
            "resume_target_field": resume_trace.get("resume_target_field"),
            "next_runtime_action": resume_trace.get("next_runtime_action"),
            "pending_question_restored": bool(
                resume_trace.get("pending_question_restored", False)
            ),
            "governed_graph_bypassed": True,
            "latest_user_question_answered": True,
            "slot_answer_detected": bool(
                resume_trace.get("slot_answer_detected", False)
            ),
            "case_delta_allowed": bool(resume_trace.get("case_delta_allowed", False)),
            "governed_graph_allowed": bool(
                resume_trace.get("governed_graph_allowed", False)
            ),
        }
    )
    if resume_trace.get("detected_slot_field"):
        trace["detected_slot_field"] = resume_trace.get("detected_slot_field")
    if hasattr(claim_policy_result, "as_trace"):
        trace.update(claim_policy_result.as_trace())
    if hasattr(evidence_context, "as_trace"):
        trace.update(evidence_context.as_trace())
    trace["evidence_used_in_answer"] = bool(evidence_used_in_answer)
    trace["composer_attempted"] = bool(composer_attempted)
    trace["composer_succeeded"] = bool(composer_succeeded)
    trace["fallback_reason"] = safe_fallback_reason(fallback_reason)
    if composer_succeeded:
        trace["reply_source"] = "governed_output_contract"
        trace["answer_markdown_source"] = "governed_composer"
    trace.update(_runtime_action_trace(runtime_action))
    return trace


def _side_answer_with_resume(answer_markdown: str, resume_decision: Any) -> str:
    base = str(answer_markdown or "").strip()
    if not base:
        return render_communication_template(
            "side_answer_resume",
            {"mode": "empty_base", "base": ""},
            fallback="Ich beantworte die Nebenfrage allgemein und ohne technische Freigabe.",
        )

    if bool(getattr(resume_decision, "slot_answer_detected", False)):
        detected_value = str(
            getattr(resume_decision, "detected_slot_value", "") or ""
        ).strip()
        detected_field = str(
            getattr(resume_decision, "detected_slot_field", "") or ""
        ).strip()
        if detected_value and detected_field == "medium":
            # Dedup seam (T5.1): if the base answer already names the detected
            # value, one acknowledgment is enough — do not append a second seam
            # restating the same fact (mirrors the resume-path guard below at :550).
            if detected_value.casefold() in base.casefold():
                return base
            return render_communication_template(
                "side_answer_resume",
                {
                    "mode": "medium_candidate",
                    "base": base,
                    "detected_value": detected_value,
                },
                fallback=(
                    f"{base}\n\n"
                    f"Ich habe {detected_value} als moegliche Angabe zum Medium erkannt. "
                    "Die technische Uebernahme laeuft nicht ueber diese Erklaerung, "
                    "sondern ueber den validierten Fallstatus."
                ),
            )
        return render_communication_template(
            "side_answer_resume",
            {"mode": "technical_candidate", "base": base},
            fallback=(
                f"{base}\n\n"
                "Ich habe in deiner Nachricht eine moegliche technische Angabe erkannt. "
                "Die Erklaerung selbst bestaetigt diesen Wert nicht als technische Wahrheit."
            ),
        )

    target_question = str(
        getattr(resume_decision, "resume_target_question", "") or ""
    ).strip()
    next_action = str(getattr(resume_decision, "next_runtime_action", "") or "")
    if target_question and next_action in {
        "continue_pending_question",
        "ask_reprioritized_question",
    }:
        if target_question.casefold() not in base.casefold():
            return render_communication_template(
                "side_answer_resume",
                {
                    "mode": "resume_question",
                    "base": base,
                    "target_question": target_question,
                },
                fallback=f"{base}\n\n{target_question}",
            )
    return base


def _active_case_context_payload(
    governed_state: GovernedSessionState | None,
) -> dict[str, Any]:
    if governed_state is None:
        return {
            "known_facts": [],
            "open_points": [],
            "recent_messages": [],
            "conversation_message_count": 0,
            "context_policy": "bounded_active_case_side_context",
        }
    assertions = (
        getattr(getattr(governed_state, "asserted", None), "assertions", {}) or {}
    )
    known_facts: list[dict[str, str]] = []
    for field_name, claim in list(assertions.items())[:_ACTIVE_CASE_SIDE_FACT_LIMIT]:
        value = getattr(claim, "asserted_value", None)
        if value is None or str(value).strip() == "":
            continue
        known_facts.append(
            {
                "field": str(field_name),
                "value": _bounded_prompt_text(value, limit=240),
            }
        )
    open_points = [
        str(field)
        for field in list(
            getattr(getattr(governed_state, "asserted", None), "blocking_unknowns", [])
            or []
        )[:_ACTIVE_CASE_SIDE_OPEN_POINT_LIMIT]
        if str(field).strip()
    ]
    all_messages = list(getattr(governed_state, "conversation_messages", []) or [])
    conversation_messages = []
    for message in all_messages[-_ACTIVE_CASE_SIDE_CONTEXT_MESSAGES:]:
        content = _bounded_prompt_text(
            getattr(message, "content", ""),
            limit=_ACTIVE_CASE_SIDE_MESSAGE_LIMIT,
        )
        if not content.strip():
            continue
        conversation_messages.append(
            {
                "role": str(getattr(message, "role", "") or ""),
                "content": content,
            }
        )
    pending = getattr(governed_state, "pending_question", None)
    return {
        "known_facts": known_facts,
        "open_points": open_points,
        "recent_messages": conversation_messages,
        "conversation_message_count": len(all_messages),
        "context_policy": "bounded_active_case_side_context",
        "pending_question": {
            "target_field": str(getattr(pending, "target_field", "") or ""),
            "question_text": _bounded_prompt_text(
                getattr(pending, "question_text", ""),
                limit=500,
            ),
        }
        if pending is not None
        else None,
    }


def _bounded_prompt_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()} ... [gekürzt: {len(text) - limit} Zeichen]"


async def _compose_active_case_side_answer_with_llm(
    *,
    message: str,
    grounded_answer: str,
    governed_state: GovernedSessionState | None,
    resume_decision: Any,
) -> str:
    from app.llm.factory import get_async_llm  # noqa: PLC0415

    client, model = get_async_llm("governed_answer_composer")
    resume_trace = (
        resume_decision.as_trace() if hasattr(resume_decision, "as_trace") else {}
    )
    payload = {
        "latest_user_message": message,
        "grounded_answer": _bounded_prompt_text(
            grounded_answer,
            limit=_ACTIVE_CASE_SIDE_GROUNDED_LIMIT,
        ),
        "active_case_context": _active_case_context_payload(governed_state),
        "resume_trace": resume_trace,
        "instructions": [
            "Answer the user's latest side question first.",
            "Use grounded_answer as the technical basis; do not invent stronger claims.",
            "Briefly connect to the active sealing case context when useful.",
            "Do not automatically repeat an old slot question such as 'Welches Medium'.",
            "If a next step is useful, phrase it naturally as an optional continuation, not as a blunt intake fallback.",
            "Ask at most one question.",
            "Do not claim final suitability, manufacturer approval, compliance approval, or final release.",
            (
                "Do not use positive suitability wording such as 'ist geeignet', "
                "'geeignet fuer', 'gut geeignet' or 'gute Eignung'."
            ),
        ],
    }
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": render_communication_template(
                    "active_case_side_answer_system",
                    fallback=(
                        "You are SealAI's senior sealing-engineering communication layer. "
                        "You produce the final visible German answer for a side question inside "
                        "an active sealing case. Be warm, precise, human, and technically careful. "
                        "Return JSON with key answer_markdown only."
                    ),
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, default=str),
            },
        ],
        temperature=0.25,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content if response.choices else ""
    data = json.loads(str(raw or "{}"))
    answer = str(data.get("answer_markdown") or "").strip()
    if not answer:
        raise ValueError("empty_active_case_side_answer")
    resume_trace = (
        resume_decision.as_trace() if hasattr(resume_decision, "as_trace") else {}
    )
    target_question = str(resume_trace.get("resume_target_question") or "").strip()
    target_field = str(resume_trace.get("resume_target_field") or "").strip()
    answer = _strip_pending_question_leak(
        answer,
        target_question=target_question,
        target_field=target_field,
    )
    if not answer:
        raise ValueError("empty_active_case_side_answer_after_pending_question_strip")
    return answer


def _strip_pending_question_leak(
    answer: str,
    *,
    target_question: str,
    target_field: str,
) -> str:
    text = str(answer or "").strip()
    if not text:
        return ""
    if target_question:
        text = text.replace(target_question, "").strip()
    if target_field == "medium" and "welches medium" in text.casefold():
        parts = re.split(r"(?<=[.!?])\s+|\n+", text)
        parts = [
            part.strip()
            for part in parts
            if part.strip() and "welches medium" not in part.casefold()
        ]
        text = " ".join(parts).strip()
    return re.sub(r"\s{2,}", " ", text).strip()


def _should_bypass_active_case_side_composer(
    *,
    message: str,
    grounded_answer: str,
    claim_policy_result: Any | None,
) -> bool:
    """Avoid a second wording LLM when the knowledge answer is already final-grade."""

    answer = str(grounded_answer or "").strip()
    if len(answer) < int(os.getenv("SEALAI_ACTIVE_CASE_SIDE_BYPASS_MIN_CHARS", "700")):
        return False
    policy = str(getattr(claim_policy_result, "claim_policy_result", "") or "")
    if policy not in {"passed", "rewritten"}:
        return False
    if bool(getattr(claim_policy_result, "answer_safety_fallback_used", False)):
        return False
    if getattr(claim_policy_result, "forbidden_claims_detected", ()):
        return False
    normalized = f" {str(message or '').casefold()} "
    comparison_markers = (
        "vergleich",
        "vergleiche",
        "vergleicht",
        "vergeliche",
        "vegeliche",
        "unterschied",
        " vs ",
        " versus ",
        "gegenüber",
        "gegenueber",
    )
    if any(marker in normalized for marker in comparison_markers):
        return True
    material_mentions = sum(
        1
        for token in (
            "ptfe",
            "peek",
            "pom",
            "nbr",
            "fkm",
            "ffkm",
            "epdm",
            "hnbr",
            "vmq",
        )
        if token in answer.casefold()
    )
    return material_mentions >= 2 and any(
        marker in answer.casefold()
        for marker in ("vergleich", "unterschied", "gegenueber", "gegenüber")
    )


async def _compose_active_case_side_answer(
    *,
    message: str,
    grounded_answer: str,
    governed_state: GovernedSessionState | None,
    resume_decision: Any,
    claim_policy_result: Any | None = None,
) -> tuple[str, bool, bool, str | None]:
    if not _active_case_side_answer_composer_enabled():
        return (
            _side_answer_with_resume(grounded_answer, resume_decision),
            False,
            False,
            "composer_disabled",
        )

    if _should_bypass_active_case_side_composer(
        message=message,
        grounded_answer=grounded_answer,
        claim_policy_result=claim_policy_result,
    ):
        return (
            _side_answer_with_resume(grounded_answer, resume_decision),
            False,
            False,
            "composer_bypassed_guarded_grounded_answer",
        )

    try:
        answer = await asyncio.wait_for(
            _compose_active_case_side_answer_with_llm(
                message=message,
                grounded_answer=grounded_answer,
                governed_state=governed_state,
                resume_decision=resume_decision,
            ),
            timeout=float(os.getenv("SEALAI_ACTIVE_CASE_SIDE_ANSWER_TIMEOUT_S", "8.0")),
        )
        resume_trace = (
            resume_decision.as_trace() if hasattr(resume_decision, "as_trace") else {}
        )
        answer = _strip_pending_question_leak(
            answer,
            target_question=str(
                resume_trace.get("resume_target_question") or ""
            ).strip(),
            target_field=str(resume_trace.get("resume_target_field") or "").strip(),
        )
        if not answer:
            raise ValueError(
                "empty_active_case_side_answer_after_pending_question_strip"
            )
        return answer, True, True, None
    except Exception as exc:  # noqa: BLE001
        fallback_reason = safe_fallback_reason(
            f"side_composer:{exc.__class__.__name__}"
        )
        _log.warning(
            "[active_case_side_answer] composer fallback reason=%s", fallback_reason
        )
        return grounded_answer, True, False, fallback_reason


async def _build_active_case_process_payload(
    *,
    message: str,
    session_id: str | None = None,
    governed_state: GovernedSessionState | None,
    decision: Any,
    runtime_action: Any | None = None,
) -> dict[str, Any]:
    result = await build_active_case_process_answer(
        latest_user_message=message,
        governed_state=governed_state,
        turn_decision=decision,
    )
    answer_trace = _process_answer_trace(
        result=result,
        decision=decision,
        runtime_action=runtime_action,
    )
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
    return apply_v92_contracts_to_payload(
        payload,
        session_id=str(session_id or "default"),
        user_message=message,
        state=governed_state,
        route_hint="active_case_process_question",
        case_id=str(session_id) if session_id else None,
    )


@traceable(name="sealai.active_case_side_answer", run_type="chain")
async def _build_active_case_side_payload(
    *,
    message: str,
    session_id: str | None = None,
    governed_state: GovernedSessionState | None,
    decision: Any,
    conversation_route: Any | None,
    runtime_action: Any | None = None,
    current_user: RequestUser | None = None,
) -> dict[str, Any]:
    knowledge_response = await build_case_side_knowledge_response(
        message=message,
        override_class="exploration_answer",
        conversation_route=conversation_route,
        governed_state=governed_state,
        current_user=current_user,
    )
    resume_decision = reevaluate_active_case_resume(
        latest_user_message=message,
        governed_state=governed_state,
        turn_decision=decision,
    )
    base_answer = str(
        getattr(knowledge_response, "answer_markdown", None)
        or getattr(knowledge_response, "content", "")
        or ""
    ).strip()
    evidence_context = build_active_case_side_evidence_context(
        knowledge_response=knowledge_response,
        latest_user_message=message,
    )
    speakable_facts = build_active_case_side_speakable_facts(
        governed_state,
        evidence_context=evidence_context,
    )
    evidence_enrichment = enrich_active_case_side_answer_with_evidence(
        latest_user_message=message,
        answer_markdown=base_answer,
        evidence_context=evidence_context,
    )
    claim_policy_result = enforce_active_case_side_claim_policy(
        latest_user_message=message,
        answer_markdown=evidence_enrichment.answer_markdown,
        speakable_facts=speakable_facts,
    )
    (
        answer_markdown,
        composer_attempted,
        composer_succeeded,
        fallback_reason,
    ) = await _compose_active_case_side_answer(
        message=message,
        grounded_answer=claim_policy_result.answer_markdown,
        governed_state=governed_state,
        resume_decision=resume_decision,
        claim_policy_result=claim_policy_result,
    )
    if composer_succeeded:
        claim_policy_result = enforce_active_case_side_claim_policy(
            latest_user_message=message,
            answer_markdown=answer_markdown,
            speakable_facts=speakable_facts,
        )
        answer_markdown = claim_policy_result.answer_markdown
    answer_trace = _side_answer_trace(
        knowledge_response=knowledge_response,
        resume_decision=resume_decision,
        decision=decision,
        claim_policy_result=claim_policy_result,
        evidence_context=evidence_context,
        evidence_used_in_answer=evidence_enrichment.evidence_used_in_answer,
        composer_attempted=composer_attempted,
        composer_succeeded=composer_succeeded,
        fallback_reason=fallback_reason,
        runtime_action=runtime_action,
    )
    emit_quality_trace(
        component="active_case_side_answer",
        tags=("active-case-side-answer", "claim-policy"),
        session_id=session_id,
        route="active_case_side_question",
        answer_mode="active_case_side_question",
        mutation_policy=answer_trace.get("mutation_policy"),
        claim_policy_result=answer_trace.get("claim_policy_result"),
        forbidden_claims_count=len(answer_trace.get("forbidden_claims_detected") or []),
        answer_safety_rewritten=answer_trace.get("answer_safety_rewritten"),
        answer_safety_fallback_used=answer_trace.get("answer_safety_fallback_used"),
        evidence_context_available=answer_trace.get("evidence_context_available"),
        evidence_refs_count=answer_trace.get("evidence_refs_count"),
        composer_attempted=answer_trace.get("composer_attempted"),
        composer_succeeded=answer_trace.get("composer_succeeded"),
        runtime_action_type=answer_trace.get("runtime_action_type"),
        graph_allowed=answer_trace.get("graph_allowed"),
    )

    from app.agent.api.utils import _knowledge_response_run_meta  # noqa: PLC0415

    knowledge_run_meta = _knowledge_response_run_meta(knowledge_response)
    knowledge_trace = knowledge_run_meta.get("answer_trace")
    if isinstance(knowledge_trace, dict):
        for key, value in knowledge_trace.items():
            if key.startswith("rag_") and answer_trace.get(key) is None:
                answer_trace[key] = value

    payload = build_public_response_core(
        reply=answer_markdown,
        structured_state=None,
        policy_path="knowledge",
        run_meta=with_answer_trace(
            knowledge_run_meta,
            answer_trace,
        ),
    )
    payload["answer_markdown"] = answer_markdown
    payload = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="knowledge",
            answer_mode="active_case_side_question",
            deterministic_fallback_reply=answer_markdown,
            existing_answer_markdown=payload.get("answer_markdown"),
            existing_answer_markdown_source=answer_trace.get("answer_markdown_source"),
            existing_reply_source=answer_trace.get("reply_source"),
            composer_tier="tier_b"
            if answer_trace.get("composer_attempted")
            else "tier_a",
            fallback_reason=answer_trace.get("fallback_reason"),
        ),
    )
    payload["assistant_message"] = str(
        payload.get("answer_markdown") or payload.get("reply") or ""
    ).strip()
    payload["type"] = "state_update"
    return apply_v92_contracts_to_payload(
        payload,
        session_id=str(session_id or "default"),
        user_message=message,
        state=governed_state,
        route_hint="active_case_side_question",
        case_id=str(session_id) if session_id else None,
    )


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
    runtime_action: Any | None = None,
) -> ChatResponse:
    from app.agent.runtime.conversation_runtime import run_conversation  # noqa: PLC0415

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
        direct_reply = _open_case_ack_continue_reply(
            message=message,
            governed_state=governed,
        )

    result = await run_conversation(
        message,
        history=history,
        case_summary=case_summary,
        mode=mode,
        direct_reply=direct_reply,
    )
    structured_state: dict[str, Any] | None = None
    state_for_contract = governed
    if result.reply_text and governed is not None and _light_case_active(governed):
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
        state_for_contract = updated

    run_meta = with_answer_trace(
        {"version_provenance": _build_fast_path_version_provenance(decision=None)},
        build_answer_trace(
            reply_source="light_conversation",
            answer_markdown_source="light_conversation",
            final_visible_source="answer_markdown",
        ),
    )
    payload = build_public_response_core(
        reply=result.reply_text,
        structured_state=structured_state,
        policy_path=mode.lower(),
        run_meta=_with_runtime_action_trace(run_meta, runtime_action),
    )
    payload = apply_v92_contracts_to_payload(
        payload,
        session_id=str(request.session_id or "default"),
        user_message=message,
        state=state_for_contract,
        route_hint=mode.lower(),
        case_id=str(request.session_id or "default"),
    )
    return ChatResponse(
        session_id=request.session_id,
        **payload,
    )


async def _run_governed_graph_once(
    request: ChatRequest,
    *,
    current_user: RequestUser,
    pre_gate_classification: str | None = None,
    runtime_action: Any | None = None,
) -> tuple[GraphState, GovernedSessionState]:
    turn_result = await run_governed_graph_turn(
        request=request,
        current_user=current_user,
        pre_gate_classification=pre_gate_classification,
        runtime_action=runtime_action,
    )
    return turn_result.result_state, turn_result.persisted_state


def _with_engine_sidecar_trace(
    response: ChatResponse,
    *,
    executed: bool,
    state_available: bool,
    error: Exception | None = None,
) -> ChatResponse:
    meta = dict(response.run_meta or {})
    answer_trace = dict(meta.get("answer_trace") or {})
    answer_trace.update(
        {
            "conversation_first_runtime": True,
            "visible_runtime": "light_conversation",
            "engine_sidecar": "governed_langgraph",
            "governed_graph_sidecar_executed": executed,
            "governed_graph_visible_reply_suppressed": True,
            "engine_sidecar_state_available": state_available,
        }
    )
    if error is not None:
        answer_trace.update(
            {
                "engine_sidecar_error": safe_fallback_reason(error),
                "engine_sidecar_fallback": "visible_conversation_without_fresh_engine_state",
            }
        )
    meta["answer_trace"] = answer_trace
    return response.model_copy(update={"run_meta": meta})


def _state_has_open_invite_facts(state: GovernedSessionState | None) -> bool:
    if state is None:
        return False
    assertions = getattr(getattr(state, "asserted", None), "assertions", {}) or {}
    if any(field in assertions for field in _OPEN_INVITE_FACT_FIELDS):
        return True
    observed = getattr(getattr(state, "observed", None), "raw_extractions", []) or []
    for extraction in observed:
        field_name = str(getattr(extraction, "field_name", "") or "")
        raw_value = getattr(extraction, "raw_value", None)
        if field_name in _OPEN_INVITE_FACT_FIELDS and raw_value not in (None, ""):
            return True
    return False


def _open_sealing_invite_reply(
    *,
    pre_gate_classification: str | None,
    runtime_action: Any | None,
    sidecar_state: GovernedSessionState | None,
) -> str | None:
    answer_mode = _runtime_action_value(getattr(runtime_action, "answer_mode", None))
    if pre_gate_classification != "DOMAIN_INQUIRY" or answer_mode != "governed_intake":
        return None
    if _state_has_open_invite_facts(sidecar_state):
        return None
    return render_communication_template(
        "free_conversation_open_invite",
        fallback=(
            "Gerne unterstuetze ich dich. Erzaehl mir bitte von deiner Dichtungssituation: "
            "Welche Anwendung liegt vor, welches Medium beruehrt die Dichtung und welche "
            "Rahmenbedingungen sind wichtig?"
        ),
    )


def _rwdr_p0_leakage_guidance_reply(
    *,
    pre_gate_classification: str | None,
    runtime_action: Any | None,
    message: str,
) -> str | None:
    """Deterministic senior-engineer review hint for the P0 RWDR leakage turn.

    Fires only on the governed-intake domain path, so smalltalk, meta/UI help,
    knowledge, and active-case side/process turns are untouched. When the user
    message signals an RWDR seal with a leakage/replacement intent, the visible
    reply becomes one shaft/counterface (Wellenlauffläche) review hint plus
    exactly one next question from the RWDR domain logic, instead of the generic
    intake invite. The hint/question text is owned by the deterministic RWDR
    service — the chat LLM does not produce it.
    """

    answer_mode = _runtime_action_value(getattr(runtime_action, "answer_mode", None))
    if pre_gate_classification != "DOMAIN_INQUIRY" or answer_mode != "governed_intake":
        return None
    guidance = build_rwdr_p0_leakage_guidance(message)
    if guidance is None:
        return None
    return guidance.reply_markdown()


def _open_case_ack_continue_reply(
    *,
    message: str,
    governed_state: GovernedSessionState | None,
) -> str | None:
    if governed_state is None or not _light_case_active(governed_state):
        return None
    if _state_has_open_invite_facts(governed_state):
        return None
    if not _OPEN_CASE_ACK_RE.match(str(message or "")):
        return None
    return render_communication_template(
        "free_conversation_ack_continue",
        fallback=(
            "Ich bin auch gespannt, lass uns loslegen. Erzaehl mir zuerst kurz, "
            "welche Anwendung wir betrachten, welches Medium die Dichtung beruehrt "
            "und welche Rahmenbedingungen dir wichtig sind."
        ),
    )


async def _run_conversation_first_with_engine_sidecar(
    request: ChatRequest,
    *,
    current_user: RequestUser,
    pre_gate_classification: str | None = None,
    runtime_action: Any | None = None,
    governed_state: GovernedSessionState | None = None,
) -> ChatResponse:
    sidecar_state = governed_state
    sidecar_error: Exception | None = None
    sidecar_executed = False
    try:
        _, sidecar_state = await _run_governed_graph_once(
            request,
            current_user=current_user,
            pre_gate_classification=pre_gate_classification,
            runtime_action=runtime_action,
        )
        sidecar_executed = True
    except Exception as exc:  # noqa: BLE001
        sidecar_error = exc
        _log.exception(
            "[runtime_authority] conversation-first sidecar failed session=%s reason=%s",
            request.session_id,
            safe_fallback_reason(exc),
        )

    # P0 RWDR leakage/replacement: surface one deterministic shaft/counterface
    # review hint + one next question instead of a generic intake invite.
    direct_reply = _rwdr_p0_leakage_guidance_reply(
        pre_gate_classification=pre_gate_classification,
        runtime_action=runtime_action,
        message=request.message,
    ) or _open_sealing_invite_reply(
        pre_gate_classification=pre_gate_classification,
        runtime_action=runtime_action,
        sidecar_state=sidecar_state,
    )
    response = await _run_light_chat_response(
        message=request.message,
        request=request,
        current_user=current_user,
        mode="EXPLORATION",
        governed_state_override=sidecar_state,
        direct_reply=direct_reply,
        runtime_action=runtime_action,
    )
    return _with_engine_sidecar_trace(
        response,
        executed=sidecar_executed,
        state_available=sidecar_state is not None,
        error=sidecar_error,
    )


async def _run_governed_chat_response(
    request: ChatRequest,
    *,
    current_user: RequestUser,
    pre_gate_classification: str | None = None,
    runtime_action: Any | None = None,
) -> ChatResponse:
    result_state, persisted_state = await _run_governed_graph_once(
        request,
        current_user=current_user,
        pre_gate_classification=pre_gate_classification,
        runtime_action=runtime_action,
    )
    context = _build_governed_reply_context(
        result_state=result_state,
        persisted_state=persisted_state,
    )
    payload = _assemble_governed_stream_payload(
        context=context,
        session_id=str(request.session_id or "default"),
        user_message=request.message,
        state=result_state,
    )
    payload["run_meta"] = _with_runtime_action_trace(
        payload.get("run_meta"),
        runtime_action,
    )
    payload = await apply_async_adversarial_review_to_payload(payload)
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
            turn_index=int(
                getattr(result_state, "user_turn_index", 0)
                or result_state.analysis_cycle
                or 0
            ),
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
    runtime_action: Any | None = None,
) -> ChatResponse:
    from app.agent.api.utils import _fast_response_run_meta  # noqa: PLC0415

    payload = build_public_response_core(
        reply=fast_response.content,
        structured_state=None,
        policy_path="conversation",
        run_meta=_with_runtime_action_trace(
            _fast_response_run_meta(fast_response),
            runtime_action,
        ),
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
    payload = apply_v92_contracts_to_payload(
        payload,
        session_id=str(request.session_id or "default"),
        user_message=request.message,
        state=None,
        route_hint="fast",
        case_id=str(request.session_id or "default") if request.session_id else None,
    )
    return ChatResponse(session_id=request.session_id, **payload)


async def _chat_response_from_knowledge_response(
    *,
    request: ChatRequest,
    knowledge_response: Any,
    runtime_action: Any | None = None,
) -> ChatResponse:
    from app.agent.api.utils import _knowledge_response_run_meta  # noqa: PLC0415

    payload = build_public_response_core(
        reply=knowledge_response.content,
        structured_state=None,
        policy_path="knowledge",
        run_meta=_with_runtime_action_trace(
            _knowledge_response_run_meta(knowledge_response),
            runtime_action,
        ),
    )
    answer_markdown = str(
        getattr(knowledge_response, "answer_markdown", "") or ""
    ).strip()
    if answer_markdown:
        payload["answer_markdown"] = answer_markdown
    answer_trace = getattr(knowledge_response, "answer_trace", None)
    answer_markdown_source = (
        answer_trace.get("answer_markdown_source")
        if isinstance(answer_trace, dict)
        else "knowledge_service"
    )
    composer_attempted = bool(
        answer_trace.get("composer_attempted")
        if isinstance(answer_trace, dict)
        else False
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
    payload = apply_v92_contracts_to_payload(
        payload,
        session_id=str(request.session_id or "default"),
        user_message=request.message,
        state=None,
        route_hint="knowledge",
        case_id=str(request.session_id or "default") if request.session_id else None,
    )
    return ChatResponse(
        session_id=request.session_id,
        **payload,
    )


async def chat_endpoint(request: ChatRequest, current_user: RequestUser):
    early_guard_reply = await collect_unsafe_user_instruction_reply_with_trace(
        latest_user_message=request.message,
        turn_context=None,
    )
    if early_guard_reply is not None:
        payload = build_public_response_core(
            reply=early_guard_reply.text,
            structured_state=None,
            policy_path="governed_guard",
            run_meta=with_answer_trace(
                {"guard": "unsafe_forced_case_claim"},
                early_guard_reply.answer_trace,
            ),
        )
        payload = apply_v92_contracts_to_payload(
            payload,
            session_id=str(request.session_id or "default"),
            user_message=request.message,
            state=None,
            route_hint="unsafe_or_blocked",
            case_id=str(request.session_id or "default")
            if request.session_id
            else None,
        )
        return ChatResponse(
            session_id=request.session_id,
            **payload,
        )

    dispatch = await _resolve_runtime_dispatch(request, current_user=current_user)
    if dispatch.rfq_response is not None:
        return await _chat_response_from_rfq_readiness(
            request=request,
            answer_markdown=dispatch.rfq_response,
            projection=dispatch.rfq_readiness_projection,
            runtime_action=_v7_dispatch_runtime_action(dispatch),
            state=dispatch.governed_state,
        )
    if dispatch.fast_response is not None:
        response = await _chat_response_from_fast_response(
            request=request,
            fast_response=dispatch.fast_response,
            runtime_action=_v7_dispatch_runtime_action(dispatch),
        )
        # Bridge the mobile triage pending question so the next "Ja"/"Nein"/
        # "Weiß ich nicht" turn resolves through the existing slot binder. No-op
        # for non-mobile fast responses; runs after the reply is built.
        await persist_mobile_triage_pending_question(
            current_user=current_user,
            session_id=request.session_id,
            fast_response=dispatch.fast_response,
        )
        return response
    if dispatch.knowledge_response is not None:
        return await _chat_response_from_knowledge_response(
            request=request,
            knowledge_response=dispatch.knowledge_response,
            runtime_action=_v7_dispatch_runtime_action(dispatch),
        )

    if _is_light_runtime_mode(dispatch.runtime_mode):
        return await _run_light_chat_response(
            message=request.message,
            request=request,
            current_user=current_user,
            mode=dispatch.runtime_mode,
            governed_state_override=dispatch.governed_state,
            direct_reply=dispatch.direct_reply,
            runtime_action=_v7_dispatch_runtime_action(dispatch),
        )

    if dispatch.runtime_mode == "GOVERNED":
        runtime_action = _v7_dispatch_runtime_action(dispatch)
        if _is_v7_active_case_process_question(dispatch):
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
            return ChatResponse(session_id=request.session_id, **payload)
        if _is_v7_active_case_side_question(dispatch):
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
            return ChatResponse(session_id=request.session_id, **payload)
        if not _runtime_action_allows_graph(dispatch):
            payload = _runtime_action_blocked_graph_payload(runtime_action)
            payload = apply_v92_contracts_to_payload(
                payload,
                session_id=str(request.session_id or "default"),
                user_message=request.message,
                state=dispatch.governed_state,
                route_hint="unsafe_or_blocked",
                case_id=str(request.session_id or "default")
                if request.session_id
                else None,
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
            return ChatResponse(session_id=request.session_id, **payload)
        _log.debug(
            "[runtime_authority] json session=%s authority=conversation_first_sidecar reason=%s",
            request.session_id,
            dispatch.gate_reason,
        )
        return await _run_conversation_first_with_engine_sidecar(
            request,
            current_user=current_user,
            pre_gate_classification=dispatch.pre_gate_classification,
            runtime_action=runtime_action,
            governed_state=dispatch.governed_state,
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
async def chat_route(
    request: ChatRequest, current_user: RequestUser = Depends(get_current_request_user)
):
    return await chat_endpoint(request, current_user=current_user)


@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest, current_user: RequestUser = Depends(get_current_request_user)
):
    return StreamingResponse(
        event_generator(request, current_user=current_user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
