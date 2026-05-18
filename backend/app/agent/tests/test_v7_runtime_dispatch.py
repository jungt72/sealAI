from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.agent.api.dispatch import RuntimeDispatchResolution, _resolve_runtime_dispatch
from app.agent.api.models import ChatRequest, ChatResponse
from app.agent.api.routes.chat import chat_endpoint
from app.agent.api.streaming import event_generator
from app.agent.communication.conversation_controller_v7 import (
    ConversationControllerInput,
    ConversationControllerV7,
)
from app.agent.communication.v7_contracts import (
    AnswerMode,
    MutationPolicy,
    RuntimeAnswerBuilder,
    RuntimeActionType,
)
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    ConversationMessage,
    GovernedSessionState,
    PendingQuestion,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.domain.source_validation import SourceType, ValidationStatus
from app.services.auth.dependencies import RequestUser
from app.services.knowledge_service import (
    KNOWLEDGE_RAG_HIT_LABEL,
    KnowledgeAnswerResult,
    KnowledgeEvidence,
    KnowledgeResponse,
)
from app.services.pre_gate_classifier import ClassificationResult, PreGateClassifier


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


@pytest.fixture(autouse=True)
def _disable_active_case_llm_composers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_ACTIVE_CASE_PROCESS_ANSWER_COMPOSER", "false")
    monkeypatch.setenv("SEALAI_ENABLE_ACTIVE_CASE_SIDE_ANSWER_COMPOSER", "false")


def _pending_medium_question() -> PendingQuestion:
    return PendingQuestion(
        target_field="medium",
        expected_answer_type="medium_value",
        question_text="Welches Medium soll abgedichtet werden?",
        ambiguity_policy="clarify_if_broad_or_hazardous",
        source="governed_next_question",
        status="open",
    )


def _active_state() -> GovernedSessionState:
    return GovernedSessionState(
        conversation_messages=[
            ConversationMessage(
                role="user", content="servus, ich brauche eine Dichtungsloesung"
            ),
            ConversationMessage(
                role="assistant", content="Welches Medium soll abgedichtet werden?"
            ),
        ],
        pending_question=_pending_medium_question(),
        user_turn_index=2,
    )


def _active_state_with_medium_asserted() -> GovernedSessionState:
    return GovernedSessionState(
        conversation_messages=[
            ConversationMessage(
                role="user", content="servus, ich brauche eine Dichtungsloesung"
            ),
            ConversationMessage(
                role="assistant", content="Welches Medium soll abgedichtet werden?"
            ),
        ],
        pending_question=_pending_medium_question(),
        asserted=AssertedState(
            assertions={
                "medium": AssertedClaim(
                    field_name="medium",
                    asserted_value="Wasser",
                    confidence="confirmed",
                )
            },
            blocking_unknowns=["temperature_c", "pressure_bar"],
        ),
        user_turn_index=3,
    )


def _knowledge_response_with_fact_evidence(content: str) -> KnowledgeResponse:
    return KnowledgeResponse(
        content=content,
        answer_markdown=content,
        answer_result=KnowledgeAnswerResult(
            answer=content,
            answer_available=True,
            rag_lookup_attempted=True,
            rag_answer_found=True,
            rag_miss=False,
            source_type=SourceType.rag_verified,
            validation_status=ValidationStatus.documented,
            user_visible_label=KNOWLEDGE_RAG_HIT_LABEL,
            knowledge_evidence=(
                KnowledgeEvidence(
                    source_type="fact_card",
                    title="Elastomer-Werkstoffkontext",
                    content=(
                        "FKM wird haeufig bei Oelen, Kraftstoffen und hoeheren Temperaturen betrachtet; "
                        "NBR wird haeufig bei Oelen, Fetten und moderaten Bedingungen betrachtet."
                    ),
                    source_name="SeaLAI FactCard",
                    note="documented",
                ),
            ),
        ),
    )


def test_pre_gate_treats_thanks_with_tail_as_social_conversation() -> None:
    result = PreGateClassifier().classify("danke nach dem fix")

    assert result.classification is PreGateClassification.GREETING
    assert result.reasoning == "deterministic_social_conversation"
    assert result.escalate_to_graph is False


@pytest.mark.asyncio
async def test_active_case_social_thanks_uses_light_conversation_not_governed_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="danke nach dem fix", session_id="active-case"),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.fast_response is None
    assert dispatch.governed_state is state
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ANSWER_ONLY
    assert dispatch.runtime_action.answer_builder == RuntimeAnswerBuilder.LIGHT_RUNTIME
    assert dispatch.runtime_action.graph_allowed is False
    assert dispatch.runtime_action.graph_invocation_skipped_reason == (
        "light_runtime_does_not_require_governed_graph"
    )
    load_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_case_context_recall_routes_to_process_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Was wollte ich von dir?", session_id="active-case"),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.governed_state is state
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.ACTIVE_CASE_PROCESS_QUESTION
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ANSWER_THEN_RESUME
    assert dispatch.runtime_action.answer_builder == RuntimeAnswerBuilder.ACTIVE_CASE_PROCESS
    assert dispatch.runtime_action.graph_allowed is False
    load_state.assert_awaited_once()


