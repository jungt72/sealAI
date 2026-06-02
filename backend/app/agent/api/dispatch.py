import logging
import os
import dataclasses
import re
from typing import Any, Literal

from app.domain.conversation_intent import ConversationRoutingDecision
from app.agent.state.models import GovernedSessionState
from app.agent.communication.v7_contracts import (
    AnswerMode,
    MutationPolicy,
    RuntimeAction,
    RuntimeAnswerBuilder,
    RuntimeActionType,
    TurnDecision,
    build_answer_only_runtime_action,
    build_rfq_readiness_runtime_action,
    build_runtime_action_from_turn_decision,
)
from app.agent.communication.rfq_intent import (
    build_rfq_readiness_answer,
    classify_rfq_readiness_intent,
)
from app.agent.runtime.answer_trace import build_answer_trace
from app.agent.v91.semantic_boundary import (
    build_v91_turn_policy,
    merge_v91_trace_into_runtime_action,
)
from app.services.auth.dependencies import RequestUser
from app.agent.api.deps import (
    _runtime_mode_for_pre_gate,
)
from app.agent.api.loaders import (
    _bridge_knowledge_session_to_governed_state,
    _load_live_governed_state,
    _load_live_knowledge_session_context,
    _persist_live_knowledge_session_context,
)
from app.observability.langsmith import traceable
from app.observability.sealai_quality import emit_quality_trace, stable_trace_hash

_log = logging.getLogger(__name__)

# Feature flags
_ENABLE_BINARY_GATE: bool = (
    os.environ.get("SEALAI_ENABLE_BINARY_GATE", "true").lower() == "true"
)
_ENABLE_CONVERSATION_RUNTIME: bool = (
    os.environ.get("SEALAI_ENABLE_CONVERSATION_RUNTIME", "true").lower() == "true"
)
_FORCE_LLM_FAST_RESPONDER: bool = (
    os.environ.get("SEALAI_FORCE_LLM_FAST_RESPONDER", "true").lower()
    in {"1", "true", "yes", "on"}
)


