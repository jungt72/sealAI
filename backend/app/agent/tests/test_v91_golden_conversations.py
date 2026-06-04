from __future__ import annotations

from app.agent.communication.governed_answer_context import (
    build_governed_answer_context,
)
from app.agent.communication.v7_contracts import (
    AnswerMode,
    MutationPolicy,
    RuntimeAnswerBuilder,
    TurnDecision,
    TurnKind,
    build_answer_only_runtime_action,
    build_runtime_action_from_turn_decision,
)
from app.agent.state.models import ConversationStrategyContract, GovernedSessionState
from app.agent.v91.contracts import (
    CaseBinding,
    DomainRelevance,
    KnowledgeRagPolicy,
    LLMFreedomLevel,
    ResponseAction,
    SemanticIntent,
)
from app.agent.v91.final_answer_guard import validate_v91_final_answer
from app.agent.v91.semantic_boundary import build_v91_turn_policy


def _decision(
    *,
    answer_mode: AnswerMode,
    turn_kind: TurnKind,
    mutation_policy: MutationPolicy = MutationPolicy.FORBIDDEN,
) -> TurnDecision:
    return TurnDecision(
        turn_kind=turn_kind,
        primary_interpretation="golden",
        answer_mode=answer_mode,
        mutation_policy=mutation_policy,
        confidence=0.88,
    )


def test_golden_nbr_question_is_free_knowledge_without_case_mutation() -> None:
    decision = _decision(
        answer_mode=AnswerMode.NO_CASE_KNOWLEDGE,
        turn_kind=TurnKind.KNOWLEDGE,
    )
    policy = build_v91_turn_policy(
        message="Was ist NBR?",
        pre_gate_classification="KNOWLEDGE_QUERY",
        pre_gate_reason="knowledge",
        turn_decision=decision,
        runtime_action=build_runtime_action_from_turn_decision(decision),
    )

    assert (
        policy.semantic_boundary.intent
        == SemanticIntent.MATERIAL_OR_MEDIUM_KNOWLEDGE.value
    )
    assert policy.semantic_boundary.case_binding == CaseBinding.NONE.value
    assert policy.semantic_boundary.should_mutate_case is False
    assert (
        policy.semantic_boundary.domain_relevance
        == DomainRelevance.SEALING_RELATED.value
    )
    assert policy.freedom_decision.level == LLMFreedomLevel.FREE_EXPLANATION.value
    assert policy.response_policy.action == ResponseAction.ANSWER_ONLY.value
    assert policy.response_policy.graph_allowed is False
    assert policy.knowledge_policy.rag_policy == KnowledgeRagPolicy.OPTIONAL.value


def test_golden_concrete_fkm_water_glycol_case_is_governed_not_final() -> None:
    decision = _decision(
        answer_mode=AnswerMode.GOVERNED_INTAKE,
        turn_kind=TurnKind.CASE_INTAKE,
        mutation_policy=MutationPolicy.PROPOSED,
    )
    policy = build_v91_turn_policy(
        message="FKM oder EPDM bei Wasser-Glykol 110 Grad und 8 bar?",
        pre_gate_classification="DOMAIN_INQUIRY",
        pre_gate_reason="domain",
        turn_decision=decision,
        runtime_action=build_runtime_action_from_turn_decision(decision),
    )

    assert policy.semantic_boundary.intent in {
        SemanticIntent.CONCRETE_SUITABILITY.value,
        SemanticIntent.CASE_INTAKE.value,
    }
    assert policy.semantic_boundary.case_binding == CaseBinding.NEW_CASE_CANDIDATE.value
    assert policy.semantic_boundary.should_mutate_case is True
    assert policy.freedom_decision.level == LLMFreedomLevel.RESTRICTED_CASE_CLAIMS.value
    assert policy.response_policy.action == ResponseAction.ENTER_GOVERNED_GRAPH.value
    assert policy.response_policy.graph_allowed is True
    assert "final_material_recommendation" in policy.freedom_decision.forbidden_actions


def test_golden_user_pushing_for_simple_approval_is_blocked_by_claim_guard() -> None:
    strategy = ConversationStrategyContract(
        focus_key="pressure_bar",
        primary_question="Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
        primary_question_reason="Der Druck bestimmt Bauform und Extrusionsrisiko.",
        response_mode="single_question",
    )
    governed_context = build_governed_answer_context(
        GovernedSessionState(),
        strategy=strategy,
        response_class="structured_clarification",
    )
    assert governed_context.v91_final_answer_context is not None

    result = validate_v91_final_answer(
        "Das passt sicher, FKM ist final freigegeben. Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
        governed_context.v91_final_answer_context,
    )

    assert result.passed is False
    assert any(finding.startswith("claim_guard:") for finding in result.findings)


def test_golden_rfq_send_request_stays_readiness_boundary_without_dispatch() -> None:
    runtime_action = build_answer_only_runtime_action(
        answer_mode=AnswerMode.RFQ_READINESS,
        answer_builder=RuntimeAnswerBuilder.RFQ_READINESS,
        reason="rfq_status",
        decision_source="golden",
        graph_invocation_skipped_reason="rfq_readiness_without_graph",
    )
    policy = build_v91_turn_policy(
        message="Kannst du das an den Hersteller senden?",
        pre_gate_classification="DOMAIN_INQUIRY",
        pre_gate_reason="rfq",
        runtime_action=runtime_action,
    )

    assert policy.semantic_boundary.intent == SemanticIntent.RFQ_OR_EXPORT.value
    assert policy.response_policy.graph_allowed is False
    assert policy.response_policy.action == ResponseAction.ANSWER_ONLY.value
    assert (
        "external_dispatch_without_consent" in policy.freedom_decision.forbidden_actions
    )


def test_golden_weather_question_is_not_a_sealing_case() -> None:
    runtime_action = build_answer_only_runtime_action(
        answer_mode=AnswerMode.META_QUESTION,
        answer_builder=RuntimeAnswerBuilder.FAST_RESPONSE,
        reason="deterministic_non_sealing_utility",
        decision_source="golden",
        graph_invocation_skipped_reason="non_sealing_utility",
    )
    policy = build_v91_turn_policy(
        message="Wie wird das Wetter morgen?",
        pre_gate_classification="META_QUESTION",
        pre_gate_reason="deterministic_non_sealing_utility",
        runtime_action=runtime_action,
    )

    assert policy.semantic_boundary.intent == SemanticIntent.NON_SEALING_UTILITY.value
    assert policy.semantic_boundary.domain_relevance == DomainRelevance.IRRELEVANT.value
    assert policy.semantic_boundary.case_binding == CaseBinding.NONE.value
    assert policy.response_policy.graph_allowed is False