def _process_decision(message: str, state: GovernedSessionState):
    pre_gate = PreGateClassifier().classify(message)
    return ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=state.pending_question,
        )
    )


async def _collect_sse_payloads(gen):
    payloads: list[dict] = []
    async for frame in gen:
        if not isinstance(frame, str) or not frame.startswith("data: "):
            continue
        raw = frame[6:].strip()
        if raw == "[DONE]":
            payloads.append({"type": "__DONE__"})
            continue
        payloads.append(json.loads(raw))
    return payloads


@pytest.mark.asyncio
async def test_active_case_material_followup_routes_as_v7_side_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="und FKM mit NBR?", session_id="active-case"),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.knowledge_response is None
    assert dispatch.governed_state is state
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert dispatch.turn_decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert dispatch.turn_decision.resume_target_candidate is not None
    assert dispatch.turn_decision.resume_target_candidate.target_field == "medium"
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ANSWER_THEN_RESUME
    assert dispatch.runtime_action.graph_allowed is False
    assert dispatch.runtime_action.graph_invocation_skipped_reason == (
        "active_case_side_question_answered_by_communication_runtime"
    )
    load_state.assert_awaited_once_with(
        current_user=_user(),
        session_id="active-case",
        create_if_missing=False,
    )


@pytest.mark.asyncio
async def test_active_case_material_limit_question_routes_as_side_question_not_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Ich benötige die Grenzwerte von PTFE.",
            session_id="active-case",
        ),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.knowledge_response is None
    assert dispatch.governed_state is state
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert dispatch.turn_decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ANSWER_THEN_RESUME
    assert dispatch.runtime_action.answer_builder == RuntimeAnswerBuilder.ACTIVE_CASE_SIDE
    assert dispatch.runtime_action.graph_allowed is False
    load_state.assert_awaited_once_with(
        current_user=_user(),
        session_id="active-case",
        create_if_missing=False,
    )


@pytest.mark.asyncio
async def test_active_case_explanatory_term_question_routes_as_v7_side_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="was genau ist chloroxyd?", session_id="active-case"),
        current_user=_user(),
    )

    assert (
        dispatch.pre_gate_classification == PreGateClassification.KNOWLEDGE_QUERY.value
    )
    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.knowledge_response is None
    assert dispatch.governed_state is state
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert dispatch.turn_decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert dispatch.turn_decision.resume_target_candidate is not None
    assert dispatch.turn_decision.resume_target_candidate.target_field == "medium"
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ANSWER_THEN_RESUME
    assert dispatch.runtime_action.graph_allowed is False
    load_state.assert_awaited_once_with(
        current_user=_user(),
        session_id="active-case",
        create_if_missing=False,
    )


@pytest.mark.asyncio
async def test_no_case_material_comparison_stays_direct_knowledge_without_case_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_state = AsyncMock(
        side_effect=AssertionError(
            "no-case knowledge without session must not load governed state"
        )
    )
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="bitte vergleiche NBR und PTFE fuer mich", session_id=None),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.governed_state is None
    assert dispatch.knowledge_response is not None
    assert dispatch.knowledge_response.no_case_created is True
    assert "Werkstoffvergleich: NBR vs PTFE" in dispatch.knowledge_response.content
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.MATERIAL_COMPARISON
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ANSWER_ONLY
    assert dispatch.runtime_action.graph_allowed is False
    load_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_case_term_question_uses_runtime_action_answer_only_knowledge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_state = AsyncMock(
        side_effect=AssertionError("no-case knowledge must not load governed state")
    )
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Was ist ein Radialwellendichtring?", session_id=None),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.knowledge_response is not None
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.NO_CASE_KNOWLEDGE
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ANSWER_ONLY
    assert dispatch.runtime_action.answer_builder == RuntimeAnswerBuilder.KNOWLEDGE
    assert dispatch.runtime_action.graph_allowed is False
    assert dispatch.runtime_action.graph_invocation_skipped_reason == (
        "no_case_knowledge_answered_by_knowledge_path"
    )
    load_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_case_knowledge_question_forced_domain_is_v8_side_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    monkeypatch.setattr(
        PreGateClassifier,
        "classify",
        lambda self, message, language_hint=None: ClassificationResult(
            classification=PreGateClassification.DOMAIN_INQUIRY,
            confidence=0.88,
            reasoning="forced_domain_for_v8_side_question",
            escalate_to_graph=True,
        ),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_governed_state",
        AsyncMock(return_value=state),
    )
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Was ist ein Radialwellendichtring?", session_id="active-case"),
        current_user=_user(),
    )

    assert dispatch.knowledge_response is None
    assert dispatch.knowledge_override_class is None
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ANSWER_THEN_RESUME
    assert dispatch.runtime_action.answer_builder == RuntimeAnswerBuilder.ACTIVE_CASE_SIDE
    assert dispatch.runtime_action.graph_allowed is False
    assert dispatch.runtime_action.graph_invocation_skipped_reason == (
        "active_case_side_question_answered_by_communication_runtime"
    )
    assert dispatch.runtime_action.as_trace()["decision_source"] == "communication_runtime_v8"


