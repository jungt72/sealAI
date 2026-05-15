from __future__ import annotations

from types import SimpleNamespace

from app.agent.api.dispatch import RuntimeDispatchResolution, _with_v91_policy_trace
from app.agent.communication.v7_contracts import (
    AnswerMode,
    MutationPolicy,
    RuntimeActionType,
    RuntimeAnswerBuilder,
    TurnDecision,
    TurnKind,
    build_answer_only_runtime_action,
    build_runtime_action_from_turn_decision,
)
from app.agent.v91.contracts import (
    CaseBinding,
    DomainRelevance,
    KnowledgeRagPolicy,
    LLMFreedomLevel,
    RedFlagType,
    ResponseAction,
    SemanticIntent,
)
from app.agent.v91.semantic_boundary import (
    build_v91_turn_policy,
    merge_v91_trace_into_runtime_action,
)


def _decision(
    *,
    answer_mode: AnswerMode,
    turn_kind: TurnKind,
    mutation_policy: MutationPolicy = MutationPolicy.FORBIDDEN,
) -> TurnDecision:
    return TurnDecision(
        turn_kind=turn_kind,
        primary_interpretation="test",
        answer_mode=answer_mode,
        mutation_policy=mutation_policy,
        confidence=0.82,
    )


def test_v91_policy_maps_general_knowledge_to_free_answer_only() -> None:
    decision = _decision(
        answer_mode=AnswerMode.NO_CASE_KNOWLEDGE,
        turn_kind=TurnKind.KNOWLEDGE,
    )
    runtime_action = build_runtime_action_from_turn_decision(
        decision,
        reason="knowledge_answer_without_case_mutation",
    )

    policy = build_v91_turn_policy(
        message="Was bedeutet Reibung?",
        pre_gate_classification="KNOWLEDGE_QUERY",
        pre_gate_reason="knowledge",
        turn_decision=decision,
        runtime_action=runtime_action,
    )

    assert policy.semantic_boundary.intent == SemanticIntent.GENERAL_KNOWLEDGE.value
    assert policy.semantic_boundary.domain_relevance == DomainRelevance.SEALING_RELATED.value
    assert policy.semantic_boundary.case_binding == CaseBinding.NONE.value
    assert policy.freedom_decision.level == LLMFreedomLevel.FREE_EXPLANATION.value
    assert policy.response_policy.action == ResponseAction.ANSWER_ONLY.value
    assert policy.response_policy.graph_allowed is False
    assert policy.knowledge_policy.rag_policy == KnowledgeRagPolicy.OPTIONAL.value


def test_v91_policy_restricts_concrete_material_suitability_claims() -> None:
    decision = _decision(
        answer_mode=AnswerMode.GOVERNED_INTAKE,
        turn_kind=TurnKind.CASE_INTAKE,
        mutation_policy=MutationPolicy.PROPOSED,
    )
    runtime_action = build_runtime_action_from_turn_decision(
        decision,
        reason="governed_intake_requires_langgraph",
    )

    policy = build_v91_turn_policy(
        message="Ist FKM bei Wasser-Glykol und 110 Grad geeignet?",
        pre_gate_classification="DOMAIN_INQUIRY",
        pre_gate_reason="domain",
        turn_decision=decision,
        runtime_action=runtime_action,
    )
    red_flag_types = {flag.type for flag in policy.freedom_decision.red_flags}

    assert policy.semantic_boundary.intent == SemanticIntent.CONCRETE_SUITABILITY.value
    assert policy.semantic_boundary.case_binding == CaseBinding.NEW_CASE_CANDIDATE.value
    assert policy.semantic_boundary.should_mutate_case is True
    assert policy.freedom_decision.level == LLMFreedomLevel.RESTRICTED_CASE_CLAIMS.value
    assert RedFlagType.FINAL_SUITABILITY.value in red_flag_types
    assert policy.response_policy.action == ResponseAction.ENTER_GOVERNED_GRAPH.value
    assert policy.response_policy.graph_allowed is True
    assert policy.knowledge_policy.fallback_allowed is False