def _knowledge_answer_composer_enabled() -> bool:
    return os.environ.get(
        "SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true"
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _knowledge_debug_trace_enabled() -> bool:
    return os.environ.get("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _knowledge_rag_retriever(
    *,
    query: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
    max_results: int = 3,
) -> list[dict[str, Any]]:
    """Shared RAG-backed retriever for no-case and side-question knowledge."""

    from app.services.rag.constants import RAG_SHARED_TENANT_ID  # noqa: PLC0415
    from app.services.rag.rag_orchestrator import hybrid_retrieve  # noqa: PLC0415

    effective_tenant = (tenant_id or "").strip() or RAG_SHARED_TENANT_ID
    try:
        return list(
            hybrid_retrieve(
                query=query,
                tenant=effective_tenant,
                k=max(1, int(max_results or 3)),
                user_id=user_id,
            )
            or []
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[runtime_dispatch] knowledge RAG lookup failed (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return []


def _knowledge_tenant_id(current_user: RequestUser | None) -> str:
    from app.services.rag.constants import RAG_SHARED_TENANT_ID  # noqa: PLC0415

    tenant_id = getattr(current_user, "tenant_id", None)
    return str(tenant_id).strip() if tenant_id else RAG_SHARED_TENANT_ID


def _knowledge_user_id(current_user: RequestUser | None) -> str | None:
    user_id = getattr(current_user, "user_id", None)
    return str(user_id).strip() if user_id else None


_CONTEXTUAL_MATERIAL_COMPARISON_RE = re.compile(
    r"\b(?:vergleiche?|vergleich|unterschied|gegen[üu]ber|gegenueber|vs\.?|versus|mit|gegen|besser|schlechter)\b",
    re.IGNORECASE | re.UNICODE,
)

_CONTEXTUAL_MATERIAL_PAIR_ANAPHORA_RE = re.compile(
    r"\b(?:die\s+beiden|beide)\b"
    r"|\b(?:vergleiche?|vergleich|unterschied(?:e)?|im\s+vergleich|besser|schlechter|"
    r"welche[rs]?\s+ist\s+besser)\b.*\b(?:das|damit|daf[uü]r|hier|anwendung)\b",
    re.IGNORECASE | re.UNICODE,
)


def _contextualized_knowledge_message(
    message: str,
    *,
    recent_history: tuple[Any, ...] = (),
) -> str:
    """Resolve elliptical material follow-ups before KnowledgeService answers.

    The answer composer receives recent_history, but the deterministic
    KnowledgeService runs first. Without this resolver, "bitte vergleiche mit
    NBR" after a PTFE question is answered as a single-material NBR definition.
    """

    raw_message = str(message or "").strip()
    if not raw_message:
        return raw_message
    try:
        from app.services.knowledge.material_comparison import extract_material_ids  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return raw_message

    latest_materials = list(extract_material_ids(raw_message))
    if len(latest_materials) >= 2:
        return raw_message
    if len(latest_materials) == 0:
        if not _CONTEXTUAL_MATERIAL_PAIR_ANAPHORA_RE.search(raw_message):
            return raw_message
        pair = _last_prior_material_pair(recent_history)
        if pair is None:
            return raw_message
        left, right = pair
        return (
            f"Vergleiche {left} mit {right}. "
            f"Die aktuelle Nutzer-Folgefrage lautet: {raw_message}"
        )
    if len(latest_materials) != 1:
        return raw_message
    if not _CONTEXTUAL_MATERIAL_COMPARISON_RE.search(raw_message):
        return raw_message

    anchor = _last_prior_material_subject(
        recent_history,
        exclude=set(latest_materials),
    )
    if not anchor:
        return raw_message

    comparison_material = latest_materials[0]
    return (
        f"Vergleiche {anchor} mit {comparison_material}. "
        f"Die aktuelle Nutzer-Folgefrage lautet: {raw_message}"
    )


def _last_prior_material_pair(
    recent_history: tuple[Any, ...],
) -> tuple[str, str] | None:
    try:
        from app.services.knowledge.material_comparison import extract_material_ids  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None

    def collect(roles: set[str]) -> list[str]:
        recent: list[str] = []
        for turn in recent_history:
            role = _history_turn_value(turn, "role")
            content = _history_turn_value(turn, "content")
            if role not in roles or not content:
                continue
            for material in extract_material_ids(content):
                if material in recent:
                    recent.remove(material)
                recent.append(material)
        return recent

    user_materials = collect({"user"})
    if len(user_materials) >= 2:
        return user_materials[-2], user_materials[-1]
    all_materials = collect({"user", "assistant"})
    if len(all_materials) >= 2:
        return all_materials[-2], all_materials[-1]
    return None


def _last_prior_material_subject(
    recent_history: tuple[Any, ...],
    *,
    exclude: set[str],
) -> str | None:
    try:
        from app.services.knowledge.material_comparison import extract_material_ids  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None

    user_candidates: list[str] = []
    assistant_candidates: list[str] = []
    for turn in recent_history:
        role = _history_turn_value(turn, "role")
        content = _history_turn_value(turn, "content")
        if role not in {"user", "assistant"} or not content:
            continue
        for material in extract_material_ids(content):
            if material in exclude:
                continue
            if role == "user":
                user_candidates.append(material)
            else:
                assistant_candidates.append(material)
    for material in reversed(user_candidates):
        return material
    for material in reversed(assistant_candidates):
        return material
    return None


def _history_turn_value(turn: Any, key: str) -> str:
    if isinstance(turn, dict):
        return str(turn.get(key) or "").strip()
    return str(getattr(turn, key, "") or "").strip()


@dataclasses.dataclass(frozen=True, slots=True)
class KnowledgeDebugTrace:
    route: str | None
    knowledge_mode: str | None
    reply_source: str
    answer_markdown_source: Literal[
        "reply_passthrough",
        "composer",
        "composer_fallback",
        "composer_safe_fallback",
    ]
    composer_enabled: bool
    composer_attempted: bool
    composer_succeeded: bool
    composer_fallback_reason: str | None
    evidence_count: int
    evidence_source_types: list[str]
    history_count: int
    regulatory_currentness_required: bool
    limitations_count: int

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class _MobileTriageFastResponse:
    """Patch 9.5 fast-response carrier for mobile leakage triage (§4.8).

    Compatible with the existing fast-response surfacing (``.content`` +
    getattr-based run_meta). Carries the full AssistantTurnEnvelope so the
    pocket cockpit / action chips / trace travel in run_meta additively.
    """

    content: str
    mobile_triage_envelope: dict[str, Any]
    source_classification: Any = None
    no_case_created: bool = True


@dataclasses.dataclass(frozen=True)
class RuntimeDispatchResolution:
    gate_route: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"]
    gate_reason: str
    runtime_mode: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"]
    gate_applied: bool
    pre_gate_classification: str | None = None
    pre_gate_reason: str | None = None
    session_zone: str | None = None
    direct_reply: str | None = None
    rfq_response: str | None = None
    rfq_readiness_projection: dict[str, Any] | None = None
    fast_response: Any | None = None
    knowledge_response: Any | None = None
    knowledge_override_class: str | None = None
    governed_state: GovernedSessionState | None = None
    conversation_route: ConversationRoutingDecision | None = None
    turn_decision: TurnDecision | None = None
    runtime_action: RuntimeAction | None = None
    v91_policy: Any | None = None
    semantic_pre_gate_trace: dict[str, Any] | None = None


def _governed_state_has_active_case(state: GovernedSessionState | None) -> bool:
    if state is None:
        return False
    if getattr(state, "pending_question", None) is not None:
        return True
    if getattr(state, "conversation_messages", None):
        return True
    asserted = getattr(state, "asserted", None)
    if getattr(asserted, "assertions", None):
        return True
    observed = getattr(state, "observed", None)
    if getattr(observed, "raw_extractions", None):
        return True
    governance = getattr(state, "governance", None)
    if getattr(governance, "requirement_class", None) is not None:
        return True
    return False


def _knowledge_turn_needs_active_case_probe(message: str) -> bool:
    """Return whether a knowledge-looking turn should inspect active case state.

    V7 treats knowledge inside an active case as a side question: answer it
    without mutation, then resume the primary task. To make that decision
    reliably, a session-scoped knowledge turn may read existing governed state
    with ``create_if_missing=False``. This read-only probe must never create a
    case or convert the knowledge turn into governed intake.
    """

    normalized = " ".join((message or "").casefold().strip().split())
    if not normalized:
        return False
    if normalized.startswith(
        (
            "was genau ist",
            "was eigentlich ist",
            "was genau sind",
            "was eigentlich sind",
            "was ist",
            "was sind",
            "was bedeutet",
            "was heisst",
            "was heißt",
            "wie funktioniert",
            "warum",
            "wieso",
            "weshalb",
            "erkläre",
            "erklaere",
            "erklär",
            "erklaer",
        )
    ):
        return True
    if len(normalized) > 80:
        return False
    return normalized.startswith(
        (
            "und ",
            "auch ",
            "damit ",
            "dann ",
            "wie damit",
            "was damit",
            "wie ist es mit ",
            "wie sieht es mit ",
            "was ist mit ",
        )
    )


async def _load_existing_governed_state_for_v7(
    *,
    request: Any,
    current_user: RequestUser,
) -> GovernedSessionState | None:
    if not getattr(request, "session_id", None):
        return None
    try:
        return await _load_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            create_if_missing=False,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[runtime_dispatch] v7 existing governed state load failed (%s: %s) — continuing without active-case context",
            type(exc).__name__,
            exc,
        )
        return None


async def _resolve_v8_turn_decision(
    *,
    request: Any,
    pre_gate: Any,
    governed_state: GovernedSessionState | None,
) -> TurnDecision:
    from app.agent.communication.communication_runtime_v8 import (  # noqa: PLC0415
        CommunicationRuntimeV8,
    )
    from app.agent.communication.conversation_controller_v7 import (  # noqa: PLC0415
        ConversationControllerInput,
    )
    from app.agent.graph.slot_answer_binding import resolve_slot_answer_binding  # noqa: PLC0415

    turn_index = int(getattr(governed_state, "user_turn_index", 0) or 0) + 1
    pending_question = (
        getattr(governed_state, "pending_question", None)
        if governed_state is not None
        else None
    )
    slot_binding = resolve_slot_answer_binding(
        pending_question=pending_question,
        message=request.message,
        turn_index=turn_index,
    )
    return await CommunicationRuntimeV8().decide(
        ConversationControllerInput(
            user_message=request.message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=float(getattr(pre_gate, "confidence", 0.5) or 0.5),
            pre_gate_reason=str(getattr(pre_gate, "reasoning", "") or ""),
            active_case_exists=_governed_state_has_active_case(governed_state),
            pending_question=pending_question,
            slot_answer_binding=slot_binding,
        )
    )


def _v7_answer_mode(decision: TurnDecision | None) -> str | None:
    if decision is None:
        return None
    mode = getattr(decision, "answer_mode", None)
    return str(getattr(mode, "value", mode) or "") or None


def _v7_runtime_action(
    decision: TurnDecision | None,
    *,
    reason: str | None = None,
) -> RuntimeAction | None:
    if decision is None:
        return None
    return build_runtime_action_from_turn_decision(
        decision,
        reason=reason,
        decision_source="communication_runtime_v8",
    )


def _fast_response_runtime_action(
    classification: Any,
    *,
    reason: str,
) -> RuntimeAction:
    value = str(getattr(classification, "value", classification) or "")
    if value == "GREETING":
        answer_mode = AnswerMode.SMALLTALK
    elif value == "META_QUESTION":
        answer_mode = AnswerMode.META_QUESTION
    elif value == "BLOCKED":
        answer_mode = AnswerMode.SAFETY_BLOCKED
    else:
        answer_mode = AnswerMode.CLARIFICATION
    return build_answer_only_runtime_action(
        answer_mode=answer_mode,
        answer_builder=RuntimeAnswerBuilder.FAST_RESPONSE,
        reason=reason,
        decision_source="pre_gate_fast_responder",
        graph_invocation_skipped_reason="fast_response_does_not_require_governed_graph",
        next_runtime_action="return_fast_response",
    )


def _light_runtime_action(
    *,
    reason: str,
    decision_source: str = "pre_gate_light_runtime",
    answer_mode: AnswerMode = AnswerMode.CLARIFICATION,
) -> RuntimeAction:
    return build_answer_only_runtime_action(
        answer_mode=answer_mode,
        answer_builder=RuntimeAnswerBuilder.LIGHT_RUNTIME,
        reason=reason,
        decision_source=decision_source,
        graph_invocation_skipped_reason="light_runtime_does_not_require_governed_graph",
        next_runtime_action="run_light_runtime",
    )


def _rfq_readiness_graph_runtime_action(
    *,
    rfq_action_type: str,
    reason: str,
    trace: dict[str, Any] | None = None,
) -> RuntimeAction:
    safe_trace = {
        "answer_mode": AnswerMode.RFQ_READINESS.value,
        "rfq_intent_detected": True,
        "rfq_action_type": rfq_action_type,
        "consent_required": True,
        "dispatch_allowed": False,
        "external_contact_allowed": False,
        "manufacturer_review_framing": True,
        "final_approval_claim_allowed": False,
        "governed_graph_bypassed": False,
        "v92_route_hint": "rfq_readiness",
    }
    safe_trace.update(trace or {})
    return RuntimeAction(
        action_type=RuntimeActionType.ENTER_GOVERNED_GRAPH,
        answer_mode=AnswerMode.RFQ_READINESS,
        mutation_policy=MutationPolicy.FORBIDDEN,
        graph_allowed=True,
        graph_entry_reason="rfq_readiness_requires_governed_graph",
        answer_builder=RuntimeAnswerBuilder.GOVERNED_OUTPUT_CONTRACT,
        resume_strategy=None,
        next_runtime_action="enter_governed_langgraph",
        reason=reason,
        decision_source="rfq_readiness_intent",
        rfq_action=rfq_action_type,
        trace=safe_trace,
    )


async def _resolve_runtime_dispatch_impl(
    request: Any,  # ChatRequest
    *,
    current_user: RequestUser | None,
) -> RuntimeDispatchResolution:
    if current_user is None:
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason="missing_current_user",
            runtime_mode="GOVERNED",
            gate_applied=False,
        )

    if not _ENABLE_BINARY_GATE:
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason="binary_gate_disabled",
            runtime_mode="GOVERNED",
            gate_applied=False,
        )

    # Patch 9.5 — mobile leakage triage (§4.8/§7.3). Photo + leakage intent
    # returns an immediate, useful pocket output BEFORE any slow vision step
    # (no-empty-spinner). Only fires with an attachment, so text-only leakage
    # turns keep their existing governed path unchanged.
    if getattr(request, "has_attachment", False):
        from app.agent.communication.mobile_triage import (  # noqa: PLC0415
            build_mobile_leakage_triage,
            build_visual_low_confidence_guidance,
            is_leakage_triage_intent,
        )

        if is_leakage_triage_intent(request.message, has_attachment=True):
            # AC7: an unreadable/low-confidence photo gets measurement/photo
            # guidance instead of a triage question — never an identification.
            if getattr(request, "attachment_low_confidence", False):
                envelope = build_visual_low_confidence_guidance()
                reason = "visual_low_confidence_guidance"
            else:
                envelope = build_mobile_leakage_triage(has_attachment=True)
                reason = "mobile_leakage_triage"
            return RuntimeDispatchResolution(
                gate_route="CONVERSATION",
                gate_reason=reason,
                runtime_mode="CONVERSATION",
                gate_applied=True,
                fast_response=_MobileTriageFastResponse(
                    content=envelope.chat_reply.markdown,
                    mobile_triage_envelope=envelope.model_dump(mode="json"),
                ),
                runtime_action=_fast_response_runtime_action(None, reason=reason),
            )

    try:
        from app.domain.pre_gate_classification import PreGateClassification  # noqa: PLC0415
        from app.domain.conversation_intent import classify_conversation_route  # noqa: PLC0415
        from app.services.fast_responder_service import FastResponderService  # noqa: PLC0415
        from app.services.pre_gate_classifier import PreGateClassifier  # noqa: PLC0415
        from app.services.semantic_intent_router import (  # noqa: PLC0415
            refine_pre_gate_classification,
            semantic_pre_gate_candidate,
        )

        pre_gate = PreGateClassifier().classify(request.message)
        semantic_pre_gate_trace: dict[str, Any] | None = None
        if semantic_pre_gate_candidate(request.message, pre_gate):
            semantic_recent_history: tuple[Any, ...] = ()
            if request.session_id:
                try:
                    semantic_knowledge_context = await _load_live_knowledge_session_context(
                        current_user=current_user,
                        session_id=request.session_id,
                    )
                    if semantic_knowledge_context is not None:
                        semantic_recent_history = tuple(
                            getattr(
                                semantic_knowledge_context,
                                "conversation_turns",
                                (),
                            )
                            or ()
                        )
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "[runtime_dispatch] semantic pre-gate history load failed (%s: %s) — routing without knowledge history",
                        type(exc).__name__,
                        exc,
                    )
            semantic_decision = await refine_pre_gate_classification(
                message=request.message,
                deterministic=pre_gate,
                recent_history=semantic_recent_history,
            )
            semantic_pre_gate_trace = semantic_decision.as_trace()
            pre_gate = semantic_decision.classification_result(pre_gate)
        conversation_route = classify_conversation_route(
            request.message,
            pre_gate_classification=pre_gate.classification,
        )
        if pre_gate.classification is not PreGateClassification.BLOCKED:
            rfq_intent = classify_rfq_readiness_intent(request.message)
            if rfq_intent.detected:
                governed_state = await _load_existing_governed_state_for_v7(
                    request=request,
                    current_user=current_user,
                )
                if _governed_state_has_active_case(governed_state):
                    return RuntimeDispatchResolution(
                        gate_route="GOVERNED",
                        gate_reason=f"runtime_action_rfq_readiness_graph:{rfq_intent.reason}",
                        runtime_mode="GOVERNED",
                        gate_applied=False,
                        pre_gate_classification=pre_gate.classification.value,
                        pre_gate_reason=pre_gate.reasoning,
                        governed_state=governed_state,
                        conversation_route=conversation_route,
                        semantic_pre_gate_trace=semantic_pre_gate_trace,
                        runtime_action=_rfq_readiness_graph_runtime_action(
                            rfq_action_type=rfq_intent.rfq_action_type,
                            reason=rfq_intent.reason,
                            trace=rfq_intent.as_trace(),
                        ),
                    )
                rfq_answer = build_rfq_readiness_answer(
                    latest_user_message=request.message,
                    governed_state=governed_state,
                    intent=rfq_intent,
                )
                return RuntimeDispatchResolution(
                    gate_route="CONVERSATION",
                    gate_reason=f"runtime_action_rfq_readiness:{rfq_intent.reason}",
                    runtime_mode="CONVERSATION",
                    gate_applied=False,
                    pre_gate_classification=pre_gate.classification.value,
                    pre_gate_reason=pre_gate.reasoning,
                    rfq_response=rfq_answer.answer_markdown,
                    rfq_readiness_projection=rfq_answer.projection.public_dict(),
                    governed_state=governed_state,
                    conversation_route=conversation_route,
                    semantic_pre_gate_trace=semantic_pre_gate_trace,
                    runtime_action=build_rfq_readiness_runtime_action(
                        rfq_action_type=rfq_answer.rfq_action_type,
                        action_type=rfq_answer.action_type,
                        reason=rfq_intent.reason,
                        trace=rfq_answer.trace,
                    ),
                )
        if pre_gate.classification is PreGateClassification.GREETING:
            # Smalltalk must stay free and natural, but it must not touch
            # governed state, LangGraph, RAG, or active-case composers.
            return RuntimeDispatchResolution(
                gate_route="CONVERSATION",
                gate_reason=f"pre_gate_llm_fast_responder:{pre_gate.reasoning}",
                runtime_mode="CONVERSATION",
                gate_applied=False,
                pre_gate_classification=pre_gate.classification.value,
                pre_gate_reason=pre_gate.reasoning,
                conversation_route=conversation_route,
                semantic_pre_gate_trace=semantic_pre_gate_trace,
                runtime_action=_light_runtime_action(
                    reason=f"pre_gate_llm_fast_responder:{pre_gate.reasoning}",
                    decision_source="pre_gate_llm_fast_responder",
                    answer_mode=AnswerMode.SMALLTALK,
                ),
            )

        if pre_gate.classification is PreGateClassification.META_QUESTION and request.session_id:
            governed_state = await _load_existing_governed_state_for_v7(
                request=request,
                current_user=current_user,
            )
            turn_decision = await _resolve_v8_turn_decision(
                request=request,
                pre_gate=pre_gate,
                governed_state=governed_state,
            )
            if (
                _v7_answer_mode(turn_decision)
                == AnswerMode.ACTIVE_CASE_PROCESS_QUESTION.value
            ):
                return RuntimeDispatchResolution(
                    gate_route="GOVERNED",
                    gate_reason=f"v7_active_case_process_question:{pre_gate.reasoning}",
                    runtime_mode="GOVERNED",
                    gate_applied=False,
                    pre_gate_classification=pre_gate.classification.value,
                    pre_gate_reason=pre_gate.reasoning,
                    governed_state=governed_state,
                    conversation_route=conversation_route,
                    semantic_pre_gate_trace=semantic_pre_gate_trace,
                    turn_decision=turn_decision,
                    runtime_action=_v7_runtime_action(
                        turn_decision,
                        reason="active_case_process_question_before_governed_graph",
                    ),
                )
        if (
            pre_gate.classification is PreGateClassification.GREETING
            and request.session_id
            and _ENABLE_CONVERSATION_RUNTIME
        ):
            governed_state = await _load_existing_governed_state_for_v7(
                request=request,
                current_user=current_user,
            )
            if _governed_state_has_active_case(governed_state):
                turn_decision = await _resolve_v8_turn_decision(
                    request=request,
                    pre_gate=pre_gate,
                    governed_state=governed_state,
                )
                if _v7_answer_mode(turn_decision) in {
                    AnswerMode.GOVERNED_INTAKE.value,
                    AnswerMode.PENDING_SLOT_ANSWER.value,
                }:
                    return RuntimeDispatchResolution(
                        gate_route="GOVERNED",
                        gate_reason=f"active_case_social_semantic_{_v7_answer_mode(turn_decision)}:{pre_gate.reasoning}",
                        runtime_mode="GOVERNED",
                        gate_applied=False,
                        pre_gate_classification=pre_gate.classification.value,
                        pre_gate_reason=pre_gate.reasoning,
                        governed_state=governed_state,
                        conversation_route=conversation_route,
                        semantic_pre_gate_trace=semantic_pre_gate_trace,
                        turn_decision=turn_decision,
                        runtime_action=_v7_runtime_action(
                            turn_decision,
                            reason="active_case_social_turn_semantic_slot_or_intake",
                        ),
                    )
                if _v7_answer_mode(turn_decision) in {
                    AnswerMode.ACTIVE_CASE_SIDE_QUESTION.value,
                    AnswerMode.ACTIVE_CASE_PROCESS_QUESTION.value,
                }:
                    return RuntimeDispatchResolution(
                        gate_route="GOVERNED",
                        gate_reason=f"active_case_social_semantic_{_v7_answer_mode(turn_decision)}:{pre_gate.reasoning}",
                        runtime_mode="GOVERNED",
                        gate_applied=False,
                        pre_gate_classification=pre_gate.classification.value,
                        pre_gate_reason=pre_gate.reasoning,
                        governed_state=governed_state,
                        conversation_route=conversation_route,
                        semantic_pre_gate_trace=semantic_pre_gate_trace,
                        turn_decision=turn_decision,
                        runtime_action=_v7_runtime_action(
                            turn_decision,
                            reason="active_case_social_turn_semantic_answer_first",
                        ),
                    )
                return RuntimeDispatchResolution(
                    gate_route="CONVERSATION",
                    gate_reason=f"active_case_social_turn:{pre_gate.reasoning}",
                    runtime_mode="CONVERSATION",
                    gate_applied=False,
                    pre_gate_classification=pre_gate.classification.value,
                    pre_gate_reason=pre_gate.reasoning,
                    governed_state=governed_state,
                    conversation_route=conversation_route,
                    semantic_pre_gate_trace=semantic_pre_gate_trace,
                    turn_decision=turn_decision,
                    runtime_action=_light_runtime_action(
                        reason=f"active_case_social_turn:{pre_gate.reasoning}",
                        decision_source="pre_gate_active_case_social_turn",
                    ),
                )
        if pre_gate.classification in FastResponderService.allowed_classifications:
            if (
                _FORCE_LLM_FAST_RESPONDER
                and _ENABLE_CONVERSATION_RUNTIME
                and pre_gate.classification is not PreGateClassification.BLOCKED
            ):
                runtime_mode = _runtime_mode_for_pre_gate(pre_gate.classification.value)
                return RuntimeDispatchResolution(
                    gate_route=runtime_mode,
                    gate_reason=f"pre_gate_llm_fast_responder:{pre_gate.reasoning}",
                    runtime_mode=runtime_mode,
                    gate_applied=False,
                    pre_gate_classification=pre_gate.classification.value,
                    pre_gate_reason=pre_gate.reasoning,
                    conversation_route=conversation_route,
                    semantic_pre_gate_trace=semantic_pre_gate_trace,
                    runtime_action=_light_runtime_action(
                        reason=f"pre_gate_llm_fast_responder:{pre_gate.reasoning}",
                    ),
                )
            fast_response = FastResponderService().respond(
                request.message,
                pre_gate.classification,
            )
            return RuntimeDispatchResolution(
                gate_route="CONVERSATION",
                gate_reason=f"pre_gate:{pre_gate.reasoning}",
                runtime_mode="CONVERSATION",
                gate_applied=False,
                pre_gate_classification=pre_gate.classification.value,
                pre_gate_reason=pre_gate.reasoning,
                fast_response=fast_response,
                conversation_route=conversation_route,
                semantic_pre_gate_trace=semantic_pre_gate_trace,
                runtime_action=_fast_response_runtime_action(
                    pre_gate.classification,
                    reason=f"pre_gate:{pre_gate.reasoning}",
                ),
            )

        if pre_gate.classification in {
            PreGateClassification.KNOWLEDGE_QUERY,
            PreGateClassification.DEEP_DIVE,
        }:
            governed_state = None
            if request.session_id:
                governed_state = await _load_existing_governed_state_for_v7(
                    request=request,
                    current_user=current_user,
                )
            turn_decision = await _resolve_v8_turn_decision(
                request=request,
                pre_gate=pre_gate,
                governed_state=governed_state,
            )
            # §8 knowledge-mode sub-classifier over the already-knowledge-routed
            # turn. AC9 hard invariant: this knowledge path never mutates the
            # governed CaseState — concrete facts are kept in the transient
            # knowledge-bridge context and bridged later on case intent. The §8
            # mode here only shapes the answer (AC8); it must never write a case.
            from app.agent.communication.knowledge_modes import (  # noqa: PLC0415
                resolve_knowledge_mode,
            )

            knowledge_mode = resolve_knowledge_mode(
                request.message,
                has_active_case=governed_state is not None,
            )
            if (
                _v7_answer_mode(turn_decision)
                in {
                    AnswerMode.ACTIVE_CASE_SIDE_QUESTION.value,
                    AnswerMode.ACTIVE_CASE_PROCESS_QUESTION.value,
                }
            ):
                return RuntimeDispatchResolution(
                    gate_route="GOVERNED",
                    gate_reason=f"v7_{_v7_answer_mode(turn_decision)}:{pre_gate.reasoning}",
                    runtime_mode="GOVERNED",
                    gate_applied=False,
                    pre_gate_classification=pre_gate.classification.value,
                    pre_gate_reason=pre_gate.reasoning,
                    governed_state=governed_state,
                    conversation_route=conversation_route,
                    semantic_pre_gate_trace=semantic_pre_gate_trace,
                    turn_decision=turn_decision,
                    runtime_action=_v7_runtime_action(
                        turn_decision,
                        reason="active_case_side_or_process_question_before_governed_graph",
                    ),
                )
            if (
                governed_state is not None
                and _v7_answer_mode(turn_decision)
                in {
                    AnswerMode.GOVERNED_INTAKE.value,
                    AnswerMode.PENDING_SLOT_ANSWER.value,
                }
            ):
                return RuntimeDispatchResolution(
                    gate_route="GOVERNED",
                    gate_reason=f"v7_{_v7_answer_mode(turn_decision)}:{pre_gate.reasoning}",
                    runtime_mode="GOVERNED",
                    gate_applied=False,
                    pre_gate_classification=pre_gate.classification.value,
                    pre_gate_reason=pre_gate.reasoning,
                    governed_state=governed_state,
                    conversation_route=conversation_route,
                    semantic_pre_gate_trace=semantic_pre_gate_trace,
                    turn_decision=turn_decision,
                    runtime_action=_v7_runtime_action(
                        turn_decision,
                        reason="knowledge_pre_gate_promoted_to_governed_graph",
                    ),
                )

            from dataclasses import replace  # noqa: PLC0415
            from app.services.knowledge_service import KnowledgeService  # noqa: PLC0415
            from app.services.knowledge_case_bridge_service import (
                KnowledgeCaseBridgeService,
            )  # noqa: PLC0415

            recent_knowledge_history: tuple[Any, ...] = ()
            knowledge_context = None
            bridge_service = KnowledgeCaseBridgeService()
            if request.session_id:
                try:
                    knowledge_context = await _load_live_knowledge_session_context(
                        current_user=current_user,
                        session_id=request.session_id,
                    )
                    if knowledge_context is not None:
                        recent_knowledge_history = tuple(
                            getattr(knowledge_context, "conversation_turns", ()) or ()
                        )
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "[runtime_dispatch] knowledge context load failed (%s: %s) — answering without prior knowledge-session context",
                        type(exc).__name__,
                        exc,
                    )

            knowledge_query = _contextualized_knowledge_message(
                request.message,
                recent_history=recent_knowledge_history,
            )
            knowledge_response = KnowledgeService(
                rag_retriever=_knowledge_rag_retriever,
            ).answer(
                knowledge_query,
                source_classification=pre_gate.classification,
                tenant_id=_knowledge_tenant_id(current_user),
                user_id=_knowledge_user_id(current_user),
            )
            if request.session_id:
                try:
                    knowledge_context = bridge_service.update_context(
                        request.message,
                        context=knowledge_context,
                        session_id=request.session_id,
                        role="user",
                    )
                    invitation = bridge_service.build_bridge_invitation(
                        request.message,
                        context=knowledge_context,
                    )
                    if invitation:
                        knowledge_response = replace(
                            knowledge_response,
                            content=f"{knowledge_response.content}\n\n{invitation}",
                        )
                        knowledge_context = bridge_service.mark_transition_offered(
                            knowledge_context,
                        )
                    knowledge_context = bridge_service.update_context(
                        knowledge_response.content,
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
                        "[runtime_dispatch] knowledge context update failed (%s: %s) — returning knowledge response without bridge context",
                        type(exc).__name__,
                        exc,
                    )
            knowledge_response = await _compose_knowledge_answer_if_enabled(
                user_message=request.message,
                knowledge_response=knowledge_response,
                conversation_route=conversation_route,
                recent_history=recent_knowledge_history,
                knowledge_mode=knowledge_mode,
            )
            return RuntimeDispatchResolution(
                gate_route="CONVERSATION",
                gate_reason=f"pre_gate:{pre_gate.reasoning}",
                runtime_mode="CONVERSATION",
                gate_applied=False,
                pre_gate_classification=pre_gate.classification.value,
                pre_gate_reason=pre_gate.reasoning,
                knowledge_response=knowledge_response,
                conversation_route=conversation_route,
                semantic_pre_gate_trace=semantic_pre_gate_trace,
                turn_decision=turn_decision,
                runtime_action=_v7_runtime_action(
                    turn_decision,
                    reason="direct_knowledge_response",
                ),
            )

        if pre_gate.classification is not PreGateClassification.DOMAIN_INQUIRY:
            runtime_mode = (
                _runtime_mode_for_pre_gate(pre_gate.classification.value)
                if _ENABLE_CONVERSATION_RUNTIME
                else "GOVERNED"
            )
            return RuntimeDispatchResolution(
                gate_route=runtime_mode,
                gate_reason=f"pre_gate:{pre_gate.reasoning}",
                runtime_mode=runtime_mode,
                gate_applied=False,
                pre_gate_classification=pre_gate.classification.value,
                pre_gate_reason=pre_gate.reasoning,
                conversation_route=conversation_route,
                semantic_pre_gate_trace=semantic_pre_gate_trace,
                runtime_action=_light_runtime_action(
                    reason=f"pre_gate:{pre_gate.reasoning}",
                ),
            )

        governed_state = None
        if request.session_id:
            knowledge_context = None
            try:
                knowledge_context = await _load_live_knowledge_session_context(
                    current_user=current_user,
                    session_id=request.session_id,
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "[runtime_dispatch] knowledge bridge load failed (%s: %s) — continuing without bridge seed",
                    type(exc).__name__,
                    exc,
                )
            if knowledge_context is not None and (
                knowledge_context.mentioned_parameters
                or knowledge_context.conversation_turns
                or knowledge_context.explored_concepts
            ):
                try:
                    governed_state = await _bridge_knowledge_session_to_governed_state(
                        current_user=current_user,
                        session_id=request.session_id,
                        context=knowledge_context,
                    )
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "[runtime_dispatch] knowledge bridge seed failed (%s: %s) — falling back to plain governed state load",
                        type(exc).__name__,
                        exc,
                    )
            if governed_state is None:
                try:
                    governed_state = await _load_live_governed_state(
                        current_user=current_user,
                        session_id=request.session_id,
                        create_if_missing=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "[runtime_dispatch] governed state load failed (%s: %s) — continuing governed without mutable state override",
                        type(exc).__name__,
                        exc,
                    )
        turn_decision = await _resolve_v8_turn_decision(
            request=request,
            pre_gate=pre_gate,
            governed_state=governed_state,
        )
        runtime_action = _v7_runtime_action(
            turn_decision,
            reason="governed_domain_or_slot_turn",
        )
        if _v7_answer_mode(turn_decision) in {
            AnswerMode.SMALLTALK.value,
            AnswerMode.META_QUESTION.value,
        }:
            return RuntimeDispatchResolution(
                gate_route="CONVERSATION",
                gate_reason=f"v8_semantic_{_v7_answer_mode(turn_decision)}:{pre_gate.reasoning}",
                runtime_mode="CONVERSATION",
                gate_applied=False,
                pre_gate_classification=pre_gate.classification.value,
                pre_gate_reason=pre_gate.reasoning,
                governed_state=governed_state,
                conversation_route=conversation_route,
                semantic_pre_gate_trace=semantic_pre_gate_trace,
                turn_decision=turn_decision,
                runtime_action=runtime_action,
            )
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason=f"pre_gate:{pre_gate.reasoning}",
            runtime_mode="GOVERNED",
            gate_applied=False,
            pre_gate_classification=pre_gate.classification.value,
            pre_gate_reason=pre_gate.reasoning,
            governed_state=governed_state,
            conversation_route=conversation_route,
            semantic_pre_gate_trace=semantic_pre_gate_trace,
            turn_decision=turn_decision,
            runtime_action=runtime_action,
        )

    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[runtime_dispatch] gate/session resolution failed (%s: %s) — fail-closed to conversation fallback",
            type(exc).__name__,
            exc,
        )
        return RuntimeDispatchResolution(
            gate_route="CONVERSATION",
            gate_reason=f"gate_session_fail_closed:{type(exc).__name__}",
            runtime_mode="CONVERSATION",
            gate_applied=False,
            direct_reply=(
                "Ich kann die Anfrage gerade nicht sicher einordnen. "
                "Bitte beschreibe kurz, worum es geht; ich uebernehme dabei keine technische Annahme."
            ),
            runtime_action=_light_runtime_action(
                reason=f"gate_session_fail_closed:{type(exc).__name__}",
                decision_source="runtime_dispatch_exception",
            ),
        )