@pytest.mark.asyncio
async def test_domain_inquiry_builds_runtime_action_for_governed_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Ich brauche eine Dichtung fuer eine Pumpe",
            session_id="active-case",
        ),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.GOVERNED_INTAKE
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ENTER_GOVERNED_GRAPH
    assert dispatch.runtime_action.graph_allowed is True
    assert dispatch.runtime_action.graph_entry_reason == "governed_intake_or_domain_continuation"
    load_state.assert_awaited_once_with(
        current_user=_user(),
        session_id="active-case",
        create_if_missing=True,
    )


def _assert_active_rfq_graph_dispatch(
    dispatch: RuntimeDispatchResolution,
    *,
    rfq_action_type: str,
) -> None:
    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.rfq_response is None
    assert dispatch.rfq_readiness_projection is None
    assert dispatch.governed_state is not None
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ENTER_GOVERNED_GRAPH
    assert dispatch.runtime_action.answer_mode == AnswerMode.RFQ_READINESS
    assert dispatch.runtime_action.answer_builder == RuntimeAnswerBuilder.GOVERNED_OUTPUT_CONTRACT
    assert dispatch.runtime_action.mutation_policy == MutationPolicy.FORBIDDEN
    assert dispatch.runtime_action.graph_allowed is True
    assert dispatch.runtime_action.graph_entry_reason == "rfq_readiness_requires_governed_graph"
    assert dispatch.runtime_action.decision_source == "rfq_readiness_intent"

    trace = dispatch.runtime_action.as_trace()
    assert trace["answer_mode"] == "rfq_readiness"
    assert trace["runtime_action_type"] == "enter_governed_graph"
    assert trace["runtime_answer_builder"] == "governed_output_contract"
    assert trace["graph_allowed"] is True
    assert trace["graph_entry_reason"] == "rfq_readiness_requires_governed_graph"
    assert trace["rfq_intent_detected"] is True
    assert trace["rfq_action_type"] == rfq_action_type
    assert trace["dispatch_allowed"] is False
    assert trace["external_contact_allowed"] is False
    assert trace["consent_required"] is True
    assert trace["manufacturer_review_framing"] is True
    assert trace["final_approval_claim_allowed"] is False
    assert trace["governed_graph_bypassed"] is False
    assert trace["v92_route_hint"] == "rfq_readiness"


