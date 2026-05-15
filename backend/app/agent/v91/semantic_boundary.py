from __future__ import annotations

import re
from typing import Any

from app.agent.v91.contracts import (
    AnswerDepth,
    CaseBinding,
    CommunicationPlan,
    DomainRelevance,
    KnowledgePolicy,
    KnowledgeRagPolicy,
    LLMFreedomDecision,
    LLMFreedomLevel,
    RedFlag,
    RedFlagType,
    ResponseAction,
    ResponsePolicy,
    SemanticBoundaryDecision,
    SemanticIntent,
    V91TurnPolicyBundle,
)


_SUITABILITY_RE = re.compile(
    r"\b(geeignet|eignung|passt|passend|kompatibel|vertraeglich|verträglich|freigabe|freigeben|freigegeben|beste|optimal)\b",
    re.IGNORECASE,
)
_COMPLIANCE_RE = re.compile(
    r"\b(atex|fda|lebensmittel|food|pharma|trinkwasser|zertifikat|zertifiziert|compliance|reach|pfa?s)\b",
    re.IGNORECASE,
)
_RFQ_RE = re.compile(
    r"\b(rfq|anfrage|anfragebasis|hersteller|senden|export|weitergeben|angebot)\b",
    re.IGNORECASE,
)
_NUMERIC_LIMIT_RE = re.compile(
    r"\b\d+(?:[,.]\d+)?\s*(bar|°c|grad|rpm|u/min|mm|m/s|mpa)\b",
    re.IGNORECASE,
)
_DOCUMENT_RE = re.compile(
    r"\b(dokument|datenblatt|paperless|pdf|quelle|nachweis|zertifikat|upload)\b",
    re.IGNORECASE,
)


def build_v91_turn_policy(
    *,
    message: str,
    pre_gate_classification: Any | None = None,
    pre_gate_reason: str | None = None,
    governed_state: Any | None = None,
    conversation_route: Any | None = None,
    turn_decision: Any | None = None,
    runtime_action: Any | None = None,
) -> V91TurnPolicyBundle:
    """Map the current V7/V8 runtime decision to the V9.1 policy vocabulary.

    This adapter is intentionally read-only. It does not decide whether LangGraph
    may run; it describes the already computed RuntimeAction in V9.1 terms.
    """

    normalized_message = " ".join((message or "").strip().split())
    answer_mode = _enum_value(getattr(turn_decision, "answer_mode", None))
    turn_kind = _enum_value(getattr(turn_decision, "turn_kind", None))
    action_type = _enum_value(getattr(runtime_action, "action_type", None))
    answer_builder = _enum_value(getattr(runtime_action, "answer_builder", None))
    mutation_policy = _enum_value(getattr(runtime_action, "mutation_policy", None))
    graph_allowed = bool(getattr(runtime_action, "graph_allowed", False))
    active_case_exists = _has_active_case(governed_state)
    pre_gate = _enum_value(pre_gate_classification)

    red_flags = _red_flags(normalized_message, graph_allowed=graph_allowed, action_type=action_type)
    intent = _semantic_intent(
        message=normalized_message,
        pre_gate=pre_gate,
        pre_gate_reason=str(pre_gate_reason or ""),
        answer_mode=answer_mode,
        turn_kind=turn_kind,
        action_type=action_type,
        answer_builder=answer_builder,
        red_flags=red_flags,
    )
    domain_relevance = _domain_relevance(
        intent=intent,
        pre_gate=pre_gate,
        graph_allowed=graph_allowed,
        red_flags=red_flags,
    )
    case_binding = _case_binding(
        intent=intent,
        active_case_exists=active_case_exists,
        mutation_policy=mutation_policy,
        graph_allowed=graph_allowed,
    )
    semantic_boundary = SemanticBoundaryDecision(
        intent=intent,
        domain_relevance=domain_relevance,
        case_binding=case_binding,
        active_case_exists=active_case_exists,
        should_mutate_case=_should_mutate_case(mutation_policy, graph_allowed),
        graph_candidate=graph_allowed,
        confidence=_confidence(turn_decision),
        reason=_safe_reason(pre_gate_reason or getattr(runtime_action, "reason", None)),
    )
    freedom_decision = _freedom_decision(
        intent=intent,
        red_flags=red_flags,
        graph_allowed=graph_allowed,
        action_type=action_type,
    )
    response_policy = _response_policy(
        action_type=action_type,
        answer_mode=answer_mode,
        graph_allowed=graph_allowed,
        freedom_decision=freedom_decision,
    )
    knowledge_policy = _knowledge_policy(
        intent=intent,
        answer_mode=answer_mode,
        red_flags=red_flags,
        response_policy=response_policy,
    )
    communication_plan = CommunicationPlan(
        response_mode=_communication_response_mode(intent, freedom_decision),
        answer_depth=response_policy.answer_depth,
        include_boundary_notice=bool(red_flags)
        or _enum_value(freedom_decision.level)
        in {
            LLMFreedomLevel.RESTRICTED_CASE_CLAIMS.value,
            LLMFreedomLevel.BLOCKED_OR_REFUSAL.value,
        },
        forbidden_claims=freedom_decision.forbidden_actions,
    )
    return V91TurnPolicyBundle(
        semantic_boundary=semantic_boundary,
        freedom_decision=freedom_decision,
        response_policy=response_policy,
        knowledge_policy=knowledge_policy,
        communication_plan=communication_plan,
    )


