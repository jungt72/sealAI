import logging
import os
import dataclasses
from typing import Any, Literal

from app.domain.conversation_intent import ConversationRoutingDecision
from app.agent.state.models import GovernedSessionState
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
    return os.environ.get("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "false").lower() in {
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
    fast_response: Any | None = None
    knowledge_response: Any | None = None
    governed_state: GovernedSessionState | None = None
    conversation_route: ConversationRoutingDecision | None = None

async def _resolve_runtime_dispatch(
    request: Any, # ChatRequest
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
            )

        if pre_gate.classification in {
            PreGateClassification.KNOWLEDGE_QUERY,
            PreGateClassification.DEEP_DIVE,
        }:
            from dataclasses import replace  # noqa: PLC0415
            from app.services.knowledge_service import KnowledgeService  # noqa: PLC0415
            from app.services.knowledge_case_bridge_service import KnowledgeCaseBridgeService  # noqa: PLC0415

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
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason=f"pre_gate:{pre_gate.reasoning}",
            runtime_mode="GOVERNED",
            gate_applied=False,
            pre_gate_classification=pre_gate.classification.value,
            pre_gate_reason=pre_gate.reasoning,
            governed_state=governed_state,
            conversation_route=conversation_route,
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
        knowledge_mode = str(
            getattr(
                getattr(knowledge_response, "source_classification", None),
                "value",
                getattr(knowledge_response, "source_classification", None),
            )
            or ""
        ) or None
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
    knowledge_mode = getattr(context, "knowledge_mode", None) if context is not None else None
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
