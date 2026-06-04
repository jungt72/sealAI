"""Stable v0.8.3 CaseType projection taxonomy.

This module is intentionally deterministic and side-effect free.  It exposes
CaseType as a domain/projection primitive only; it does not persist CaseType or
create database authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from app.domain.conversation_intent import ConversationIntent


class CaseType(str, Enum):
    new_rfq = "new_rfq"
    manufacturer_matching = "manufacturer_matching"
    compatibility_inquiry = "compatibility_inquiry"
    complaint_case = "complaint_case"
    failure_analysis = "failure_analysis"
    replacement_reorder = "replacement_reorder"
    unknown_legacy_part = "unknown_legacy_part"
    drawing_review = "drawing_review"
    quote_comparison = "quote_comparison"
    compliance_certificate_request = "compliance_certificate_request"
    material_substitution = "material_substitution"
    emergency_mro = "emergency_mro"
    manufacturer_support_intake = "manufacturer_support_intake"
    general_knowledge = "general_knowledge"
    no_case = "no_case"
    unknown = "unknown"


@dataclass(frozen=True, slots=True)
class CaseTypeAssignment:
    """Code-level projection facts for S-CASE-TYPE-001."""

    case_type: CaseType
    case_type_assigned: bool
    case_type_remains_unassigned: bool
    case_type_mapped_from_legacy_routing: bool
    source: str
    reason: str

    @property
    def event_name(self) -> str:
        if self.case_type_remains_unassigned:
            return "CaseTypeRemainsUnassigned"
        if self.case_type_mapped_from_legacy_routing:
            return "CaseTypeMappedFromLegacyRouting"
        return "CaseTypeAssigned"


_CONVERSATION_INTENT_TO_CASE_TYPE: dict[ConversationIntent, CaseType] = {
    ConversationIntent.small_talk: CaseType.no_case,
    ConversationIntent.meta_question: CaseType.no_case,
    ConversationIntent.general_sealing_question: CaseType.general_knowledge,
    # Needs/current-state analysis can precede a real case. Keep the projection
    # conservative until legacy routing or governed state supplies stronger
    # evidence.
    ConversationIntent.needs_analysis: CaseType.unknown,
    ConversationIntent.current_state_analysis: CaseType.unknown,
    ConversationIntent.new_rfq: CaseType.new_rfq,
    ConversationIntent.manufacturer_matching: CaseType.manufacturer_matching,
    ConversationIntent.compatibility_inquiry: CaseType.compatibility_inquiry,
    ConversationIntent.complaint_case: CaseType.complaint_case,
    ConversationIntent.failure_analysis: CaseType.failure_analysis,
    ConversationIntent.replacement_reorder: CaseType.replacement_reorder,
    ConversationIntent.unknown_legacy_part: CaseType.unknown_legacy_part,
    ConversationIntent.drawing_review: CaseType.drawing_review,
    ConversationIntent.quote_comparison: CaseType.quote_comparison,
    ConversationIntent.compliance_certificate_request: (
        CaseType.compliance_certificate_request
    ),
    ConversationIntent.material_substitution: CaseType.material_substitution,
    ConversationIntent.emergency_mro: CaseType.emergency_mro,
    ConversationIntent.manufacturer_support_intake: (
        CaseType.manufacturer_support_intake
    ),
    ConversationIntent.off_topic: CaseType.no_case,
    ConversationIntent.unsupported: CaseType.no_case,
}

_LEGACY_SIGNAL_TO_CASE_TYPE: dict[str, CaseType] = {
    "new_design": CaseType.new_rfq,
    "new_rfq": CaseType.new_rfq,
    "rfq": CaseType.new_rfq,
    "inquiry": CaseType.new_rfq,
    "domain_inquiry": CaseType.new_rfq,
    "manufacturer_inquiry": CaseType.new_rfq,
    "rca": CaseType.failure_analysis,
    "rca_failure_analysis": CaseType.failure_analysis,
    "root_cause_analysis": CaseType.failure_analysis,
    "failure_analysis": CaseType.failure_analysis,
    "retrofit": CaseType.replacement_reorder,
    "replacement": CaseType.replacement_reorder,
    "replacement_reorder": CaseType.replacement_reorder,
    "reorder": CaseType.replacement_reorder,
    "spare_part": CaseType.unknown_legacy_part,
    "spare_part_identification": CaseType.unknown_legacy_part,
    "part_identification": CaseType.unknown_legacy_part,
    "legacy_part": CaseType.unknown_legacy_part,
    "unknown_legacy_part": CaseType.unknown_legacy_part,
    "manufacturer_matching": CaseType.manufacturer_matching,
    "matching": CaseType.manufacturer_matching,
    "manufacturer_fit": CaseType.manufacturer_matching,
    "compatibility": CaseType.compatibility_inquiry,
    "compatibility_inquiry": CaseType.compatibility_inquiry,
    "complaint": CaseType.complaint_case,
    "complaint_case": CaseType.complaint_case,
    "certificate_request": CaseType.compliance_certificate_request,
    "compliance_certificate_request": CaseType.compliance_certificate_request,
    "compliance": CaseType.compliance_certificate_request,
    "drawing_review": CaseType.drawing_review,
    "quote_comparison": CaseType.quote_comparison,
    "material_substitution": CaseType.material_substitution,
    "emergency_mro": CaseType.emergency_mro,
    "manufacturer_support_intake": CaseType.manufacturer_support_intake,
    "knowledge": CaseType.general_knowledge,
    "knowledge_query": CaseType.general_knowledge,
    "general_knowledge": CaseType.general_knowledge,
    "no_case": CaseType.no_case,
}


def case_type_from_conversation_intent(intent: ConversationIntent | str) -> CaseType:
    normalized_intent = _coerce_conversation_intent(intent)
    if normalized_intent is None:
        return CaseType.unknown
    return _CONVERSATION_INTENT_TO_CASE_TYPE[normalized_intent]


def assign_case_type_from_conversation_intent(
    intent: ConversationIntent | str,
) -> CaseTypeAssignment:
    case_type = case_type_from_conversation_intent(intent)
    return CaseTypeAssignment(
        case_type=case_type,
        case_type_assigned=case_type not in {CaseType.no_case, CaseType.unknown},
        case_type_remains_unassigned=case_type is CaseType.no_case,
        case_type_mapped_from_legacy_routing=False,
        source="conversation_intent",
        reason=f"conversation_intent:{_normalize(intent)}",
    )


def case_type_from_legacy_routing(
    *,
    request_type: Any = None,
    engineering_path: Any = None,
    routing: Mapping[str, Any] | None = None,
) -> CaseType:
    return assign_case_type_from_legacy_routing(
        request_type=request_type,
        engineering_path=engineering_path,
        routing=routing,
    ).case_type


def assign_case_type_from_legacy_routing(
    *,
    request_type: Any = None,
    engineering_path: Any = None,
    routing: Mapping[str, Any] | None = None,
) -> CaseTypeAssignment:
    routing_payload = dict(routing or {})

    explicit_case_type = _coerce_case_type(routing_payload.get("case_type"))
    if explicit_case_type is not None:
        return _legacy_assignment(explicit_case_type, "routing.case_type")

    conversation_intent = _coerce_conversation_intent(
        routing_payload.get("conversation_intent") or routing_payload.get("intent")
    )
    if conversation_intent is not None:
        case_type = case_type_from_conversation_intent(conversation_intent)
        return _legacy_assignment(case_type, "routing.conversation_intent")

    for source, value in (
        ("request_type", request_type),
        ("routing.request_type", routing_payload.get("request_type")),
        ("routing.legacy_request_type", routing_payload.get("legacy_request_type")),
        ("routing.mode", routing_payload.get("mode")),
        ("routing.path", routing_payload.get("path")),
        ("engineering_path", engineering_path),
        ("routing.engineering_path", routing_payload.get("engineering_path")),
    ):
        normalized = _normalize(value)
        if normalized in _LEGACY_SIGNAL_TO_CASE_TYPE:
            return _legacy_assignment(_LEGACY_SIGNAL_TO_CASE_TYPE[normalized], source)

    return _legacy_assignment(CaseType.unknown, "legacy_routing")


def _legacy_assignment(case_type: CaseType, source: str) -> CaseTypeAssignment:
    return CaseTypeAssignment(
        case_type=case_type,
        case_type_assigned=case_type not in {CaseType.no_case, CaseType.unknown},
        case_type_remains_unassigned=case_type is CaseType.no_case,
        case_type_mapped_from_legacy_routing=case_type is not CaseType.unknown,
        source=source,
        reason=f"{source}:{case_type.value}",
    )


def _coerce_conversation_intent(value: Any) -> ConversationIntent | None:
    if isinstance(value, ConversationIntent):
        return value
    normalized = _normalize(value)
    if not normalized:
        return None
    try:
        return ConversationIntent(normalized)
    except ValueError:
        return None


def _coerce_case_type(value: Any) -> CaseType | None:
    if isinstance(value, CaseType):
        return value
    normalized = _normalize(value)
    if not normalized:
        return None
    try:
        return CaseType(normalized)
    except ValueError:
        return None


def _normalize(value: Any) -> str:
    return str(value or "").strip().casefold()