@traceable(name="sealai.runtime_dispatch", run_type="chain")
async def _resolve_runtime_dispatch(
    request: Any,  # ChatRequest
    *,
    current_user: RequestUser | None,
) -> RuntimeDispatchResolution:
    resolution = await _resolve_runtime_dispatch_impl(
        request,
        current_user=current_user,
    )
    traced_resolution = _with_v91_policy_trace(resolution, request=request)
    emit_quality_trace(
        component="pre_gate_router",
        tags=("runtime-dispatch", "router"),
        request=request,
        current_user=current_user,
        route=traced_resolution.gate_route,
        route_decision=traced_resolution.runtime_mode,
        case_creation_allowed=traced_resolution.runtime_mode == "GOVERNED",
        fallback_reason_hash=stable_trace_hash(traced_resolution.gate_reason),
        fallback_reason_length=len(str(traced_resolution.gate_reason or "")),
        pre_gate_classification=traced_resolution.pre_gate_classification,
        semantic_pre_gate_trace=traced_resolution.semantic_pre_gate_trace,
        semantic_pre_gate_applied=(
            (traced_resolution.semantic_pre_gate_trace or {}).get(
                "semantic_pre_gate_applied"
            )
        ),
        semantic_pre_gate_intent=(
            (traced_resolution.semantic_pre_gate_trace or {}).get(
                "semantic_pre_gate_intent"
            )
        ),
        semantic_pre_gate_classification=(
            (traced_resolution.semantic_pre_gate_trace or {}).get(
                "semantic_pre_gate_classification"
            )
        ),
        semantic_pre_gate_confidence=(
            (traced_resolution.semantic_pre_gate_trace or {}).get(
                "semantic_pre_gate_confidence"
            )
        ),
        conversation_route=getattr(traced_resolution.conversation_route, "route", None),
        runtime_action_type=getattr(traced_resolution.runtime_action, "action", None)
        or getattr(traced_resolution.runtime_action, "action_type", None)
        or getattr(traced_resolution.runtime_action, "kind", None),
        runtime_action_answer_mode=getattr(traced_resolution.runtime_action, "answer_mode", None),
        runtime_action_graph_allowed=getattr(traced_resolution.runtime_action, "graph_allowed", None),
        runtime_action_decision_source=getattr(traced_resolution.runtime_action, "decision_source", None),
        v91_policy_present=getattr(traced_resolution, "v91_policy", None) is not None,
        v92_runtime_present=True,
    )
    return traced_resolution