@pytest.mark.asyncio
async def test_active_case_rfq_readiness_question_enters_governed_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Ist meine Anfrage vollstaendig?", session_id="active-case"),
        current_user=_user(),
    )

    _assert_active_rfq_graph_dispatch(dispatch, rfq_action_type="show_readiness")
    load_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_case_rfq_missing_for_manufacturer_preserves_next_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Was fehlt noch fuer den Hersteller?", session_id="active-case"),
        current_user=_user(),
    )

    _assert_active_rfq_graph_dispatch(dispatch, rfq_action_type="show_missing_fields")
    load_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_case_create_inquiry_deferred_until_fields_and_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Erstelle mir eine Anfrage", session_id="active-case"),
        current_user=_user(),
    )

    _assert_active_rfq_graph_dispatch(dispatch, rfq_action_type="build_rfq_basis")
    load_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_case_manufacturer_send_requires_consent_and_no_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Kann ich das an einen Hersteller schicken?", session_id="active-case"),
        current_user=_user(),
    )

    _assert_active_rfq_graph_dispatch(dispatch, rfq_action_type="external_contact_request")
    load_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_active_case_create_inquiry_asks_for_qualification_without_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_state = AsyncMock(
        side_effect=AssertionError("no-session RFQ intent must not load governed state")
    )
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    async def fail_governed(*args, **kwargs):
        raise AssertionError("no active case RFQ intent must not enter governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response",
        fail_governed,
    )

    response = await chat_endpoint(
        ChatRequest(message="Erstelle mir eine Anfrage", session_id=None),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert "qualifizierten Dichtungsfall" in answer
    assert "keine Herstelleranfrage" in answer
    assert "Um welche Dichtung oder Anwendung geht es?" in answer
    projection = response.rfq_readiness_projection or {}
    assert projection["manufacturer_review_ready"] is False
    assert projection["rfq_basis_ready"] is False
    assert projection["preview_possible"] is False
    assert projection["preview_available"] is False
    assert projection["preview_action_available"] is False
    assert projection["preview_blocking_reason"] == "no_active_case"
    trace = response.run_meta["answer_trace"]
    assert trace["runtime_action_type"] == "defer_rfq_until_required_fields"
    assert trace["active_case_exists"] is False
    assert trace["graph_allowed"] is False
    assert trace["dispatch_allowed"] is False
    load_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_endpoint_preserves_v7_side_question_as_knowledge_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pre_gate = PreGateClassifier().classify("und FKM mit NBR?")
    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message="und FKM mit NBR?",
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=_pending_medium_question(),
        )
    )
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_side_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=PreGateClassification.KNOWLEDGE_QUERY.value,
        pre_gate_reason="deterministic_material_comparison_knowledge",
        governed_state=_active_state(),
        turn_decision=decision,
    )
    side_answer = _knowledge_response_with_fact_evidence(
        "## Werkstoffvergleich: FKM vs NBR\n\n"
        "FKM wird haeufig bei Oelen, Kraftstoffen und hoeheren Temperaturen betrachtet. "
        "NBR wird haeufig bei Oelen, Fetten und moderaten Bedingungen betrachtet."
    )

    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    build_side = AsyncMock(return_value=side_answer)
    monkeypatch.setattr(
        "app.agent.api.routes.chat.build_case_side_knowledge_response", build_side
    )

    async def fail_governed(*args, **kwargs):
        raise AssertionError("active-case side question must not enter governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )

    response = await chat_endpoint(
        ChatRequest(message="und FKM mit NBR?", session_id="active-case"),
        current_user=_user(),
    )

    assert "Werkstoffvergleich: FKM vs NBR" in response.answer_markdown
    assert "Oelen" in response.answer_markdown
    assert "Kraftstoffen" in response.answer_markdown
    assert "Evidenzkontext: Elastomer-Werkstoffkontext" in response.answer_markdown
    assert "Herstellerpruefung" in response.answer_markdown
    assert "Welches Medium soll abgedichtet werden?" in response.answer_markdown
    assert "final approved solution" not in response.answer_markdown.casefold()
    assert "guaranteed suitable" not in response.answer_markdown.casefold()
    assert "garantiert geeignet" not in response.answer_markdown.casefold()
    assert response.structured_state is None
    assert response.proposed_case_delta is None
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["mutation_policy"] == "forbidden"
    assert trace["resume_reevaluation_attempted"] is True
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"
    assert trace["resume_target_field"] == "medium"
    assert trace["governed_graph_bypassed"] is True
    assert trace["claim_policy_applied"] is True
    assert trace["speakable_facts_built"] is True
    assert trace["claim_policy_result"] == "rewritten"
    assert trace["forbidden_claims_detected"] == []
    assert trace["latest_user_question_answered"] is True
    assert trace["pending_question_restored"] is True
    assert trace["answer_safety_fallback_used"] is False
    assert trace["evidence_context_built"] is True
    assert trace["evidence_context_available"] is True
    assert trace["evidence_refs_count"] == 1
    assert trace["evidence_source_validation_status"] == ["documented"]
    assert trace["evidence_used_in_answer"] is True
    assert trace["evidence_fallback_reason"] is None
    assert trace["runtime_action_built"] is True
    assert trace["runtime_action_type"] == "answer_then_resume"
    assert trace["graph_allowed"] is False
    assert trace["graph_invocation_skipped_reason"] == (
        "active_case_side_question_answered_by_communication_runtime"
    )
    assert trace["operational_contract_version"] == "runtime_action_v1"
    build_side.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_case_medium_definition_side_answer_resumes_pending_medium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Was bedeutet Medium?"
    pre_gate = PreGateClassifier().classify(message)
    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=_pending_medium_question(),
        )
    )
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_side_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=PreGateClassification.KNOWLEDGE_QUERY.value,
        pre_gate_reason="deterministic_knowledge_query",
        governed_state=_active_state(),
        turn_decision=decision,
    )
    side_answer = KnowledgeResponse(
        content="Mit Medium ist der Stoff gemeint, der an der Dichtung anliegt.",
        answer_markdown="Mit Medium ist der Stoff gemeint, der an der Dichtung anliegt.",
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat.build_case_side_knowledge_response",
        AsyncMock(return_value=side_answer),
    )

    async def fail_governed(*args, **kwargs):
        raise AssertionError("active-case side question must not enter governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert "Stoff" in answer
    assert "Werkstoffbestaendigkeit" in answer
    assert "Quellung" in answer
    assert "Ich setze dabei kein Medium voraus" in answer
    assert "Welches Medium soll abgedichtet werden?" in answer
    assert "Wasser" not in answer
    assert response.proposed_case_delta is None
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["resume_reevaluation_attempted"] is True
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"
    assert trace["pending_question_restored"] is True
    assert trace["governed_graph_bypassed"] is True
    assert trace["claim_policy_applied"] is True
    assert trace["claim_policy_result"] == "rewritten"
    assert trace["evidence_context_built"] is True
    assert trace["evidence_context_available"] is False
    assert trace["evidence_refs_count"] == 0
    assert trace["evidence_used_in_answer"] is False
    assert trace["evidence_fallback_reason"] == "rag_miss"
    assert trace["runtime_action_type"] == "answer_then_resume"
    assert trace["graph_allowed"] is False


@pytest.mark.asyncio
async def test_active_case_why_medium_important_side_answer_uses_claim_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Warum ist das Medium wichtig?"
    pre_gate = PreGateClassifier().classify(message)
    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=_pending_medium_question(),
        )
    )
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_side_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=pre_gate.classification.value,
        pre_gate_reason=pre_gate.reasoning,
        governed_state=_active_state(),
        turn_decision=decision,
    )
    side_answer = KnowledgeResponse(
        content="Das Medium beeinflusst die Werkstoffauswahl.",
        answer_markdown="Das Medium beeinflusst die Werkstoffauswahl.",
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat.build_case_side_knowledge_response",
        AsyncMock(return_value=side_answer),
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert "Werkstoffauswahl" in answer
    assert "Werkstoffbestaendigkeit" in answer
    assert "Ich setze dabei kein Medium voraus" in answer
    assert "Wasser" not in answer
    assert "Welches Medium soll abgedichtet werden?" in answer
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"
    assert trace["claim_policy_applied"] is True
    assert trace["claim_policy_result"] == "rewritten"
    assert trace["evidence_context_built"] is True
    assert trace["evidence_refs_count"] == 0
    assert trace["evidence_used_in_answer"] is False
    assert trace["runtime_action_type"] == "answer_then_resume"
    assert trace["graph_allowed"] is False


@pytest.mark.asyncio
async def test_active_case_side_answer_uses_llm_composer_without_blunt_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Bitte gebe mir detaillierte Informationen ueber PTFE"
    monkeypatch.setenv("SEALAI_ENABLE_ACTIVE_CASE_SIDE_ANSWER_COMPOSER", "true")
    pre_gate = PreGateClassifier().classify(message)
    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=_pending_medium_question(),
        )
    )
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_side_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=pre_gate.classification.value,
        pre_gate_reason=pre_gate.reasoning,
        governed_state=_active_state(),
        turn_decision=decision,
    )
    side_answer = KnowledgeResponse(
        content="PTFE ist ein thermoplastischer Fluorpolymer-Werkstoff.",
        answer_markdown="PTFE ist ein thermoplastischer Fluorpolymer-Werkstoff.",
    )

    async def fake_side_composer(**kwargs):  # noqa: ANN003
        assert kwargs["message"] == message
        assert "PTFE" in kwargs["grounded_answer"]
        return (
            "PTFE ist fuer deinen Kontext vor allem als chemisch sehr bestaendiger, "
            "nicht elastischer Werkstoff interessant. Ich wuerde ihn im laufenden "
            "Fall nur als Werkstoffoption betrachten, nicht als Freigabe. "
            "Welches Medium soll abgedichtet werden?"
        )

    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat.build_case_side_knowledge_response",
        AsyncMock(return_value=side_answer),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._compose_active_case_side_answer_with_llm",
        fake_side_composer,
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert "PTFE ist fuer deinen Kontext" in answer
    assert "Welches Medium soll abgedichtet werden?" not in answer
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["composer_attempted"] is True
    assert trace["composer_succeeded"] is True
    assert trace["answer_markdown_source"] == "governed_composer"