def merge_v91_trace_into_runtime_action(
    runtime_action: Any | None,
    policy: V91TurnPolicyBundle | None,
) -> Any | None:
    if runtime_action is None or policy is None or not hasattr(runtime_action, "model_copy"):
        return runtime_action
    trace = dict(getattr(runtime_action, "trace", {}) or {})
    trace.update(policy.as_trace())
    return runtime_action.model_copy(update={"trace": trace})


def _semantic_intent(
    *,
    message: str,
    pre_gate: str,
    pre_gate_reason: str,
    answer_mode: str,
    turn_kind: str,
    action_type: str,
    answer_builder: str,
    red_flags: list[RedFlag],
) -> SemanticIntent:
    if answer_mode == "safety_blocked" or pre_gate == "BLOCKED":
        return SemanticIntent.BLOCKED
    if "non_sealing_utility" in str(pre_gate_reason or ""):
        return SemanticIntent.NON_SEALING_UTILITY
    if answer_mode == "smalltalk" or pre_gate == "GREETING":
        return SemanticIntent.SMALLTALK
    if answer_mode in {"meta_question", "active_case_process_question"}:
        return SemanticIntent.PROCESS_OR_META
    if (
        answer_mode == "rfq_readiness"
        or answer_builder == "rfq_readiness"
        or "rfq" in str(pre_gate_reason or "").casefold()
        or action_type in {
            "show_rfq_readiness",
            "answer_rfq_status",
            "build_rfq_preview",
            "defer_rfq_until_required_fields",
        }
    ):
        return SemanticIntent.RFQ_OR_EXPORT
    if answer_mode == "active_case_side_question":
        return SemanticIntent.ACTIVE_CASE_SIDE_QUESTION
    if answer_mode == "pending_slot_answer":
        return SemanticIntent.PENDING_SLOT_ANSWER
    if turn_kind == "correction":
        return SemanticIntent.CORRECTION
    if answer_mode == "material_comparison":
        return SemanticIntent.MATERIAL_COMPARISON
    if answer_mode == "no_case_knowledge":
        if _mentions_material_or_medium(message):
            return SemanticIntent.MATERIAL_OR_MEDIUM_KNOWLEDGE
        return SemanticIntent.GENERAL_KNOWLEDGE
    if any(
        _enum_value(flag.type) == RedFlagType.COMPLIANCE_OR_CERTIFICATION.value
        for flag in red_flags
    ):
        return SemanticIntent.SAFETY_OR_COMPLIANCE
    if any(
        _enum_value(flag.type) == RedFlagType.FINAL_SUITABILITY.value
        for flag in red_flags
    ):
        return SemanticIntent.CONCRETE_SUITABILITY
    if action_type == "enter_governed_graph" or answer_mode == "governed_intake":
        return SemanticIntent.CASE_INTAKE
    if answer_builder == "light_runtime":
        return SemanticIntent.NON_SEALING_UTILITY
    if not message:
        return SemanticIntent.LOW_SIGNAL
    return SemanticIntent.UNCLEAR