def _with_v91_policy_trace(
    resolution: RuntimeDispatchResolution,
    *,
    request: Any,
) -> RuntimeDispatchResolution:
    try:
        policy = build_v91_turn_policy(
            message=str(getattr(request, "message", "") or ""),
            pre_gate_classification=resolution.pre_gate_classification,
            pre_gate_reason=resolution.pre_gate_reason or resolution.gate_reason,
            governed_state=resolution.governed_state,
            conversation_route=resolution.conversation_route,
            turn_decision=resolution.turn_decision,
            runtime_action=resolution.runtime_action,
        )
        return dataclasses.replace(
            resolution,
            v91_policy=policy,
            runtime_action=merge_v91_trace_into_runtime_action(
                resolution.runtime_action,
                policy,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[runtime_dispatch] v9.1 policy adapter failed (%s: %s) — continuing with existing runtime action",
            type(exc).__name__,
            exc,
        )
        return resolution


async def _compose_knowledge_answer_if_enabled(
    *,
    user_message: str,
    knowledge_response: Any,
    conversation_route: ConversationRoutingDecision | None,
    recent_history: tuple[Any, ...] = (),
    full_history_context: bool = False,
    knowledge_mode: str | None = None,
) -> Any:
    composer_enabled = _knowledge_answer_composer_enabled()
    debug_enabled = _knowledge_debug_trace_enabled()
    if not composer_enabled and not debug_enabled:
        return _with_knowledge_answer_trace(
            knowledge_response,
            answer_markdown_source="knowledge_service",
            composer_attempted=False,
            composer_succeeded=False,
        )
    if not bool(getattr(knowledge_response, "no_case_created", True)):
        return _with_knowledge_answer_trace(
            knowledge_response,
            answer_markdown_source="knowledge_service",
            composer_attempted=False,
            composer_succeeded=False,
        )

    try:
        from app.agent.communication.knowledge_context_builder import (  # noqa: PLC0415
            KnowledgeContextBuilder,
        )

        answer_view = getattr(knowledge_response, "knowledge_answer_view", None)
        # Prefer the resolved §8 knowledge mode; fall back to the coarse pre-gate
        # source classification when the caller did not resolve a mode.
        resolved_knowledge_mode = knowledge_mode or (
            str(
                getattr(
                    getattr(knowledge_response, "source_classification", None),
                    "value",
                    getattr(knowledge_response, "source_classification", None),
                )
                or ""
            )
            or None
        )
        context_builder = (
            KnowledgeContextBuilder(history_limit=None, history_char_limit=None)
            if full_history_context
            else KnowledgeContextBuilder()
        )
        context = context_builder.build(
            user_message=user_message,
            deterministic_answer=str(getattr(knowledge_response, "content", "") or ""),
            knowledge_response=knowledge_response,
            answer_view=answer_view,
            recent_history=recent_history,
            route_label=(
                getattr(getattr(conversation_route, "route_view", None), "value", None)
                if conversation_route is not None
                else None
            ),
            knowledge_mode=resolved_knowledge_mode,
            intent=(
                getattr(getattr(conversation_route, "intent", None), "value", None)
                if conversation_route is not None
                else None
            ),
            language_hint="de",
        )

        if not composer_enabled:
            response = _with_knowledge_answer_trace(
                knowledge_response,
                answer_markdown_source="knowledge_service",
                composer_attempted=False,
                composer_succeeded=False,
            )
            return _with_knowledge_debug_trace(
                response,
                context=context,
                composer_enabled=False,
                composer_attempted=False,
                composer_succeeded=False,
                answer_markdown_source="reply_passthrough",
            )

        if _should_passthrough_high_fidelity_knowledge_answer(knowledge_response):
            response = _with_knowledge_answer_trace(
                knowledge_response,
                answer_markdown_source="knowledge_service",
                composer_attempted=False,
                composer_succeeded=False,
            )
            if debug_enabled:
                response = _with_knowledge_debug_trace(
                    response,
                    context=context,
                    composer_enabled=True,
                    composer_attempted=False,
                    composer_succeeded=False,
                    answer_markdown_source="reply_passthrough",
                )
            return response

        if _should_passthrough_deterministic_material_comparison(knowledge_response):
            # Material-vs-material stays on the neutral deterministic renderer.
            # Skipping the LLM rewrite removes the comparative-ranking surface
            # at the root (the deterministic comparison carries no preference).
            response = _with_knowledge_answer_trace(
                knowledge_response,
                answer_markdown_source="knowledge_service",
                composer_attempted=False,
                composer_succeeded=False,
            )
            if debug_enabled:
                response = _with_knowledge_debug_trace(
                    response,
                    context=context,
                    composer_enabled=True,
                    composer_attempted=False,
                    composer_succeeded=False,
                    answer_markdown_source="reply_passthrough",
                )
            return response

        from app.agent.communication.answer_composer import (  # noqa: PLC0415
            KnowledgeAnswerComposer,
            KnowledgeAnswerComposerInput,
        )

        request = KnowledgeAnswerComposerInput(
            context=context,
        )
        composed = await KnowledgeAnswerComposer().compose(request)
        answer_markdown = str(getattr(composed, "answer_markdown", "") or "").strip()
        if not answer_markdown:
            raise ValueError("empty_answer_markdown")
        response = dataclasses.replace(
            knowledge_response,
            answer_markdown=answer_markdown,
        )
        response = _with_knowledge_answer_trace(
            response,
            answer_markdown_source="knowledge_composer",
            composer_attempted=True,
            composer_succeeded=True,
        )
        if debug_enabled:
            response = _with_knowledge_debug_trace(
                response,
                context=context,
                composer_enabled=True,
                composer_attempted=True,
                composer_succeeded=True,
                answer_markdown_source="composer",
            )
        return response
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[runtime_dispatch] knowledge answer composer failed (%s); using deterministic answer",
            type(exc).__name__,
        )
        from app.agent.communication.answer_composer import (  # noqa: PLC0415
            KnowledgeAnswerComposerError,
        )

        fallback_response = knowledge_response
        answer_markdown_source = "composer_fallback"
        if isinstance(exc, KnowledgeAnswerComposerError) and str(exc).startswith(
            (
                "unsafe_answer_markdown",
                "unsafe_material_suitability",
                "unsafe_material_ranking",
            )
        ):
            # Doctrine-safety raise must fail CLOSED: never serve the base text,
            # substitute the deterministic neutral guard fallback.
            from app.agent.runtime.output_guard import (  # noqa: PLC0415
                FAST_PATH_GUARD_FALLBACK,
            )

            fallback_response = dataclasses.replace(
                knowledge_response,
                answer_markdown=FAST_PATH_GUARD_FALLBACK,
            )
            answer_markdown_source = "composer_safe_fallback"

        if not debug_enabled:
            return _with_knowledge_answer_trace(
                fallback_response,
                answer_markdown_source=answer_markdown_source,
                composer_attempted=composer_enabled,
                composer_succeeded=False,
                fallback_reason=_safe_composer_fallback_reason(exc),
            )
        response = _with_knowledge_answer_trace(
            fallback_response,
            answer_markdown_source=answer_markdown_source,
            composer_attempted=composer_enabled,
            composer_succeeded=False,
            fallback_reason=_safe_composer_fallback_reason(exc),
        )
        return _with_knowledge_debug_trace(
            response,
            context=locals().get("context"),
            composer_enabled=composer_enabled,
            composer_attempted=composer_enabled,
            composer_succeeded=False,
            answer_markdown_source=answer_markdown_source,
            composer_fallback_reason=_safe_composer_fallback_reason(exc),
        )