@pytest.mark.asyncio
async def test_active_case_help_question_answer_markdown_answers_question_before_medium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Wie kannst du mir bei meiner Dichtungssituation helfen?"
    state = _active_state()
    decision = _process_decision(message, state)
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_process_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY.value,
        pre_gate_reason="ambiguous_fail_safe_domain_inquiry",
        governed_state=state,
        turn_decision=decision,
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._persist_live_governed_state",
        AsyncMock(),
    )

    async def fail_governed(*args, **kwargs):
        raise AssertionError("process/help question must not enter governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response",
        fail_governed,
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert answer
    assert answer != "Welches Medium soll abgedichtet werden?"
    assert answer.find("Dichtungssituation") < answer.rfind("Medium")
    assert "Welches Medium soll abgedichtet werden?" in answer
    assert response.proposed_case_delta is None
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_process_question"
    assert trace["mutation_policy"] == "forbidden"
    assert trace["resume_reevaluation_attempted"] is True
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"
    assert trace["resume_target_field"] == "medium"
    assert trace["governed_graph_bypassed"] is True
    assert trace["latest_user_question_answered"] is True
    assert trace["pending_question_restored"] is True
    assert trace["runtime_action_built"] is True
    assert trace["runtime_action_type"] == "answer_then_resume"
    assert trace["graph_allowed"] is False
    assert trace["graph_invocation_skipped_reason"] == (
        "active_case_process_question_answered_by_communication_runtime"
    )


@pytest.mark.asyncio
async def test_chat_endpoint_enters_governed_graph_for_enter_graph_runtime_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Ich brauche eine Dichtung fuer eine Pumpe"
    pre_gate = PreGateClassifier().classify(message)
    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=_pending_medium_question(),
        )
    )
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="pre_gate:deterministic_domain_inquiry",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY.value,
        pre_gate_reason="deterministic_domain_inquiry",
        governed_state=_active_state(),
        turn_decision=decision,
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )

    async def fake_governed(
        request,
        *,
        current_user,
        pre_gate_classification=None,
        runtime_action=None,
    ):
        assert runtime_action is not None
        assert runtime_action.action_type == RuntimeActionType.ENTER_GOVERNED_GRAPH
        assert runtime_action.graph_allowed is True
        assert runtime_action.graph_entry_reason == "governed_intake_or_domain_continuation"
        return ChatResponse(
            session_id=request.session_id,
            reply="Graph path",
            answer_markdown="Graph path",
            structured_state=None,
            policy_path="governed",
            run_meta={
                "answer_trace": runtime_action.as_trace(),
            },
        )

    run_governed = AsyncMock(side_effect=fake_governed)
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response",
        run_governed,
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    assert response.answer_markdown == "Graph path"
    assert response.run_meta["answer_trace"]["runtime_action_type"] == "enter_governed_graph"
    run_governed.assert_awaited_once()


