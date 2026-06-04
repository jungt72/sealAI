from __future__ import annotations

import json

import pytest

from app.domain.case_type import (
    CaseType,
    assign_case_type_from_conversation_intent,
    assign_case_type_from_legacy_routing,
    case_type_from_conversation_intent,
    case_type_from_legacy_routing,
)
from app.domain.conversation_intent import ConversationIntent


def test_case_type_contains_stable_v083_values() -> None:
    expected = {
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
        "general_knowledge",
        "no_case",
        "unknown",
    }

    assert {member.value for member in CaseType} == expected


def test_case_type_serializes_as_string() -> None:
    payload = {"case_type": CaseType.compatibility_inquiry}

    assert isinstance(CaseType.compatibility_inquiry, str)
    assert json.loads(json.dumps(payload)) == {
        "case_type": "compatibility_inquiry"
    }


@pytest.mark.parametrize(
    "intent, expected_case_type",
    [
        (ConversationIntent.small_talk, CaseType.no_case),
        (ConversationIntent.meta_question, CaseType.no_case),
        (ConversationIntent.general_sealing_question, CaseType.general_knowledge),
        (ConversationIntent.needs_analysis, CaseType.unknown),
        (ConversationIntent.current_state_analysis, CaseType.unknown),
        (ConversationIntent.new_rfq, CaseType.new_rfq),
        (ConversationIntent.manufacturer_matching, CaseType.manufacturer_matching),
        (ConversationIntent.compatibility_inquiry, CaseType.compatibility_inquiry),
        (ConversationIntent.complaint_case, CaseType.complaint_case),
        (ConversationIntent.failure_analysis, CaseType.failure_analysis),
        (ConversationIntent.replacement_reorder, CaseType.replacement_reorder),
        (ConversationIntent.unknown_legacy_part, CaseType.unknown_legacy_part),
        (ConversationIntent.drawing_review, CaseType.drawing_review),
        (ConversationIntent.quote_comparison, CaseType.quote_comparison),
        (
            ConversationIntent.compliance_certificate_request,
            CaseType.compliance_certificate_request,
        ),
        (ConversationIntent.material_substitution, CaseType.material_substitution),
        (ConversationIntent.emergency_mro, CaseType.emergency_mro),
        (
            ConversationIntent.manufacturer_support_intake,
            CaseType.manufacturer_support_intake,
        ),
        (ConversationIntent.off_topic, CaseType.no_case),
        (ConversationIntent.unsupported, CaseType.no_case),
    ],
)
def test_every_conversation_intent_maps_to_case_type(
    intent: ConversationIntent,
    expected_case_type: CaseType,
) -> None:
    assert case_type_from_conversation_intent(intent) is expected_case_type


@pytest.mark.parametrize(
    "intent",
    [
        ConversationIntent.small_talk,
        ConversationIntent.meta_question,
        ConversationIntent.off_topic,
        ConversationIntent.unsupported,
    ],
)
def test_non_case_conversation_intents_remain_unassigned(
    intent: ConversationIntent,
) -> None:
    assignment = assign_case_type_from_conversation_intent(intent)

    assert assignment.case_type is CaseType.no_case
    assert assignment.case_type_assigned is False
    assert assignment.case_type_remains_unassigned is True
    assert assignment.event_name == "CaseTypeRemainsUnassigned"


@pytest.mark.parametrize(
    "intent, expected_case_type",
    [
        (ConversationIntent.manufacturer_matching, CaseType.manufacturer_matching),
        (ConversationIntent.compatibility_inquiry, CaseType.compatibility_inquiry),
        (ConversationIntent.complaint_case, CaseType.complaint_case),
        (ConversationIntent.failure_analysis, CaseType.failure_analysis),
        (ConversationIntent.replacement_reorder, CaseType.replacement_reorder),
        (ConversationIntent.unknown_legacy_part, CaseType.unknown_legacy_part),
        (ConversationIntent.emergency_mro, CaseType.emergency_mro),
    ],
)
def test_domain_case_intents_emit_assigned_fact(
    intent: ConversationIntent,
    expected_case_type: CaseType,
) -> None:
    assignment = assign_case_type_from_conversation_intent(intent)

    assert assignment.case_type is expected_case_type
    assert assignment.case_type_assigned is True
    assert assignment.case_type_remains_unassigned is False
    assert assignment.event_name == "CaseTypeAssigned"


@pytest.mark.parametrize(
    "request_type, expected_case_type",
    [
        ("new_design", CaseType.new_rfq),
        ("rfq", CaseType.new_rfq),
        ("rca_failure_analysis", CaseType.failure_analysis),
        ("retrofit", CaseType.replacement_reorder),
        ("spare_part_identification", CaseType.unknown_legacy_part),
        ("compliance", CaseType.compliance_certificate_request),
        ("manufacturer_matching", CaseType.manufacturer_matching),
        ("knowledge_query", CaseType.general_knowledge),
    ],
)
def test_legacy_request_signals_map_to_case_type(
    request_type: str,
    expected_case_type: CaseType,
) -> None:
    assignment = assign_case_type_from_legacy_routing(request_type=request_type)

    assert assignment.case_type is expected_case_type
    assert assignment.case_type_mapped_from_legacy_routing is True
    assert assignment.event_name == "CaseTypeMappedFromLegacyRouting"


def test_legacy_routing_can_map_from_conversation_intent() -> None:
    assert (
        case_type_from_legacy_routing(
            routing={"conversation_intent": "compatibility_inquiry"}
        )
        is CaseType.compatibility_inquiry
    )


def test_ambiguous_legacy_signals_remain_unknown_not_guessed() -> None:
    assignment = assign_case_type_from_legacy_routing(
        request_type="validation_check",
        engineering_path="rwdr",
    )

    assert assignment.case_type is CaseType.unknown
    assert assignment.case_type_assigned is False
    assert assignment.case_type_mapped_from_legacy_routing is False
    assert assignment.event_name == "CaseTypeAssigned"