def _should_passthrough_high_fidelity_knowledge_answer(knowledge_response: Any) -> bool:
    """Avoid slow/fragile LLM rewriting when deterministic material answer is complete."""

    answer = str(getattr(knowledge_response, "content", "") or "")
    if len(answer) < 2400:
        return False
    if "### Kennwerte" not in answer and "### Technische Richtwerte" not in answer:
        return False

    answer_view = getattr(knowledge_response, "knowledge_answer_view", None)
    evidence_items = tuple(getattr(answer_view, "knowledge_evidence", ()) or ())
    for item in evidence_items:
        note = str(getattr(item, "note", "") or "")
        if note.startswith("system_derived_material_definition:"):
            return True
    return False


def _should_passthrough_deterministic_material_comparison(knowledge_response: Any) -> bool:
    """Keep material-vs-material answers on the neutral deterministic renderer.

    The deterministic KnowledgeService comparison (build_material_comparison_answer
    -> _render_comparison) is symmetric and carries no application ranking.
    Skipping the LLM rewrite removes the comparative-ranking surface at the root.
    """

    answer_view = getattr(knowledge_response, "knowledge_answer_view", None)
    evidence_items = tuple(getattr(answer_view, "knowledge_evidence", ()) or ())
    for item in evidence_items:
        note = str(getattr(item, "note", "") or "")
        if note.startswith("system_derived_material_comparison:"):
            return True
    return False