def _domain_relevance(
    *,
    intent: SemanticIntent,
    pre_gate: str,
    graph_allowed: bool,
    red_flags: list[RedFlag],
) -> DomainRelevance:
    if intent in {SemanticIntent.BLOCKED, SemanticIntent.SAFETY_OR_COMPLIANCE}:
        return DomainRelevance.SAFETY_OR_COMPLIANCE
    if graph_allowed or intent in {
        SemanticIntent.CASE_INTAKE,
        SemanticIntent.PENDING_SLOT_ANSWER,
        SemanticIntent.CORRECTION,
        SemanticIntent.CONCRETE_SUITABILITY,
    }:
        return DomainRelevance.CONCRETE_SEALING_CASE
    if red_flags:
        return DomainRelevance.CONCRETE_SEALING_CASE
    if intent in {
        SemanticIntent.GENERAL_KNOWLEDGE,
        SemanticIntent.MATERIAL_OR_MEDIUM_KNOWLEDGE,
        SemanticIntent.MATERIAL_COMPARISON,
        SemanticIntent.ACTIVE_CASE_SIDE_QUESTION,
        SemanticIntent.RFQ_OR_EXPORT,
    }:
        return DomainRelevance.SEALING_RELATED
    if pre_gate in {"KNOWLEDGE_QUERY", "DEEP_DIVE", "DOMAIN_INQUIRY"}:
        return DomainRelevance.SEALING_RELATED
    if intent is SemanticIntent.SMALLTALK:
        return DomainRelevance.LOW
    return DomainRelevance.IRRELEVANT


def _case_binding(
    *,
    intent: SemanticIntent,
    active_case_exists: bool,
    mutation_policy: str,
    graph_allowed: bool,
) -> CaseBinding:
    if graph_allowed or mutation_policy in {"proposed", "allowed_by_validator", "correction"}:
        return (
            CaseBinding.CASE_MUTATION_CANDIDATE
            if active_case_exists
            else CaseBinding.NEW_CASE_CANDIDATE
        )
    if active_case_exists and intent in {
        SemanticIntent.ACTIVE_CASE_SIDE_QUESTION,
        SemanticIntent.PROCESS_OR_META,
        SemanticIntent.RFQ_OR_EXPORT,
    }:
        return CaseBinding.ACTIVE_CASE_CONTEXT
    if intent in {
        SemanticIntent.SMALLTALK,
        SemanticIntent.GENERAL_KNOWLEDGE,
        SemanticIntent.MATERIAL_OR_MEDIUM_KNOWLEDGE,
        SemanticIntent.NON_SEALING_UTILITY,
    }:
        return CaseBinding.NONE
    return CaseBinding.UNKNOWN


def _freedom_decision(
    *,
    intent: SemanticIntent,
    red_flags: list[RedFlag],
    graph_allowed: bool,
    action_type: str,
) -> LLMFreedomDecision:
    forbidden = [
        "final_engineering_release",
        "final_material_recommendation",
        "manufacturer_approval_claim",
    ]
    if intent is SemanticIntent.RFQ_OR_EXPORT:
        forbidden.extend(
            [
                "external_dispatch_without_consent",
                "automatic_manufacturer_contact",
            ]
        )
    if intent is SemanticIntent.BLOCKED:
        return LLMFreedomDecision(
            level=LLMFreedomLevel.BLOCKED_OR_REFUSAL,
            red_flags=red_flags,
            allowed_actions=["boundary_refusal"],
            forbidden_actions=forbidden,
            reason="blocked_or_unsafe_turn",
        )
    if graph_allowed or red_flags or intent in {
        SemanticIntent.CONCRETE_SUITABILITY,
        SemanticIntent.SAFETY_OR_COMPLIANCE,
        SemanticIntent.RFQ_OR_EXPORT,
        SemanticIntent.PENDING_SLOT_ANSWER,
        SemanticIntent.CORRECTION,
    }:
        return LLMFreedomDecision(
            level=LLMFreedomLevel.RESTRICTED_CASE_CLAIMS,
            red_flags=red_flags,
            allowed_actions=["orientation", "candidate_facts", "question_plan"],
            forbidden_actions=forbidden,
            reason="case_or_red_flag_claims_require_governance",
        )
    if intent in {
        SemanticIntent.ACTIVE_CASE_SIDE_QUESTION,
        SemanticIntent.MATERIAL_COMPARISON,
    }:
        return LLMFreedomDecision(
            level=LLMFreedomLevel.GUIDED_EXPLANATION,
            red_flags=red_flags,
            allowed_actions=["general_orientation", "explain_limits"],
            forbidden_actions=forbidden,
            reason="domain_answer_allowed_but_case_claims_restricted",
        )
    return LLMFreedomDecision(
        level=LLMFreedomLevel.FREE_EXPLANATION,
        red_flags=red_flags,
        allowed_actions=["explain", "summarize", "guide"],
        forbidden_actions=forbidden,
        reason=f"answer_action={action_type or 'conversation'}",
    )


