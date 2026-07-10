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


def test_simple_knowledge_uses_standard_once_without_llm_verifier():
    decision = decide_execution(
        ExecutionFeatures(route=_route(RouteName.MATERIAL_KNOWLEDGE))
    )
    assert decision.execution_class is ExecutionClass.S0
    assert decision.model_tier is ModelTier.STANDARD
    assert decision.verification_mode is VerificationMode.DETERMINISTIC


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
