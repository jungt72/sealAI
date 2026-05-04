import logging
import os
import dataclasses
from typing import Any, Literal

from app.domain.conversation_intent import ConversationRoutingDecision
from app.agent.state.models import GovernedSessionState
from app.agent.communication.v7_contracts import (
    AnswerMode,
    RuntimeAction,
    RuntimeAnswerBuilder,
    TurnDecision,
    build_answer_only_runtime_action,
    build_knowledge_override_runtime_action,
    build_rfq_readiness_runtime_action,
    build_runtime_action_from_turn_decision,
)
from app.agent.communication.rfq_intent import (
    build_rfq_readiness_answer,
    classify_rfq_readiness_intent,
)
from app.agent.runtime.answer_trace import build_answer_trace
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

_log = logging.getLogger(__name__)

# Feature flags
_ENABLE_BINARY_GATE: bool = (
    os.environ.get("SEALAI_ENABLE_BINARY_GATE", "true").lower() == "true"
)
_ENABLE_CONVERSATION_RUNTIME: bool = (
    os.environ.get("SEALAI_ENABLE_CONVERSATION_RUNTIME", "true").lower() == "true"
)


def _knowledge_answer_composer_enabled() -> bool:
    return os.environ.get(
        "SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "false"
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


@dataclasses.dataclass(frozen=True, slots=True)
class KnowledgeDebugTrace:
    route: str | None
    knowledge_mode: str | None
    reply_source: str
    answer_markdown_source: Literal[
        "reply_passthrough",
        "composer",
        "composer_fallback",
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
    fast_response: Any | None = None
    knowledge_response: Any | None = None
    knowledge_override_class: str | None = None
    governed_state: GovernedSessionState | None = None
    conversation_route: ConversationRoutingDecision | None = None
    turn_decision: TurnDecision | None = None
    runtime_action: RuntimeAction | None = None


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


def _resolve_v7_turn_decision(
    *,
    request: Any,
    pre_gate: Any,
    governed_state: GovernedSessionState | None,
) -> TurnDecision:
    from app.agent.communication.conversation_controller_v7 import (  # noqa: PLC0415
        ConversationControllerInput,
        ConversationControllerV7,
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
    return ConversationControllerV7().decide(
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
    return build_runtime_action_from_turn_decision(decision, reason=reason)


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
) -> RuntimeAction:
    return build_answer_only_runtime_action(
        answer_mode=AnswerMode.CLARIFICATION,
        answer_builder=RuntimeAnswerBuilder.LIGHT_RUNTIME,
        reason=reason,
        decision_source=decision_source,
        graph_invocation_skipped_reason="light_runtime_does_not_require_governed_graph",
        next_runtime_action="run_light_runtime",
    )


async def _resolve_runtime_dispatch(
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

    try:
        from app.domain.pre_gate_classification import PreGateClassification  # noqa: PLC0415
        from app.domain.conversation_intent import classify_conversation_route  # noqa: PLC0415
        from app.services.fast_responder_service import FastResponderService  # noqa: PLC0415
        from app.services.pre_gate_classifier import PreGateClassifier  # noqa: PLC0415

        pre_gate = PreGateClassifier().classify(request.message)
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
                    governed_state=governed_state,
                    conversation_route=conversation_route,
                    runtime_action=build_rfq_readiness_runtime_action(
                        rfq_action_type=rfq_answer.rfq_action_type,
                        action_type=rfq_answer.action_type,
                        reason=rfq_intent.reason,
                        trace=rfq_answer.trace,
                    ),
                )
        if pre_gate.classification is PreGateClassification.META_QUESTION and request.session_id:
            governed_state = await _load_existing_governed_state_for_v7(
                request=request,
                current_user=current_user,
            )
            turn_decision = _resolve_v7_turn_decision(
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
                    turn_decision=turn_decision,
                    runtime_action=_v7_runtime_action(
                        turn_decision,
                        reason="active_case_process_question_before_governed_graph",
                    ),
                )
        if pre_gate.classification in FastResponderService.allowed_classifications:
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
            if request.session_id and _knowledge_turn_needs_active_case_probe(
                request.message
            ):
                governed_state = await _load_existing_governed_state_for_v7(
                    request=request,
                    current_user=current_user,
                )
            turn_decision = _resolve_v7_turn_decision(
                request=request,
                pre_gate=pre_gate,
                governed_state=governed_state,
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
                    turn_decision=turn_decision,
                    runtime_action=_v7_runtime_action(
                        turn_decision,
                        reason="active_case_side_or_process_question_before_governed_graph",
                    ),
                )

            from dataclasses import replace  # noqa: PLC0415
            from app.services.knowledge_service import KnowledgeService  # noqa: PLC0415
            from app.services.knowledge_case_bridge_service import (
                KnowledgeCaseBridgeService,
            )  # noqa: PLC0415

            knowledge_response = KnowledgeService().answer(
                request.message,
                source_classification=pre_gate.classification,
            )
            recent_knowledge_history: tuple[Any, ...] = ()
            if request.session_id:
                try:
                    bridge_service = KnowledgeCaseBridgeService()
                    knowledge_context = await _load_live_knowledge_session_context(
                        current_user=current_user,
                        session_id=request.session_id,
                    )
                    if knowledge_context is not None:
                        recent_knowledge_history = tuple(
                            getattr(knowledge_context, "conversation_turns", ()) or ()
                        )
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
        turn_decision = _resolve_v7_turn_decision(
            request=request,
            pre_gate=pre_gate,
            governed_state=governed_state,
        )
        runtime_action = _v7_runtime_action(
            turn_decision,
            reason="governed_domain_or_slot_turn",
        )
        if bool(getattr(runtime_action, "graph_allowed", False)) and not bool(
            getattr(runtime_action, "slot_candidate_detected", False)
        ):
            from app.agent.api.knowledge_override import (  # noqa: PLC0415
                build_case_side_knowledge_response,
            )
            from app.agent.graph.output_contract_assembly import (  # noqa: PLC0415
                classify_message_as_knowledge_override,
            )

            knowledge_override = classify_message_as_knowledge_override(
                request.message
            )
            if knowledge_override is not None:
                knowledge_response = await build_case_side_knowledge_response(
                    message=request.message,
                    override_class=knowledge_override,
                    conversation_route=conversation_route,
                    governed_state=governed_state,
                )
                return RuntimeDispatchResolution(
                    gate_route="CONVERSATION",
                    gate_reason=f"runtime_action_knowledge_override:{knowledge_override}",
                    runtime_mode="CONVERSATION",
                    gate_applied=False,
                    pre_gate_classification=pre_gate.classification.value,
                    pre_gate_reason=pre_gate.reasoning,
                    knowledge_response=knowledge_response,
                    knowledge_override_class=knowledge_override,
                    governed_state=governed_state,
                    conversation_route=conversation_route,
                    turn_decision=turn_decision,
                    runtime_action=build_knowledge_override_runtime_action(
                        override_class=knowledge_override,
                        active_case_exists=_governed_state_has_active_case(
                            governed_state
                        ),
                    ),
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


async def _compose_knowledge_answer_if_enabled(
    *,
    user_message: str,
    knowledge_response: Any,
    conversation_route: ConversationRoutingDecision | None,
    recent_history: tuple[Any, ...] = (),
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
        knowledge_mode = (
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
        context = KnowledgeContextBuilder().build(
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
            knowledge_mode=knowledge_mode,
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
        if not debug_enabled:
            return _with_knowledge_answer_trace(
                knowledge_response,
                answer_markdown_source="composer_fallback",
                composer_attempted=composer_enabled,
                composer_succeeded=False,
                fallback_reason=_safe_composer_fallback_reason(exc),
            )
        response = _with_knowledge_answer_trace(
            knowledge_response,
            answer_markdown_source="composer_fallback",
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
            answer_markdown_source="composer_fallback",
            composer_fallback_reason=_safe_composer_fallback_reason(exc),
        )


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