@pytest.mark.asyncio
async def test_why_medium_question_explains_reason_then_restores_pending_medium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Warum fragst du nach dem Medium?"
    state = _active_state()
    decision = _process_decision(message, state)
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_process_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=PreGateClassification.DEEP_DIVE.value,
        pre_gate_reason="deterministic_deep_dive",
        governed_state=state,
        turn_decision=decision,
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._persist_live_governed_state",
        AsyncMock(),
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert "Werkstoffauswahl" in answer
    assert "Risikobewertung" in answer
    assert "Welches Medium soll abgedichtet werden?" in answer
    assert response.proposed_case_delta is None
    trace = response.run_meta["answer_trace"]
    assert trace["mutation_policy"] == "forbidden"
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"
    assert trace["resume_reason"] == "pending_question_still_open_and_no_slot_answer_detected"


@pytest.mark.asyncio
async def test_process_help_question_does_not_enter_governed_graph_as_plain_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Was machst du jetzt genau?"
    state = _active_state()
    decision = _process_decision(message, state)
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_process_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=PreGateClassification.META_QUESTION.value,
        pre_gate_reason="deterministic_meta_question",
        governed_state=state,
        turn_decision=decision,
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._persist_live_governed_state",
        AsyncMock(),
    )

    async def fail_governed(*args, **kwargs):
        raise AssertionError("process/help question must not enter governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response",
        fail_governed,
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    assert response.answer_markdown
    assert response.answer_markdown != "Welches Medium soll abgedichtet werden?"
    assert "Welches Medium soll abgedichtet werden?" in response.answer_markdown
    trace = response.run_meta["answer_trace"]
    assert trace["governed_graph_bypassed"] is True
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"


@pytest.mark.asyncio
async def test_pending_medium_answer_wasser_still_routes_as_slot_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _active_state()
    load_state = AsyncMock(return_value=state)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Wasser", session_id="active-case"),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.turn_decision is not None
    assert dispatch.turn_decision.answer_mode == AnswerMode.PENDING_SLOT_ANSWER
    assert dispatch.turn_decision.answer_mode != AnswerMode.ACTIVE_CASE_PROCESS_QUESTION
    assert dispatch.turn_decision.state_actions[0].field == "medium"
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.action_type == RuntimeActionType.ENTER_GOVERNED_GRAPH
    assert dispatch.runtime_action.graph_allowed is True
    assert dispatch.runtime_action.graph_entry_reason == "pending_slot_answer_requires_governed_validation"
    assert dispatch.runtime_action.slot_candidate_detected is True


@pytest.mark.asyncio
async def test_mixed_medium_answer_and_why_question_marks_slot_answer_without_blind_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Das Medium ist Wasser. Warum ist das wichtig?"
    state = _active_state()
    pre_gate = PreGateClassifier().classify(message)
    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=state.pending_question,
        )
    )
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_side_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=pre_gate.classification.value,
        pre_gate_reason=pre_gate.reasoning,
        governed_state=state,
        turn_decision=decision,
    )
    side_answer = KnowledgeResponse(
        content=(
            "Das Medium ist wichtig, weil es Werkstoffauswahl, "
            "Bestaendigkeit und Risikobewertung beeinflusst."
        ),
        answer_markdown=(
            "Das Medium ist wichtig, weil es Werkstoffauswahl, "
            "Bestaendigkeit und Risikobewertung beeinflusst."
        ),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat.build_case_side_knowledge_response",
        AsyncMock(return_value=side_answer),
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert "Werkstoffauswahl" in answer
    assert "Wasser" in answer
    assert "Welches Medium soll abgedichtet werden?" not in answer
    assert response.proposed_case_delta is None
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["resume_strategy"] == "accept_or_route_pending_slot_answer"
    assert trace["slot_answer_detected"] is True
    assert trace["resume_target_field"] == "medium"
    assert trace["pending_question_restored"] is False
    assert trace["case_delta_allowed"] is False
    assert trace["governed_graph_allowed"] is True
    assert trace["claim_policy_applied"] is True
    assert trace["evidence_context_built"] is True
    assert trace["evidence_refs_count"] == 0
    assert trace["evidence_used_in_answer"] is False


@pytest.mark.asyncio
async def test_mixed_medium_answer_and_side_question_marks_slot_without_blind_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Das Medium ist Wasser. Was bedeutet Medium?"
    pre_gate = PreGateClassifier().classify(message)
    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=_pending_medium_question(),
        )
    )
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_side_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=pre_gate.classification.value,
        pre_gate_reason=pre_gate.reasoning,
        governed_state=_active_state(),
        turn_decision=decision,
    )
    side_answer = KnowledgeResponse(
        content="Mit Medium ist der Stoff gemeint, der an der Dichtung anliegt.",
        answer_markdown="Mit Medium ist der Stoff gemeint, der an der Dichtung anliegt.",
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat.build_case_side_knowledge_response",
        AsyncMock(return_value=side_answer),
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert "Stoff" in answer
    assert "Wasser" in answer
    assert "Welches Medium soll abgedichtet werden?" not in answer
    assert response.proposed_case_delta is None
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["resume_strategy"] == "accept_or_route_pending_slot_answer"
    assert trace["slot_answer_detected"] is True
    assert trace["pending_question_restored"] is False
    assert trace["case_delta_allowed"] is False


@pytest.mark.asyncio
async def test_process_question_reprioritizes_when_pending_medium_already_asserted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Was machst du jetzt genau?"
    state = _active_state_with_medium_asserted()
    decision = _process_decision(message, state)
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_process_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=PreGateClassification.META_QUESTION.value,
        pre_gate_reason="deterministic_meta_question",
        governed_state=state,
        turn_decision=decision,
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._persist_live_governed_state",
        AsyncMock(),
    )

    response = await chat_endpoint(
        ChatRequest(message=message, session_id="active-case"),
        current_user=_user(),
    )

    answer = response.answer_markdown or ""
    assert "Welches Medium soll abgedichtet werden?" not in answer
    assert "Welche Betriebstemperatur liegt an?" in answer
    trace = response.run_meta["answer_trace"]
    assert trace["resume_strategy"] == "answer_then_reprioritize_next_question"
    assert trace["resume_reason"] == "pending_field_already_asserted"
    assert trace["resume_target_field"] == "temperature_c"
    assert trace["pending_question_restored"] is False


