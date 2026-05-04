from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agent.api.dispatch import RuntimeDispatchResolution, _resolve_runtime_dispatch
from app.agent.api.models import ChatRequest
from app.agent.api.routes.chat import chat_endpoint
from app.agent.communication.conversation_controller_v7 import (
    ConversationControllerInput,
    ConversationControllerV7,
)
from app.agent.communication.v7_contracts import AnswerMode, MutationPolicy
from app.agent.state.models import (
    ConversationMessage,
    GovernedSessionState,
    PendingQuestion,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.services.auth.dependencies import RequestUser
from app.services.knowledge_service import KnowledgeResponse
from app.services.pre_gate_classifier import PreGateClassifier


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


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
    side_answer = KnowledgeResponse(
        content="## Werkstoffvergleich: FKM vs NBR\n\nAllgemeine Orientierung, keine Materialfreigabe.",
        answer_markdown="## Werkstoffvergleich: FKM vs NBR\n\nAllgemeine Orientierung, keine Materialfreigabe.",
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
    assert response.structured_state is None
    build_side.assert_awaited_once()