def test_v91_policy_marks_rfq_as_consent_boundary_without_graph() -> None:
    runtime_action = build_answer_only_runtime_action(
        answer_mode=AnswerMode.RFQ_READINESS,
        answer_builder=RuntimeAnswerBuilder.RFQ_READINESS,
        reason="rfq_status",
        decision_source="test",
        graph_invocation_skipped_reason="rfq_readiness_answered_without_governed_graph",
    ).model_copy(update={"action_type": RuntimeActionType.SHOW_RFQ_READINESS})

    policy = build_v91_turn_policy(
        message="Kannst du die Anfragebasis an den Hersteller senden?",
        pre_gate_classification="DOMAIN_INQUIRY",
        pre_gate_reason="rfq",
        runtime_action=runtime_action,
    )

    assert policy.semantic_boundary.intent == SemanticIntent.RFQ_OR_EXPORT.value
    assert policy.freedom_decision.level == LLMFreedomLevel.RESTRICTED_CASE_CLAIMS.value
    assert policy.response_policy.action == ResponseAction.SHOW_RFQ_READINESS.value
    assert policy.response_policy.graph_allowed is False
    assert policy.as_trace()["v91_response_graph_allowed"] is False


def test_v91_policy_marks_non_sealing_utility_without_graph() -> None:
    runtime_action = build_answer_only_runtime_action(
        answer_mode=AnswerMode.META_QUESTION,
        answer_builder=RuntimeAnswerBuilder.FAST_RESPONSE,
        reason="deterministic_non_sealing_utility",
        decision_source="test",
        graph_invocation_skipped_reason="non_sealing_utility",
    )

    policy = build_v91_turn_policy(
        message="Wetter morgen?",
        pre_gate_classification="META_QUESTION",
        pre_gate_reason="deterministic_non_sealing_utility",
        runtime_action=runtime_action,
    )

    assert policy.semantic_boundary.intent == SemanticIntent.NON_SEALING_UTILITY.value
    assert policy.semantic_boundary.case_binding == CaseBinding.NONE.value
    assert policy.response_policy.graph_allowed is False


def test_v91_trace_merges_into_runtime_action_without_changing_authority() -> None:
    decision = _decision(
        answer_mode=AnswerMode.GOVERNED_INTAKE,
        turn_kind=TurnKind.CASE_INTAKE,
        mutation_policy=MutationPolicy.PROPOSED,
    )
    runtime_action = build_runtime_action_from_turn_decision(decision)
    policy = build_v91_turn_policy(
        message="Medium Wasser, Druck 3 bar",
        pre_gate_classification="DOMAIN_INQUIRY",
        turn_decision=decision,
        runtime_action=runtime_action,
    )

    merged = merge_v91_trace_into_runtime_action(runtime_action, policy)
    trace = merged.as_trace()

    assert merged.action_type == runtime_action.action_type
    assert merged.graph_allowed is True
    assert trace["runtime_action_type"] == RuntimeActionType.ENTER_GOVERNED_GRAPH.value
    assert trace["v91_semantic_intent"] == SemanticIntent.CASE_INTAKE.value
    assert trace["v91_graph_candidate"] is True


def test_v91_policy_trace_is_attached_to_dispatch_resolution() -> None:
    decision = _decision(
        answer_mode=AnswerMode.NO_CASE_KNOWLEDGE,
        turn_kind=TurnKind.KNOWLEDGE,
    )
    runtime_action = build_runtime_action_from_turn_decision(decision)
    resolution = RuntimeDispatchResolution(
        gate_route="CONVERSATION",
        gate_reason="knowledge",
        runtime_mode="CONVERSATION",
        gate_applied=True,
        pre_gate_classification="KNOWLEDGE_QUERY",
        pre_gate_reason="knowledge",
        turn_decision=decision,
        runtime_action=runtime_action,
    )

    next_resolution = _with_v91_policy_trace(
        resolution,
        request=SimpleNamespace(message="Was bedeutet Reibung?"),
    )
    trace = next_resolution.runtime_action.as_trace()

    assert next_resolution.v91_policy is not None
    assert next_resolution.runtime_action.action_type == runtime_action.action_type
    assert trace["runtime_action_type"] == RuntimeActionType.ANSWER_ONLY.value
    assert trace["v91_policy_version"] == "sealai_v9_1_policy_v1"
    assert trace["v91_semantic_intent"] == SemanticIntent.GENERAL_KNOWLEDGE.value
