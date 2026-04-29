"""Stable v0.8.3 conversation routing taxonomy.

This module maps the existing pre-gate classes onto product-level
ConversationIntent and ResponseMode values. It intentionally has no database,
LLM, LangGraph, or service dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Pattern

from app.domain.pre_gate_classification import PreGateClassification


class ConversationIntent(str, Enum):
    small_talk = "small_talk"
    meta_question = "meta_question"
    general_sealing_question = "general_sealing_question"
    needs_analysis = "needs_analysis"
    current_state_analysis = "current_state_analysis"
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
    off_topic = "off_topic"
    unsupported = "unsupported"


class ResponseMode(str, Enum):
    fast_responder = "fast_responder"
    knowledge_answer = "knowledge_answer"
    empathic_triage = "empathic_triage"
    governed_case_intake = "governed_case_intake"
    artifact_generation = "artifact_generation"
    matching_flow = "matching_flow"
    support_flow = "support_flow"
    complaint_flow = "complaint_flow"
    consent_flow = "consent_flow"
    refusal_or_boundary = "refusal_or_boundary"


class ConversationRouteView(str, Enum):
    conversation_frontdoor = "ConversationFrontdoorView"
    knowledge_question = "KnowledgeQuestionView"
    governed_domain_inquiry = "GovernedDomainInquiry"
    empathic_triage = "EmpathicTriage"
    refusal_or_boundary = "RefusalOrBoundaryView"


@dataclass(frozen=True, slots=True)
class ConversationRoutingDecision:
    user_message_received: bool
    intent_classified: bool
    response_mode_selected: bool
    intent: ConversationIntent
    response_mode: ResponseMode
    route_view: ConversationRouteView
    pre_gate_classification: PreGateClassification
    reasoning: str

    @property
    def selects_governed_case_intake(self) -> bool:
        return self.response_mode in {
            ResponseMode.governed_case_intake,
            ResponseMode.matching_flow,
            ResponseMode.support_flow,
            ResponseMode.complaint_flow,
            ResponseMode.artifact_generation,
            ResponseMode.consent_flow,
            ResponseMode.empathic_triage,
        }

    @property
    def no_durable_engineering_case_state(self) -> bool:
        return self.response_mode in {
            ResponseMode.fast_responder,
            ResponseMode.knowledge_answer,
            ResponseMode.refusal_or_boundary,
        }


def classify_conversation_intent(
    user_input: str,
    *,
    pre_gate_classification: PreGateClassification,
) -> ConversationIntent:
    """Map old pre-gate output plus shallow deterministic refinements."""

    text = _normalized(user_input)

    if pre_gate_classification is PreGateClassification.GREETING:
        return ConversationIntent.small_talk
    if pre_gate_classification is PreGateClassification.META_QUESTION:
        return ConversationIntent.meta_question
    if pre_gate_classification in {
        PreGateClassification.KNOWLEDGE_QUERY,
        PreGateClassification.DEEP_DIVE,
    }:
        return ConversationIntent.general_sealing_question
    if pre_gate_classification is PreGateClassification.BLOCKED:
        return _blocked_intent(text)

    refined = _refine_domain_intent(text)
    if refined is not None:
        return refined

    if pre_gate_classification is PreGateClassification.RECOVERY:
        return ConversationIntent.current_state_analysis
    return ConversationIntent.new_rfq


def select_response_mode(intent: ConversationIntent) -> ResponseMode:
    if intent in {ConversationIntent.small_talk, ConversationIntent.meta_question}:
        return ResponseMode.fast_responder
    if intent is ConversationIntent.general_sealing_question:
        return ResponseMode.knowledge_answer
    if intent is ConversationIntent.manufacturer_matching:
        return ResponseMode.matching_flow
    if intent is ConversationIntent.compatibility_inquiry:
        return ResponseMode.support_flow
    if intent is ConversationIntent.complaint_case:
        return ResponseMode.complaint_flow
    if intent is ConversationIntent.failure_analysis:
        return ResponseMode.empathic_triage
    if intent in {
        ConversationIntent.drawing_review,
        ConversationIntent.quote_comparison,
        ConversationIntent.compliance_certificate_request,
        ConversationIntent.material_substitution,
        ConversationIntent.manufacturer_support_intake,
    }:
        return ResponseMode.artifact_generation
    if intent in {ConversationIntent.off_topic, ConversationIntent.unsupported}:
        return ResponseMode.refusal_or_boundary
    return ResponseMode.governed_case_intake


def route_view_for_response_mode(response_mode: ResponseMode) -> ConversationRouteView:
    if response_mode is ResponseMode.fast_responder:
        return ConversationRouteView.conversation_frontdoor
    if response_mode is ResponseMode.knowledge_answer:
        return ConversationRouteView.knowledge_question
    if response_mode is ResponseMode.empathic_triage:
        return ConversationRouteView.empathic_triage
    if response_mode is ResponseMode.refusal_or_boundary:
        return ConversationRouteView.refusal_or_boundary
    return ConversationRouteView.governed_domain_inquiry


def classify_conversation_route(
    user_input: str,
    *,
    pre_gate_classification: PreGateClassification,
) -> ConversationRoutingDecision:
    intent = classify_conversation_intent(
        user_input,
        pre_gate_classification=pre_gate_classification,
    )
    response_mode = select_response_mode(intent)
    return ConversationRoutingDecision(
        user_message_received=True,
        intent_classified=True,
        response_mode_selected=True,
        intent=intent,
        response_mode=response_mode,
        route_view=route_view_for_response_mode(response_mode),
        pre_gate_classification=pre_gate_classification,
        reasoning=f"pre_gate:{pre_gate_classification.value};intent:{intent.value}",
    )


def _blocked_intent(text: str) -> ConversationIntent:
    if _matches(_OFF_TOPIC_PATTERNS, text):
        return ConversationIntent.off_topic
    return ConversationIntent.unsupported


def _refine_domain_intent(text: str) -> ConversationIntent | None:
    if not text:
        return None
    if _matches(_OFF_TOPIC_PATTERNS, text):
        return ConversationIntent.off_topic
    if _matches(_EMERGENCY_PATTERNS, text):
        return ConversationIntent.emergency_mro
    if _matches(_COMPLAINT_PATTERNS, text):
        return ConversationIntent.complaint_case
    if _matches(_MANUFACTURER_SUPPORT_PATTERNS, text):
        return ConversationIntent.manufacturer_support_intake
    if _matches(_MANUFACTURER_MATCHING_PATTERNS, text):
        return ConversationIntent.manufacturer_matching
    if _matches(_COMPATIBILITY_PATTERNS, text):
        return ConversationIntent.compatibility_inquiry
    if _matches(_REPLACEMENT_PATTERNS, text):
        return ConversationIntent.replacement_reorder
    if _matches(_UNKNOWN_LEGACY_PATTERNS, text):
        return ConversationIntent.unknown_legacy_part
    if _matches(_DRAWING_REVIEW_PATTERNS, text):
        return ConversationIntent.drawing_review
    if _matches(_QUOTE_COMPARISON_PATTERNS, text):
        return ConversationIntent.quote_comparison
    if _matches(_COMPLIANCE_PATTERNS, text):
        return ConversationIntent.compliance_certificate_request
    if _matches(_MATERIAL_SUBSTITUTION_PATTERNS, text):
        return ConversationIntent.material_substitution
    if _matches(_FAILURE_PATTERNS, text):
        return ConversationIntent.failure_analysis
    if _matches(_NEEDS_ANALYSIS_PATTERNS, text):
        return ConversationIntent.needs_analysis
    if _matches(_CURRENT_STATE_PATTERNS, text):
        return ConversationIntent.current_state_analysis
    if _matches(_GENERAL_QUESTION_PATTERNS, text) and not _matches(
        _APPLICATION_DATA_PATTERNS,
        text,
    ):
        return ConversationIntent.general_sealing_question
    if _matches(_NEW_RFQ_PATTERNS, text):
        return ConversationIntent.new_rfq
    return None


def _normalized(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _compile(*patterns: str) -> tuple[Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE | re.UNICODE) for pattern in patterns)


def _matches(patterns: tuple[Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


_GENERAL_QUESTION_PATTERNS = _compile(
    r"^(was\s+ist|was\s+bedeutet|erkl[aä]r\w*|definiere)\b",
    r"^(what\s+is|explain|define)\b",
    r"\b(unterschied\s+zwischen|vergleich\s+zwischen|difference\s+between)\b",
)

_APPLICATION_DATA_PATTERNS = _compile(
    r"\b\d+(?:[.,]\d+)?\s*(mm|bar|psi|°?\s*c|rpm|u\.?/?min)\b",
    r"\b(getriebe[oö]l|hydraulik[oö]l|medium|temperatur|druck|welle|pumpe|getriebe)\b",
)

_NEW_RFQ_PATTERNS = _compile(
    r"\b(ich|wir)\s+brauch\w*\b.*\b(dichtung|dichtring|seal|wellendichtring|o-?ring)\b",
    r"\b(suche|ben[oö]tige)\b.*\b(dichtung|dichtring|seal|wellendichtring|o-?ring)\b",
)

_MANUFACTURER_MATCHING_PATTERNS = _compile(
    r"\b(welch\w*\s+hersteller|wer\s+kann\b.*\b(herstellen|fertigen|liefern))\b",
    r"\b(passend\w*\s+hersteller|lieferant\w*\s+finden|hersteller\s+finden)\b",
    r"\b(wer\s+stellt\b.*\b(her|fertigt)|kann\s+das\s+herstellen)\b",
)

_COMPATIBILITY_PATTERNS = _compile(
    r"\b(kompatibel|best[aä]ndig|bestaendig|medienbest[aä]ndigkeit|"
    r"medienbestaendigkeit|vertr[aä]glich|vertraeglich|"
    r"chemikalienbest[aä]ndigkeit|chemikalienbestaendigkeit)\b",
    r"\b(wasser|natrium|kalium).*\b([oö]l|oel|oelanalyse|[oö]lanalyse)\b",
    r"\b([oö]lanalyse|oelanalyse)\b",
)

_COMPLAINT_PATTERNS = _compile(
    r"\b(kunden)?reklamation\b",
    r"\b(gew[aä]hrleistung|beanstandung|qualit[aä]tsmeldung)\b",
)

_FAILURE_PATTERNS = _compile(
    r"\b(leckt|leckage|undicht|ausgefallen|ausfall|verschlissen|"
    r"verschlei[ßs]|riss|risse|quellung|gequollen)\b",
    r"\b(hart|br[üu]chig|extrusion|trockenlauf|montageschaden)\b",
)

_REPLACEMENT_PATTERNS = _compile(
    r"\b(ersatzteil|ersatz\s+f[uü]r|nachbestell\w*|wieder\s+bestellen|reorder|replacement)\b",
)

_UNKNOWN_LEGACY_PATTERNS = _compile(
    r"\b(altteil|altes\s+teil|legacy|alte\s+bezeichnung|"
    r"nur\s+bezeichnung|nicht\s+mehr\s+lieferbar)\b",
)

_EMERGENCY_PATTERNS = _compile(
    r"\b(anlage\s+steht|stillstand|maschinenstillstand|dringend|notfall|"
    r"sofort|eilig|emergency|downtime)\b",
)

_DRAWING_REVIEW_PATTERNS = _compile(
    r"\b(zeichnung|drawing|cad|dwg|dxf)\b.*\b(pr[üu]fen|review|bewerten|anschauen)\b",
    r"\b(zeichnungspr[üu]fung|drawing\s+review)\b",
)

_QUOTE_COMPARISON_PATTERNS = _compile(
    r"\b(angebot\w*\s+vergleich\w*|angebote\s+vergleichen|quote\s+comparison)\b",
)

_COMPLIANCE_PATTERNS = _compile(
    r"\b(zertifikat|bescheinigung|konformit[aä]t|compliance|fda|atex|"
    r"usp\s*class\s*vi|ehedg|eu\s*1935)\b",
)

_MATERIAL_SUBSTITUTION_PATTERNS = _compile(
    r"\b(material|werkstoff)\s*(substitution|ersatz|alternative|wechsel)\b",
    r"\b(alternative\s+zu|statt\s+fkm|statt\s+nbr|statt\s+epdm)\b",
)

_MANUFACTURER_SUPPORT_PATTERNS = _compile(
    r"\b(hersteller\s+support|anwendungstechnik|technischer\s+support|support\s+anfrage)\b",
)

_NEEDS_ANALYSIS_PATTERNS = _compile(
    r"\b(welche\s+dichtung\s+brauche\s+ich|was\s+brauchen\s+wir|"
    r"bedarf\s+kl[aä]ren|anforderungen\s+kl[aä]ren)\b",
)

_CURRENT_STATE_PATTERNS = _compile(
    r"\b(was\s+ist\s+bekannt|aktueller\s+stand|ist[-\s]?zustand|bisher\s+bekannt)\b",
)

_OFF_TOPIC_PATTERNS = _compile(
    r"\b(witz|fu[ßs]ball|wetter|aktienkurs|bitcoin|rezept|roman|gedicht)\b",
    r"\b(joke|weather|stock\s+price|recipe|poem)\b",
)