def _with_knowledge_answer_trace(
    knowledge_response: Any,
    *,
    answer_markdown_source: str,
    composer_attempted: bool,
    composer_succeeded: bool,
    fallback_reason: str | None = None,
) -> Any:
    return dataclasses.replace(
        knowledge_response,
        answer_trace=build_answer_trace(
            reply_source="knowledge_service",
            answer_markdown_source=answer_markdown_source,  # type: ignore[arg-type]
            final_visible_source="answer_markdown",
            composer_attempted=composer_attempted,
            composer_succeeded=composer_succeeded,
            fallback_reason=fallback_reason,
        ),
    )


def _with_knowledge_debug_trace(
    knowledge_response: Any,
    *,
    context: Any | None,
    composer_enabled: bool,
    composer_attempted: bool,
    composer_succeeded: bool,
    answer_markdown_source: Literal[
        "reply_passthrough",
        "composer",
        "composer_fallback",
        "composer_safe_fallback",
    ],
    composer_fallback_reason: str | None = None,
) -> Any:
    trace = _build_knowledge_debug_trace(
        knowledge_response=knowledge_response,
        context=context,
        composer_enabled=composer_enabled,
        composer_attempted=composer_attempted,
        composer_succeeded=composer_succeeded,
        answer_markdown_source=answer_markdown_source,
        composer_fallback_reason=composer_fallback_reason,
    )
    return dataclasses.replace(knowledge_response, knowledge_debug=trace.as_dict())


