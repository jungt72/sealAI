import logging
import os
import dataclasses
from typing import Any, Literal

from app.domain.conversation_intent import ConversationRoutingDecision
from app.agent.state.models import GovernedSessionState
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
            if request.session_id:
                try:
                    bridge_service = KnowledgeCaseBridgeService()
                    knowledge_context = await _load_live_knowledge_session_context(
                        current_user=current_user,
                        session_id=request.session_id,
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
