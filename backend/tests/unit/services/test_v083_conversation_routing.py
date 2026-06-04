from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agent.api.dispatch import _resolve_runtime_dispatch
from app.agent.api.models import ChatRequest
from app.domain.conversation_intent import (
    ConversationIntent,
    ConversationRouteView,
    ResponseMode,
    classify_conversation_route,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.services.auth.dependencies import RequestUser
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


@pytest.mark.asyncio
async def test_greeting_routes_to_frontdoor_without_governed_case_intake(
    monkeypatch,
) -> None:
    load_state = AsyncMock(return_value=None)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Hallo", session_id="greeting-no-case"),
        current_user=_user(),
    )

    assert dispatch.pre_gate_classification == PreGateClassification.GREETING.value
    assert dispatch.fast_response is None
    assert dispatch.knowledge_response is None
    assert dispatch.governed_state is None
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.answer_builder == "light_runtime"
    assert dispatch.runtime_action.graph_allowed is False
    assert (
        dispatch.runtime_action.graph_invocation_skipped_reason
        == "light_runtime_does_not_require_governed_graph"
    )
    assert dispatch.conversation_route is not None
    assert dispatch.conversation_route.intent is ConversationIntent.small_talk
    assert dispatch.conversation_route.response_mode is ResponseMode.fast_responder
    assert (
        dispatch.conversation_route.route_view
        is ConversationRouteView.conversation_frontdoor
    )
    assert dispatch.conversation_route.no_durable_engineering_case_state is True
    # Greeting frontdoor does not touch governed case state at all.
    load_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_bare_compound_greeting_routes_to_frontdoor_without_governed_case_intake(
    monkeypatch,
) -> None:
    load_state = AsyncMock(return_value=None)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Hallo und guten morgen", session_id="bare-greeting-no-case"
        ),
        current_user=_user(),
    )

    assert dispatch.pre_gate_classification == PreGateClassification.GREETING.value
    assert dispatch.fast_response is None
    assert dispatch.knowledge_response is None
    assert dispatch.governed_state is None
    assert dispatch.runtime_action is not None
    assert dispatch.runtime_action.answer_builder == "light_runtime"
    assert dispatch.runtime_action.graph_allowed is False
    assert (
        dispatch.runtime_action.graph_invocation_skipped_reason
        == "light_runtime_does_not_require_governed_graph"
    )
    assert dispatch.conversation_route is not None
    assert dispatch.conversation_route.intent is ConversationIntent.small_talk
    assert dispatch.conversation_route.response_mode is ResponseMode.fast_responder
    assert (
        dispatch.conversation_route.route_view
        is ConversationRouteView.conversation_frontdoor
    )
    assert dispatch.conversation_route.no_durable_engineering_case_state is True
    # Greeting frontdoor does not touch governed case state at all.
    load_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_general_knowledge_routes_to_knowledge_without_governed_case_intake(
    monkeypatch,
) -> None:
    load_state = AsyncMock(
        side_effect=AssertionError("knowledge must not load/create governed case state")
    )
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Was ist FKM?", session_id=None),
        current_user=_user(),
    )

    assert (
        dispatch.pre_gate_classification == PreGateClassification.KNOWLEDGE_QUERY.value
    )
    assert dispatch.fast_response is None
    assert dispatch.knowledge_response is not None
    assert dispatch.knowledge_response.no_case_created is True
    assert dispatch.governed_state is None
    assert dispatch.conversation_route is not None
    assert (
        dispatch.conversation_route.intent
        is ConversationIntent.general_sealing_question
    )
    assert dispatch.conversation_route.response_mode is ResponseMode.knowledge_answer
    assert (
        dispatch.conversation_route.route_view
        is ConversationRouteView.knowledge_question
    )
    assert dispatch.conversation_route.no_durable_engineering_case_state is True
    assert dispatch.conversation_route.selects_governed_case_intake is False
    load_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_nbr_about_question_uses_deterministic_knowledge_without_rfq_intake(
    monkeypatch,
) -> None:
    load_state = AsyncMock(
        side_effect=AssertionError("standalone knowledge must not create a case")
    )
    rag_calls: list[dict[str, object]] = []

    def rag_retriever(**kwargs):
        rag_calls.append(dict(kwargs))
        return [
            {
                "text": "NBR ist ein polarer Acrylnitril-Butadien-Kautschuk mit typischer Oel- und Fettbestaendigkeit.",
                "metadata": {
                    "source_id": "paperless-nbr",
                    "title": "NBR Deep Research",
                    "chunk_id": "chunk-nbr-1",
                },
                "fused_score": 0.91,
            }
        ]

    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)
    monkeypatch.setattr("app.agent.api.dispatch._knowledge_rag_retriever", rag_retriever)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Was kannst du mir zu NBR sagen?", session_id=None),
        current_user=_user(),
    )

    assert dispatch.pre_gate_classification == PreGateClassification.KNOWLEDGE_QUERY.value
    assert dispatch.knowledge_response is not None
    assert dispatch.knowledge_response.no_case_created is True
    assert dispatch.governed_state is None
    assert "NBR steht für Acrylnitril" in dispatch.knowledge_response.content
    assert "Typische Orientierung" in dispatch.knowledge_response.content
    assert "Aus dem kuratierten/RAG-Wissenskontext" not in dispatch.knowledge_response.content
    assert dispatch.knowledge_response.answer_result is not None
    assert dispatch.knowledge_response.answer_result.rag_answer_found is False
    assert dispatch.knowledge_response.answer_result.source_type.value == "system_derived"
    assert {
        evidence.source_type
        for evidence in dispatch.knowledge_response.answer_result.knowledge_evidence
    } == {"deterministic"}
    assert rag_calls == []
    load_state.assert_not_awaited()