def _response_policy(
    *,
    action_type: str,
    answer_mode: str,
    graph_allowed: bool,
    freedom_decision: LLMFreedomDecision,
) -> ResponsePolicy:
    action = _response_action(action_type, freedom_decision)
    return ResponsePolicy(
        action=action,
        answer_depth=_answer_depth(answer_mode, freedom_decision),
        graph_allowed=graph_allowed,
        answer_first=action in {ResponseAction.ANSWER_ONLY, ResponseAction.ANSWER_THEN_RESUME},
        must_resume_primary_task=action is ResponseAction.ANSWER_THEN_RESUME,
        reason=freedom_decision.reason,
    )


def _knowledge_policy(
    *,
    intent: SemanticIntent,
    answer_mode: str,
    red_flags: list[RedFlag],
    response_policy: ResponsePolicy,
) -> KnowledgePolicy:
    if intent in {SemanticIntent.SMALLTALK, SemanticIntent.PROCESS_OR_META}:
        return KnowledgePolicy(
            rag_policy=KnowledgeRagPolicy.NOT_NEEDED,
            can_use_general_model_knowledge=True,
            fallback_allowed=True,
            source_scope="none",
            reason="non_technical_or_process_answer",
        )
    if intent in {SemanticIntent.BLOCKED, SemanticIntent.NON_SEALING_UTILITY}:
        return KnowledgePolicy(
            rag_policy=KnowledgeRagPolicy.DISALLOWED,
            can_use_general_model_knowledge=False,
            fallback_allowed=False,
            source_scope="none",
            reason="outside_sealing_or_blocked",
        )
    if red_flags or response_policy.graph_allowed:
        return KnowledgePolicy(
            rag_policy=KnowledgeRagPolicy.REQUIRED
            if _requires_documented_evidence(red_flags)
            else KnowledgeRagPolicy.OPTIONAL,
            can_use_general_model_knowledge=True,
            fallback_allowed=False,
            source_scope="case_orientation",
            reason="case_claims_or_red_flags_require_controlled_context",
        )
    if answer_mode in {"no_case_knowledge", "material_comparison", "active_case_side_question"}:
        return KnowledgePolicy(
            rag_policy=KnowledgeRagPolicy.OPTIONAL,
            can_use_general_model_knowledge=True,
            fallback_allowed=True,
            source_scope="general_orientation",
            reason="knowledge_answer_without_case_truth_mutation",
        )
    return KnowledgePolicy(
        rag_policy=KnowledgeRagPolicy.NOT_NEEDED,
        can_use_general_model_knowledge=True,
        fallback_allowed=False,
        source_scope="general_orientation",
        reason="no_explicit_knowledge_need",
    )


def _red_flags(message: str, *, graph_allowed: bool, action_type: str) -> list[RedFlag]:
    flags: list[RedFlag] = []
    if _SUITABILITY_RE.search(message):
        flags.append(
            RedFlag(
                type=RedFlagType.FINAL_SUITABILITY,
                severity="high",
                reason="user asks for suitability or optimal/final fit language",
            )
        )
    if _COMPLIANCE_RE.search(message):
        flags.append(
            RedFlag(
                type=RedFlagType.COMPLIANCE_OR_CERTIFICATION,
                severity="blocking" if "atex" in message.casefold() else "high",
                reason="compliance/certification topic requires evidence boundary",
            )
        )
    if _RFQ_RE.search(message) or action_type in {
        "show_rfq_readiness",
        "answer_rfq_status",
        "build_rfq_preview",
    }:
        flags.append(
            RedFlag(
                type=RedFlagType.RFQ_EXPORT_OR_DISPATCH,
                severity="medium",
                reason="RFQ/export/manufacturer topic requires consent boundary",
            )
        )
    if graph_allowed:
        flags.append(
            RedFlag(
                type=RedFlagType.CASE_STATE_MUTATION,
                severity="medium",
                reason="governed graph may create case-state candidates",
            )
        )
    if _DOCUMENT_RE.search(message):
        flags.append(
            RedFlag(
                type=RedFlagType.DOCUMENT_BASED_CLAIM,
                severity="medium",
                reason="document-based claims need evidence handling",
            )
        )
    if _NUMERIC_LIMIT_RE.search(message):
        flags.append(
            RedFlag(
                type=RedFlagType.NUMERIC_LIMIT_CLAIM,
                severity="medium",
                reason="numeric operating limits must remain governed case context",
            )
        )
    return _dedupe_flags(flags)