@pytest.mark.asyncio
async def test_stream_active_case_process_question_final_state_update_uses_answer_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Wie laeuft die Analyse ab?"
    state = _active_state()
    decision = _process_decision(message, state)
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_process_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY.value,
        pre_gate_reason="ambiguous_fail_safe_domain_inquiry",
        governed_state=state,
        turn_decision=decision,
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._persist_live_governed_state",
        AsyncMock(),
    )

    payloads = await _collect_sse_payloads(
        event_generator(
            ChatRequest(message=message, session_id="active-case"),
            current_user=_user(),
        )
    )

    state_update = next(payload for payload in payloads if payload.get("type") == "state_update")
    answer = state_update.get("answer_markdown") or ""
    assert answer
    assert "Analyse" in answer
    assert answer != "Welches Medium soll abgedichtet werden?"
    assert "Welches Medium soll abgedichtet werden?" in answer
    assert state_update["run_meta"]["answer_trace"]["answer_mode"] == "active_case_process_question"
    assert state_update["run_meta"]["answer_trace"]["resume_reevaluation_attempted"] is True
    assert state_update["run_meta"]["answer_trace"]["resume_strategy"] == "answer_then_continue_pending_question"
    assert state_update["run_meta"]["answer_trace"]["resume_target_field"] == "medium"
    assert state_update["run_meta"]["answer_trace"]["runtime_action_type"] == "answer_then_resume"
    assert state_update["run_meta"]["answer_trace"]["graph_allowed"] is False