def _build_knowledge_debug_trace(
    *,
    knowledge_response: Any,
    context: Any | None,
    composer_enabled: bool,
    composer_attempted: bool,
    composer_succeeded: bool,
    answer_markdown_source: Literal[
        "reply_passthrough",
        "composer",
        "composer_fallback",
        "composer_safe_fallback",
    ],
    composer_fallback_reason: str | None = None,
) -> KnowledgeDebugTrace:
    source_classification = getattr(
        getattr(knowledge_response, "source_classification", None),
        "value",
        getattr(knowledge_response, "source_classification", None),
    )
    evidence_items = tuple(getattr(context, "evidence_items", ()) or ())
    evidence_source_types: list[str] = []
    for item in evidence_items:
        source_type = str(getattr(item, "source_type", "unknown") or "unknown")
        if source_type not in evidence_source_types:
            evidence_source_types.append(source_type)
    route = getattr(context, "route_label", None) if context is not None else None
    knowledge_mode = (
        getattr(context, "knowledge_mode", None) if context is not None else None
    )
    return KnowledgeDebugTrace(
        route=str(route or source_classification or "") or None,
        knowledge_mode=str(knowledge_mode or source_classification or "") or None,
        reply_source="knowledge_service",
        answer_markdown_source=answer_markdown_source,
        composer_enabled=bool(composer_enabled),
        composer_attempted=bool(composer_attempted),
        composer_succeeded=bool(composer_succeeded),
        composer_fallback_reason=composer_fallback_reason,
        evidence_count=len(evidence_items),
        evidence_source_types=evidence_source_types,
        history_count=len(tuple(getattr(context, "recent_history", ()) or ())),
        regulatory_currentness_required=bool(
            getattr(context, "regulatory_currentness_required", False)
        ),
        limitations_count=len(tuple(getattr(context, "limitations", ()) or ())),
    )


def _safe_composer_fallback_reason(exc: Exception) -> str:
    reason = str(exc or "").strip()
    if reason in {"invalid_json", "invalid_payload", "empty_answer_markdown"}:
        return reason
    if reason.startswith("unsafe_answer_markdown"):
        return "unsafe_answer_markdown"
    return "composer_exception"