@pytest.mark.parametrize(
    "message",
    [
        "Vergleiche FKM und EPDM für Dichtungen.",
        "Was ist der Unterschied zwischen FKM und EPDM?",
        "Wann nimmt man EPDM statt FKM?",
        "FKM oder EPDM?",
        "PTFE vs FKM",
        "und fkm mit nbr?",
        "FKM mit NBR?",
        "FKM und NBR?",
        "Welche Vorteile hat EPDM gegenüber FKM?",
        "Was ist besser für Wasser, EPDM oder FKM?",
    ],
)
def test_generic_material_comparison_routes_to_knowledge(message: str) -> None:
    pre_gate = PreGateClassifier().classify(message)
    route = classify_conversation_route(
        message, pre_gate_classification=pre_gate.classification
    )

    assert pre_gate.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert pre_gate.reasoning == "deterministic_material_comparison_knowledge"
    assert route.intent is ConversationIntent.general_sealing_question
    assert route.response_mode is ResponseMode.knowledge_answer
    assert route.no_durable_engineering_case_state is True


def test_standalone_product_material_compatibility_routes_to_knowledge() -> None:
    message = "Bitte untersuche ob POM mit Klübersynth UH1 6-220 verträglich ist."
    pre_gate = PreGateClassifier().classify(message)
    route = classify_conversation_route(
        message, pre_gate_classification=pre_gate.classification
    )

    assert pre_gate.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert route.intent is ConversationIntent.general_sealing_question
    assert route.response_mode is ResponseMode.knowledge_answer
    assert route.no_durable_engineering_case_state is True
    assert route.selects_governed_case_intake is False


@pytest.mark.parametrize(
    "message",
    [
        "Ich habe eine rotierende Welle mit 80 mm Durchmesser, 1500 rpm und Öl bei 90 Grad.",
        "Welche Dichtung brauche ich für eine Welle mit 80 mm, 1500 rpm, Öl, 90 Grad?",
        "Kann ich bei meiner Anwendung FKM durch EPDM ersetzen? Medium ist Öl, 90 Grad, 10 bar.",
        "Unsere EPDM-Dichtung fällt nach 3 Wochen in Natronlauge aus.",
    ],
)
def test_concrete_material_or_application_prompts_remain_governed(message: str) -> None:
    pre_gate = PreGateClassifier().classify(message)
    route = classify_conversation_route(
        message, pre_gate_classification=pre_gate.classification
    )

    assert pre_gate.classification is PreGateClassification.DOMAIN_INQUIRY
    assert route.selects_governed_case_intake is True
    assert route.no_durable_engineering_case_state is False


@pytest.mark.parametrize(
    "message",
    [
        "Was bedeutet PFAS für Dichtungen?",
        "Wie funktioniert ein Radialwellendichtring?",
        "Was ist bei Salzwasser und Dichtungen kritisch?",
    ],
)
def test_existing_no_case_knowledge_prompts_stay_knowledge(message: str) -> None:
    pre_gate = PreGateClassifier().classify(message)

    assert pre_gate.classification is PreGateClassification.KNOWLEDGE_QUERY


