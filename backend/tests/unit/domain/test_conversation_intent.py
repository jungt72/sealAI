from __future__ import annotations

import json

import pytest

from app.domain.conversation_intent import (
    ConversationIntent,
    ConversationRouteView,
    ResponseMode,
    classify_conversation_route,
)
from app.domain.pre_gate_classification import PreGateClassification


def test_conversation_intent_contains_stable_v083_values() -> None:
    expected = {
        "small_talk",
        "meta_question",
        "general_sealing_question",
        "needs_analysis",
        "current_state_analysis",
        "new_rfq",
        "manufacturer_matching",
        "compatibility_inquiry",
        "complaint_case",
        "failure_analysis",
        "replacement_reorder",
        "unknown_legacy_part",
        "drawing_review",
        "quote_comparison",
        "compliance_certificate_request",
        "material_substitution",
        "emergency_mro",
        "manufacturer_support_intake",
        "off_topic",
        "unsupported",
    }

    assert {member.value for member in ConversationIntent} == expected


def test_response_mode_contains_stable_v083_values() -> None:
    expected = {
        "fast_responder",
        "knowledge_answer",
        "empathic_triage",
        "governed_case_intake",
        "artifact_generation",
        "matching_flow",
        "support_flow",
        "complaint_flow",
        "consent_flow",
        "refusal_or_boundary",
    }

    assert {member.value for member in ResponseMode} == expected


def test_values_serialize_as_strings() -> None:
    payload = {
        "intent": ConversationIntent.compatibility_inquiry,
        "response_mode": ResponseMode.support_flow,
    }

    assert isinstance(ConversationIntent.compatibility_inquiry, str)
    assert json.loads(json.dumps(payload)) == {
        "intent": "compatibility_inquiry",
        "response_mode": "support_flow",
    }


@pytest.mark.parametrize(
    "message, pre_gate, expected_intent, expected_mode, expected_view, no_case",
    [
        (
            "Hallo",
            PreGateClassification.GREETING,
            ConversationIntent.small_talk,
            ResponseMode.fast_responder,
            ConversationRouteView.conversation_frontdoor,
            True,
        ),
        (
            "Was kannst du?",
            PreGateClassification.META_QUESTION,
            ConversationIntent.meta_question,
            ResponseMode.fast_responder,
            ConversationRouteView.conversation_frontdoor,
            True,
        ),
        (
            "Was ist FKM?",
            PreGateClassification.KNOWLEDGE_QUERY,
            ConversationIntent.general_sealing_question,
            ResponseMode.knowledge_answer,
            ConversationRouteView.knowledge_question,
            True,
        ),
        (
            "Was ist der Unterschied zwischen NBR und FKM?",
            PreGateClassification.KNOWLEDGE_QUERY,
            ConversationIntent.general_sealing_question,
            ResponseMode.knowledge_answer,
            ConversationRouteView.knowledge_question,
            True,
        ),
        (
            "Wir brauchen eine Dichtung fuer Getriebeoel bei 80 Grad",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.new_rfq,
            ResponseMode.governed_case_intake,
            ConversationRouteView.governed_domain_inquiry,
            False,
        ),
        (
            "Wer kann diesen Wellendichtring herstellen?",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.manufacturer_matching,
            ResponseMode.matching_flow,
            ConversationRouteView.governed_domain_inquiry,
            False,
        ),
        (
            "Ist FKM gegen Wasser, Natrium und Kalium im Oel bestaendig?",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.compatibility_inquiry,
            ResponseMode.support_flow,
            ConversationRouteView.governed_domain_inquiry,
            False,
        ),
        (
            "Diese Dichtung leckt schon wieder",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.failure_analysis,
            ResponseMode.empathic_triage,
            ConversationRouteView.empathic_triage,
            False,
        ),
        (
            "Kundenreklamation: Wellendichtring ausgefallen",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.complaint_case,
            ResponseMode.complaint_flow,
            ConversationRouteView.governed_domain_inquiry,
            False,
        ),
        (
            "Wir brauchen ein Ersatzteil, auf dem Altteil steht nur 75x95x10",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.replacement_reorder,
            ResponseMode.governed_case_intake,
            ConversationRouteView.governed_domain_inquiry,
            False,
        ),
        (
            "Anlage steht, wir brauchen sofort eine Dichtung",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.emergency_mro,
            ResponseMode.governed_case_intake,
            ConversationRouteView.governed_domain_inquiry,
            False,
        ),
        (
            "Erzaehl mir einen Witz ueber Fussball",
            PreGateClassification.DOMAIN_INQUIRY,
            ConversationIntent.off_topic,
            ResponseMode.refusal_or_boundary,
            ConversationRouteView.refusal_or_boundary,
            True,
        ),
    ],
)
def test_v083_route_decision_for_required_examples(
    message: str,
    pre_gate: PreGateClassification,
    expected_intent: ConversationIntent,
    expected_mode: ResponseMode,
    expected_view: ConversationRouteView,
    no_case: bool,
) -> None:
    decision = classify_conversation_route(message, pre_gate_classification=pre_gate)

    assert decision.user_message_received is True
    assert decision.intent_classified is True
    assert decision.response_mode_selected is True
    assert decision.pre_gate_classification is pre_gate
    assert decision.intent is expected_intent
    assert decision.response_mode is expected_mode
    assert decision.route_view is expected_view
    assert decision.no_durable_engineering_case_state is no_case


@pytest.mark.parametrize(
    "pre_gate, expected_intent, expected_mode",
    [
        (PreGateClassification.GREETING, ConversationIntent.small_talk, ResponseMode.fast_responder),
        (PreGateClassification.META_QUESTION, ConversationIntent.meta_question, ResponseMode.fast_responder),
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
        (PreGateClassification.BLOCKED, ConversationIntent.unsupported, ResponseMode.refusal_or_boundary),
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
def test_old_pre_gate_categories_map_to_v083_taxonomy(
    pre_gate: PreGateClassification,
    expected_intent: ConversationIntent,
    expected_mode: ResponseMode,
) -> None:
    decision = classify_conversation_route("Unklarer Text", pre_gate_classification=pre_gate)

    assert decision.intent is expected_intent
    assert decision.response_mode is expected_mode