@pytest.mark.asyncio
async def test_stream_active_case_side_question_final_state_update_uses_resume_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Was bedeutet Medium?"
    pre_gate = PreGateClassifier().classify(message)
    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=_pending_medium_question(),
        )
    )
    dispatch = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="v7_active_case_side_question:test",
        runtime_mode="GOVERNED",
        gate_applied=False,
        pre_gate_classification=pre_gate.classification.value,
        pre_gate_reason=pre_gate.reasoning,
        governed_state=_active_state(),
        turn_decision=decision,
    )
    side_answer = KnowledgeResponse(
        content="Mit Medium ist der Stoff gemeint, der an der Dichtung anliegt.",
        answer_markdown="Mit Medium ist der Stoff gemeint, der an der Dichtung anliegt.",
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._resolve_runtime_dispatch",
        AsyncMock(return_value=dispatch),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat.build_case_side_knowledge_response",
        AsyncMock(return_value=side_answer),
    )

    payloads = await _collect_sse_payloads(
        event_generator(
            ChatRequest(message=message, session_id="active-case"),
            current_user=_user(),
        )
    )

    state_update = next(payload for payload in payloads if payload.get("type") == "state_update")
    answer = state_update.get("answer_markdown") or ""
    assert "Stoff" in answer
    assert "Welches Medium soll abgedichtet werden?" in answer
    trace = state_update["run_meta"]["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["resume_reevaluation_attempted"] is True
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"
    assert trace["resume_target_field"] == "medium"
    assert trace["governed_graph_bypassed"] is True
    assert trace["runtime_action_type"] == "answer_then_resume"
    assert trace["graph_allowed"] is False
    assert trace["operational_contract_version"] == "runtime_action_v1"


@pytest.mark.asyncio
async def test_stream_active_case_rfq_readiness_enters_governed_graph_with_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_governed_state",
        AsyncMock(return_value=_active_state()),
    )

    async def fake_stream_governed_graph(
        request,
        *,
        current_user,
        pre_gate_classification=None,
        runtime_action=None,
    ):
        assert runtime_action is not None
        assert runtime_action.action_type == RuntimeActionType.ENTER_GOVERNED_GRAPH
        assert runtime_action.answer_mode == AnswerMode.RFQ_READINESS
        assert runtime_action.graph_allowed is True
        assert runtime_action.graph_entry_reason == "rfq_readiness_requires_governed_graph"
        yield "data: " + json.dumps(
            {
                "type": "state_update",
                "answer_markdown": "Graph RFQ readiness path",
                "run_meta": {"answer_trace": runtime_action.as_trace()},
            }
        ) + "\n\n"
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(
        "app.agent.api.streaming._stream_governed_graph",
        fake_stream_governed_graph,
    )

    payloads = await _collect_sse_payloads(
        event_generator(
            ChatRequest(message="Was fehlt noch fuer den Hersteller?", session_id="active-case"),
            current_user=_user(),
        )
    )

    state_update = next(payload for payload in payloads if payload.get("type") == "state_update")
    trace = state_update["run_meta"]["answer_trace"]
    assert trace["answer_mode"] == "rfq_readiness"
    assert trace["runtime_action_type"] == "enter_governed_graph"
    assert trace["runtime_answer_builder"] == "governed_output_contract"
    assert trace["rfq_action_type"] == "show_missing_fields"
    assert trace["graph_allowed"] is True
    assert trace["graph_entry_reason"] == "rfq_readiness_requires_governed_graph"
    assert trace["dispatch_allowed"] is False
    assert trace["external_contact_allowed"] is False
    assert trace["consent_required"] is True
    assert trace["governed_graph_bypassed"] is False
    assert trace["operational_contract_version"] == "runtime_action_v1"