@pytest.mark.parametrize(
    "message, expected_pre_gate, expected_intent, expected_mode",
    [
        (
            "Was kannst du?",
            PreGateClassification.META_QUESTION,
            ConversationIntent.meta_question,
            ResponseMode.fast_responder,
        ),
        (
            "Was ist der Unterschied zwischen NBR und FKM?",
            PreGateClassification.KNOWLEDGE_QUERY,
            ConversationIntent.general_sealing_question,
            ResponseMode.knowledge_answer,
        ),
        (
            "Wir brauchen eine Dichtung fuer Getriebeoel bei 80 Grad",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.new_rfq,
            ResponseMode.governed_case_intake,
        ),
        (
            "Wer kann diesen Wellendichtring herstellen?",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.manufacturer_matching,
            ResponseMode.matching_flow,
        ),
        (
            "Ist FKM gegen Wasser, Natrium und Kalium im Oel bestaendig?",
            PreGateClassification.KNOWLEDGE_QUERY,
            ConversationIntent.general_sealing_question,
            ResponseMode.knowledge_answer,
        ),
        (
            "Diese Dichtung leckt schon wieder",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.failure_analysis,
            ResponseMode.empathic_triage,
        ),
        (
            "Kundenreklamation: Wellendichtring ausgefallen",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.complaint_case,
            ResponseMode.complaint_flow,
        ),
        (
            "Wir brauchen ein Ersatzteil, auf dem Altteil steht nur 75x95x10",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.replacement_reorder,
            ResponseMode.governed_case_intake,
        ),
        (
            "Anlage steht, wir brauchen sofort eine Dichtung",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.emergency_mro,
            ResponseMode.governed_case_intake,
        ),
    ],
)
def test_pre_gate_output_refines_to_v083_route_facts(
    message: str,
    expected_pre_gate: PreGateClassification,
    expected_intent: ConversationIntent,
    expected_mode: ResponseMode,
) -> None:
    pre_gate = PreGateClassifier().classify(message)
    route = classify_conversation_route(
        message, pre_gate_classification=pre_gate.classification
    )

    assert pre_gate.classification is expected_pre_gate
    assert route.intent is expected_intent
    assert route.response_mode is expected_mode


def test_off_topic_input_has_boundary_route_fact_without_case_intake() -> None:
    pre_gate = PreGateClassifier().classify("Erzaehl mir einen Witz ueber Fussball")
    route = classify_conversation_route(
        "Erzaehl mir einen Witz ueber Fussball",
        pre_gate_classification=pre_gate.classification,
    )

    assert route.intent is ConversationIntent.off_topic
    assert route.response_mode is ResponseMode.refusal_or_boundary
    assert route.route_view is ConversationRouteView.refusal_or_boundary
    assert route.no_durable_engineering_case_state is True


@pytest.mark.parametrize(
    "pre_gate, expected_intent, expected_mode",
    [
        (
            PreGateClassification.GREETING,
            ConversationIntent.small_talk,
            ResponseMode.fast_responder,
        ),
        (
            PreGateClassification.META_QUESTION,
            ConversationIntent.meta_question,
            ResponseMode.fast_responder,
        ),
        (
            PreGateClassification.KNOWLEDGE_QUERY,
            ConversationIntent.general_sealing_question,
            ResponseMode.knowledge_answer,
        ),
        (
            PreGateClassification.DEEP_DIVE,
            ConversationIntent.general_sealing_question,
            ResponseMode.knowledge_answer,
        ),
        (
            PreGateClassification.BLOCKED,
            ConversationIntent.unsupported,
            ResponseMode.refusal_or_boundary,
        ),
        (
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.new_rfq,
            ResponseMode.governed_case_intake,
        ),
        (
            PreGateClassification.RECOVERY,
            ConversationIntent.current_state_analysis,
            ResponseMode.governed_case_intake,
        ),
    ],
)
def test_old_pre_gate_categories_still_have_stable_mapping(
    pre_gate: PreGateClassification,
    expected_intent: ConversationIntent,
    expected_mode: ResponseMode,
) -> None:
    route = classify_conversation_route(
        "Unklarer Text", pre_gate_classification=pre_gate
    )

    assert route.pre_gate_classification is pre_gate
    assert route.intent is expected_intent
    assert route.response_mode is expected_mode
