from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.agent.api.dispatch import RuntimeDispatchResolution, _resolve_runtime_dispatch
from app.agent.api.models import ChatRequest
from app.agent.api.routes.chat import chat_endpoint
from app.agent.api.streaming import event_generator
from app.agent.communication.conversation_controller_v7 import (
    ConversationControllerInput,
    ConversationControllerV7,
)
from app.agent.communication.v7_contracts import AnswerMode, MutationPolicy
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
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
    assert "Welches Medium soll abgedichtet werden?" in response.answer_markdown
    assert "final approved solution" not in response.answer_markdown.casefold()
    assert "guaranteed suitable" not in response.answer_markdown.casefold()
    assert response.structured_state is None
    assert response.proposed_case_delta is None
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["mutation_policy"] == "forbidden"
    assert trace["resume_reevaluation_attempted"] is True
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"
    assert trace["resume_target_field"] == "medium"
    assert trace["governed_graph_bypassed"] is True
    assert trace["latest_user_question_answered"] is True
    assert trace["pending_question_restored"] is True
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
    assert "Welches Medium soll abgedichtet werden?" in answer
    assert response.proposed_case_delta is None
    trace = response.run_meta["answer_trace"]
    assert trace["answer_mode"] == "active_case_side_question"
    assert trace["resume_reevaluation_attempted"] is True
    assert trace["resume_strategy"] == "answer_then_continue_pending_question"
    assert trace["pending_question_restored"] is True
    assert trace["governed_graph_bypassed"] is True


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