def _response_action(
    action_type: str,
    freedom_decision: LLMFreedomDecision,
) -> ResponseAction:
    if _enum_value(freedom_decision.level) == LLMFreedomLevel.BLOCKED_OR_REFUSAL.value:
        return ResponseAction.BLOCK
    try:
        return ResponseAction(action_type)
    except Exception:
        return ResponseAction.ANSWER_ONLY


def _answer_depth(answer_mode: str, freedom_decision: LLMFreedomDecision) -> AnswerDepth:
    if answer_mode in {"material_comparison", "active_case_side_question"}:
        return AnswerDepth.DEEP
    if _enum_value(freedom_decision.level) == LLMFreedomLevel.RESTRICTED_CASE_CLAIMS.value:
        return AnswerDepth.NORMAL
    if answer_mode in {"smalltalk", "meta_question"}:
        return AnswerDepth.SHORT
    return AnswerDepth.NORMAL


def _communication_response_mode(
    intent: SemanticIntent,
    freedom_decision: LLMFreedomDecision,
) -> str:
    if _enum_value(freedom_decision.level) == LLMFreedomLevel.BLOCKED_OR_REFUSAL.value:
        return "boundary_refusal"
    if intent in {SemanticIntent.CASE_INTAKE, SemanticIntent.CONCRETE_SUITABILITY}:
        return "case_challenge"
    if intent in {SemanticIntent.PENDING_SLOT_ANSWER, SemanticIntent.LOW_SIGNAL, SemanticIntent.UNCLEAR}:
        return "clarification"
    if intent in {SemanticIntent.GENERAL_KNOWLEDGE, SemanticIntent.MATERIAL_OR_MEDIUM_KNOWLEDGE}:
        return "direct_answer"
    return "guided_explanation"


def _requires_documented_evidence(red_flags: list[RedFlag]) -> bool:
    return any(
        _enum_value(flag.type)
        in {
            RedFlagType.COMPLIANCE_OR_CERTIFICATION.value,
            RedFlagType.DOCUMENT_BASED_CLAIM.value,
            RedFlagType.FINAL_RELEASE.value,
            RedFlagType.MANUFACTURER_OR_ARTICLE_EQUIVALENCE.value,
        }
        for flag in red_flags
    )


def _mentions_material_or_medium(message: str) -> bool:
    lowered = message.casefold()
    return any(
        token in lowered
        for token in (
            "nbr",
            "fkm",
            "epdm",
            "ptfe",
            "ffkm",
            "hnbr",
            "medium",
            "werkstoff",
            "material",
            "dichtung",
        )
    )


def _should_mutate_case(mutation_policy: str, graph_allowed: bool) -> bool:
    return graph_allowed or mutation_policy in {
        "proposed",
        "allowed_by_validator",
        "correction",
    }


def _has_active_case(governed_state: Any | None) -> bool:
    if governed_state is None:
        return False
    if getattr(governed_state, "pending_question", None) is not None:
        return True
    if getattr(governed_state, "conversation_messages", None):
        return True
    asserted = getattr(governed_state, "asserted", None)
    if getattr(asserted, "assertions", None):
        return True
    observed = getattr(governed_state, "observed", None)
    return bool(getattr(observed, "raw_extractions", None))


def _confidence(turn_decision: Any | None) -> float:
    try:
        return max(0.0, min(1.0, float(getattr(turn_decision, "confidence", 0.5) or 0.5)))
    except Exception:
        return 0.5


def _safe_reason(value: Any, *, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _dedupe_flags(flags: list[RedFlag]) -> list[RedFlag]:
    deduped: list[RedFlag] = []
    seen: set[str] = set()
    for flag in flags:
        key = str(getattr(flag.type, "value", flag.type))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(flag)
    return deduped
