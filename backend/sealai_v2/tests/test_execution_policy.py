from sealai_v2.orchestration.execution_policy import (
    ExecutionClass,
    ExecutionFeatures,
    ModelTier,
    StreamingMode,
    VerificationMode,
    decide_execution,
    deterministic_response,
)
from sealai_v2.pipeline.routing import (
    RouteDecision,
    RouteName,
    classify_route_deterministic,
    requests_calculation,
)


def _route(name, *, forced=False, signals=0):
    return RouteDecision(name, "test", 1.0, forced, signals)


def test_deterministic_router_never_needs_an_llm_intent():
    assert (
        classify_route_deterministic("Hallo!").route is RouteName.SMALLTALK_NAVIGATION
    )


def test_calculation_context_requires_an_explicit_kernel_term():
    assert requests_calculation("Bitte die Umfangsgeschwindigkeit berechnen") is True
    assert requests_calculation("FKM in Heißdampf bei 140 °C einordnen") is False
    assert (
        classify_route_deterministic("Was ist PTFE?").route
        is RouteName.MATERIAL_KNOWLEDGE
    )
    assert (
        classify_route_deterministic("Was ist eine Radialwellendichtung?").route
        is RouteName.GENERAL_SEALING_KNOWLEDGE
    )
    assert (
        classify_route_deterministic("Details zu Skydrol als Dichtungsmedium").route
        is RouteName.GENERAL_SEALING_KNOWLEDGE
    )
    assert (
        classify_route_deterministic("RWDR 40x62x8 bei 8000 U/min").route
        is RouteName.ENGINEERING_CASE
    )
    assert (
        classify_route_deterministic("Erzaehl mir etwas").route
        is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    )


def test_missing_contract_field_stops_before_any_model():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True),
            contract_status="NEEDS_CLARIFICATION",
            required_missing=("Medium",),
        )
    )
    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert "Medium" in deterministic_response(decision, missing_fields=("Medium",))


def test_exact_validated_cache_hit_is_d0_without_model():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.MATERIAL_KNOWLEDGE), exact_cache_hit=True
        )
    )
    assert decision.execution_class is ExecutionClass.D0
    assert decision.model_tier is ModelTier.NONE


def test_high_risk_without_evidence_requires_human_and_no_model():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True),
            risk_flags=("ATEX",),
            authoritative_evidence_count=0,
        )
    )
    assert decision.execution_class is ExecutionClass.H1
    assert decision.verification_mode is VerificationMode.HUMAN
    assert decision.streaming_mode is StreamingMode.ATOMIC


def test_ungrounded_technical_case_is_a_deterministic_evidence_gap():
    decision = decide_execution(
        ExecutionFeatures(route=_route(RouteName.ENGINEERING_CASE, forced=True))
    )

    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert decision.reason == "technical_evidence_gap"
    assert "kein unabhängig geprüfter Beleg" in deterministic_response(decision)


def test_signal_free_ambiguity_never_becomes_a_technical_evidence_gap():
    route = classify_route_deterministic("Erzaehl mir etwas")
    decision = decide_execution(ExecutionFeatures(route=route))
    response = deterministic_response(decision)

    assert route.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert route.deterministic_signal_count == 0
    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert decision.reason == "ambiguous_no_domain_signal"
    assert "fachliche Frage zur Dichtungstechnik" in response
    assert "Werkstoff" not in response
    assert "Herstellerdatenblatt" not in response


def test_ambiguous_high_risk_input_still_fails_closed():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.UNSUPPORTED_OR_AMBIGUOUS, forced=True),
            risk_flags=("Sauerstoff",),
        )
    )

    assert decision.execution_class is ExecutionClass.H1
    assert decision.model_tier is ModelTier.NONE
    assert decision.needs_human_review is True
    assert decision.reason == "ambiguous_high_risk_input"


def test_simple_knowledge_uses_standard_once_without_llm_verifier():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.MATERIAL_KNOWLEDGE),
            authoritative_evidence_count=1,
        )
    )
    assert decision.execution_class is ExecutionClass.S0
    assert decision.model_tier is ModelTier.STANDARD
    assert decision.verification_mode is VerificationMode.DETERMINISTIC


def test_case_intake_invite_is_deterministic_without_llm_verifier():
    # Intake is governed conversation planning, not technical generation.  The response is stable
    # across providers and cannot accidentally contain retrieved claims.
    decision = decide_execution(
        ExecutionFeatures(route=_route(RouteName.CASE_INTAKE_INVITE))
    )
    assert decision.execution_class is ExecutionClass.S0
    assert decision.model_tier is ModelTier.NONE
    assert decision.verification_mode is VerificationMode.DETERMINISTIC
    assert decision.streaming_mode is StreamingMode.ATOMIC


def test_ungrounded_knowledge_is_a_deterministic_evidence_gap():
    decision = decide_execution(
        ExecutionFeatures(route=_route(RouteName.MATERIAL_KNOWLEDGE))
    )

    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert decision.reason == "knowledge_evidence_gap"
    response = deterministic_response(decision)
    assert "kein unabhängig geprüfter Beleg" in response
    assert "bestätige oder verwerfe" in response


def test_well_sourced_knowledge_does_not_escalate_only_because_of_citation_count():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.MATERIAL_KNOWLEDGE),
            authoritative_evidence_count=12,
            document_count=8,
        )
    )
    assert decision.execution_class is ExecutionClass.S0
    assert decision.model_tier is ModelTier.STANDARD


def test_untrusted_knowledge_context_still_uses_frontier():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.MATERIAL_KNOWLEDGE),
            authoritative_evidence_count=8,
            document_count=8,
            untrusted_content_count=1,
        )
    )
    assert decision.execution_class is ExecutionClass.C1
    assert decision.model_tier is ModelTier.FRONTIER


def test_standard_technical_case_uses_small_model_plus_selective_verifier():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True, signals=1),
            authoritative_evidence_count=2,
        )
    )
    assert decision.execution_class is ExecutionClass.S1
    assert decision.reasoning_effort == "high"
    assert decision.verification_mode is VerificationMode.CLAIM_LLM


def test_reviewed_policy_fact_routes_decision_case_directly_to_frontier():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True, signals=1),
            authoritative_evidence_count=1,
            reviewed_policy_fact_count=1,
        )
    )
    assert decision.execution_class is ExecutionClass.C2
    assert decision.model_tier is ModelTier.FRONTIER
    assert decision.needs_human_review is True


def test_complex_context_routes_frontier_directly_without_cheap_first_attempt():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True),
            authoritative_evidence_count=3,
            document_count=4,
        )
    )
    assert decision.execution_class is ExecutionClass.C1
    assert decision.model_tier is ModelTier.FRONTIER
    assert decision.verification_mode is VerificationMode.DETERMINISTIC
